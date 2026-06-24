from __future__ import annotations

import argparse
from pathlib import Path

from oag_dispatch_support import (
    Issue,
    JsonObject,
    JsonValue,
    hash_known_paths,
    issue,
    load_json,
    normalize_rel,
    path_matches,
    project_rel,
    resolve_project_path,
    schema_issues,
)
from oag_dispatch_wavefront import (
    WAVEFRONT_FIELDS,
    collect_wavefront_claim_issues,
    dispatch_has_wavefront_metadata,
    is_canonical_aggregate_path,
    is_shard_scope_path,
    requires_shard_scope,
)
from oag_dispatch_support import git_status_paths

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


def string_list(payload: JsonObject, *fields: str) -> list[str]:
    values: list[str] = []
    for field in fields:
        raw = payload.get(field)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if isinstance(item, str))
    return sorted(set(values))


def filesystem_delta(dispatch: JsonObject) -> list[str]:
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


def actual_delta(dispatch: JsonObject) -> tuple[list[str], list[str]]:
    ip_rel = str(dispatch.get("ip_dir") or "")
    _, current = git_status_paths(ip_rel)
    baseline = dispatch.get("baseline") if isinstance(dispatch.get("baseline"), dict) else {}
    previous = baseline.get("git_status_paths") if isinstance(baseline.get("git_status_paths"), list) else []
    previous_set = {str(item) for item in previous}
    delta = sorted({path for path in current if path not in previous_set} | set(filesystem_delta(dispatch)))
    return current, delta


def append_schema_issues(issues: list[Issue], schema_name: str, document: JsonObject, prefix: str) -> None:
    for item in schema_issues(schema_name, document):
        issues.append(issue(f"{prefix}_{item['code']}", item["message"], item["path"]))


def json_shape_name(payload: JsonValue) -> str:
    if payload is None:
        return "null"
    if isinstance(payload, list):
        return "array"
    if isinstance(payload, str):
        return "string"
    if isinstance(payload, bool):
        return "boolean"
    if isinstance(payload, int | float):
        return "number"
    return type(payload).__name__


def load_json_object(path: Path, artifact_name: str, issue_code: str, issues: list[Issue]) -> JsonObject:
    try:
        payload = load_json(path)
    except (OSError, ValueError) as exc:
        issues.append(issue(issue_code, f"cannot load {artifact_name}: {exc}", project_rel(path)))
        return {}
    if not isinstance(payload, dict):
        issues.append(
            issue(
                f"{issue_code}_SHAPE",
                f"{artifact_name} JSON must be an object, got {json_shape_name(payload)}",
                project_rel(path),
            )
        )
        return {}
    return payload


