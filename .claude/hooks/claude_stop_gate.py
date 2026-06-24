#!/usr/bin/env python3
"""Claude Code Stop hook: block incomplete OAG runs and main-agent locked writes.

Output contract (Claude Code Stop hook):
  - print {"decision": "block", "reason": "<next-action prompt>"} on stdout to block the stop
  - exit 0 ALWAYS (a hook must never break the turn)

Target resolution order:
  1. hook stdin payload: {"ip_dir": "...", "run_id": "..."}
  2. environment: OAG_IP_DIR / OAG_RUN_ID
  3. fallback scan: <project>/*/ontology/runs/active_run.json

For each target it calls oag.stop_check. If a run wants to continue, it blocks
the stop with that run's prompt block. It also runs the main-write gate: after
scope lock, RTL/TB/sim/lint/coverage/formal/SDC/signoff/filelist writes require
native OAG subagent dispatch + receipt or a human waiver. Human-decision states
stay silent because the agent has no further local action to take. Repeated
identical blocks are also capped so a stale run-loop prompt cannot burn the
whole turn.

This is the Claude Code-hook-shaped sibling of scripts-driven oag.stop_check; the older
hooks/oag_stop_check.py stays as a manual/example runner.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .claude/
PROJECT = ROOT.parent  # project root that holds the IP folders
CACHE_PATH = Path(os.environ.get("OAG_STOP_GATE_CACHE") or ROOT / ".cache" / "stop_gate.json")
sys.path.insert(0, str(ROOT / "scripts"))
INACTIVE_RUN_STATUSES = {"complete", "parked", "needs_human"}

import oag_cli  # noqa: E402
import oag_main_write_gate  # noqa: E402


def _read_cache() -> dict:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "oag_stop_gate_cache.v1", "entries": {}}
    return data if isinstance(data, dict) else {"schema_version": "oag_stop_gate_cache.v1", "entries": {}}


def _write_cache(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception:
        return


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _max_block_repeats(result: dict) -> int:
    if os.environ.get("OAG_STOP_GATE_MAX_BLOCK_REPEATS") is not None:
        return max(_safe_int(os.environ.get("OAG_STOP_GATE_MAX_BLOCK_REPEATS"), 3), 0)
    policy = result.get("policy") if isinstance(result.get("policy"), dict) else {}
    if "stop_hook_max_repeats" in policy:
        return max(_safe_int(policy.get("stop_hook_max_repeats"), 3), 0)
    return 3


def _block_allowed(cache: dict, *, key: str, digest: str, max_repeats: int) -> bool:
    if max_repeats <= 0:
        return False
    entries = cache.setdefault("entries", {})
    if not isinstance(entries, dict):
        cache["entries"] = entries = {}
    entry = entries.get(key)
    if not isinstance(entry, dict) or entry.get("digest") != digest:
        entries[key] = {
            "digest": digest,
            "count": 1,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return True
    count = int(entry.get("count") or 0) + 1
    entry["count"] = count
    entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return count <= max_repeats


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _project_path(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT / path
    return str(path.resolve())


def _target_runs(payload: dict) -> list[dict[str, str]]:
    payload_ip = str(payload.get("ip_dir") or "").strip()
    env_ip = os.environ.get("OAG_IP_DIR", "").strip()
    payload_run = str(payload.get("run_id") or "").strip()
    env_run = os.environ.get("OAG_RUN_ID", "").strip()
    run_id = payload_run or env_run

    explicit_ip = payload_ip or env_ip
    if explicit_ip:
        return [{"ip_dir": _project_path(explicit_ip), "run_id": run_id}]

    found: list[dict[str, str]] = []
    for active in PROJECT.glob("*/ontology/runs/active_run.json"):
        try:
            data = json.loads(active.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        active_run = str(data.get("run_id") or "") if isinstance(data, dict) else ""
        status = str(data.get("status") or "") if isinstance(data, dict) else ""
        if not status and active_run:
            state_path = active.parents[2] / "ontology" / "runs" / active_run / "run_state.json"
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                state = {}
            status = str(state.get("status") or "") if isinstance(state, dict) else ""
        if status in INACTIVE_RUN_STATUSES:
            continue
        if run_id and active_run != run_id:
            continue
        # <ip>/ontology/runs/active_run.json -> <ip>
        found.append({"ip_dir": str(active.parents[2]), "run_id": active_run})
    return found


def _dedupe_targets(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for target in targets:
        key = (target.get("ip_dir", ""), target.get("run_id", ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        unique.append(target)
    return unique


def _recent_context_targets() -> list[dict[str, str]]:
    cache_path = ROOT / ".cache" / "context_inject.json"
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    target = data.get("last_target")
    if not isinstance(target, dict):
        return []
    ip_dir = str(target.get("ip_dir") or "").strip()
    if not ip_dir:
        return []
    path = Path(ip_dir).expanduser()
    if not path.is_absolute():
        path = PROJECT / path
    if not path.is_dir():
        return []
    return [{"ip_dir": str(path.resolve()), "run_id": ""}]


def _stop_check(target: dict[str, str]) -> dict:
    args = {"ip_dir": target["ip_dir"]}
    if target.get("run_id"):
        args["run_id"] = target["run_id"]
    response = oag_cli.dispatch_call({"tool": "oag.stop_check", "arguments": args})
    if not isinstance(response, dict) or not response.get("ok"):
        return {}
    result = response.get("result")
    return result if isinstance(result, dict) else {}


def _main_write_gate(target: dict[str, str]) -> dict:
    return oag_main_write_gate.check_ip(Path(target["ip_dir"]))


def main() -> int:
    payload = _read_payload()
    cache = _read_cache()
    cache_changed = False
    blocks: list[str] = []
    targets = _dedupe_targets(_target_runs(payload))
    for target in targets:
        try:
            result = _stop_check(target)
        except Exception:
            continue  # fail open: a hook must never break the turn
        if result.get("reason") == "needs_human_decision":
            continue
        should_continue = result.get("should_continue") is True
        if not should_continue:
            continue
        reason_code = str(result.get("reason") or "")
        name = result.get("ip") or Path(target["ip_dir"]).name
        prompt = str(result.get("prompt_block") or "").strip()
        header = f"[OAG:{name}] run incomplete ({reason_code})."
        block = f"{header}\n{prompt}".strip()
        key = f"{Path(target['ip_dir']).resolve()}::{target.get('run_id') or result.get('run_id') or ''}"
        if _block_allowed(cache, key=key, digest=_digest(block), max_repeats=_max_block_repeats(result)):
            blocks.append(block)
        cache_changed = True
    write_gate_targets = targets or _recent_context_targets()
    for target in _dedupe_targets(write_gate_targets):
        try:
            result = _main_write_gate(target)
        except Exception:
            continue
        if result.get("status") != "fail":
            continue
        name = result.get("ip") or Path(target["ip_dir"]).name
        lines = [f"[OAG:{name}] locked implementation write requires native subagent evidence."]
        for item in result.get("issues", [])[:8]:
            if isinstance(item, dict):
                path = f" ({item.get('path')})" if item.get("path") else ""
                lines.append(f"- {item.get('code')}: {item.get('message')}{path}")
        lines.extend(
            [
                "Required next step: create an OAG dispatch and spawn the owning native subagent,",
                "or record a human main-agent subagent waiver before stopping.",
            ]
        )
        block = "\n".join(lines)
        key = f"{Path(target['ip_dir']).resolve()}::main-write-gate"
        if _block_allowed(cache, key=key, digest=_digest(block), max_repeats=3):
            blocks.append(block)
        cache_changed = True

    if blocks:
        reason = (
            "Active OAG run(s) still require closure. "
            "Do not stop until the prompt below is handled:\n\n" + "\n\n".join(blocks)
        )
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    if cache_changed:
        _write_cache(cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
