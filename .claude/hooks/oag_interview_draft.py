#!/usr/bin/env python3
"""Requirement interview draft hook.

Input JSON may include:
  {
    "ip_dir": "example_ip",
    "stage": "req",
    "intent": "deep interview",
    "title": "Architecture interview round 1",
    "summary": "...",
    "facts": ["..."],
    "open_questions": ["..."],
    "context_pressure": "high"
  }

The hook saves a draft when draft content is present. If context pressure is
high/critical during an interview and no draft content is provided, it returns a
non-zero guard result so the caller can summarize first.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import oag_cli  # noqa: E402


def _payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
    return {
        "ip_dir": data.get("ip_dir") or os.environ.get("OAG_IP_DIR", ""),
        "stage": data.get("stage") or os.environ.get("OAG_STAGE", "req"),
        "intent": data.get("intent") or os.environ.get("OAG_INTENT", ""),
        "title": data.get("title") or os.environ.get("OAG_DRAFT_TITLE", "Interview draft"),
        "summary": data.get("summary") or os.environ.get("OAG_DRAFT_SUMMARY", ""),
        "facts": data.get("facts") if isinstance(data.get("facts"), list) else [],
        "decisions": data.get("decisions") if isinstance(data.get("decisions"), list) else [],
        "assumptions": data.get("assumptions") if isinstance(data.get("assumptions"), list) else [],
        "open_questions": data.get("open_questions") if isinstance(data.get("open_questions"), list) else [],
        "context_pressure": data.get("context_pressure") or os.environ.get("OAG_CONTEXT_PRESSURE", ""),
        "context_usage": data.get("context_usage") or os.environ.get("OAG_CONTEXT_USAGE", ""),
        "actor": data.get("actor") if isinstance(data.get("actor"), dict) else {"kind": "ai", "id": "claude", "surface": "hook"},
    }


def _has_draft_content(data: dict[str, Any]) -> bool:
    return bool(
        str(data.get("summary") or "").strip()
        or data.get("facts")
        or data.get("decisions")
        or data.get("assumptions")
        or data.get("open_questions")
    )


def _pressure_high(data: dict[str, Any]) -> bool:
    pressure = str(data.get("context_pressure") or "").lower()
    if pressure in {"high", "critical", "compact", "compaction"}:
        return True
    raw = str(data.get("context_usage") or "").strip().rstrip("%")
    if not raw:
        return False
    try:
        value = float(raw)
    except ValueError:
        return False
    return value >= 70 if value > 1 else value >= 0.70


def main() -> int:
    data = _payload()
    if not data["ip_dir"]:
        print(json.dumps({"ok": False, "error": "ip_dir is required"}, indent=2))
        return 1
    is_interview = "interview" in str(data.get("intent") or "").lower() or str(data.get("stage") or "") == "req"
    if _has_draft_content(data):
        response = oag_cli.dispatch_call({"tool": "oag.draft", "arguments": data})
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if response.get("ok") else 1
    if is_interview and _pressure_high(data):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "context pressure is high; summarize interview into oag.draft before continuing",
                    "next_action": "call oag.draft with summary/facts/open_questions",
                },
                indent=2,
            )
        )
        return 2
    print(json.dumps({"ok": True, "status": "no_draft_needed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
