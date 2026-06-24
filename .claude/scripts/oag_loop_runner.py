#!/usr/bin/env python3
"""Bounded OAG loop runner wrapper for plan-only and dispatch-safe modes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import oag_cli  # noqa: E402
from oag_loop_core import loop_decision_from_plan, loop_policy_storage, resolve_loop_policy, write_loop_decision  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--run-id", default=os.environ.get("OAG_RUN_ID", ""))
    parser.add_argument("--until", default=None)
    parser.add_argument("--requirement", action="append", default=[])
    parser.add_argument("--obligation", action="append", default=[])
    parser.add_argument("--owner-module", action="append", default=[])
    parser.add_argument("--job-type", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=None)
    parser.add_argument("--mode", choices=("plan_only", "dispatch", "execute"), default=None)
    parser.add_argument("--write-decision", dest="write_decision", action="store_true", default=True)
    parser.add_argument("--no-write-decision", dest="write_decision", action="store_false")
    parser.add_argument("--json", action="store_true")
    return parser


def _policy_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "until": args.until,
        "requirement": args.requirement,
        "obligation": args.obligation,
        "owner_module": args.owner_module,
        "job_type": args.job_type,
        "limit": args.limit,
        "max_iterations": args.max_iterations,
        "mode": args.mode,
    }


def _run_next(ip: Path, run_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    response = oag_cli.dispatch_call(
        {
            "tool": "oag.run.next",
            "arguments": {
                "ip_dir": str(ip),
                "run_id": run_id,
                "loop_policy": loop_policy_storage(policy),
            },
        }
    )
    if not response.get("ok"):
        return {
            "schema_version": "oag_loop_runner.v1",
            "status": "failed",
            "decision": "stop",
            "reason": "planner_error",
            "errors": [str(item) for item in response.get("errors") or []],
            "loop_policy": loop_policy_storage(policy),
            "recommended_batch": None,
        }
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    plan = result.get("loop_plan") if isinstance(result.get("loop_plan"), dict) else {}
    if plan:
        decision = loop_decision_from_plan(plan)
    else:
        batch = result.get("next_batch") if isinstance(result.get("next_batch"), dict) else None
        decision = {
            "schema_version": "oag_loop_hook_decision.v1",
            "decision": "continue" if batch else "stop",
            "reason": "batch_available" if batch else str(result.get("loop_stop_reason") or "no_runnable_batch"),
            "loop_policy": result.get("loop_policy") if isinstance(result.get("loop_policy"), dict) else loop_policy_storage(policy),
            "recommended_batch": batch,
            "plan": {},
        }
    return {
        "schema_version": "oag_loop_runner.v1",
        "status": "pass",
        "run_id": result.get("run_id") or run_id,
        "planner_result": result,
        "decision": decision.get("decision"),
        "reason": decision.get("reason"),
        "loop_policy": decision.get("loop_policy") if isinstance(decision.get("loop_policy"), dict) else loop_policy_storage(policy),
        "recommended_batch": decision.get("recommended_batch") if isinstance(decision.get("recommended_batch"), dict) else None,
        "plan": decision.get("plan") if isinstance(decision.get("plan"), dict) else plan,
        "dispatch_command_candidates": result.get("dispatch_command_candidates")
        if isinstance(result.get("dispatch_command_candidates"), list)
        else [],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    ip = Path(args.ip_dir).resolve()
    run_id = str(args.run_id or "")
    policy = resolve_loop_policy(ip, _policy_args(args), force_active=True)
    mode = str(policy.get("mode") or "plan_only")
    result = _run_next(ip, run_id, policy)
    batch = result.get("recommended_batch") if isinstance(result.get("recommended_batch"), dict) else None
    if result.get("status") != "pass":
        payload = result
    elif not batch:
        payload = {**result, "mode": mode, "decision": "stop", "reason": result.get("reason") or "boundary_reached"}
    elif mode == "dispatch":
        payload = {**result, "mode": mode, "decision": "continue", "reason": "dispatch_ready"}
    elif mode == "execute":
        payload = {
            **result,
            "mode": mode,
            "decision": "stop",
            "reason": "execute_not_implemented",
            "execution_guard": {
                "can_execute": bool(batch.get("can_execute")),
                "job_type": str(batch.get("job_type") or ""),
                "message": "bounded runner does not execute RTL, TB, or record jobs in this release",
            },
        }
    else:
        payload = {**result, "mode": mode, "decision": "continue", "reason": "plan_available"}
    if args.write_decision and run_id:
        path = write_loop_decision(ip, run_id, payload)
        payload["loop_decision_path"] = str(path)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = run(args)
    except Exception as exc:
        payload = {
            "schema_version": "oag_loop_runner.v1",
            "status": "failed",
            "decision": "stop",
            "reason": "runner_error",
            "errors": [str(exc)],
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload.get("status") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
