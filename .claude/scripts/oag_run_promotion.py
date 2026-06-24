#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, NamedTuple

from oag_run_authority import (
    GraphRecordContext,
    OagGraphRecordError,
    _safe_filename,
    _str_items,
    _wavefront_run,
    require_graph_dependencies_closed,
    require_graph_evidence_ready,
    require_record_authority,
)
from oag_wavefront_core import graph_paths
from oag_wavefront_records import RecordRequest, record_wavefront_task


class IntegrationPromotionContext(NamedTuple):
    record: GraphRecordContext
    merge: dict[str, Any]


class CanonicalArtifactSnapshot(NamedTuple):
    ref: str
    path: Path
    content: bytes | None
    digest: str


class IntegrationPromotionRollback(NamedTuple):
    context: IntegrationPromotionContext
    base_receipt: dict[str, Any]
    snapshots: list[CanonicalArtifactSnapshot]
    attempted_hashes: dict[str, str]
    pass_receipt_path: str
    issues: list[Any]


def promote_integration_merge(context: IntegrationPromotionContext) -> dict[str, Any]:
    require_record_authority(context.record)
    require_graph_dependencies_closed(context.record)
    require_graph_evidence_ready(context.record)
    outputs = _promotion_canonical_outputs(context)
    pending = _promotion_pending_artifacts(context)
    snapshots = _snapshot_canonical_outputs(context.record.ip, outputs)
    before = _snapshot_hashes(snapshots)
    base_receipt = {
        "schema_version": "oag_integration_promotion_receipt.v1",
        "run_id": str(context.record.state.get("run_id") or ""),
        "task_id": str(context.record.task.get("task_id") or ""),
        "actor": context.record.actor,
        "pending_artifacts": pending,
        "canonical_outputs": outputs,
        "before_hashes": before,
        "created_at": _now(),
    }
    if _truthy_policy(context.merge.get("simulate_failure") or context.merge.get("force_failure")):
        receipt = {**base_receipt, "status": "rollback", "reason": "simulated merge failure before canonical promotion"}
        receipt_path = _write_integration_promotion_receipt(context, receipt)
        return {
            "status": "failed",
            "reason": "simulated_merge_failure",
            "receipt_path": str(receipt_path),
            "canonical_hashes_unchanged": before,
        }
    if not _truthy_policy(context.merge.get("validated")):
        raise OagGraphRecordError(
            "INTEGRATION_PROMOTION_VALIDATION_REQUIRED",
            "integration-promotion error: canonical aggregate promotion requires validated=true",
        )
    source = context.record.ip / pending[0]
    for ref in outputs:
        target = context.record.ip / ref
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    after = {ref: _artifact_digest(context.record.ip / ref) for ref in outputs}
    receipt = {**base_receipt, "status": "pass", "after_hashes": after}
    receipt_path = _write_integration_promotion_receipt(context, receipt)
    graph_record = record_wavefront_task(
        RecordRequest(
            run=_wavefront_run(context.record.ip, str(context.record.state.get("run_id") or "")),
            task_id=str(context.record.task.get("task_id") or ""),
            status="closed",
            barrier_outputs=_str_items(context.record.task.get("barrier_outputs")),
            receipt=str(receipt_path),
        )
    )
    if graph_record.get("status") != "pass":
        issues = graph_record.get("issues") if isinstance(graph_record.get("issues"), list) else []
        rollback_receipt = _write_graph_record_failure_rollback_receipt(
            IntegrationPromotionRollback(context, base_receipt, snapshots, after, str(receipt_path), issues)
        )
        raise OagGraphRecordError(
            "INTEGRATION_PROMOTION_GRAPH_RECORD_FAILED",
            f"integration-promotion error: graph task record failed: {issues}; rollback_receipt={rollback_receipt}",
        )
    return {
        "status": "promoted",
        "receipt_path": str(receipt_path),
        "canonical_outputs": outputs,
        "canonical_hashes": after,
        "graph_record": graph_record,
    }


