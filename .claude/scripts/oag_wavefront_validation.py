#!/usr/bin/env python3
from __future__ import annotations

from oag_wavefront_core import Issue, JsonObject, issue, validate_named_schema
from oag_wavefront_graph import VALID_KINDS, VALID_OWNERSHIP, VALID_STATUSES, normalize_list, task_map, task_write_paths


def verify_invariants(graph: JsonObject, locks: JsonObject, barriers: JsonObject) -> list[Issue]:
    issues: list[Issue] = []
    for item in validate_named_schema("oag_wavefront_task_graph.schema.json", graph):
        issues.append(issue(f"GRAPH_SCHEMA_{item['code']}", item["message"], item["path"]))
    for item in validate_named_schema("oag_ownership_locks.schema.json", locks):
        issues.append(issue(f"LOCKS_SCHEMA_{item['code']}", item["message"], item["path"]))
    _check_tasks(graph, issues)
    _check_locks(graph, locks, issues)
    if not isinstance(barriers.get("tokens", []), list):
        issues.append(issue("BARRIER_TOKENS", "barriers.tokens must be a list"))
    return issues


def _check_tasks(graph: JsonObject, issues: list[Issue]) -> None:
    tasks = task_map(graph)
    if len(tasks) != len(graph.get("tasks", [])):
        issues.append(issue("DUPLICATE_TASK_ID", "task_id values must be unique"))
    for task in graph.get("tasks", []):
        if not isinstance(task, dict):
            continue
        _check_task(tasks, task, issues)


def _check_task(tasks: dict[str, JsonObject], task: JsonObject, issues: list[Issue]) -> None:
    task_id = str(task.get("task_id") or "")
    status = str(task.get("status") or "")
    kind = str(task.get("kind") or "")
    ownership = str(task.get("ownership_mode") or "")
    if status not in VALID_STATUSES:
        issues.append(issue("TASK_STATUS", f"invalid task status: {status}", task_id))
    if kind not in VALID_KINDS:
        issues.append(issue("TASK_KIND", f"invalid task kind: {kind}", task_id))
    if ownership not in VALID_OWNERSHIP:
        issues.append(issue("OWNERSHIP_MODE", f"invalid ownership mode: {ownership}", task_id))
    if task.get("may_claim_complete") is not False:
        issues.append(issue("TASK_COMPLETION_CLAIM", "task must keep may_claim_complete=false", task_id))
    for dep in normalize_list(task.get("depends_on")):
        if dep not in tasks:
            issues.append(issue("MISSING_DEPENDENCY", f"task dependency does not exist: {dep}", task_id))
    if kind == "write" and ownership != "exclusive_file":
        issues.append(issue("WRITE_OWNERSHIP", "write tasks require exclusive_file ownership", task_id))
    if kind == "integration" and ownership != "integration_owner":
        issues.append(issue("INTEGRATION_OWNERSHIP", "integration tasks require integration_owner ownership", task_id))
    if normalize_list(task.get("shared_artifacts")) and ownership != "integration_owner":
        issues.append(issue("SHARED_ARTIFACT_OWNERSHIP", "shared artifacts require integration_owner ownership", task_id))
    if kind in {"write", "integration"} and not task_write_paths(task):
        issues.append(issue("MISSING_WRITE_SCOPE", "write/integration task has no write paths", task_id))
    if kind == "read_only" and task_write_paths(task):
        issues.append(issue("READ_ONLY_WRITE_SCOPE", "read_only task must not own write paths", task_id))


def _check_locks(graph: JsonObject, locks: JsonObject, issues: list[Issue]) -> None:
    tasks = task_map(graph)
    seen_paths: dict[str, str] = {}
    for lock in locks.get("locks", []):
        if not isinstance(lock, dict):
            continue
        task_id = str(lock.get("task_id") or "")
        path = str(lock.get("path") or "")
        if task_id not in tasks:
            issues.append(issue("LOCK_TASK_MISSING", "ownership lock refers to unknown task", path))
        if path in seen_paths and seen_paths[path] != task_id:
            issues.append(issue("DOUBLE_WRITER_LOCK", f"path locked by {seen_paths[path]} and {task_id}", path))
        seen_paths[path] = task_id
