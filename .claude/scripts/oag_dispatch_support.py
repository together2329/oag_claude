from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from oag_dispatch_prompt import build_prompt_contract

SCRIPTS_DIR = Path(__file__).resolve().parent
CODEX_ROOT = SCRIPTS_DIR.parent
PROJECT_ROOT = Path(os.environ.get("OAG_PROJECT_ROOT") or CODEX_ROOT.parent).expanduser().resolve()
SCHEMAS_DIR = CODEX_ROOT / "schemas"

sys.path.insert(0, str(SCRIPTS_DIR))
import oag_paths  # noqa: E402
from oag_validate_json import validate_document  # noqa: E402

if TYPE_CHECKING:
    JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
    JsonObject = dict[str, JsonValue]
    Issue = dict[str, str]
else:
    JsonValue = str
    JsonObject = dict
    Issue = dict


AGENT_RE = re.compile(r"^oag-[a-z0-9_-]+$")
STAGE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_RE = re.compile(r"[^A-Za-z0-9]+")
LOCK_REQUIRED_AGENT_FRAGMENTS = (
    "rtl-implementation",
    "tb-implementation",
    "rtl-lint-static",
    "sim-execution",
    "coverage",
    "mutation-guard",
    "evidence-validator",
    "gate-reviewer",
    "custom-worker",
)
LOCK_REQUIRED_STAGES = {"rtl", "lint", "tb", "sim", "coverage", "cov", "formal", "signoff", "gate", "closure"}


class DispatchInputError(ValueError):
    pass


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def compact_timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def issue(code: str, message: str, path: str | None = None) -> Issue:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def load_json(path: Path) -> JsonValue:
    return json.loads(path.read_text(encoding="utf-8"))


