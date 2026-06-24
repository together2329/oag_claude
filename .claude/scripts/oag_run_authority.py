#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, NamedTuple

from oag_wavefront_core import WavefrontRun
from oag_wavefront_graph import dependency_ready, load_graph, task_map


class OagGraphRecordError(ValueError):
    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return self.message


class GraphRecordContext(NamedTuple):
    ip: Path
    state: dict[str, Any]
    actor: dict[str, Any]
    task: dict[str, Any]


def find_graph_record_task(ip: Path, state: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    graph = load_graph(_wavefront_run(ip, str(state.get("run_id") or "")))
    tasks = task_map(graph)
    requested_task = str(arguments.get("task_id") or "").strip()
    if requested_task:
        task = tasks.get(requested_task)
        if not task:
            raise OagGraphRecordError(
                "PARENT_AUTHORITY_TASK_NOT_FOUND",
                f"parent-authority task not found in run graph: {requested_task}",
            )
        return task
    obligation = str(arguments.get("obligation") or state.get("active_obligation") or "").strip()
    safe_obligation = _safe_filename(obligation)
    task = tasks.get(f"closure.{safe_obligation}") if safe_obligation else None
    if not task:
        raise OagGraphRecordError(
            "PARENT_AUTHORITY_CLOSURE_TASK_REQUIRED",
            "parent-authority closure task is required for graph-backed oag.run.record",
        )
    return task


def require_record_authority(context: GraphRecordContext) -> None:
    task_kind = str(context.task.get("kind") or "")
    authority = _actor_graph_authority(context.actor)
    if authority == "worker":
        raise OagGraphRecordError(
            "PARENT_AUTHORITY_WORKER_REJECTED",
            "parent-authority error: worker/dispatch actors cannot call oag.run.record for graph-backed closure",
        )
    if task_kind == "closure" and authority != "parent":
        raise OagGraphRecordError(
            "PARENT_AUTHORITY_PARENT_REQUIRED",
            "parent-authority error: closure records must be parent-owned",
        )
    if task_kind == "integration" and authority != "integration_owner":
        raise OagGraphRecordError(
            "PARENT_AUTHORITY_INTEGRATION_OWNER_REQUIRED",
            "parent-authority error: integration promotion records must be integration-owner-owned",
        )
    if task_kind not in {"closure", "integration"}:
        raise OagGraphRecordError(
            "PARENT_AUTHORITY_INVALID_TASK_KIND",
            f"parent-authority error: graph task kind cannot close ROCEV records: {task_kind or '<missing>'}",
        )


def require_graph_dependencies_closed(context: GraphRecordContext) -> None:
    tasks = task_map(load_graph(_wavefront_run(context.ip, str(context.state.get("run_id") or ""))))
    deps_ok, dep_blockers = dependency_ready(context.task, tasks)
    if not deps_ok:
        joined = "; ".join(dep_blockers)
        raise OagGraphRecordError(
            "PARENT_AUTHORITY_DEPENDENCIES_OPEN",
            f"parent-authority blocked: graph dependencies are not closed: {joined}",
        )


def require_graph_evidence_ready(context: GraphRecordContext) -> None:
    missing = _required_graph_evidence_missing(context)
    if missing:
        raise OagGraphRecordError(
            "PARENT_AUTHORITY_EVIDENCE_MISSING",
            f"parent-authority blocked: required graph evidence is missing: {', '.join(missing)}",
        )


def _wavefront_run(ip: Path, run_id: str) -> WavefrontRun:
    return WavefrontRun(ip, _safe_filename(run_id))


def _safe_filename(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return text or "unnamed"


def _str_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _actor_graph_authority(actor: dict[str, Any]) -> str:
    text = " ".join(str(actor.get(key) or "") for key in ("kind", "id", "surface")).lower().replace("-", "_")
    if any(token in text for token in ("dispatch", "worker", "subagent")):
        return "worker"
    if "integration_owner" in text:
        return "integration_owner"
    return "parent"


def _required_graph_evidence_missing(context: GraphRecordContext) -> list[str]:
    missing: list[str] = []
    for ref in _str_items(context.task.get("required_evidence")):
        path = context.ip / ref
        if path.is_dir():
            if not any(path.iterdir()):
                missing.append(ref)
        elif not path.is_file():
            missing.append(ref)
    return missing
