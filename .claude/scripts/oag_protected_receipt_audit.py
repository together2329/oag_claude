#!/usr/bin/env python3
"""Audit post-lock protected IP artifacts against subagent receipts.

This check is intentionally independent of git tracking. Product IP directories
may be ignored/untracked while `.claude` remains the durable pack repository.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parent
CODEX_ROOT = SCRIPTS_DIR.parent
PROJECT_ROOT = Path(os.environ.get("OAG_PROJECT_ROOT") or CODEX_ROOT.parent).expanduser().resolve()
SCHEMAS_DIR = CODEX_ROOT / "schemas"

sys.path.insert(0, str(SCRIPTS_DIR))
import oag_paths  # noqa: E402
from oag_validate_json import validate_document  # pylint: disable=wrong-import-position


PASSING_RECEIPT_STATUSES = {"HANDOFF_PASS", "STATIC_HANDOFF_PASS", "RTL_HANDOFF_PASS"}
SAFE_RECEIPT_STATUSES = PASSING_RECEIPT_STATUSES | {"FAIL", "BLOCKED", "INCONCLUSIVE"}
PROTECTED_REL_DIRS = (
    Path("rtl"),
    Path("tb"),
    Path("sim"),
    Path("lint"),
    Path("evidence"),
    Path("gate"),
    Path("scoreboard"),
    Path("reports"),
    Path("ontology/evidence/stage_runs"),
)
SKIP_FILENAMES = {".gitkeep", ".DS_Store"}


def issue(code: str, message: str, path: str | None = None, *, severity: str = "error") -> dict[str, str]:
    payload = {"code": code, "message": message, "severity": severity}
    if path:
        payload["path"] = path
    return payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_issues(schema_name: str, document: Any) -> list[dict[str, str]]:
    schema = load_json(SCHEMAS_DIR / schema_name)
    return validate_document(schema, document)


def project_rel(path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        rel = resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {path}") from exc
    # Preserve LOGICAL path identity: the .oag resolver may return targets under
    # <ip>/.oag/..., but recorded keys (receipt _path, coverage/hash keys, error
    # paths) must stay in their legacy logical form so cross-layout matching with
    # receipt/dispatch-recorded relative paths keeps working. On legacy layout no
    # .oag segment is present, so this is a no-op (byte-identical behavior).
    parts = tuple(part for part in rel.parts if part != oag_paths.HIDDEN_DIR)
    return Path(*parts).as_posix() if parts else ""


def resolve_ip_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"ip-dir must stay under project root: {raw}") from exc
    if not resolved.is_dir():
        raise ValueError(f"ip-dir does not exist: {raw}")
    return resolved


def normalize_path(raw: str, ip_dir: Path) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    path = Path(value).expanduser()
    if path.is_absolute():
        return project_rel(path)
    project_candidate = (PROJECT_ROOT / path).resolve(strict=False)
    try:
        project_candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {raw}") from exc
    ip_rel = project_rel(ip_dir)
    if value == ip_rel or value.startswith(ip_rel + "/"):
        return project_rel(project_candidate)
    return project_rel(ip_dir / path)


def path_matches(path: str, patterns: list[str]) -> bool:
    normalized_path = path.strip("/")
    for raw in patterns:
        pattern = str(raw or "").strip().strip("/")
        if not pattern:
            continue
        if any(char in pattern for char in "*?["):
            if fnmatch.fnmatch(normalized_path, pattern) or fnmatch.fnmatch(normalized_path, pattern.rstrip("/") + "/*"):
                return True
            continue
        if normalized_path == pattern or normalized_path.startswith(pattern + "/"):
            return True
    return False


def string_list(payload: dict[str, Any], *fields: str) -> list[str]:
    values: list[str] = []
    for field in fields:
        raw = payload.get(field)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if isinstance(item, str))
    return sorted(set(values))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_protected_files(ip_dir: Path) -> list[Path]:
    files: list[Path] = []
    for rel in PROTECTED_REL_DIRS:
        # Only the ontology subtree migrates to .oag; all other protected dirs
        # (rtl/tb/sim/lint/evidence/gate/scoreboard/reports) stay top-level.
        if rel.parts and rel.parts[0] == "ontology":
            root = oag_paths.legacy_or_hidden(ip_dir, rel.as_posix())
        else:
            root = ip_dir / rel
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(path for path in root.rglob("*") if path.is_file())
        for path in candidates:
            if path.name in SKIP_FILENAMES:
                continue
            files.append(path)
    return sorted(set(files))


def hash_claims_from_payload(payload: dict[str, Any], ip_dir: Path) -> dict[str, str]:
    claims: dict[str, str] = {}

    def add(path: Any, digest: Any) -> None:
        if not isinstance(path, str) or not isinstance(digest, str):
            return
        digest = digest.strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            return
        claims[normalize_path(path, ip_dir)] = digest

    raw_hashes = payload.get("artifact_hashes")
    if isinstance(raw_hashes, dict):
        for path, digest in raw_hashes.items():
            add(path, digest)
    elif isinstance(raw_hashes, list):
        for item in raw_hashes:
            if isinstance(item, dict):
                add(item.get("path"), item.get("sha256"))

    for field in ("input_fingerprints", "output_fingerprints", "fingerprints", "checked_artifact_hashes"):
        raw = payload.get(field)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                add(item.get("path"), item.get("sha256"))
    return claims


def stage_receipt_hash_claims(ip_dir: Path, issues: list[dict[str, str]]) -> dict[str, str]:
    claims: dict[str, str] = {}
    root = oag_paths.legacy_or_hidden(ip_dir, "ontology/evidence/stage_runs")
    if not root.is_dir():
        return claims
    for path in sorted(root.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception as exc:
            issues.append(issue("STAGE_RECEIPT_JSON", f"cannot load stage receipt: {exc}", project_rel(path)))
            continue
        if isinstance(payload, dict):
            claims.update(hash_claims_from_payload(payload, ip_dir))
    return claims


def load_receipts(ip_dir: Path, issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    receipt_dir = oag_paths.legacy_or_hidden(ip_dir, "knowledge/subagents")
    receipts: list[dict[str, Any]] = []
    if not receipt_dir.is_dir():
        issues.append(issue("RECEIPT_DIR_MISSING", "missing knowledge/subagents directory", project_rel(receipt_dir)))
        return receipts
    for receipt_path in sorted(receipt_dir.glob("*.json")):
        try:
            receipt = load_json(receipt_path)
        except Exception as exc:
            issues.append(issue("RECEIPT_JSON", f"cannot load receipt: {exc}", project_rel(receipt_path)))
            continue
        if not isinstance(receipt, dict):
            issues.append(issue("RECEIPT_JSON", "receipt JSON must be an object", project_rel(receipt_path)))
            continue
        for item in schema_issues("oag_subagent_receipt.schema.json", receipt):
            issues.append(issue(f"RECEIPT_SCHEMA_{item['code']}", item["message"], item["path"]))
        receipt["_path"] = project_rel(receipt_path)
        receipts.append(receipt)
    return receipts


def load_dispatch_for_receipt(receipt: dict[str, Any], ip_dir: Path, issues: list[dict[str, str]]) -> dict[str, Any] | None:
    dispatch_raw = str(receipt.get("dispatch_path") or "")
    if not dispatch_raw:
        issues.append(issue("DISPATCH_PATH_MISSING", "receipt is missing dispatch_path", str(receipt.get("_path") or "")))
        return None
    try:
        dispatch_path = PROJECT_ROOT / normalize_path(dispatch_raw, ip_dir)
        dispatch = load_json(dispatch_path)
    except Exception as exc:
        issues.append(issue("DISPATCH_LOAD", f"cannot load dispatch for receipt: {exc}", str(receipt.get("_path") or "")))
        return None
    if not isinstance(dispatch, dict):
        issues.append(issue("DISPATCH_JSON", "dispatch JSON must be an object", project_rel(dispatch_path)))
        return None
    for item in schema_issues("oag_dispatch.schema.json", dispatch):
        issues.append(issue(f"DISPATCH_SCHEMA_{item['code']}", item["message"], item["path"]))
    dispatch["_path"] = project_rel(dispatch_path)
    if str(dispatch.get("dispatch_id") or "") != str(receipt.get("dispatch_id") or ""):
        issues.append(issue("DISPATCH_ID_MISMATCH", "receipt.dispatch_id does not match dispatch.dispatch_id", str(receipt.get("_path") or "")))
    expected_receipt = normalize_path(str(dispatch.get("receipt_path") or ""), ip_dir)
    if expected_receipt != str(receipt.get("_path") or ""):
        issues.append(issue("RECEIPT_PATH_MISMATCH", "dispatch.receipt_path does not match receipt path", str(receipt.get("_path") or "")))
    return dispatch


def audit_dispatch_inventory(ip_dir: Path, receipt_paths: set[str], require_all: bool, issues: list[dict[str, str]], warnings: list[dict[str, str]]) -> None:
    root = oag_paths.legacy_or_hidden(ip_dir, "knowledge/dispatches")
    if not root.is_dir():
        warnings.append(issue("DISPATCH_DIR_MISSING", "missing knowledge/dispatches directory", project_rel(root), severity="warning"))
        return
    for path in sorted(root.glob("*.json")):
        try:
            dispatch = load_json(path)
        except Exception as exc:
            issues.append(issue("DISPATCH_JSON", f"cannot load dispatch: {exc}", project_rel(path)))
            continue
        if not isinstance(dispatch, dict):
            issues.append(issue("DISPATCH_JSON", "dispatch JSON must be an object", project_rel(path)))
            continue
        receipt_path = normalize_path(str(dispatch.get("receipt_path") or ""), ip_dir)
        if receipt_path and receipt_path not in receipt_paths:
            item = issue("DISPATCH_RECEIPT_MISSING", "dispatch receipt is not present", project_rel(path), severity="error" if require_all else "warning")
            (issues if require_all else warnings).append(item)


def audit(ip_dir_arg: str, *, strict_hashes: bool, require_all_dispatch_receipts: bool) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    ip_dir = resolve_ip_dir(ip_dir_arg)
    # iter_protected_files returns resolved filesystem paths (which may live under
    # <ip>/.oag/...); key everything by the LOGICAL project_rel form but read the
    # actual resolved path for hashing so .oag-layout files are found.
    protected_resolved = iter_protected_files(ip_dir)
    protected_files = [project_rel(path) for path in protected_resolved]
    protected_hashes = {project_rel(path): sha256(path) for path in protected_resolved}
    receipts = load_receipts(ip_dir, issues)
    receipt_paths = {str(receipt.get("_path") or "") for receipt in receipts}
    audit_dispatch_inventory(ip_dir, receipt_paths, require_all_dispatch_receipts, issues, warnings)

    coverage: dict[str, list[str]] = {path: [] for path in protected_files}
    hash_claims: dict[str, str] = stage_receipt_hash_claims(ip_dir, issues)
    receipt_summaries: list[dict[str, Any]] = []

    for receipt in receipts:
        status = str(receipt.get("status") or "")
        if status not in SAFE_RECEIPT_STATUSES:
            issues.append(issue("RECEIPT_STATUS", f"unsafe receipt status: {status}", str(receipt.get("_path") or "")))
        if receipt.get("may_claim_complete") is not False:
            issues.append(issue("RECEIPT_COMPLETION_CLAIM", "subagent receipt must keep may_claim_complete=false", str(receipt.get("_path") or "")))

        dispatch = load_dispatch_for_receipt(receipt, ip_dir, issues)
        allowed = []
        if dispatch:
            allowed = [normalize_path(path, ip_dir) for path in string_list(dispatch, "allowed_write_paths")]
        changed = [normalize_path(path, ip_dir) for path in string_list(receipt, "changed_paths")]
        generated = [normalize_path(path, ip_dir) for path in string_list(receipt, "generated_side_effects")]
        for path in changed:
            if allowed and not path_matches(path, allowed):
                issues.append(issue("OWNED_PATH_OUT_OF_SCOPE", "receipt changed path is outside dispatch allowed_write_paths", path))
        for path in generated:
            side_effects = [normalize_path(item, ip_dir) for item in string_list(dispatch or {}, "allowed_tool_side_effects")]
            if side_effects and not path_matches(path, side_effects):
                issues.append(issue("GENERATED_PATH_OUT_OF_SCOPE", "receipt generated side effect is outside dispatch allowed_tool_side_effects", path))

        hash_claims.update(hash_claims_from_payload(receipt, ip_dir))
        if status in PASSING_RECEIPT_STATUSES:
            for protected in protected_files:
                if path_matches(protected, changed) and (not allowed or path_matches(protected, allowed)):
                    coverage[protected].append(str(receipt.get("_path") or ""))
        receipt_summaries.append(
            {
                "path": str(receipt.get("_path") or ""),
                "status": status,
                "dispatch_id": str(receipt.get("dispatch_id") or ""),
                "covered_count": sum(1 for protected in protected_files if path_matches(protected, changed)),
            }
        )

    for path, covering_receipts in coverage.items():
        if not covering_receipts:
            issues.append(issue("UNCOVERED_PROTECTED_ARTIFACT", "protected artifact has no passing subagent receipt coverage", path))
            continue
        claimed_hash = hash_claims.get(path)
        if strict_hashes and not claimed_hash:
            issues.append(issue("MISSING_ARTIFACT_HASH", "protected artifact coverage has no receipt or stage sha256 claim", path))
        elif strict_hashes and claimed_hash != protected_hashes[path]:
            issues.append(issue("STALE_ARTIFACT_HASH", "protected artifact hash claim does not match current file", path))

    return {
        "schema_version": "oag_protected_receipt_audit.v1",
        "status": "fail" if issues else "pass",
        "ip_dir": project_rel(ip_dir),
        "strict_hashes": strict_hashes,
        "require_all_dispatch_receipts": require_all_dispatch_receipts,
        "protected_prefixes": [path.as_posix() for path in PROTECTED_REL_DIRS],
        "protected_artifacts": sorted(protected_files),
        "protected_artifact_hashes": protected_hashes,
        "covered_artifacts": sorted(path for path, receipts_for_path in coverage.items() if receipts_for_path),
        "uncovered_artifacts": sorted(path for path, receipts_for_path in coverage.items() if not receipts_for_path),
        "coverage": coverage,
        "receipts": receipt_summaries,
        "warnings": warnings,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit protected IP artifacts against OAG subagent receipts.")
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--strict-hashes", action="store_true")
    parser.add_argument("--require-all-dispatch-receipts", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = audit(
            args.ip_dir,
            strict_hashes=bool(args.strict_hashes),
            require_all_dispatch_receipts=bool(args.require_all_dispatch_receipts),
        )
    except Exception as exc:
        result = {
            "schema_version": "oag_protected_receipt_audit.v1",
            "status": "fail",
            "issues": [issue("EXCEPTION", str(exc))],
            "warnings": [],
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag protected receipt audit")
    else:
        print("FAIL oag protected receipt audit", file=sys.stderr)
        for item in result.get("issues", []):
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
