#!/usr/bin/env python3
"""Create and verify OAG native-subagent dispatch records."""

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
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
CODEX_ROOT = SCRIPTS_DIR.parent
PROJECT_ROOT = Path(os.environ.get("OAG_PROJECT_ROOT") or CODEX_ROOT.parent).expanduser().resolve()
SCHEMAS_DIR = CODEX_ROOT / "schemas"

sys.path.insert(0, str(SCRIPTS_DIR))
from oag_validate_json import validate_document  # pylint: disable=wrong-import-position
import oag_paths  # noqa: E402


AGENT_RE = re.compile(r"^oag-[a-z0-9_-]+$")
STAGE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_RE = re.compile(r"[^A-Za-z0-9]+")
RECEIPT_SAFE_STATUSES = {
    "HANDOFF_PASS",
    "STATIC_HANDOFF_PASS",
    "RTL_HANDOFF_PASS",
    "FAIL",
    "BLOCKED",
    "INCONCLUSIVE",
}
LEGACY_RECEIPT_STATUSES = {"PASS"}
FORBIDDEN_STATUS_WORDS = ("COMPLETE", "DONE", "SIGNOFF", "RELEASED", "CLOSED")
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


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def compact_timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def issue(code: str, message: str, path: str | None = None) -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def project_rel(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {path}") from exc


def resolve_project_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"path must stay under project root: {raw}") from exc
    return resolved


def normalize_rel(raw: str) -> str:
    return project_rel(resolve_project_path(raw))


def ensure_under_ip(raw: str, ip_dir: Path, *, field: str) -> str:
    path = resolve_project_path(raw)
    try:
        path.relative_to(ip_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"{field} must stay under ip_dir: {raw}") from exc
    return project_rel(path)


