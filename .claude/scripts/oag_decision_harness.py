#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import oag_paths
from oag_wavefront_core import JsonObject, WavefrontRun, display_path, issue, resolve_project_path, result, utc_now, validate_named_schema, write_json
from oag_wavefront_graph import load_graph, normalize_list


REVIEW_DECISION_TYPES = {
    "requirement_to_obligation",
    "obligation_to_contract",
    "rtl_readiness",
    "rtl_conformance",
    "tb_proof_adequacy",
    "evidence_validation",
    "custom_review",
}


def _run(ip_dir: str, run_id: str) -> WavefrontRun:
    return WavefrontRun(resolve_project_path(ip_dir), run_id)


def _slug(raw: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
    return slug or "decision"


def _decision_path(ip_dir: Path, decision_id: str) -> Path:
    return oag_paths.legacy_or_hidden(ip_dir, f"knowledge/decisions/{decision_id}.json")


def _review_pending_tasks(run: WavefrontRun) -> list[JsonObject]:
    graph = load_graph(run)
    return [
        task
        for task in graph.get("tasks", [])
        if isinstance(task, dict) and str(task.get("status") or "") == "review_pending"
    ]


def _prompt_for_task(task: JsonObject, run: WavefrontRun) -> str:
    task_id = str(task.get("task_id") or "")
    phase = str(task.get("phase") or "")
    agent_type = str(task.get("agent_type") or "oag-custom-reviewer")
    receipt = str(task.get("receipt_path") or "")
    write_paths = normalize_list(task.get("allowed_write_paths")) + normalize_list(task.get("shared_artifacts"))
    return "\n".join(
        [
            f"Review OAG wavefront task `{task_id}` before handoff_pass.",
            "",
            "Decide exactly one verdict: approved, rejected, or needs_human_review.",
            "Use `oag-custom-reviewer` as the MVP reviewer role unless a narrower reviewer is explicitly assigned.",
            "Do not record handoff_pass unless the review verdict is approved and the rationale is concrete.",
            "",
            f"- run_id: {run.run_id}",
            f"- ip_dir: {display_path(run.ip_dir)}",
            f"- phase: {phase}",
            f"- producer_agent_type: {agent_type}",
            f"- receipt_path: {receipt or '<missing>'}",
            f"- owned_paths: {write_paths}",
            "",
            "Required review output:",
            "- decision_type",
            "- verdict",
            "- rationale.summary",
            "- rationale.checked_against",
            "- rationale.preserved when approving",
            "- rationale.blockers with required_action when rejecting or routing to human review",
        ]
    )


def cmd_next(args: argparse.Namespace) -> JsonObject:
    run = _run(args.ip_dir, args.run_id)
    pending = _review_pending_tasks(run)
    if not pending:
        return result("pass", "oag_decision_next.v1", decision_available=False, next_prompt="")
    task = pending[0]
    return result(
        "pass",
        "oag_decision_next.v1",
        decision_available=True,
        task_id=str(task.get("task_id") or ""),
        next_prompt=_prompt_for_task(task, run),
    )


def cmd_should_continue(args: argparse.Namespace) -> JsonObject:
    next_result = cmd_next(args)
    should_continue = bool(next_result.get("decision_available"))
    return result(
        "pass",
        "oag_decision_should_continue.v1",
        should_continue=should_continue,
        reason="review_pending" if should_continue else "no_review_pending_decision",
        next_prompt=str(next_result.get("next_prompt") or ""),
        task_id=str(next_result.get("task_id") or ""),
    )


def cmd_record(args: argparse.Namespace) -> JsonObject:
    run = _run(args.ip_dir, args.run_id)
    decision_type = str(args.decision_type or "")
    if decision_type not in REVIEW_DECISION_TYPES:
        return result("fail", "oag_decision_record_result.v1", issues=[issue("DECISION_TYPE", f"invalid decision_type: {decision_type}")])
    blockers = normalize_list(args.blocker)
    verdict = str(args.verdict or "")
    if verdict == "approved" and blockers:
        return result("fail", "oag_decision_record_result.v1", issues=[issue("APPROVED_WITH_BLOCKERS", "approved decisions cannot include blockers")])
    if verdict == "rejected" and not blockers:
        return result("fail", "oag_decision_record_result.v1", issues=[issue("REJECTED_WITHOUT_BLOCKERS", "rejected decisions require at least one blocker")])
    now = utc_now()
    decision_id = str(args.decision_id or f"DEC_{_slug(decision_type).upper()}_{_slug(args.task_id).upper()}_{_slug(now)}")
    payload: JsonObject = {
        "schema_version": "oag_wavefront_decision.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "decision_id": decision_id,
        "decision_type": decision_type,
        "target": {
            "kind": "wavefront_task",
            "run_id": run.run_id,
            "task_id": str(args.task_id),
        },
        "verdict": verdict,
        "rationale": {
            "summary": str(args.summary or ""),
            "checked_against": normalize_list(args.checked_against),
            "preserved": normalize_list(args.preserved),
            "blockers": blockers,
        },
        "reviewer": {
            "kind": str(args.reviewer_kind or "ai"),
            "id": str(args.reviewer_id or "claude"),
        },
        "unlocks": {
            "wavefront_status": str(args.wavefront_status or ("handoff_pass" if verdict == "approved" else "")),
            "barrier_outputs": normalize_list(args.barrier_output),
        },
        "created_at": now,
    }
    issues = [
        issue(f"DECISION_SCHEMA_{item['code']}", item["message"], item["path"])
        for item in validate_named_schema("oag_wavefront_decision.schema.json", payload)
    ]
    if issues:
        return result("fail", "oag_decision_record_result.v1", issues=issues)
    path = _decision_path(run.ip_dir, decision_id)
    write_json(path, payload)
    return result(
        "pass",
        "oag_decision_record_result.v1",
        decision_id=decision_id,
        path=display_path(path),
        decision=payload,
        issues=[],
    )


def print_result(payload: JsonObject, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload.get("status") == "pass":
        if payload.get("next_prompt"):
            print(payload["next_prompt"])
        elif payload.get("path"):
            print(payload["path"])
        else:
            print(f"PASS {payload.get('schema_version')}")
    else:
        print(f"FAIL {payload.get('schema_version')}", file=sys.stderr)
        for item in payload.get("issues", []):
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and route OAG decision-first review records.")
    sub = parser.add_subparsers(dest="command", required=True)

    next_cmd = sub.add_parser("next", help="Return the next review decision prompt.")
    next_cmd.add_argument("--ip-dir", required=True)
    next_cmd.add_argument("--run-id", required=True)
    next_cmd.add_argument("--json", action="store_true")

    should = sub.add_parser("should-continue", help="Return whether a stop hook should continue for review decisions.")
    should.add_argument("--ip-dir", required=True)
    should.add_argument("--run-id", required=True)
    should.add_argument("--json", action="store_true")

    record = sub.add_parser("record", help="Write an oag_wavefront_decision.v1 record.")
    record.add_argument("--ip-dir", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--task-id", required=True)
    record.add_argument("--decision-type", required=True)
    record.add_argument("--decision-id", default="")
    record.add_argument("--verdict", required=True, choices=["approved", "rejected", "needs_human_review", "needs_clarification", "needs_decision", "blocked", "inconclusive", "waived"])
    record.add_argument("--summary", required=True)
    record.add_argument("--checked-against", action="append", required=True)
    record.add_argument("--preserved", action="append")
    record.add_argument("--blocker", action="append")
    record.add_argument("--barrier-output", action="append")
    record.add_argument("--wavefront-status", default="")
    record.add_argument("--reviewer-kind", default="ai")
    record.add_argument("--reviewer-id", default="claude")
    record.add_argument("--json", action="store_true")
    return parser


def dispatch(args: argparse.Namespace) -> JsonObject:
    if args.command == "next":
        return cmd_next(args)
    if args.command == "should-continue":
        return cmd_should_continue(args)
    return cmd_record(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = dispatch(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = result("fail", "oag_decision_harness_error.v1", issues=[issue("EXCEPTION", str(exc))])
    print_result(payload, bool(getattr(args, "json", False)))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
