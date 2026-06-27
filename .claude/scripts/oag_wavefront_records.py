#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field

from pathlib import Path

from oag_wavefront_core import (
    JsonObject,
    WavefrontEvent,
    WavefrontRun,
    append_event,
    display_path,
    ip_rel_path,
    issue,
    load_json,
    resolve_read_path,
    result,
    run_state_lock,
    utc_now,
    validate_named_schema,
)
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
    decision: str = ""


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
        issues = _transition_issues(request, task)
        issues.extend(_barrier_output_issues(request))
        decision_path, decision_payload, decision_issues = _validated_decision(request)
        issues.extend(decision_issues)
        if issues:
            return result("fail", "oag_wavefront_record_result.v1", issues=issues)
        task["status"] = request.status
        task["recorded_at"] = utc_now()
        if request.receipt:
            task["receipt_path"] = ip_rel_path(request.receipt, request.run.ip_dir)
        if decision_path:
            task["decision_path"] = display_path(decision_path)
        if decision_payload:
            task["decision_id"] = str(decision_payload.get("decision_id") or "")
            task["decision_type"] = str(decision_payload.get("decision_type") or "")
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
                details={"barrier_outputs": request.barrier_outputs, "receipt": request.receipt, "decision": request.decision},
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


def _transition_issues(request: RecordRequest, task: JsonObject) -> list[dict[str, str]]:
    current_status = str(task.get("status") or "")
    if request.status == "review_pending" and current_status != "claimed":
        return [
            issue(
                "TASK_REVIEW_PENDING_TRANSITION",
                f"review_pending requires current task status claimed, got {current_status}",
                request.task_id,
            )
        ]
    if request.status == "handoff_pass" and current_status != "review_pending":
        return [
            issue(
                "TASK_HANDOFF_PASS_TRANSITION",
                f"handoff_pass requires current task status review_pending, got {current_status}",
                request.task_id,
            )
        ]
    return []


def _barrier_output_issues(request: RecordRequest) -> list[dict[str, str]]:
    if request.barrier_outputs and request.status not in DONE_STATUSES:
        return [
            issue(
                "BARRIER_OUTPUT_BEFORE_APPROVAL",
                f"barrier outputs require a done status, got {request.status}",
                request.task_id,
            )
        ]
    return []


def _validated_decision(request: RecordRequest) -> tuple[Path | None, JsonObject, list[dict[str, str]]]:
    if request.status != "handoff_pass" and not request.decision:
        return None, {}, []
    if request.status == "handoff_pass" and not request.decision:
        return None, {}, [issue("HANDOFF_DECISION_REQUIRED", "handoff_pass requires an approved review decision", request.task_id)]
    path = resolve_read_path(request.decision)
    if not path.is_file():
        return path, {}, [issue("DECISION_NOT_FOUND", f"decision file not found: {display_path(path)}", request.task_id)]
    try:
        payload = load_json(path)
    except (OSError, ValueError) as exc:
        return path, {}, [issue("DECISION_LOAD_FAILED", str(exc), display_path(path))]
    if not isinstance(payload, dict):
        return path, {}, [issue("DECISION_OBJECT", "decision file must contain a JSON object", display_path(path))]
    issues: list[dict[str, str]] = [
        issue(f"DECISION_SCHEMA_{item['code']}", item["message"], item["path"])
        for item in validate_named_schema("oag_wavefront_decision.schema.json", payload)
    ]
    issues.extend(_decision_semantic_issues(request, payload))
    return path, payload, issues


def _decision_semantic_issues(request: RecordRequest, payload: JsonObject) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    if str(target.get("run_id") or "") != request.run.run_id:
        issues.append(issue("DECISION_RUN_MISMATCH", "decision target.run_id does not match wavefront run", request.task_id))
    if str(target.get("task_id") or "") != request.task_id:
        issues.append(issue("DECISION_TASK_MISMATCH", "decision target.task_id does not match wavefront task", request.task_id))
    verdict = str(payload.get("verdict") or "")
    if request.status == "handoff_pass" and verdict != "approved":
        issues.append(issue("DECISION_NOT_APPROVED", f"handoff_pass requires verdict=approved, got {verdict}", request.task_id))
    rationale = payload.get("rationale") if isinstance(payload.get("rationale"), dict) else {}
    blockers = rationale.get("blockers") if isinstance(rationale.get("blockers"), list) else []
    if verdict == "approved" and blockers:
        issues.append(issue("APPROVED_DECISION_WITH_BLOCKERS", "approved decisions must not carry blockers", request.task_id))
    unlocks = payload.get("unlocks") if isinstance(payload.get("unlocks"), dict) else {}
    unlock_status = str(unlocks.get("wavefront_status") or "")
    if unlock_status and unlock_status != request.status:
        issues.append(issue("DECISION_UNLOCK_STATUS", f"decision unlock status {unlock_status} does not match requested status {request.status}", request.task_id))
    allowed_outputs = set(normalize_list(unlocks.get("barrier_outputs")))
    if allowed_outputs:
        requested_outputs = set(request.barrier_outputs)
        missing = sorted(requested_outputs - allowed_outputs)
        if missing:
            issues.append(issue("DECISION_BARRIER_OUTPUT", f"decision does not unlock requested barrier outputs: {missing}", request.task_id))
    return issues


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