def _truthy_policy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_dir(ip: Path, run_id: str) -> Path:
    return graph_paths(_wavefront_run(ip, run_id))["run_dir"]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _artifact_digest(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir():
        items = []
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            items.append(f"{child.relative_to(path)}:{hashlib.sha256(child.read_bytes()).hexdigest()}")
        payload = "\n".join(items)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "missing"


def _snapshot_canonical_outputs(ip: Path, refs: list[str]) -> list[CanonicalArtifactSnapshot]:
    snapshots: list[CanonicalArtifactSnapshot] = []
    for ref in refs:
        path = ip / ref
        content = path.read_bytes() if path.is_file() else None
        snapshots.append(CanonicalArtifactSnapshot(ref, path, content, _artifact_digest(path)))
    return snapshots


def _snapshot_hashes(snapshots: list[CanonicalArtifactSnapshot]) -> dict[str, str]:
    return {snapshot.ref: snapshot.digest for snapshot in snapshots}


def _restore_canonical_outputs(snapshots: list[CanonicalArtifactSnapshot]) -> dict[str, str]:
    restored: dict[str, str] = {}
    for snapshot in snapshots:
        if snapshot.content is None:
            if snapshot.path.is_file() or snapshot.path.is_symlink():
                snapshot.path.unlink()
            elif snapshot.path.exists():
                raise OagGraphRecordError(
                    "INTEGRATION_PROMOTION_ROLLBACK_FAILED",
                    f"integration-promotion rollback cannot remove non-file canonical output: {snapshot.ref}",
                )
        else:
            snapshot.path.parent.mkdir(parents=True, exist_ok=True)
            snapshot.path.write_bytes(snapshot.content)
        restored[snapshot.ref] = _artifact_digest(snapshot.path)
    return restored


def _write_graph_record_failure_rollback_receipt(rollback: IntegrationPromotionRollback) -> Path:
    restored = _restore_canonical_outputs(rollback.snapshots)
    receipt = {
        **rollback.base_receipt,
        "status": "rollback",
        "reason": "graph_record_failed_after_canonical_promotion",
        "graph_record_issues": rollback.issues,
        "attempted_hashes": rollback.attempted_hashes,
        "restored_hashes": restored,
        "pass_receipt_path": rollback.pass_receipt_path,
        "restored": restored == _snapshot_hashes(rollback.snapshots),
    }
    return _write_integration_promotion_receipt(rollback.context, receipt)


def _promotion_canonical_outputs(context: IntegrationPromotionContext) -> list[str]:
    allowed = set(_str_items(context.record.task.get("canonical_outputs")) + _str_items(context.record.task.get("shared_artifacts")))
    requested = _str_items(
        context.merge.get("canonical_outputs")
        or context.merge.get("canonical_output")
        or context.merge.get("canonical_refs")
        or context.merge.get("canonical_ref")
    )
    outputs = requested or sorted(allowed)
    unexpected = [ref for ref in outputs if ref not in allowed]
    if unexpected:
        raise OagGraphRecordError(
            "INTEGRATION_PROMOTION_UNOWNED_CANONICAL_OUTPUT",
            f"integration-promotion error: canonical output is not owned by integration task: {', '.join(unexpected)}",
        )
    if not outputs:
        raise OagGraphRecordError(
            "INTEGRATION_PROMOTION_NO_CANONICAL_OUTPUTS",
            "integration-promotion error: integration task declares no canonical aggregate outputs",
        )
    return outputs


def _promotion_pending_artifacts(context: IntegrationPromotionContext) -> list[str]:
    pending = _str_items(
        context.merge.get("pending_artifacts")
        or context.merge.get("pending_artifact")
        or context.merge.get("pending_merge_artifacts")
        or context.merge.get("pending_merge_artifact")
    )
    if not pending:
        raise OagGraphRecordError(
            "INTEGRATION_PROMOTION_PENDING_REQUIRED",
            "integration-promotion error: pending merge artifact is required before canonical promotion",
        )
    missing = [ref for ref in pending if not (context.record.ip / ref).is_file()]
    if missing:
        raise OagGraphRecordError(
            "INTEGRATION_PROMOTION_PENDING_MISSING",
            f"integration-promotion error: pending merge artifact missing: {', '.join(missing)}",
        )
    return pending


def _write_integration_promotion_receipt(context: IntegrationPromotionContext, receipt: dict[str, Any]) -> Path:
    task_id = _safe_filename(str(context.record.task.get("task_id") or "integration"))
    run_id = _safe_filename(str(context.record.state.get("run_id") or "run"))
    path = _run_dir(context.record.ip, run_id) / "integration_promotions" / f"{task_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    _write_json(path, receipt)
    return path
