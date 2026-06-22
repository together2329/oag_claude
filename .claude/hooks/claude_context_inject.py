#!/usr/bin/env python3
"""Claude Code hook: inject compact OAG context before IP work.

The hook is intentionally fail-open. If it cannot infer an IP, it stays silent.
If it can infer an IP, it calls `oag.context` and adds the active run's persisted
next-action prompt without mutating run state. Identical context is deduped by a
durable content hash cache. PostCompact does not inject context directly because
Claude Code treats it as a stateless hook; instead it records a recovery marker that
the next UserPromptSubmit consumes to force one re-injection.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from oag_hook_utils import (
    INACTIVE_RUN_STATUSES,
    ROOT,
    first_text,
    hook_additional_context,
    infer_stage,
    parse_run_limit_command,
    prompt_text,
    read_payload,
    target_ip_dirs,
)

sys.path.insert(0, str(ROOT / "scripts"))

import oag_cli  # noqa: E402

CACHE_PATH = ROOT / ".cache" / "context_inject.json"
RECOVERY_KEY = "__post_compact_recovery__"


def _read_cache() -> dict[str, Any]:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "oag_context_inject_cache.v1", "entries": {}}
    return data if isinstance(data, dict) else {"schema_version": "oag_context_inject_cache.v1", "entries": {}}


def _write_cache(cache: dict[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception:
        return


def _cache_key(ip: Path, *, stage: str) -> str:
    return f"{ip.resolve()}::{stage or 'unknown'}"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _event_name(payload: dict[str, Any]) -> str:
    return first_text(payload, ("hook_event_name", "hookEventName", "hook_event", "hookEvent", "event")) or "UserPromptSubmit"


def _find_payload_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                return item
        for item in value.values():
            found = _find_payload_value(item, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_payload_value(item, keys)
            if found not in (None, ""):
                return found
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "force", "forced", "high"}


def _force_reinject(payload: dict[str, Any], hook_event: str) -> bool:
    if os.environ.get("OAG_FORCE_CONTEXT_INJECT") or os.environ.get("OAG_CONTEXT_RECOVERY"):
        return True
    lowered_event = hook_event.replace("_", "").replace("-", "").lower()
    if "postcompact" in lowered_event or "compact" in lowered_event:
        return True
    marker = _find_payload_value(
        payload,
        {
            "force_context_injection",
            "forceContextInjection",
            "context_compacted",
            "contextCompacted",
            "context_lost",
            "contextLost",
            "post_compact",
            "postCompact",
        },
    )
    if _truthy(marker):
        return True
    pressure = first_text(payload, ("context_pressure", "contextPressure", "context_usage", "contextUsage"))
    return str(pressure).strip().lower() in {"critical", "compacted", "lost"}


def _is_post_compact_event(hook_event: str) -> bool:
    normalized = hook_event.replace("_", "").replace("-", "").lower()
    return "postcompact" in normalized or normalized == "compact"


def _mark_recovery_pending(cache: dict[str, Any], *, hook_event: str) -> None:
    cache[RECOVERY_KEY] = {
        "hook_event": hook_event,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _has_recovery_pending(cache: dict[str, Any]) -> bool:
    return isinstance(cache.get(RECOVERY_KEY), dict)


def _clear_recovery_pending(cache: dict[str, Any]) -> None:
    cache.pop(RECOVERY_KEY, None)


def _cache_allows_injection(cache: dict[str, Any], key: str, digest: str, *, force: bool) -> bool:
    if force:
        return True
    entries = cache.get("entries")
    if not isinstance(entries, dict):
        return True
    entry = entries.get(key)
    return not isinstance(entry, dict) or entry.get("content_hash") != digest


def _remember_injection(cache: dict[str, Any], key: str, digest: str, *, hook_event: str) -> None:
    entries = cache.setdefault("entries", {})
    if not isinstance(entries, dict):
        cache["entries"] = entries = {}
    entries[key] = {
        "content_hash": digest,
        "hook_event": hook_event,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    ip_dir = key.rsplit("::", 1)[0]
    if ip_dir and Path(ip_dir).is_dir():
        cache["last_target"] = {
            "ip_dir": ip_dir,
            "hook_event": hook_event,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }


def _active_run_block(ip: Path) -> str:
    active_path = ip / "ontology" / "runs" / "active_run.json"
    if not active_path.is_file():
        return ""
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(active, dict):
        return ""
    if str(active.get("status") or "") in INACTIVE_RUN_STATUSES:
        return ""
    run_id = str(active.get("run_id") or "")
    if not run_id:
        return ""
    state_path = ip / "ontology" / "runs" / run_id / "run_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if not isinstance(state, dict):
        return ""
    if str(state.get("status") or "") in INACTIVE_RUN_STATUSES:
        return ""
    action = state.get("next_action") if isinstance(state.get("next_action"), dict) else {}
    block = str(action.get("prompt_block") or "").strip()
    if block:
        return block
    next_path = ip / "ontology" / "runs" / run_id / "next_action.json"
    try:
        next_action = json.loads(next_path.read_text(encoding="utf-8"))
    except Exception:
        next_action = {}
    if isinstance(next_action, dict):
        return str(next_action.get("prompt_block") or "").strip()
    return ""


def _context_for(ip: Path, *, stage: str, intent: str) -> str:
    response = oag_cli.dispatch_call(
        {
            "tool": "oag.context",
            "arguments": {
                "ip_dir": str(ip),
                "stage": stage,
                "intent": intent,
                "limit": 4,
            },
        }
    )
    if not isinstance(response, dict) or not response.get("ok"):
        return ""
    result = response.get("result")
    if not isinstance(result, dict):
        return ""
    return str(result.get("prompt_block") or "").strip()


def _configure_run_limit(ip: Path, *, limit: str) -> str:
    response = oag_cli.dispatch_call(
        {
            "tool": "oag.configure",
            "arguments": {
                "ip_dir": str(ip),
                "hook_auto_continue_until": limit,
                "actor": {"kind": "human", "id": os.environ.get("USER") or "owner", "surface": "chat"},
                "approval": {"kind": "human", "approved": True, "reason": "explicit short run-limit command"},
            },
        }
    )
    if not isinstance(response, dict) or not response.get("ok"):
        return ""
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    applied = str((result.get("updates") or {}).get("hook_auto_continue_until") or limit)
    return "\n".join(
        [
            "=== OAG RUN LIMIT CONFIGURED ===",
            f"ip={ip.name}",
            f"hook_auto_continue_until={applied}",
            "note=Stop hook will only auto-continue through this stage; later actions stay silent until explicitly requested.",
            "=== END OAG RUN LIMIT CONFIGURED ===",
        ]
    )


def main() -> int:
    payload = read_payload()
    prompt = prompt_text(payload)
    hook_event = _event_name(payload)
    cache = _read_cache()
    if _is_post_compact_event(hook_event):
        _mark_recovery_pending(cache, hook_event=hook_event)
        _write_cache(cache)
        return 0
    recovery_pending = _has_recovery_pending(cache)
    force = _force_reinject(payload, hook_event) or recovery_pending
    stage = str(payload.get("stage") or os.environ.get("OAG_STAGE") or infer_stage(prompt) or "")
    intent = str(payload.get("intent") or prompt[:240] or "claude prompt")
    blocks: list[str] = []
    injected: list[tuple[str, str]] = []
    run_limit = parse_run_limit_command(prompt)
    target_ips = target_ip_dirs(payload, require_signal=(not force and not bool(run_limit)))
    if run_limit:
        for ip in target_ips:
            try:
                configured = _configure_run_limit(ip, limit=run_limit)
            except Exception:
                configured = ""
            if configured:
                blocks.append(configured)
                injected.append((_cache_key(ip, stage=f"run-limit:{run_limit}"), _content_hash(configured)))
        if blocks:
            for key, digest in injected:
                _remember_injection(cache, key, digest, hook_event=hook_event)
            _write_cache(cache)
            print(json.dumps(hook_additional_context("\n\n".join(blocks), hook_event), ensure_ascii=False))
        return 0
    for ip in target_ips:
        try:
            context = _context_for(ip, stage=stage, intent=intent)
            active = _active_run_block(ip)
        except Exception:
            continue
        if not context and not active:
            continue
        parts = [f"=== OAG CONTEXT INJECTION ({ip.name}) ==="]
        if context:
            parts.append(context)
        if active:
            parts.append(active)
        parts.append("=== END OAG CONTEXT INJECTION ===")
        block = "\n".join(parts)
        key = _cache_key(ip, stage=stage)
        digest = _content_hash(block)
        if not _cache_allows_injection(cache, key, digest, force=force):
            continue
        blocks.append(block)
        injected.append((key, digest))

    if blocks:
        if recovery_pending:
            _clear_recovery_pending(cache)
        for key, digest in injected:
            _remember_injection(cache, key, digest, hook_event=hook_event)
        _write_cache(cache)
        print(json.dumps(hook_additional_context("\n\n".join(blocks), hook_event), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