def git_status_paths(ip_rel: str) -> tuple[str, list[str]]:
    proc = subprocess.run(
        ["git", "status", "--short", "-uall", "--", ip_rel],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    raw = proc.stdout
    paths: list[str] = []
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if path:
            paths.append(path)
    return raw, sorted(set(paths))


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


def scope_lock_status(ip_dir: Path) -> dict[str, Any]:
    path = oag_paths.legacy_or_hidden(ip_dir, "ontology/scope_lock.json")
    if not path.is_file():
        return {"state": "draft", "locked": False, "missing": True}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
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
    nonce = uuid.uuid4().hex[:8].upper()
    return f"DISPATCH_{stem}_{compact_timestamp()}_{nonce}"


def build_prompt_contract(dispatch: dict[str, Any]) -> str:
    lines = [
        "OAG DISPATCH",
        f"- dispatch_id: {dispatch['dispatch_id']}",
        f"- dispatch_path: {dispatch['dispatch_path']}",
        f"- agent_type: {dispatch['agent_type']}",
        f"- ip_dir: {dispatch['ip_dir']}",
        f"- stage: {dispatch['stage']}",
        f"- receipt_path: {dispatch['receipt_path']}",
        f"- allowed_write_paths: {', '.join(dispatch['allowed_write_paths']) or '(none)'}",
        f"- allowed_tool_side_effects: {', '.join(dispatch['allowed_tool_side_effects']) or '(none)'}",
    ]
    if dispatch.get("wavefront_run_id"):
        lines.extend(
            [
                f"- wavefront_run_id: {dispatch['wavefront_run_id']}",
                f"- task_id: {dispatch.get('task_id') or '(none)'}",
                f"- ownership_mode: {dispatch.get('ownership_mode') or '(none)'}",
            ]
        )
    lines.extend(
        [
            "Receipt requirements:",
            "- include dispatch_id and dispatch_path exactly as above",
            "- include wavefront_run_id/task_id when this dispatch belongs to a wavefront task",
            "- list changed_paths and generated_side_effects separately",
            "- use HANDOFF_PASS, STATIC_HANDOFF_PASS, RTL_HANDOFF_PASS, FAIL, BLOCKED, or INCONCLUSIVE",
            "- set may_claim_complete=false",
            "- end with OAG_EVIDENCE_RECORDED: <relative-path>",
        ]
    )
    return "\n".join(lines)


def create_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    ip_dir.mkdir(parents=True, exist_ok=True)
    ip_rel = project_rel(ip_dir)
    if not AGENT_RE.match(args.agent_type):
        raise ValueError(f"invalid agent type: {args.agent_type}")
    role_name = args.role_name or args.agent_type
    if not AGENT_RE.match(role_name):
        raise ValueError(f"invalid role name: {role_name}")
    role_kind = args.role_kind or ("custom" if role_name.startswith("oag-custom-") else "core")
    if role_kind not in {"core", "custom"}:
        raise ValueError(f"invalid role kind: {role_kind}")
    if not STAGE_RE.match(args.stage):
        raise ValueError(f"invalid stage: {args.stage}")

    allowed_write_paths = [
        ensure_under_ip(item, ip_dir, field="allowed_write_path")
        for item in (args.allowed_write_path or [])
    ]
    allowed_tool_side_effects = [
        ensure_under_ip(item, ip_dir, field="allowed_tool_side_effect")
        for item in (args.allowed_tool_side_effect or [])
    ]
    receipt_path = ensure_under_ip(args.receipt_path, ip_dir, field="receipt_path")
    if not path_matches(receipt_path, allowed_write_paths):
        allowed_write_paths.append(str(Path(receipt_path).parent).replace("\\", "/") + "/")
    if dispatch_requires_lock(args.agent_type, args.stage, allowed_write_paths):
        lock = scope_lock_status(ip_dir)
        if lock.get("locked") is not True:
            raise ValueError(
                "scope lock required before implementation, validation, or gate dispatch; "
                "ask the user to confirm scope and run oag.lock"
            )

    status_raw, status_paths = git_status_paths(ip_rel)
    dispatch_path = oag_paths.state_path(ip_dir, "knowledge/dispatches/unused.json")
    oag_paths.state_path(ip_dir, "knowledge/dispatches").mkdir(parents=True, exist_ok=True)
    dispatch: dict[str, Any] | None = None
    for sequence in range(0, 100):
        dispatch_id = safe_dispatch_id(ip_dir.name, args.agent_type, sequence=sequence)
        candidate_path = oag_paths.state_path(ip_dir, f"knowledge/dispatches/{dispatch_id}.json")
        dispatch_rel = project_rel(candidate_path)
        candidate = {
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
            "baseline": {
                "created_at": utc_now(),
                "git_status_raw": status_raw,
                "git_status_paths": status_paths,
                "file_hashes": hash_known_paths([ip_rel]),
            },
            "created_at": utc_now(),
        }
        candidate["prompt_contract"] = build_prompt_contract(candidate)
        try:
            with candidate_path.open("x", encoding="utf-8") as fh:
                fh.write(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
        except FileExistsError:
            continue
        dispatch_path = candidate_path
        dispatch = candidate
        break
    if dispatch is None:
        raise ValueError("could not allocate a unique dispatch id")
    dispatch["path"] = dispatch_rel
    return {
        "schema_version": "oag_dispatch_create_result.v1",
        "status": "pass",
        "dispatch": dispatch,
    }


def schema_issues(schema_name: str, document: Any) -> list[dict[str, str]]:
    schema = load_json(SCHEMAS_DIR / schema_name)
    return validate_document(schema, document)


def string_list(payload: dict[str, Any], *fields: str) -> list[str]:
    values: list[str] = []
    for field in fields:
        raw = payload.get(field)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if isinstance(item, str))
    return sorted(set(values))


def filesystem_delta(dispatch: dict[str, Any]) -> list[str]:
    ip_rel = str(dispatch.get("ip_dir") or "")
    baseline = dispatch.get("baseline") if isinstance(dispatch.get("baseline"), dict) else {}
    previous_hashes = baseline.get("file_hashes") if isinstance(baseline.get("file_hashes"), dict) else {}
    current_hashes = hash_known_paths([ip_rel])
    changed = {
        path
        for path, digest in current_hashes.items()
        if str(previous_hashes.get(path) or "") != digest
    }
    changed.update(str(path) for path in previous_hashes if path not in current_hashes)
    return sorted(changed)


def actual_delta(dispatch: dict[str, Any]) -> tuple[list[str], list[str]]:
    ip_rel = str(dispatch.get("ip_dir") or "")
    _, current = git_status_paths(ip_rel)
    baseline = dispatch.get("baseline") if isinstance(dispatch.get("baseline"), dict) else {}
    previous = baseline.get("git_status_paths") if isinstance(baseline.get("git_status_paths"), list) else []
    previous_set = {str(item) for item in previous}
    delta = sorted({path for path in current if path not in previous_set} | set(filesystem_delta(dispatch)))
    return current, delta


def verify_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    dispatch_path = resolve_project_path(args.dispatch)
    receipt_path = resolve_project_path(args.receipt)
    try:
        dispatch = load_json(dispatch_path)
    except Exception as exc:
        dispatch = {}
        issues.append(issue("DISPATCH_LOAD", f"cannot load dispatch: {exc}", project_rel(dispatch_path)))
    try:
        receipt = load_json(receipt_path)
    except Exception as exc:
        receipt = {}
        issues.append(issue("RECEIPT_LOAD", f"cannot load receipt: {exc}", project_rel(receipt_path)))

    if dispatch:
        for item in schema_issues("oag_dispatch.schema.json", dispatch):
            issues.append(issue(f"DISPATCH_SCHEMA_{item['code']}", item["message"], item["path"]))
    if receipt:
        for item in schema_issues("oag_subagent_receipt.schema.json", receipt):
            issues.append(issue(f"RECEIPT_SCHEMA_{item['code']}", item["message"], item["path"]))

    if dispatch and receipt:
        dispatch_id = str(dispatch.get("dispatch_id") or "")
        receipt_dispatch_id = str(receipt.get("dispatch_id") or "")
        if receipt_dispatch_id != dispatch_id:
            issues.append(issue("DISPATCH_ID_MISMATCH", "receipt.dispatch_id does not match dispatch.dispatch_id"))
        receipt_dispatch_path = str(receipt.get("dispatch_path") or "")
        if receipt_dispatch_path and normalize_rel(receipt_dispatch_path) != project_rel(dispatch_path):
            issues.append(issue("DISPATCH_PATH_MISMATCH", "receipt.dispatch_path does not match the dispatch file"))
        if normalize_rel(str(dispatch.get("receipt_path") or "")) != project_rel(receipt_path):
            issues.append(issue("RECEIPT_PATH_MISMATCH", "dispatch.receipt_path does not match the receipt file"))
        if receipt.get("may_claim_complete") is not False or dispatch.get("may_claim_complete") is not False:
            issues.append(issue("COMPLETION_CLAIM", "dispatch and receipt must keep may_claim_complete=false"))
        for field in ("wavefront_run_id", "task_id", "ownership_mode"):
            dispatch_value = str(dispatch.get(field) or "")
            receipt_value = str(receipt.get(field) or "")
            if dispatch_value and receipt_value and receipt_value != dispatch_value:
                issues.append(issue("WAVEFRONT_FIELD_MISMATCH", f"receipt.{field} does not match dispatch.{field}"))

        status = str(receipt.get("status") or "")
        if status in LEGACY_RECEIPT_STATUSES:
            issues.append(issue("LEGACY_STATUS", "receipt status PASS is no longer accepted for dispatch-verified subagents"))
        elif status not in RECEIPT_SAFE_STATUSES:
            issues.append(issue("STATUS", f"receipt status is not an OAG handoff status: {status}"))
        status_upper = status.upper()
        if any(word in status_upper for word in FORBIDDEN_STATUS_WORDS):
            issues.append(issue("STATUS_COMPLETION_LANGUAGE", "receipt status must not imply completion or signoff"))

        allowed_write_paths = [str(item) for item in dispatch.get("allowed_write_paths") or []]
        allowed_tool_side_effects = [str(item) for item in dispatch.get("allowed_tool_side_effects") or []]
        owned = string_list(receipt, "changed_paths", "owned_changed_paths")
        generated = string_list(receipt, "generated_side_effects")
        for path in owned:
            if not path_matches(normalize_rel(path), allowed_write_paths):
                issues.append(issue("OWNED_PATH_OUT_OF_SCOPE", "receipt changed path is outside allowed_write_paths", path))
        for path in generated:
            if not path_matches(normalize_rel(path), allowed_tool_side_effects):
                issues.append(issue("GENERATED_PATH_OUT_OF_SCOPE", "receipt generated side effect is outside allowed_tool_side_effects", path))

        current_paths, delta_paths = actual_delta(dispatch)
        expected_paths = [
            *allowed_write_paths,
            *allowed_tool_side_effects,
            str(dispatch.get("receipt_path") or ""),
            str(dispatch.get("dispatch_path") or ""),
        ]
        out_of_scope_actual = [
            path for path in delta_paths
            if not path_matches(path, expected_paths)
        ]
        for path in out_of_scope_actual:
            issues.append(issue("ACTUAL_PATH_OUT_OF_SCOPE", "actual git status delta is outside dispatch scope", path))
    else:
        current_paths, delta_paths = [], []
        owned, generated = [], []
        out_of_scope_actual = []

    return {
        "schema_version": "oag_dispatch_verify_result.v1",
        "status": "fail" if issues else "pass",
        "dispatch_path": str(dispatch_path),
        "receipt_path": str(receipt_path),
        "dispatch_id": dispatch.get("dispatch_id") if isinstance(dispatch, dict) else "",
        "receipt_status": receipt.get("status") if isinstance(receipt, dict) else "",
        "owned_changed_paths": owned,
        "generated_side_effects": generated,
        "actual_status_paths": current_paths,
        "actual_delta_paths": delta_paths,
        "out_of_scope_paths": out_of_scope_actual,
        "issues": issues,
    }


def print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print(f"PASS {result['schema_version']}")
    else:
        print(f"FAIL {result['schema_version']}", file=sys.stderr)
        for item in result.get("issues", []):
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify OAG native-subagent dispatch records.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a dispatch record before native subagent spawn.")
    create.add_argument("--ip-dir", required=True)
    create.add_argument("--agent-type", required=True)
    create.add_argument("--role-kind", choices=["core", "custom"])
    create.add_argument("--role-name")
    create.add_argument("--registered-id")
    create.add_argument("--stage", required=True)
    create.add_argument("--owned-obligation", action="append")
    create.add_argument("--contract", action="append")
    create.add_argument("--allowed-write-path", action="append")
    create.add_argument("--allowed-tool-side-effect", action="append")
    create.add_argument("--receipt-path", required=True)
    create.add_argument("--wavefront-run-id")
    create.add_argument("--task-id")
    create.add_argument("--ownership-mode", choices=["none", "exclusive_file", "integration_owner"])
    create.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify", help="Verify a dispatch against a child receipt and actual path delta.")
    verify.add_argument("--dispatch", required=True)
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_dispatch(args)
        else:
            result = verify_dispatch(args)
    except Exception as exc:
        result = {
            "schema_version": "oag_dispatch_error.v1",
            "status": "fail",
            "issues": [issue("EXCEPTION", str(exc))],
        }
    print_result(result, bool(getattr(args, "json", False)))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
