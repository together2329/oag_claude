#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: remind agents to persist interview drafts.

The hook does not invent facts from a chat transcript. It only injects a compact
draft instruction when a requirement/interview prompt is under explicit context
pressure.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from oag_hook_utils import hook_additional_context, prompt_text, read_payload, target_ip_dirs


def _pressure_value(payload: dict[str, Any]) -> str:
    for key in ("context_pressure", "contextPressure", "context_usage", "contextUsage"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, (int, float)):
            return str(value)
    return os.environ.get("OAG_CONTEXT_PRESSURE") or os.environ.get("OAG_CONTEXT_USAGE") or ""


def _is_high_pressure(value: str) -> bool:
    raw = str(value or "").strip().lower().rstrip("%")
    if raw in {"high", "critical", "compact", "compaction", "near_limit"}:
        return True
    if not raw:
        return False
    try:
        number = float(raw)
    except ValueError:
        return False
    return number >= 70 if number > 1 else number >= 0.70


def _is_interview_prompt(text: str) -> bool:
    lower = text.lower()
    return bool(re.search(r"\b(req|requirement|requirements|interview|locked truth|deep interview)\b", lower))


def main() -> int:
    payload = read_payload()
    prompt = prompt_text(payload)
    pressure = _pressure_value(payload)
    if not (_is_high_pressure(pressure) and _is_interview_prompt(prompt)):
        return 0
    targets = target_ip_dirs(payload, require_signal=False)
    if not targets:
        return 0
    lines = [
        "=== OAG DRAFT PRESSURE GUARD ===",
        "Context pressure is high during requirement/interview work.",
        "Before continuing, persist the current interview state with oag.draft.",
        "",
        "Required draft payload:",
        "- summary: concise state of the interview",
        "- facts: confirmed facts only",
        "- decisions: explicit user decisions only",
        "- assumptions: unresolved assumptions",
        "- open_questions: remaining questions",
        "",
        "Do not promote this draft to locked truth until a human explicitly confirms it.",
    ]
    for ip in targets:
        lines.append(
            "Command: python3 .claude/scripts/oag_cli.py call --json "
            + json.dumps(
                {
                    "tool": "oag.draft",
                    "arguments": {
                        "ip_dir": str(ip),
                        "stage": "req",
                        "intent": "context pressure interview checkpoint",
                        "title": "Context pressure interview draft",
                        "summary": "<summarize confirmed interview state>",
                        "facts": ["<confirmed fact>"],
                        "open_questions": ["<open question>"],
                    },
                },
                ensure_ascii=False,
            )
        )
    lines.append("=== END OAG DRAFT PRESSURE GUARD ===")
    print(json.dumps(hook_additional_context("\n".join(lines)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
