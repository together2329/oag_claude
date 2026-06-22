#!/usr/bin/env python3
"""Claude Code SubagentStop hook for OAG evidence-producing subagents.

This hook does not spawn subagents. Claude Code does that through
multi_agent_v1.spawn_agent. The hook only checks that evidence-producing OAG
subagents end with a durable receipt line:

  OAG_EVIDENCE_RECORDED: <relative-path>

The path must point to a non-empty file inside either:
  - <ip>/knowledge/subagents/
  - knowledge/subagents/

JSON receipts must match the stable oag_subagent_receipt.v1 fields and pass
the dispatch/receipt/path-scope verifier.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / "scripts" / "oag_dispatch.py"
CACHE_PATH = Path(os.environ.get("OAG_SUBAGENT_GATE_CACHE") or ROOT / ".cache" / "subagent_oag_gate.json")
MAX_ATTEMPTS = 3
RECEIPT_RE = re.compile(r"OAG_EVIDENCE_RECORDED:\s*(\S+)")
REQUIRED_RECEIPT_FIELDS = {
    "schema_version",
    "product_name",
    "internal_gateway",
    "role_name",
    "dispatch_id",
    "dispatch_path",
    "shard_scope",
    "stage",
    "status",
    "owned_obligations",
    "contracts",
    "allowed_write_paths",
    "changed_paths",
    "generated_side_effects",
    "evidence_outputs",
    "may_claim_complete",
    "created_at",
}
RECEIPT_STATUSES = {"HANDOFF_PASS", "STATIC_HANDOFF_PASS", "RTL_HANDOFF_PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"}
CONTEXT_PRESSURE_MARKERS = (
    "context compacted",
    "context_length_exceeded",
    "skill descriptions were shortened",
    "context_too_large",
    "claude ran out of room in the model's context window",
    "your input exceeds the context window",
    "long threads and multiple compactions",
)


def read_payload() -> dict:
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


def read_cache() -> dict:
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "oag_subagent_gate_cache.v1", "entries": {}}
    return payload if isinstance(payload, dict) else {"schema_version": "oag_subagent_gate_cache.v1", "entries": {}}


def write_cache(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception:
        return


def cache_key(payload: dict) -> str:
    parts = [
        str(payload.get("cwd") or ""),
        str(payload.get("session_id") or ""),
        str(payload.get("agent_id") or ""),
        str(payload.get("agent_type") or ""),
    ]
    return hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()


def attempt_allowed(payload: dict) -> bool:
    cache = read_cache()
    entries = cache.setdefault("entries", {})
    if not isinstance(entries, dict):
        cache["entries"] = entries = {}
    key = cache_key(payload)
    entry = entries.get(key)
    if not isinstance(entry, dict):
        entry = {"attempts": 0}
        entries[key] = entry
    attempts = int(entry.get("attempts") or 0) + 1
    entry["attempts"] = attempts
    entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_cache(cache)
    return attempts <= MAX_ATTEMPTS


def clear_attempt(payload: dict) -> None:
    cache = read_cache()
    entries = cache.get("entries")
    if isinstance(entries, dict):
        entries.pop(cache_key(payload), None)
        write_cache(cache)


def transcript_has_context_pressure(path: str) -> bool:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False
    return any(marker in text for marker in CONTEXT_PRESSURE_MARKERS)


def is_allowed_receipt_path(base: Path, receipt: Path) -> bool:
    try:
        relative = receipt.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == "knowledge" and parts[1] == "subagents":
        return True
    if len(parts) >= 3 and parts[1] == "knowledge" and parts[2] == "subagents":
        return True
    return False


def dispatch_verify(cwd: Path, receipt: Path, payload: dict) -> bool:
    dispatch_path = payload.get("dispatch_path")
    if not isinstance(dispatch_path, str) or not dispatch_path.strip() or Path(dispatch_path).is_absolute():
        return False
    dispatch = (cwd / dispatch_path).resolve()
    try:
        dispatch.relative_to(cwd.resolve())
    except ValueError:
        return False
    if not dispatch.is_file():
        return False
    proc = subprocess.run(
        [
            sys.executable,
            str(DISPATCH),
            "verify",
            "--dispatch",
            str(dispatch),
            "--receipt",
            str(receipt),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd,
        env={**os.environ, "OAG_PROJECT_ROOT": str(cwd)},
    )
    if proc.returncode != 0:
        return False
    try:
        result = json.loads(proc.stdout)
    except Exception:
        return False
    return isinstance(result, dict) and result.get("status") == "pass"


def valid_receipt_payload(cwd: Path, receipt: Path) -> bool:
    if receipt.suffix.lower() != ".json":
        return False
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    if REQUIRED_RECEIPT_FIELDS - set(payload):
        return False
    if payload.get("schema_version") != "oag_subagent_receipt.v1":
        return False
    if payload.get("product_name") != "IP Dev Agent":
        return False
    if payload.get("internal_gateway") != "Ontology Agent Gateway":
        return False
    if payload.get("may_claim_complete") is not False:
        return False
    if payload.get("status") not in RECEIPT_STATUSES:
        return False
    for field in (
        "owned_obligations",
        "contracts",
        "allowed_write_paths",
        "changed_paths",
        "generated_side_effects",
        "evidence_outputs",
    ):
        if not isinstance(payload.get(field), list):
            return False
    return dispatch_verify(cwd, receipt, payload)


def valid_receipt(payload: dict) -> bool:
    message = str(payload.get("last_assistant_message") or "")
    match = RECEIPT_RE.search(message)
    if not match:
        return False
    raw_path = match.group(1)
    if not raw_path or Path(raw_path).is_absolute():
        return False
    cwd = Path(str(payload.get("cwd") or ".")).expanduser().resolve()
    receipt = (cwd / raw_path).resolve()
    if not is_allowed_receipt_path(cwd, receipt):
        return False
    try:
        if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size <= 0:
            return False
    except Exception:
        return False
    return valid_receipt_payload(cwd, receipt)


def directive(payload: dict) -> str:
    agent_type = payload.get("agent_type") or "oag-subagent"
    return (
        f"{agent_type} stopped without a valid OAG evidence receipt.\n\n"
        "Before stopping, write a non-empty receipt JSON file under:\n"
        "- <ip>/knowledge/subagents/\n\n"
        "Then make the final line exactly:\n"
        "OAG_EVIDENCE_RECORDED: <relative-path>\n\n"
        "The receipt must name dispatch_id, dispatch_path, shard scope, changed_paths, "
        "generated_side_effects, commands or artifacts, ROCEV links, blockers, and whether "
        "the bounded handoff result is HANDOFF_PASS, STATIC_HANDOFF_PASS, RTL_HANDOFF_PASS, "
        "FAIL, BLOCKED, or INCONCLUSIVE. JSON receipts must use "
        "schema_version=oag_subagent_receipt.v1, may_claim_complete=false, and must pass "
        ".claude/scripts/oag_dispatch.py verify. Do not claim final completion."
    )


def main() -> int:
    payload = read_payload()
    if payload.get("hook_event_name") != "SubagentStop":
        return 0
    if not str(payload.get("agent_type") or "").startswith("oag-"):
        return 0
    if transcript_has_context_pressure(str(payload.get("transcript_path") or "")):
        return 0
    if valid_receipt(payload):
        clear_attempt(payload)
        return 0
    if attempt_allowed(payload):
        print(json.dumps({"decision": "block", "reason": directive(payload)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
