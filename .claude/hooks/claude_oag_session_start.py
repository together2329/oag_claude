#!/usr/bin/env python3
"""Claude Code SessionStart hook: keep OAG native-subagent config in a v1-safe state.

This follows the OMO/LazyClaude Code pattern: do not directly force multi-agent v1.
Instead, keep multi-agent enabled while force-disabling multi_agent_v2 on every
startup so Claude Code can fall back to the v1 multi-agent path when available.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from oag_hook_utils import hook_additional_context

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import oag_claude_config_doctor  # noqa: E402


DISABLE_ENVS = {
    "OAG_CODEX_CONFIG_MIGRATION_DISABLED",
    "LAZYCODEX_CONFIG_MIGRATION_DISABLED",
    "OMO_CODEX_CONFIG_MIGRATION_DISABLED",
}


def _disabled() -> bool:
    return any(str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"} for name in DISABLE_ENVS)


def main() -> int:
    if _disabled():
        return 0
    try:
        result = oag_claude_config_doctor.run(
            oag_claude_config_doctor.default_config_path(),
            apply=True,
            include_omo_plugin_features=True,
        )
    except Exception:
        return 0

    if not result.get("changed"):
        return 0

    context = "\n".join(
        [
            "=== OAG CODEX CONFIG MIGRATION ===",
            "IP Dev Agent patched user Claude Code config for native subagent safety.",
            "multi_agent and child_agents_md are enabled; multi_agent_v2 is force-disabled.",
            "Open a fresh trusted project session if the active runtime was created before this patch.",
            "=== END OAG CODEX CONFIG MIGRATION ===",
        ]
    )
    print(json.dumps(hook_additional_context(context, "SessionStart"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