def project_rel(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise DispatchInputError(f"path escapes project root: {path}") from exc


def resolve_project_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise DispatchInputError(f"path must stay under project root: {raw}") from exc
    return resolved


def normalize_rel(raw: str) -> str:
    return project_rel(resolve_project_path(raw))


def ensure_under_ip(raw: str, ip_dir: Path, *, field: str) -> str:
    path = resolve_project_path(raw)
    try:
        path.relative_to(ip_dir.resolve())
    except ValueError as exc:
        raise DispatchInputError(f"{field} must stay under ip_dir: {raw}") from exc
    return project_rel(path)


def git_status_paths(ip_rel: str) -> tuple[str, list[str]]:
    proc = subprocess.run(
        ["git", "status", "--short", "-uall", "--", ip_rel],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if path:
            paths.append(path)
    return proc.stdout, sorted(set(paths))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.rglob("*") if item.is_file() and ".git" not in item.parts)
    return []


def hash_known_paths(paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for raw in paths:
        if any(char in raw for char in "*?["):
            continue
        for file_path in files_under(resolve_project_path(raw)):
            hashes[project_rel(file_path)] = sha256(file_path)
    return hashes


def scope_lock_status(ip_dir: Path) -> JsonObject:
    path = oag_paths.legacy_or_hidden(ip_dir, "ontology/scope_lock.json")
    if not path.is_file():
        return {"state": "draft", "locked": False, "missing": True}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "draft", "locked": False, "invalid": True}
    if not isinstance(data, dict):
        return {"state": "draft", "locked": False, "invalid": True}
    state = str(data.get("state") or data.get("status") or "draft").strip().lower()
    return {"state": state, "locked": state == "locked", "path": project_rel(path), "lock": data}


def dispatch_requires_lock(agent_type: str, stage: str, allowed_write_paths: list[str]) -> bool:
    agent = agent_type.lower()
    stage_name = stage.lower()
    if any(fragment in agent for fragment in LOCK_REQUIRED_AGENT_FRAGMENTS):
        return True
    if stage_name in LOCK_REQUIRED_STAGES:
        return True
    protected_prefixes = (
        "/req/locked_truth.md",
        "/ontology/requirements.yaml",
        "/ontology/obligations.yaml",
        "/ontology/contracts.yaml",
        "/ontology/structure.yaml",
        "/ontology/decomposition.yaml",
        "/rtl/",
        "/tb/",
        "/sim/",
        "/lint/",
        "/cov/",
        "/formal/",
        "/signoff/",
    )
    return any(any(prefix in f"/{path}" for prefix in protected_prefixes) for path in allowed_write_paths)


def path_matches(path: str, patterns: list[str]) -> bool:
    path = path.strip("/")
    for pattern in patterns:
        normalized = pattern.strip("/")
        if not normalized:
            continue
        if any(char in normalized for char in "*?["):
            if fnmatch.fnmatch(path, normalized) or fnmatch.fnmatch(path, normalized.rstrip("/") + "/*"):
                return True
            continue
        if path == normalized or path.startswith(normalized + "/"):
            return True
    return False


def safe_dispatch_id(ip_id: str, agent_type: str, *, sequence: int = 0) -> str:
    agent_tail = agent_type.removeprefix("oag-").replace("-agent", "")
    stem = SAFE_RE.sub("_", f"{ip_id}_{agent_tail}").strip("_").upper()
    if sequence:
        stem = f"{stem}_{sequence:02d}"
    return f"DISPATCH_{stem}_{compact_timestamp()}_{uuid.uuid4().hex[:8].upper()}"


def schema_issues(schema_name: str, document: JsonValue) -> list[Issue]:
    return validate_document(load_json(SCHEMAS_DIR / schema_name), document)


def create_dispatch(args: argparse.Namespace) -> JsonObject:
    ip_dir = resolve_project_path(args.ip_dir)
    ip_dir.mkdir(parents=True, exist_ok=True)
    ip_rel = project_rel(ip_dir)
    if not AGENT_RE.match(args.agent_type):
        raise DispatchInputError(f"invalid agent type: {args.agent_type}")
    role_name = args.role_name or args.agent_type
    if not AGENT_RE.match(role_name):
        raise DispatchInputError(f"invalid role name: {role_name}")
    role_kind = args.role_kind or ("custom" if role_name.startswith("oag-custom-") else "core")
    if role_kind not in {"core", "custom"}:
        raise DispatchInputError(f"invalid role kind: {role_kind}")
    if not STAGE_RE.match(args.stage):
        raise DispatchInputError(f"invalid stage: {args.stage}")

    allowed_write_paths = [ensure_under_ip(item, ip_dir, field="allowed_write_path") for item in (args.allowed_write_path or [])]
    allowed_tool_side_effects = [
        ensure_under_ip(item, ip_dir, field="allowed_tool_side_effect")
        for item in (args.allowed_tool_side_effect or [])
    ]
    receipt_path = ensure_under_ip(args.receipt_path, ip_dir, field="receipt_path")
    if not path_matches(receipt_path, allowed_write_paths):
        allowed_write_paths.append(str(Path(receipt_path).parent).replace("\\", "/") + "/")
    if dispatch_requires_lock(args.agent_type, args.stage, allowed_write_paths) and scope_lock_status(ip_dir).get("locked") is not True:
        raise DispatchInputError("scope lock required before implementation, validation, or gate dispatch; ask the user to confirm scope and run oag.lock")

    status_raw, status_paths = git_status_paths(ip_rel)
    oag_paths.state_path(ip_dir, "knowledge/dispatches").mkdir(parents=True, exist_ok=True)
    for sequence in range(0, 100):
        dispatch_id = safe_dispatch_id(ip_dir.name, args.agent_type, sequence=sequence)
        candidate_path = oag_paths.state_path(ip_dir, f"knowledge/dispatches/{dispatch_id}.json")
        dispatch_rel = project_rel(candidate_path)
        candidate: JsonObject = {
            "schema_version": "oag_dispatch.v1",
            "product_name": "IP Dev Agent",
            "internal_gateway": "Ontology Agent Gateway",
            "dispatch_id": dispatch_id,
            "dispatch_path": dispatch_rel,
            "agent_type": args.agent_type,
            "role_name": role_name,
            "role_kind": role_kind,
            "registered_id": args.registered_id or role_name,
            "ip_id": ip_dir.name,
            "ip_dir": ip_rel,
            "stage": args.stage,
            "owned_obligations": args.owned_obligation or [],
            "contracts": args.contract or [],
            "allowed_write_paths": sorted(set(allowed_write_paths)),
            "allowed_tool_side_effects": sorted(set(allowed_tool_side_effects)),
            "receipt_path": receipt_path,
            "may_claim_complete": False,
            "wavefront_run_id": args.wavefront_run_id or "",
            "task_id": args.task_id or "",
            "ownership_mode": args.ownership_mode or "",
            "baseline": {"created_at": utc_now(), "git_status_raw": status_raw, "git_status_paths": status_paths, "file_hashes": hash_known_paths([ip_rel])},
            "created_at": utc_now(),
        }
        candidate["prompt_contract"] = build_prompt_contract(candidate)
        try:
            with candidate_path.open("x", encoding="utf-8") as fh:
                fh.write(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
        except FileExistsError:
            continue
        candidate["path"] = dispatch_rel
        return {"schema_version": "oag_dispatch_create_result.v1", "status": "pass", "dispatch": candidate}
    raise DispatchInputError("could not allocate a unique dispatch id")
