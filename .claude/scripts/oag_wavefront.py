#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from oag_wavefront_core import JsonObject, WavefrontRun, issue, resolve_project_path, resolve_read_path, result
from oag_wavefront_graph import VALID_STATUSES, normalize_list
from oag_wavefront_ops import ClaimRequest, PlanRequest, claim_wavefront_task, create_wavefront_run, load_wavefront_run_status
from oag_wavefront_records import RecordRequest, close_wavefront_run, ready_wavefront_tasks, record_wavefront_task, verify_wavefront_run
from oag_wavefront_templates import load_template


def _run(ip_dir: str, run_id: str) -> WavefrontRun:
    return WavefrontRun(resolve_project_path(ip_dir), run_id)


def cmd_plan(args: argparse.Namespace) -> JsonObject:
    run = _run(args.ip_dir, args.run_id)
    template = load_template(resolve_read_path(args.template))
    return create_wavefront_run(
        PlanRequest(
            run=run,
            raw_tasks=template["tasks"],
            template=str(args.template),
            barrier_tokens=normalize_list(args.barrier),
        )
    )


def cmd_ready(args: argparse.Namespace) -> JsonObject:
    return ready_wavefront_tasks(_run(args.ip_dir, args.run_id))


def cmd_status(args: argparse.Namespace) -> JsonObject:
    return load_wavefront_run_status(_run(args.ip_dir, args.run_id), "oag_wavefront_status_result.v1")


def cmd_claim(args: argparse.Namespace) -> JsonObject:
    return claim_wavefront_task(
        ClaimRequest(
            run=_run(args.ip_dir, args.run_id),
            task_id=args.task_id,
            claimed_by=args.claimed_by or "",
            dispatch_id=args.dispatch_id or "",
        )
    )


def cmd_record(args: argparse.Namespace) -> JsonObject:
    return record_wavefront_task(
        RecordRequest(
            run=_run(args.ip_dir, args.run_id),
            task_id=args.task_id,
            status=args.status,
            barrier_outputs=normalize_list(args.barrier_output),
            receipt=args.receipt or "",
            decision=args.decision or "",
        )
    )


def cmd_verify(args: argparse.Namespace) -> JsonObject:
    return verify_wavefront_run(_run(args.ip_dir, args.run_id))


def cmd_close(args: argparse.Namespace) -> JsonObject:
    return close_wavefront_run(_run(args.ip_dir, args.run_id), bool(args.allow_open))


def print_result(payload: JsonObject, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload.get("status") == "pass":
        print(f"PASS {payload.get('schema_version')}")
    else:
        print(f"FAIL {payload.get('schema_version')}", file=sys.stderr)
        for item in payload.get("issues", []):
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and gate OAG dependency-aware wavefront work.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Create a wavefront task graph from a template.")
    plan.add_argument("--ip-dir", required=True)
    plan.add_argument("--run-id", required=True)
    plan.add_argument("--template", required=True)
    plan.add_argument("--barrier", action="append")
    plan.add_argument("--json", action="store_true")

    ready = sub.add_parser("ready", help="List dependency-satisfied tasks.")
    ready.add_argument("--ip-dir", required=True)
    ready.add_argument("--run-id", required=True)
    ready.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Summarize a wavefront run.")
    status.add_argument("--ip-dir", required=True)
    status.add_argument("--run-id", required=True)
    status.add_argument("--json", action="store_true")

    claim = sub.add_parser("claim", help="Claim a ready task and create ownership locks.")
    claim.add_argument("--ip-dir", required=True)
    claim.add_argument("--run-id", required=True)
    claim.add_argument("--task-id", required=True)
    claim.add_argument("--claimed-by", default="")
    claim.add_argument("--dispatch-id", default="")
    claim.add_argument("--json", action="store_true")

    record = sub.add_parser("record", help="Record bounded worker status and barrier outputs.")
    record.add_argument("--ip-dir", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--task-id", required=True)
    record.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    record.add_argument("--barrier-output", action="append")
    record.add_argument("--receipt", default="")
    record.add_argument("--decision", default="", help="Approved oag_wavefront_decision.v1 JSON required for handoff_pass.")
    record.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify", help="Verify graph, lock, and barrier invariants.")
    verify.add_argument("--ip-dir", required=True)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--json", action="store_true")

    close = sub.add_parser("close", help="Close a wavefront run after all active ownership is released.")
    close.add_argument("--ip-dir", required=True)
    close.add_argument("--run-id", required=True)
    close.add_argument("--allow-open", action="store_true")
    close.add_argument("--json", action="store_true")
    return parser


def dispatch(args: argparse.Namespace) -> JsonObject:
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "ready":
        return cmd_ready(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "claim":
        return cmd_claim(args)
    if args.command == "record":
        return cmd_record(args)
    if args.command == "verify":
        return cmd_verify(args)
    return cmd_close(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = dispatch(args)
    except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
        payload = result("fail", "oag_wavefront_error.v1", issues=[issue("EXCEPTION", str(exc))])
    print_result(payload, bool(getattr(args, "json", False)))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
