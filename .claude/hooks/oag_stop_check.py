#!/usr/bin/env python3
"""Stop/finish hook example for OAG run-loop checks.

Returns non-zero when an active OAG run is incomplete so the runtime can show
the next-action prompt block instead of stopping silently.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import oag_cli  # noqa: E402


def _payload() -> dict:
    raw = sys.stdin.read()
    if raw.strip():
        data = json.loads(raw)
    else:
        data = {}
    return {
        "ip_dir": data.get("ip_dir") or os.environ.get("OAG_IP_DIR", ""),
        "stage": data.get("stage") or os.environ.get("OAG_STAGE", ""),
        "intent": data.get("intent") or os.environ.get("OAG_INTENT", ""),
        "run_id": data.get("run_id") or os.environ.get("OAG_RUN_ID", ""),
    }


def main() -> int:
    args = _payload()
    if not args["ip_dir"]:
        print(json.dumps({"ok": False, "error": "ip_dir is required"}, indent=2))
        return 1
    response = oag_cli.dispatch_call({"tool": "oag.stop_check", "arguments": args})
    print(json.dumps(response, ensure_ascii=False, indent=2))
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    if not response.get("ok"):
        return 1
    if result.get("reason") == "needs_human_decision":
        return 0
    if result.get("should_continue") is True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
