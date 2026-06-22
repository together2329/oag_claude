#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: inject OAG mode directive on exact `oag` trigger."""

from __future__ import annotations

import json
import re
from pathlib import Path

from oag_hook_utils import hook_additional_context, prompt_text, read_payload


ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE_PATH = ROOT / "oag" / "oag-mode-directive.md"
TRIGGER_RE = re.compile(r"(?<![A-Za-z0-9_-])oag(?![A-Za-z0-9_-])", re.IGNORECASE)
DIRECTIVE_MARKER = "OAG MODE ENABLED!"


def read_directive() -> str:
    try:
        text = DIRECTIVE_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        text = ""
    if text:
        return text
    return "\n".join(
        [
            "OAG MODE ENABLED!",
            "Use Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision.",
            "Short new-IP requests enter requirement interview mode; do not edit locked truth, canonical ontology, RTL, TB, or tests until scope is confirmed.",
            "Check oag.lock_status before implementation; no lock, no RTL, no TB, no closure.",
            "Use multi_agent_v1.spawn_agent with fork_context=false for bounded native Claude Code subagent work.",
            "Final closure requires oag.check, oag_closure_check.py, and oag.decide with record_decision=true.",
        ]
    )


def transcript_already_has_directive(payload: dict) -> bool:
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
        if isinstance(context, str) and DIRECTIVE_MARKER in context:
            return True
    return False


def main() -> int:
    payload = read_payload()
    prompt = prompt_text(payload)
    if not TRIGGER_RE.search(prompt):
        return 0
    if transcript_already_has_directive(payload):
        return 0
    directive = read_directive()
    print(json.dumps(hook_additional_context(directive), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
