#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field

from oag_wavefront_core import JsonObject, WavefrontEvent, WavefrontRun, append_event, ip_rel_path, issue, result, run_state_lock, utc_now
from oag_wavefront_graph import (
    ACTIVE_STATUSES,
    DONE_STATUSES,
    VALID_STATUSES,
    load_barriers,
    load_graph,
    load_locks,
    normalize_list,
    ready_tasks,
    task_map,
    write_barriers,
    write_graph,
    write_locks,
)
from oag_wavefront_core import graph_paths
from oag_wavefront_validation import verify_invariants


@dataclass(frozen=True)
class RecordRequest:
    run: WavefrontRun
    task_id: str
    status: str
    barrier_outputs: list[str] = field(default_factory=list)
    receipt: str = ""


def ready_wavefront_tasks(run: WavefrontRun) -> JsonObject:
    graph = load_graph(run)
    locks = load_locks(run)
    barriers = load_barriers(run)
    issues = verify_invariants(graph, locks, barriers)
    if issues:
        return result("fail", "oag_wavefront_ready_result.v1", ready_tasks=[], issues=issues)
    ready = ready_tasks(graph, barriers)
    append_event(WavefrontEvent(run, "ready", details={"ready_tasks": [task["task_id"] for task in ready]}))
    return result("pass", "oag_wavefront_ready_result.v1", ready_tasks=ready)


def record_wavefront_task(request: RecordRequest) -> JsonObject:
    with run_state_lock(request.run):
        graph = load_graph(request.run)
        locks = load_locks(request.run)
        barriers = load_barriers(request.run)
        tasks = task_map(graph)
        task = tasks.get(request.task_id)
        if not task:
            return result("fail", "oag_wavefront_record_result.v1", issues=[issue("TASK_NOT_FOUND", f"task not found: {request.task_id}")])
        if request.status not in VALID_STATUSES:
            return result("fail", "oag_wavefront_record_result.v1", issues=[issue("TASK_STATUS", f"invalid status: {request.status}")])
        undeclared_outputs = _undeclared_barrier_outputs(request, task)
        if undeclared_outputs:
            return result(
                "fail",
                "oag_wavefront_record_result.v1",
                issues=[
                    issue("BARRIER_OUTPUT_UNDECLARED", f"task did not declare barrier output: {token}", request.task_id)
                    for token in undeclared_outputs
                ],
            )
        task["status"] = request.status
        task["recorded_at"] = utc_now()
        if request.receipt:
            task["receipt_path"] = ip_rel_path(request.receipt, request.run.ip_dir)
        if request.status not in ACTIVE_STATUSES:
            locks["locks"] = [lock for lock in locks.get("locks", []) if not isinstance(lock, dict) or lock.get("task_id") != request.task_id]
            claim_file = graph_paths(request.run)["claims"] / f"{request.task_id}.lock"
            if claim_file.is_file():
                claim_file.unlink()
        tokens = set(str(item) for item in barriers.get("tokens", []))
        tokens.update(request.barrier_outputs)
        barriers["tokens"] = sorted(tokens)
        write_graph(request.run, graph)
        write_locks(request.run, locks)
        write_barriers(request.run, barriers)
        append_event(
            WavefrontEvent(
                request.run,
                "recorded",
                task_id=request.task_id,
                status=request.status,
                details={"barrier_outputs": request.barrier_outputs, "receipt": request.receipt},
            )
        )
        return result(
            "pass",
            "oag_wavefront_record_result.v1",
            task=task,
            barrier_tokens=barriers.get("tokens", []),
            active_locks=locks.get("locks", []),
        )


def _undeclared_barrier_outputs(request: RecordRequest, task: JsonObject) -> list[str]:
    declared_outputs = set(normalize_list(task.get("barrier_outputs")))
    return [token for token in request.barrier_outputs if token not in declared_outputs]


def verify_wavefront_run(run: WavefrontRun) -> JsonObject:
    graph = load_graph(run)
    locks = load_locks(run)
    barriers = load_barriers(run)
    issues = verify_invariants(graph, locks, barriers)
    append_event(WavefrontEvent(run, "verified", status="fail" if issues else "pass", details={"issues": issues}))
    return result("fail" if issues else "pass", "oag_wavefront_verify_result.v1", issues=issues)


def close_wavefront_run(run: WavefrontRun, allow_open: bool) -> JsonObject:
    graph = load_graph(run)
    locks = load_locks(run)
    active = [lock for lock in locks.get("locks", []) if isinstance(lock, dict)]
    open_tasks = [
        task for task in graph.get("tasks", [])
        if isinstance(task, dict) and str(task.get("status") or "") not in DONE_STATUSES
    ]
    issues: list[dict[str, str]] = []
    if active:
        issues.append(issue("ACTIVE_LOCKS", "cannot close wavefront with active ownership locks"))
    if open_tasks and not allow_open:
        issues.append(issue("OPEN_TASKS", "cannot close wavefront with open tasks"))
    if issues:
        return result("fail", "oag_wavefront_close_result.v1", issues=issues, open_tasks=open_tasks, active_locks=active)
    graph["closed_at"] = utc_now()
    write_graph(run, graph)
    append_event(WavefrontEvent(run, "closed", status="pass", details={"open_tasks": [task.get("task_id") for task in open_tasks]}))
    return result("pass", "oag_wavefront_close_result.v1", open_tasks=open_tasks, active_locks=active)
