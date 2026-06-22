#!/usr/bin/env python3
"""Pre-work hook example for OAG.

Input JSON may include:
  {"ip_dir":"example_ip","stage":"sim","intent":"debug coverage"}

The hook prints a compact OAG context response. It is safe to run manually.
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
    }


def main() -> int:
    args = _payload()
    if not args["ip_dir"]:
        print(json.dumps({"ok": False, "error": "ip_dir is required"}, indent=2))
        return 1
    response = oag_cli.dispatch_call({"tool": "oag.context", "arguments": args})
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
