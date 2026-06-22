#!/usr/bin/env python3
"""Claude Code SubagentStart hook for OAG native subagents.

This hook does not spawn subagents. Claude Code does that natively. The hook records
that an OAG child thread started and injects the minimum OAG work contract the
child must follow before the SubagentStop receipt gate runs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
START_LOG = Path(os.environ.get("OAG_SUBAGENT_START_CACHE") or ROOT / ".cache" / "subagent_oag_starts.jsonl")


def read_payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def append_start_event(payload: dict[str, Any]) -> None:
    event = {
        "schema_version": "oag_subagent_start_event.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_type": str(payload.get("agent_type") or ""),
        "agent_id": str(payload.get("agent_id") or ""),
        "session_id": str(payload.get("session_id") or ""),
        "cwd": str(payload.get("cwd") or ""),
        "model": str(payload.get("model") or ""),
        "permission_mode": str(payload.get("permission_mode") or ""),
    }
    try:
        START_LOG.parent.mkdir(parents=True, exist_ok=True)
        with START_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception:
        return


def additional_context(agent_type: str) -> dict[str, Any]:
    text = f"""OAG SUBAGENT START CONTRACT

You are a native Claude Code OAG subagent: {agent_type}.

Before acting, verify your assignment is self-contained and includes TASK,
DELIVERABLE, SCOPE, VERIFY, dispatch_id, dispatch_path, allowed write paths,
allowed tool side effects, and required evidence output. If required scope,
dispatch, or evidence instructions are missing, return BLOCKED with the missing
field instead of guessing.

Stay inside your assigned shard. Do not manually edit protected truth,
generated ontology files, .claude files, scripts, or unrelated paths. If your
assignment explicitly allows oag.compile, it may refresh
<ip>/ontology/generated/* as generated tool output; report those generated side
effects separately from owned changed paths and do not claim ownership of them.

Short IP intake guard: if your assignment is based only on a short new-IP
request such as "I need mctp rx ip" and does not include confirmed scope or a
concrete spec, do not implement, enrich locked truth, or edit canonical
ontology. Return only draft requirement questions, assumptions, and blockers.
Protocol IP scope must be explicit for spec version, transport boundary,
interfaces, single-packet versus multi-packet support, buffering/backpressure,
filtering/addressing, and error/drop/status policy.

Scope lock guard: implementation, validation, gate-review, and closure
assignments require <ip>/ontology/scope_lock.json state=locked. If the lock is
missing or draft, return BLOCKED and do not edit RTL, TB, canonical ontology,
tests, filelists, or signoff evidence.

Use HANDOFF_PASS, STATIC_HANDOFF_PASS, or RTL_HANDOFF_PASS for a bounded
successful handoff. Do not use PASS, COMPLETE, DONE, SIGNOFF, RELEASED, or
CLOSED to describe the IP.

Before stopping, write a non-empty OAG subagent receipt under
<ip>/knowledge/subagents/. The receipt must include dispatch_id, dispatch_path,
changed_paths, generated_side_effects, and may_claim_complete=false. End with:
OAG_EVIDENCE_RECORDED: <relative-path>
"""
    return {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": text,
        }
    }


def main() -> int:
    payload = read_payload()
    if payload.get("hook_event_name") != "SubagentStart":
        return 0
    agent_type = str(payload.get("agent_type") or "")
    if not agent_type.startswith("oag-"):
        return 0
    append_start_event(payload)
    print(json.dumps(additional_context(agent_type), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
