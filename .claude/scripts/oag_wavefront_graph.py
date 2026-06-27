#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Final

from oag_wavefront_core import (
    Issue,
    JsonObject,
    WavefrontRun,
    display_path,
    graph_paths,
    ip_rel_path,
    issue,
    load_json,
    path_fingerprint,
    utc_now,
    write_json,
)


TASK_ID_RE: Final = re.compile(r"^[A-Za-z0-9_.-]+$")
DONE_STATUSES: Final = {"handoff_pass", "closed", "waived"}
ACTIVE_STATUSES: Final = {"claimed", "review_pending"}
VALID_STATUSES: Final = {
    "pending",
    "claimed",
    "review_pending",
    "handoff_pass",
    "blocked",
    "failed",
    "inconclusive",
    "waived",
    "closed",
}
VALID_KINDS: Final = {"read_only", "write", "integration", "closure"}
VALID_OWNERSHIP: Final = {"none", "exclusive_file", "integration_owner"}


@dataclass(frozen=True)
class GraphSeed:
    run: WavefrontRun
    template: str
    tasks: list[JsonObject]
    created_at: str


def normalize_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if isinstance(raw, str) and raw:
        return [raw]
    return []


def normalize_task(raw: JsonObject, ip_dir: Path) -> JsonObject:
    task_id = str(raw.get("task_id") or "").strip()
    if not TASK_ID_RE.match(task_id):
        raise ValueError(f"invalid task_id: {task_id}")
    kind = str(raw.get("kind") or "read_only").strip()
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid task kind for {task_id}: {kind}")
    ownership_mode = str(raw.get("ownership_mode") or ("none" if kind == "read_only" else "exclusive_file")).strip()
    if ownership_mode not in VALID_OWNERSHIP:
        raise ValueError(f"invalid ownership_mode for {task_id}: {ownership_mode}")
    allowed_write_paths = [ip_rel_path(item, ip_dir) for item in normalize_list(raw.get("allowed_write_paths"))]
    shared_artifacts = [ip_rel_path(item, ip_dir) for item in normalize_list(raw.get("shared_artifacts"))]
    stale_if_paths_changed = [ip_rel_path(item, ip_dir) for item in normalize_list(raw.get("stale_if_paths_changed"))]
    return {
        **raw,
        "task_id": task_id,
        "kind": kind,
        "phase": str(raw.get("phase") or kind),
        "agent_type": str(raw.get("agent_type") or ""),
        "depends_on": normalize_list(raw.get("depends_on")),
        "barrier_inputs": normalize_list(raw.get("barrier_inputs")),
        "barrier_outputs": normalize_list(raw.get("barrier_outputs")),
        "allowed_write_paths": sorted(set(allowed_write_paths)),
        "shared_artifacts": sorted(set(shared_artifacts)),
        "stale_if_paths_changed": sorted(set(stale_if_paths_changed)),
        "ownership_mode": ownership_mode,
        "status": str(raw.get("status") or "pending"),
        "may_claim_complete": False,
    }


def load_graph(run: WavefrontRun) -> JsonObject:
    path = graph_paths(run)["graph"]
    if not path.is_file():
        raise ValueError(f"wavefront graph is missing: {path}")
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"wavefront graph is not an object: {path}")
    return data


def write_graph(run: WavefrontRun, graph: JsonObject) -> None:
    graph["updated_at"] = utc_now()
    write_json(graph_paths(run)["graph"], graph)


def initial_locks_payload(run: WavefrontRun, now: str) -> JsonObject:
    return {
        "schema_version": "oag_ownership_locks.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run.run_id,
        "ip_id": run.ip_dir.name,
        "locks": [],
        "updated_at": now,
    }


def initial_barriers_payload(run: WavefrontRun, barrier_tokens: list[str], now: str) -> JsonObject:
    return {
        "schema_version": "oag_wavefront_barriers.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run.run_id,
        "ip_id": run.ip_dir.name,
        "tokens": barrier_tokens,
        "updated_at": now,
    }


def load_locks(run: WavefrontRun) -> JsonObject:
    path = graph_paths(run)["locks"]
    if path.is_file():
        data = load_json(path)
        if isinstance(data, dict):
            return data
    return initial_locks_payload(run, utc_now())


def write_locks(run: WavefrontRun, locks: JsonObject) -> None:
    locks["updated_at"] = utc_now()
    write_json(graph_paths(run)["locks"], locks)


