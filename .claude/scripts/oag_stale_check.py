#!/usr/bin/env python3
"""Detect stale OAG lifecycle artifacts from hashes and derived_from edges."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
CODEX_ROOT = SCRIPTS_DIR.parent
SCHEMAS_DIR = CODEX_ROOT / "schemas"

sys.path.insert(0, str(SCRIPTS_DIR))
import oag_paths  # noqa: E402
from oag_validate_json import validate_document  # pylint: disable=wrong-import-position


LIFECYCLE_PATH = Path("ontology/artifact_lifecycle.json")


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def str_items(value: Any) -> list[str]:
    return [str(item).strip() for item in as_list(value) if str(item).strip()]


def read_json(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [issue("STALE_LIFECYCLE_INVALID_JSON", f"Cannot read lifecycle JSON: {exc}", str(path))]
    if not isinstance(payload, dict):
        return None, [issue("STALE_LIFECYCLE_SHAPE", "Lifecycle document must be a JSON object.", str(path))]
    return payload, []


def load_schema() -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / "oag_artifact_lifecycle.schema.json").read_text(encoding="utf-8"))


def schema_issues(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        issue("STALE_LIFECYCLE_SCHEMA", f"{item.get('code')}: {item.get('message')}", str(item.get("path") or ""))
        for item in validate_document(load_schema(), payload)
    ]


def artifact_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("path") or "").strip()


def aliases(item: dict[str, Any]) -> set[str]:
    values = {artifact_id(item), str(item.get("path") or "").strip()}
    object_id = str(item.get("object_id") or "").strip()
    path = str(item.get("path") or "").strip()
    if object_id:
        values.add(object_id)
        if path:
            values.add(f"{path}:{object_id}")
    return {value for value in values if value}


def content_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def expected_hash(item: dict[str, Any]) -> tuple[str, int | None]:
    hash_info = item.get("hash") if isinstance(item.get("hash"), dict) else {}
    expected = str(hash_info.get("content_sha256") or "").strip()
    size = hash_info.get("size_bytes")
    return expected, size if isinstance(size, int) else None


def changed_by_hash(ip_dir: Path, item: dict[str, Any]) -> tuple[bool, list[dict[str, str]]]:
    expected, expected_size = expected_hash(item)
    if not expected:
        return False, []
    rel = str(item.get("path") or artifact_id(item))
    try:
        path = oag_paths.legacy_or_hidden(ip_dir, rel)
    except ValueError:
        path = ip_dir / rel
    if not path.is_file():
        return True, [issue("STALE_HASH_FILE_MISSING", "Lifecycle hash target file is missing.", rel)]
    actual = content_sha256(path)
    actual_size = path.stat().st_size
    changed = actual != expected or (expected_size is not None and actual_size != expected_size)
    if not changed:
        return False, []
    details = f"expected {expected}"
    if expected_size is not None:
        details += f" size {expected_size}"
    details += f", actual {actual} size {actual_size}"
    if item.get("approval_state") == "approved" and item.get("validity_state") == "current":
        return True, [issue("STALE_HASH_MISMATCH_CURRENT", f"Approved/current artifact hash is stale: {details}", rel)]
    return True, []


def reverse_dependency_closure(items: list[dict[str, Any]], changed_items: set[str]) -> set[str]:
    id_to_item = {artifact_id(item): item for item in items if artifact_id(item)}
    reverse: dict[str, list[str]] = defaultdict(list)
    for item in items:
        aid = artifact_id(item)
        if not aid:
            continue
        for ref in str_items(item.get("derived_from")):
            reverse[ref].append(aid)

    changed_aliases: set[str] = set()
    for aid in changed_items:
        item = id_to_item.get(aid)
        if item:
            changed_aliases.update(aliases(item))
        else:
            changed_aliases.add(aid)

    stale: set[str] = set()
    queue: deque[str] = deque(sorted(changed_aliases))
    seen_refs: set[str] = set()
    while queue:
        ref = queue.popleft()
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        for dependent in reverse.get(ref, []):
            if dependent in changed_items or dependent in stale:
                continue
            stale.add(dependent)
            item = id_to_item.get(dependent)
            if item:
                queue.extend(sorted(aliases(item)))
    return stale


def check(ip_dir: Path, *, require: bool = False) -> dict[str, Any]:
    path = oag_paths.legacy_or_hidden(ip_dir, LIFECYCLE_PATH)
    issues: list[dict[str, str]] = []
    if not path.is_file():
        if require:
            issues.append(issue("STALE_LIFECYCLE_MISSING", "Required ontology/artifact_lifecycle.json is missing.", str(path)))
        return {
            "schema_version": "oag_stale_check.v1",
            "status": "fail" if issues else "pass",
            "ip": ip_dir.name,
            "lifecycle_path": str(path),
            "changed_artifacts": [],
            "stale_artifacts": [],
            "counts": {"artifacts": 0, "changed": 0, "stale": 0, "issues": len(issues)},
            "issues": issues,
            "next_actions": ["Create lifecycle metadata before stale propagation checks."] if issues else [],
        }

    payload, load_issues = read_json(path)
    issues.extend(load_issues)
    if payload is None:
        payload = {}
    else:
        issues.extend(schema_issues(payload))

    artifacts = payload.get("artifacts")
    items = [item for item in artifacts if isinstance(item, dict)] if isinstance(artifacts, list) else []
    changed: set[str] = set()
    for item in items:
        aid = artifact_id(item)
        if not aid:
            continue
        is_changed, hash_issues = changed_by_hash(ip_dir, item)
        if is_changed:
            changed.add(aid)
        issues.extend(hash_issues)

    stale = reverse_dependency_closure(items, changed)
    id_to_item = {artifact_id(item): item for item in items if artifact_id(item)}
    for aid in sorted(stale):
        item = id_to_item.get(aid) or {}
        if item.get("approval_state") == "approved" and item.get("validity_state") == "current":
            issues.append(issue("STALE_DEPENDENT_CURRENT", "Approved/current artifact depends on changed input and must be revalidated or marked stale.", aid))

    return {
        "schema_version": "oag_stale_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "lifecycle_path": str(path),
        "changed_artifacts": sorted(changed),
        "stale_artifacts": sorted(stale),
        "counts": {"artifacts": len(items), "changed": len(changed), "stale": len(stale), "issues": len(issues)},
        "issues": issues,
        "next_actions": ["Recompute affected artifacts, update hashes, or mark stale before using downstream evidence."] if issues else ["No stale lifecycle propagation detected."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--require", action="store_true", help="Fail when ontology/artifact_lifecycle.json is missing.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check(Path(args.ip_dir), require=args.require)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS OAG stale check")
    else:
        print("FAIL OAG stale check", file=sys.stderr)
        for item in result["issues"]:
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