def verify_dispatch(args: argparse.Namespace) -> JsonObject:
    issues: list[Issue] = []
    dispatch_path = resolve_project_path(args.dispatch)
    receipt_path = resolve_project_path(args.receipt)
    dispatch = load_json_object(dispatch_path, "dispatch", "DISPATCH_LOAD", issues)
    receipt = load_json_object(receipt_path, "receipt", "RECEIPT_LOAD", issues)

    if dispatch:
        append_schema_issues(issues, "oag_dispatch.schema.json", dispatch, "DISPATCH_SCHEMA")
    if receipt:
        append_schema_issues(issues, "oag_subagent_receipt.schema.json", receipt, "RECEIPT_SCHEMA")

    if dispatch and receipt:
        dispatch_id = str(dispatch.get("dispatch_id") or "")
        if str(receipt.get("dispatch_id") or "") != dispatch_id:
            issues.append(issue("DISPATCH_ID_MISMATCH", "receipt.dispatch_id does not match dispatch.dispatch_id"))
        receipt_dispatch_path = str(receipt.get("dispatch_path") or "")
        if receipt_dispatch_path and normalize_rel(receipt_dispatch_path) != project_rel(dispatch_path):
            issues.append(issue("DISPATCH_PATH_MISMATCH", "receipt.dispatch_path does not match the dispatch file"))
        if normalize_rel(str(dispatch.get("receipt_path") or "")) != project_rel(receipt_path):
            issues.append(issue("RECEIPT_PATH_MISMATCH", "dispatch.receipt_path does not match the receipt file"))
        if receipt.get("may_claim_complete") is not False or dispatch.get("may_claim_complete") is not False:
            issues.append(issue("COMPLETION_CLAIM", "dispatch and receipt must keep may_claim_complete=false"))

        wavefront_dispatch = dispatch_has_wavefront_metadata(dispatch)
        if wavefront_dispatch:
            for field in WAVEFRONT_FIELDS:
                dispatch_value = str(dispatch.get(field) or "")
                receipt_value = str(receipt.get(field) or "")
                if not dispatch_value:
                    issues.append(issue("DISPATCH_WAVEFRONT_FIELD_MISSING", f"dispatch.{field} is required for wavefront dispatches"))
                elif not receipt_value:
                    issues.append(issue("WAVEFRONT_FIELD_MISSING", f"receipt.{field} is required for wavefront dispatches"))
                elif receipt_value != dispatch_value:
                    issues.append(issue("WAVEFRONT_FIELD_MISMATCH", f"receipt.{field} does not match dispatch.{field}"))
            issues.extend(collect_wavefront_claim_issues(dispatch))

        status = str(receipt.get("status") or "")
        if status in LEGACY_RECEIPT_STATUSES:
            issues.append(issue("LEGACY_STATUS", "receipt status PASS is no longer accepted for dispatch-verified subagents"))
        elif status not in RECEIPT_SAFE_STATUSES:
            issues.append(issue("STATUS", f"receipt status is not an OAG handoff status: {status}"))
        if any(word in status.upper() for word in FORBIDDEN_STATUS_WORDS):
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
        expected_paths = [*allowed_write_paths, *allowed_tool_side_effects, str(dispatch.get("receipt_path") or ""), str(dispatch.get("dispatch_path") or "")]
        out_of_scope_actual = [path for path in delta_paths if not path_matches(path, expected_paths)]
        for path in out_of_scope_actual:
            issues.append(issue("ACTUAL_PATH_OUT_OF_SCOPE", "actual git status delta is outside dispatch scope", path))
        if wavefront_dispatch:
            ip_rel = str(dispatch.get("ip_dir") or "")
            ownership_mode = str(dispatch.get("ownership_mode") or "")
            wavefront_bookkeeping_paths = [str(dispatch.get("dispatch_path") or ""), *allowed_tool_side_effects]
            scoped_wavefront_paths = [
                path
                for path in sorted(set(owned + delta_paths))
                if not path_matches(normalize_rel(path), wavefront_bookkeeping_paths)
            ]
            for path in scoped_wavefront_paths:
                if ownership_mode != "integration_owner" and is_canonical_aggregate_path(path, ip_rel):
                    issues.append(issue("WORKER_CANONICAL_AGGREGATE_WRITE", "ordinary wavefront workers must not write canonical aggregate evidence", path))
                if requires_shard_scope(dispatch) and not is_shard_scope_path(path, dispatch, ip_rel):
                    issues.append(issue("WORKER_SHARD_SCOPE", "ordinary wavefront workers may only write shard evidence paths", path))
    else:
        current_paths, delta_paths = [], []
        owned, generated = [], []
        out_of_scope_actual = []

    return {
        "schema_version": "oag_dispatch_verify_result.v1",
        "status": "fail" if issues else "pass",
        "dispatch_path": str(dispatch_path),
        "receipt_path": str(receipt_path),
        "dispatch_id": dispatch.get("dispatch_id", ""),
        "receipt_status": receipt.get("status", ""),
        "owned_changed_paths": owned,
        "generated_side_effects": generated,
        "actual_status_paths": current_paths,
        "actual_delta_paths": delta_paths,
        "out_of_scope_paths": out_of_scope_actual,
        "issues": issues,
    }
