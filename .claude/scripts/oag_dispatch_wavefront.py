from __future__ import annotations

import json
from pathlib import Path

import oag_paths
from oag_dispatch_support import Issue, JsonObject, issue, load_json, normalize_rel, project_rel, resolve_project_path

WAVEFRONT_FIELDS = ("wavefront_run_id", "task_id", "ownership_mode")
CANONICAL_AGGREGATE_EVIDENCE = frozenset(
    {
        "sim/scoreboard_events.jsonl",
        "cov/coverage.json",
        "formal/formal_status.json",
    }
)
SHARD_EVIDENCE_PREFIXES = ("sim/slices/", "cov/slices/", "formal/slices/", "knowledge/subagents/")


def dispatch_has_wavefront_metadata(dispatch: JsonObject) -> bool:
    return any(str(dispatch.get(field) or "") for field in WAVEFRONT_FIELDS)


def ip_relative(normalized_project_path: str, ip_rel: str) -> str:
    normalized = normalized_project_path.strip("/")
    ip_prefix = ip_rel.strip("/")
    if normalized == ip_prefix:
        return ""
    prefix = f"{ip_prefix}/"
    if normalized.startswith(prefix):
        return normalized[len(prefix):]
    return normalized


def is_canonical_aggregate_path(path: str, ip_rel: str) -> bool:
    return ip_relative(normalize_rel(path), ip_rel) in CANONICAL_AGGREGATE_EVIDENCE


def requires_shard_scope(dispatch: JsonObject) -> bool:
    stage = str(dispatch.get("stage") or "").lower()
    return str(dispatch.get("ownership_mode") or "") == "exclusive_file" and stage in {"sim", "coverage", "cov", "formal", "closure"}


def is_shard_scope_path(path: str, dispatch: JsonObject, ip_rel: str) -> bool:
    rel = ip_relative(normalize_rel(path), ip_rel)
    receipt_rel = ip_relative(normalize_rel(str(dispatch.get("receipt_path") or "")), ip_rel)
    return rel == receipt_rel or any(rel.startswith(prefix) for prefix in SHARD_EVIDENCE_PREFIXES)


def load_wavefront_json(path: Path, issues: list[Issue], code: str) -> JsonObject:
    if not path.is_file():
        issues.append(issue(code, f"missing wavefront state file: {project_rel(path)}", project_rel(path)))
        return {}
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(issue(code, f"cannot load wavefront state file: {exc}", project_rel(path)))
        return {}
    if not isinstance(data, dict):
        issues.append(issue(code, "wavefront state file must contain a JSON object", project_rel(path)))
        return {}
    return data


def collect_wavefront_claim_issues(dispatch: JsonObject) -> list[Issue]:
    issues: list[Issue] = []
    run_id = str(dispatch.get("wavefront_run_id") or "")
    task_id = str(dispatch.get("task_id") or "")
    ownership_mode = str(dispatch.get("ownership_mode") or "")
    if not run_id or not task_id or not ownership_mode:
        for field in WAVEFRONT_FIELDS:
            if not str(dispatch.get(field) or ""):
                issues.append(issue("DISPATCH_WAVEFRONT_FIELD_MISSING", f"dispatch.{field} is required for wavefront dispatches"))
        return issues

    ip_dir = resolve_project_path(str(dispatch.get("ip_dir") or ""))
    graph_path = oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}/wavefront_task_graph.json")
    locks_path = oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}/ownership_locks.json")
    graph = load_wavefront_json(graph_path, issues, "WAVEFRONT_GRAPH_LOAD")
    locks = load_wavefront_json(locks_path, issues, "WAVEFRONT_LOCKS_LOAD")
    if issues:
        return issues

    tasks = [task for task in graph.get("tasks", []) if isinstance(task, dict)]
    matching_tasks = [task for task in tasks if str(task.get("task_id") or "") == task_id]
    if not matching_tasks:
        issues.append(issue("WAVEFRONT_TASK_NOT_FOUND", "dispatch.task_id is not present in the wavefront graph", task_id))
        return issues
    task = matching_tasks[0]
    if str(task.get("status") or "") != "claimed":
        issues.append(issue("WAVEFRONT_TASK_UNCLAIMED", f"wavefront task status is {task.get('status')}", task_id))
    if str(task.get("ownership_mode") or "") != ownership_mode:
        issues.append(issue("WAVEFRONT_OWNERSHIP_MISMATCH", "dispatch.ownership_mode does not match the graph task", task_id))
    if task.get("may_claim_complete") is not False:
        issues.append(issue("WAVEFRONT_TASK_COMPLETION_CLAIM", "graph task must keep may_claim_complete=false", task_id))

    dispatch_id = str(dispatch.get("dispatch_id") or "")
    matching_locks = [
        lock
        for lock in locks.get("locks", [])
        if isinstance(lock, dict) and str(lock.get("task_id") or "") == task_id and str(lock.get("dispatch_id") or "") == dispatch_id
    ]
    if not matching_locks:
        issues.append(issue("WAVEFRONT_CLAIM_DISPATCH_MISMATCH", "no ownership lock binds dispatch_id to dispatch.task_id", task_id))
    return issues
