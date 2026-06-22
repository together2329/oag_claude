#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: enforce native-only subagent requests."""

from __future__ import annotations

import json
import re
from pathlib import Path

from oag_hook_utils import hook_additional_context, prompt_text, read_payload


GUARD_MARKER = "NATIVE CODEX SUBAGENT GUARD"
SUBAGENT_REQUEST_RE = re.compile(
    r"(?<![A-Za-z0-9_-])("
    r"sub\s*agent|subagent|sub-agent|"
    r"spawn[_\s-]*agent|"
    r"multi[_\s-]*agent(?:_v1)?|"
    r"parallel\s+agents?|"
    r"agent\s+per|"
    r"서브\s*에이전트"
    r")(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)


def transcript_already_has_guard(payload: dict) -> bool:
    transcript_path = str(payload.get("transcript_path") or "").strip()
    if not transcript_path:
        return False
    try:
        raw = Path(transcript_path).read_bytes()
    except Exception:
        return False
    tail = raw[-512_000:].decode("utf-8", errors="ignore")
    for line in tail.splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        hook_output = item.get("hookSpecificOutput")
        if not isinstance(hook_output, dict):
            continue
        context = hook_output.get("additionalContext")
        if isinstance(context, str) and GUARD_MARKER in context:
            return True
    return False


def guard_text() -> str:
    return "\n".join(
        [
            GUARD_MARKER,
            "",
            "The user requested subagent or parallel-agent work. Use native Claude Code subagents only.",
            "Use `multi_agent_v1.spawn_agent` where the current surface exposes it, or the equivalent Claude Code CLI/App native `spawn_agent` collaboration event.",
            "Do not treat missing direct `multi_agent_v1` namespace visibility as failure; Claude Code CLI/App may expose native spawning only as an internal `spawn_agent` collaboration event.",
            "Do not decide native-spawn availability from the visible callable tool namespace alone.",
            "For Claude Code CLI/App probes, explicitly request the native `spawn_agent` collaboration event even when no `multi_agent_v1` tool namespace is visible.",
            "For a subagent capability probe, first attempt a minimal read-only native spawn, wait for the child, and then report the result.",
            "Do not answer BLOCKED or report an observed native-spawn blocker before an actual `spawn_agent` attempt fails or the runtime returns a spawn-unavailable error.",
            "Do not run `omo run --agent`, `./.claude/bin/omo run`, Python scripts, shell wrappers, or manual explorer-style role-play as a substitute.",
            "Do not try to lazy-load native subagent tools through tool search or MCP; native subagents are a Claude Code runtime collaboration capability.",
            "Only if an actual native spawn attempt fails or the active Claude Code runtime reports that spawning is unavailable, stop and report the observed native-spawn blocker.",
            "Continue with a non-native fallback only if the user explicitly waives the native-subagent requirement.",
        ]
    )


def main() -> int:
    payload = read_payload()
    prompt = prompt_text(payload)
    if not SUBAGENT_REQUEST_RE.search(prompt):
        return 0
    if transcript_already_has_guard(payload):
        return 0
    print(json.dumps(hook_additional_context(guard_text()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
