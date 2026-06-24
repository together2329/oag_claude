#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from oag_wavefront_core import (
    Issue,
    JsonObject,
    WavefrontEvent,
    WavefrontRun,
    append_event,
    display_path,
    graph_paths,
    issue,
    result,
    run_state_lock,
    utc_now,
    write_json,
)
from oag_wavefront_graph import (
    GraphSeed,
    active_lock_paths,
    barrier_ready,
    build_wavefront_graph,
    dependency_ready,
    initial_barriers_payload,
    initial_locks_payload,
    load_barriers,
    load_graph,
    load_locks,
    normalize_wavefront_tasks,
    ready_tasks,
    stale_path_issues,
    task_map,
    task_write_paths,
    write_graph,
    write_locks,
)
from oag_wavefront_validation import verify_invariants


@dataclass(frozen=True)
class PlanRequest:
    run: WavefrontRun
    raw_tasks: list[Any]
    template: str = ""
    barrier_tokens: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClaimRequest:
    run: WavefrontRun
    task_id: str
    claimed_by: str = ""
    dispatch_id: str = ""


def create_wavefront_run(request: PlanRequest) -> JsonObject:
    now = utc_now()
    paths = graph_paths(request.run)
    tasks, task_issues = normalize_wavefront_tasks(request.raw_tasks, request.run.ip_dir)
    if task_issues:
        return _plan_failure(paths, task_issues)
    seed = GraphSeed(request.run, request.template, tasks, now)
    graph = build_wavefront_graph(seed)
    locks = initial_locks_payload(request.run, now)
    barriers = initial_barriers_payload(request.run, request.barrier_tokens, now)
    issues = verify_invariants(graph, locks, barriers)
    if issues:
        return _plan_failure(paths, issues)
    with run_state_lock(request.run):
        paths["run_dir"].mkdir(parents=True, exist_ok=True)
        paths["claims"].mkdir(parents=True, exist_ok=True)
        write_json(paths["graph"], graph)
        write_json(paths["locks"], locks)
        write_json(paths["barriers"], barriers)
        append_event(WavefrontEvent(request.run, "planned", details={"template": request.template, "tasks": [task["task_id"] for task in tasks]}))
    return result(
        "pass",
        "oag_wavefront_plan_result.v1",
        graph_path=display_path(paths["graph"]),
        locks_path=display_path(paths["locks"]),
        barriers_path=display_path(paths["barriers"]),
        events_path=display_path(paths["events"]),
        ready_tasks=[task["task_id"] for task in ready_tasks(graph, barriers)],
        issues=issues,
    )


def _plan_failure(paths: dict[str, Path], issues: list[Issue]) -> JsonObject:
    return result(
        "fail",
        "oag_wavefront_plan_result.v1",
        graph_path=display_path(paths["graph"]),
        locks_path=display_path(paths["locks"]),
        barriers_path=display_path(paths["barriers"]),
        events_path=display_path(paths["events"]),
        ready_tasks=[],
        issues=issues,
    )


def load_wavefront_run_status(run: WavefrontRun, schema_version: str = "oag_wavefront_run_status.v1") -> JsonObject:
    paths = graph_paths(run)
    required_paths = [paths["graph"], paths["locks"], paths["barriers"]]
    missing_paths = [display_path(path) for path in required_paths if not path.is_file()]
    if missing_paths:
        return result(
            "missing",
            schema_version,
            graph_exists=paths["graph"].is_file(),
            run_id=run.run_id,
            graph_path=display_path(paths["graph"]),
            locks_path=display_path(paths["locks"]),
            barriers_path=display_path(paths["barriers"]),
            events_path=display_path(paths["events"]),
            counts={},
            ready_task_ids=[],
            active_locks=[],
            barrier_tokens=[],
            issues=[issue("STATE_MISSING", f"missing wavefront state file: {path}", path) for path in missing_paths],
        )
    try:
        graph = load_graph(run)
        locks = load_locks(run)
        barriers = load_barriers(run)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return result(
            "fail",
            schema_version,
            graph_exists=True,
            run_id=run.run_id,
            graph_path=display_path(paths["graph"]),
            locks_path=display_path(paths["locks"]),
            barriers_path=display_path(paths["barriers"]),
            events_path=display_path(paths["events"]),
            counts={},
            ready_task_ids=[],
            active_locks=[],
            barrier_tokens=[],
            issues=[issue("STATE_LOAD", str(exc), display_path(paths["graph"]))],
        )
    return _status_payload(StatusState(run, graph, locks, barriers, schema_version))


@dataclass(frozen=True)
class StatusState:
    run: WavefrontRun
    graph: JsonObject
    locks: JsonObject
    barriers: JsonObject
    schema_version: str


