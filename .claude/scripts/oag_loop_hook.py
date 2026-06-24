#!/usr/bin/env python3
"""Boundary-aware OAG loop hook decision adapter."""

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
from oag_loop_core import loop_decision_from_plan, loop_policy_storage, resolve_loop_policy  # noqa: E402


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


def _planner_error(ip: Path, run_id: str, errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "oag_loop_hook_decision.v1",
        "decision": "stop",
        "reason": "planner_error",
        "ip": ip.name,
        "run_id": run_id,
        "errors": errors,
        "loop_policy": {},
        "recommended_batch": None,
    }


def decide(args: argparse.Namespace) -> dict[str, Any]:
    ip = Path(args.ip_dir).resolve()
    run_id = str(args.run_id or "")
    policy = resolve_loop_policy(ip, _policy_args(args), force_active=True)
    call = {
        "tool": "oag.run.next",
        "arguments": {
            "ip_dir": str(ip),
            "run_id": run_id,
            "loop_policy": loop_policy_storage(policy),
        },
    }
    try:
        response = oag_cli.dispatch_call(call)
    except Exception as exc:
        return _planner_error(ip, run_id, [str(exc)])
    if not response.get("ok"):
        return _planner_error(ip, run_id, [str(item) for item in response.get("errors") or []])
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
    decision.update(
        {
            "ip": ip.name,
            "run_id": result.get("run_id") or run_id,
            "status": result.get("status"),
            "prompt_block": result.get("prompt_block") or "",
        }
    )
    return decision


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = decide(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload.get("reason") != "planner_error" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