def load_barriers(run: WavefrontRun) -> JsonObject:
    path = graph_paths(run)["barriers"]
    if path.is_file():
        data = load_json(path)
        if isinstance(data, dict):
            return data
    return initial_barriers_payload(run, [], utc_now())


def write_barriers(run: WavefrontRun, barriers: JsonObject) -> None:
    barriers["updated_at"] = utc_now()
    write_json(graph_paths(run)["barriers"], barriers)


def task_map(graph: JsonObject) -> dict[str, JsonObject]:
    return {str(task.get("task_id")): task for task in graph.get("tasks", []) if isinstance(task, dict)}


def dependency_ready(task: JsonObject, tasks: dict[str, JsonObject]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    for dep in normalize_list(task.get("depends_on")):
        dep_task = tasks.get(dep)
        if not dep_task:
            blockers.append(f"missing dependency {dep}")
            continue
        if str(dep_task.get("status") or "") not in DONE_STATUSES:
            blockers.append(f"dependency {dep} status={dep_task.get('status')}")
    return not blockers, blockers


def barrier_ready(task: JsonObject, barriers: JsonObject) -> tuple[bool, list[str]]:
    tokens = {str(item) for item in barriers.get("tokens", [])}
    blockers = [item for item in normalize_list(task.get("barrier_inputs")) if item not in tokens]
    return not blockers, blockers


def active_lock_paths(locks: JsonObject, *, exclude_task: str = "") -> dict[str, str]:
    paths: dict[str, str] = {}
    for lock in locks.get("locks", []):
        if not isinstance(lock, dict):
            continue
        task_id = str(lock.get("task_id") or "")
        if exclude_task and task_id == exclude_task:
            continue
        path = str(lock.get("path") or "")
        if path:
            paths[path] = task_id
    return paths


def task_write_paths(task: JsonObject) -> list[str]:
    return sorted(set(normalize_list(task.get("allowed_write_paths")) + normalize_list(task.get("shared_artifacts"))))


def seed_pre_edit_hashes(task: JsonObject, ip_dir: Path) -> None:
    hashes = {
        path: path_fingerprint(ip_dir / path)
        for path in normalize_list(task.get("stale_if_paths_changed"))
    }
    if hashes:
        task["pre_edit_hashes"] = hashes


def stale_path_issues(task: JsonObject, ip_dir: Path) -> list[Issue]:
    hashes = task.get("pre_edit_hashes") if isinstance(task.get("pre_edit_hashes"), dict) else {}
    issues: list[Issue] = []
    for path in normalize_list(task.get("stale_if_paths_changed")):
        expected = str(hashes.get(path) or "")
        observed = path_fingerprint(ip_dir / path)
        if expected and observed != expected:
            issues.append(issue("STALE_PATH_CHANGED", f"path changed since wavefront plan: {path}", path))
    return issues


def ready_tasks(graph: JsonObject, barriers: JsonObject) -> list[JsonObject]:
    tasks = task_map(graph)
    ready: list[JsonObject] = []
    for task in graph.get("tasks", []):
        if not isinstance(task, dict) or task.get("status") != "pending":
            continue
        deps_ok, _ = dependency_ready(task, tasks)
        barriers_ok, _ = barrier_ready(task, barriers)
        if deps_ok and barriers_ok:
            ready.append(task)
    return ready


def build_wavefront_graph(seed: GraphSeed) -> JsonObject:
    return {
        "schema_version": "oag_wavefront_task_graph.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": seed.run.run_id,
        "ip_id": seed.run.ip_dir.name,
        "ip_dir": display_path(seed.run.ip_dir),
        "template": seed.template,
        "tasks": seed.tasks,
        "created_at": seed.created_at,
        "updated_at": seed.created_at,
    }


def normalize_wavefront_tasks(raw_tasks: list[Any], ip_dir: Path) -> tuple[list[JsonObject], list[Issue]]:
    tasks: list[JsonObject] = []
    issues: list[Issue] = []
    for index, raw_task in enumerate(raw_tasks):
        if not isinstance(raw_task, dict):
            issues.append(issue("TASK_OBJECT", "task must be an object", f"tasks/{index}"))
            continue
        try:
            task = normalize_task(raw_task, ip_dir)
        except ValueError as exc:
            issues.append(issue("TASK_INVALID", str(exc), f"tasks/{index}"))
            continue
        seed_pre_edit_hashes(task, ip_dir)
        tasks.append(task)
    if not tasks:
        issues.append(issue("NO_TASKS", "wavefront template produced no tasks"))
    return tasks, issues