def _status_payload(state: StatusState) -> JsonObject:
    counts: dict[str, int] = {}
    for task in state.graph.get("tasks", []):
        if isinstance(task, dict):
            status = str(task.get("status") or "")
            counts[status] = counts.get(status, 0) + 1
    issues = verify_invariants(state.graph, state.locks, state.barriers)
    paths = graph_paths(state.run)
    return result(
        "fail" if issues else "pass",
        state.schema_version,
        graph_exists=True,
        run_id=state.run.run_id,
        graph_path=display_path(paths["graph"]),
        locks_path=display_path(paths["locks"]),
        barriers_path=display_path(paths["barriers"]),
        events_path=display_path(paths["events"]),
        counts=counts,
        ready_task_ids=[task["task_id"] for task in ready_tasks(state.graph, state.barriers)],
        active_locks=state.locks.get("locks", []),
        barrier_tokens=state.barriers.get("tokens", []),
        issues=issues,
    )


def claim_wavefront_task(request: ClaimRequest) -> JsonObject:
    with run_state_lock(request.run):
        graph = load_graph(request.run)
        locks = load_locks(request.run)
        barriers = load_barriers(request.run)
        tasks = task_map(graph)
        task = tasks.get(request.task_id)
        if not task:
            return result("fail", "oag_wavefront_claim_result.v1", issues=[issue("TASK_NOT_FOUND", f"task not found: {request.task_id}")])
        issues = _collect_claim_issues(ClaimCheck(request, task, tasks, barriers, locks))
        if issues:
            append_event(WavefrontEvent(request.run, "blocked", task_id=request.task_id, status="blocked", details={"issues": issues}))
            return result("fail", "oag_wavefront_claim_result.v1", issues=issues)
        return _persist_claim(ClaimPersistence(request, graph, locks, task))


@dataclass
class ClaimCheck:
    request: ClaimRequest
    task: JsonObject
    tasks: dict[str, JsonObject]
    barriers: JsonObject
    locks: JsonObject
    issues: list[Issue] = field(default_factory=list)


@dataclass(frozen=True)
class ClaimPersistence:
    request: ClaimRequest
    graph: JsonObject
    locks: JsonObject
    task: JsonObject


def _collect_claim_issues(check: ClaimCheck) -> list[Issue]:
    request = check.request
    task = check.task
    if task.get("status") != "pending":
        check.issues.append(issue("TASK_NOT_PENDING", f"task status is {task.get('status')}", request.task_id))
    deps_ok, dep_blockers = dependency_ready(task, check.tasks)
    if not deps_ok:
        check.issues.extend(issue("DEPENDENCY_UNMET", blocker, request.task_id) for blocker in dep_blockers)
    barriers_ok, barrier_blockers = barrier_ready(task, check.barriers)
    if not barriers_ok:
        check.issues.extend(issue("BARRIER_UNMET", f"missing barrier token: {token}", request.task_id) for token in barrier_blockers)
    check.issues.extend(stale_path_issues(task, request.run.ip_dir))
    active = active_lock_paths(check.locks)
    for path in task_write_paths(task):
        if path in active:
            check.issues.append(issue("OWNERSHIP_CONFLICT", f"path already locked by {active[path]}", path))
    return check.issues


def _persist_claim(persistence: ClaimPersistence) -> JsonObject:
    request = persistence.request
    graph = persistence.graph
    locks = persistence.locks
    task = persistence.task
    write_paths = task_write_paths(task)
    claim_file = graph_paths(request.run)["claims"] / f"{request.task_id}.lock"
    claim_file.parent.mkdir(parents=True, exist_ok=True)
    claim_time = utc_now()
    try:
        with claim_file.open("x", encoding="utf-8") as fh:
            fh.write(json.dumps({"task_id": request.task_id, "claimed_by": request.claimed_by, "claimed_at": claim_time}) + "\n")
    except FileExistsError:
        return result("fail", "oag_wavefront_claim_result.v1", issues=[issue("TASK_ALREADY_CLAIMED", "task claim lock already exists", request.task_id)])

    task["status"] = "claimed"
    task["claimed_by"] = request.claimed_by
    task["claimed_at"] = claim_time
    for lock_path in write_paths:
        locks.setdefault("locks", []).append(
            {
                "task_id": request.task_id,
                "path": lock_path,
                "mode": task.get("ownership_mode"),
                "dispatch_id": request.dispatch_id,
                "claimed_at": task["claimed_at"],
            }
        )
    write_graph(request.run, graph)
    write_locks(request.run, locks)
    append_event(WavefrontEvent(request.run, "claimed", task_id=request.task_id, status="claimed", details={"write_paths": write_paths}))
    return result(
        "pass",
        "oag_wavefront_claim_result.v1",
        task=task,
        active_locks=locks.get("locks", []),
        issues=[],
    )
