#!/usr/bin/env python3
"""Check or patch user Claude Code config for OAG native subagent workflows."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and older
    import tomli as tomllib  # type: ignore[no-redef]


FEATURES = ("multi_agent", "child_agents_md", "hooks")
OPTIONAL_OMO_FEATURES = ("plugins", "plugin_hooks")
OAG_MCP_SERVER_NAMES = ("ip-dev-agent-oag", "ontology" + "-ip-agent-oag")
MULTI_AGENT_V2_MAX_THREADS = 10000
MULTI_AGENT_V2_GUARD_COMMENT = (
    "# Managed by IP Dev Agent: multi_agent_v2 is re-disabled on every Claude Code session start\n"
    "# because v2 can fail every turn with HTTP 400 in current Claude Code runtimes (openai/claude#26753).\n"
    "# Disable this startup guard with OAG_CODEX_CONFIG_MIGRATION_DISABLED=1.\n"
)


def default_config_path() -> Path:
    claude_home = os.environ.get("CODEX_HOME")
    if claude_home:
        return Path(claude_home).expanduser() / "config.toml"
    return Path.home() / ".claude" / "config.toml"


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def parse_toml(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    return tomllib.loads(text)


def try_parse_toml(text: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    try:
        return parse_toml(text), []
    except Exception as exc:  # TOML can be invalid while boolean shorthand conflicts with a subtable.
        return {}, [issue("TOML_INVALID", f"config.toml could not be parsed before normalization: {exc}")]


def find_section(lines: list[str], section: str) -> tuple[int, int] | None:
    header = f"[{section}]"
    start = None
    for idx, line in enumerate(lines):
        stripped = strip_trailing_comment(line)
        if stripped == header:
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if re.match(r"^\[[^\]]+\]$", strip_trailing_comment(lines[idx])):
            end = idx
            break
    return start, end


def strip_trailing_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def ensure_setting(text: str, section: str, key: str, value: str) -> str:
    lines = text.splitlines()
    bounds = find_section(lines, section)
    if bounds is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", f"{key} = {value}"])
        return "\n".join(lines).rstrip() + "\n"

    start, end = bounds
    key_re = re.compile(rf"^(\s*){re.escape(key)}\s*=.*$")
    for idx in range(start + 1, end):
        if key_re.match(lines[idx]):
            lines[idx] = f"{key} = {value}"
            return "\n".join(lines).rstrip() + "\n"
    lines.insert(end, f"{key} = {value}")
    return "\n".join(lines).rstrip() + "\n"


def ensure_min_int_setting(text: str, section: str, key: str, minimum: int) -> str:
    lines = text.splitlines()
    bounds = find_section(lines, section)
    if bounds is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", f"{key} = {minimum}"])
        return "\n".join(lines).rstrip() + "\n"

    start, end = bounds
    key_re = re.compile(rf"^(\s*){re.escape(key)}\s*=\s*(.+)$")
    for idx in range(start + 1, end):
        match = key_re.match(lines[idx])
        if not match:
            continue
        raw_value = strip_trailing_comment(match.group(2))
        try:
            current = int(raw_value)
        except ValueError:
            current = 0
        if current >= minimum:
            return "\n".join(lines).rstrip() + "\n"
        lines[idx] = f"{key} = {minimum}"
        return "\n".join(lines).rstrip() + "\n"
    lines.insert(end, f"{key} = {minimum}")
    return "\n".join(lines).rstrip() + "\n"


def remove_setting(text: str, section: str, key: str) -> str:
    lines = text.splitlines()
    bounds = find_section(lines, section)
    if bounds is None:
        return text if text.endswith("\n") else text + ("\n" if text else "")
    start, end = bounds
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    next_lines = [line for idx, line in enumerate(lines) if not (start < idx < end and key_re.match(line))]
    return "\n".join(next_lines).rstrip() + "\n"


def remove_sections(text: str, sections: tuple[str, ...]) -> str:
    next_text = text if text.endswith("\n") or not text else text + "\n"
    for section in sections:
        lines = next_text.splitlines()
        bounds = find_section(lines, section)
        if bounds is None:
            continue
        start, end = bounds
        del lines[start:end]
        while start < len(lines) and not lines[start].strip():
            del lines[start]
        next_text = "\n".join(lines).rstrip() + "\n"
    return next_text


def remove_oag_mcp_servers(text: str) -> str:
    sections = tuple(
        section
        for server_name in OAG_MCP_SERVER_NAMES
        for section in (f"mcp_servers.{server_name}", f"mcp_servers.{server_name}.env")
    )
    return remove_sections(text, sections)


def section_lines(text: str, section: str) -> list[str]:
    lines = text.splitlines()
    bounds = find_section(lines, section)
    if bounds is None:
        return []
    start, end = bounds
    return lines[start + 1 : end]


def needs_multi_agent_v2_guard_patch(text: str) -> bool:
    features_lines = section_lines(text, "features")
    if any(re.match(r"^\s*multi_agent_v2\s*=", line) for line in features_lines):
        return True
    v2_lines = section_lines(text, "features.multi_agent_v2")
    if not v2_lines:
        return True
    return not any(re.match(r"^\s*enabled\s*=\s*false(?:\s*#.*)?\s*$", line) for line in v2_lines)


def desired_config(text: str, *, include_omo_plugin_features: bool) -> str:
    should_annotate_v2_guard = needs_multi_agent_v2_guard_patch(text)
    next_text = text if text.endswith("\n") or not text else text + "\n"
    next_text = remove_oag_mcp_servers(next_text)
    for feature in FEATURES:
        next_text = ensure_setting(next_text, "features", feature, "true")
    if include_omo_plugin_features:
        for feature in OPTIONAL_OMO_FEATURES:
            next_text = ensure_setting(next_text, "features", feature, "true")
    next_text = remove_setting(next_text, "features", "multi_agent_v2")
    next_text = ensure_setting(next_text, "features.multi_agent_v2", "enabled", "false")
    next_text = ensure_setting(next_text, "features.multi_agent_v2", "max_concurrent_threads_per_session", str(MULTI_AGENT_V2_MAX_THREADS))
    next_text = ensure_min_int_setting(next_text, "agents", "max_depth", 1)
    if should_annotate_v2_guard and "[features.multi_agent_v2]" in next_text and "openai/claude#26753" not in next_text:
        next_text = next_text.replace("[features.multi_agent_v2]", f"{MULTI_AGENT_V2_GUARD_COMMENT}[features.multi_agent_v2]", 1)
    return next_text


def config_status(config: dict[str, Any], *, include_omo_plugin_features: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    features = config.get("features") if isinstance(config.get("features"), dict) else {}
    agents = config.get("agents") if isinstance(config.get("agents"), dict) else {}
    required = list(FEATURES)
    if include_omo_plugin_features:
        required.extend(OPTIONAL_OMO_FEATURES)
    for feature in required:
        if features.get(feature) is not True:
            issues.append(issue("FEATURE_DISABLED", f"[features].{feature} must be true."))
    v2 = features.get("multi_agent_v2")
    if isinstance(v2, bool):
        issues.append(issue("MULTI_AGENT_V2_BOOLEAN", "[features].multi_agent_v2 boolean shorthand must be removed."))
    if not isinstance(v2, dict) or v2.get("enabled") is not False:
        issues.append(issue("MULTI_AGENT_V2_ENABLED", "[features.multi_agent_v2].enabled must be false."))
    if not isinstance(v2, dict) or int(v2.get("max_concurrent_threads_per_session") or 0) < MULTI_AGENT_V2_MAX_THREADS:
        issues.append(issue("MULTI_AGENT_V2_LIMIT", "[features.multi_agent_v2].max_concurrent_threads_per_session should be 10000."))
    if int(agents.get("max_depth") or 0) < 1:
        issues.append(issue("AGENT_DEPTH", "[agents].max_depth must be at least 1."))
    mcp_servers = config.get("mcp_servers") if isinstance(config.get("mcp_servers"), dict) else {}
    for server_name in OAG_MCP_SERVER_NAMES:
        if server_name in mcp_servers:
            issues.append(issue("OAG_MCP_ENABLED", f"[mcp_servers.{server_name}] must be removed; OAG uses scripts/skills/hooks, not an MCP server."))
    return issues


def run(config_path: Path, *, apply: bool, include_omo_plugin_features: bool) -> dict[str, Any]:
    before = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    before_payload, parse_issues = try_parse_toml(before)
    before_issues = [
        *parse_issues,
        *config_status(before_payload, include_omo_plugin_features=include_omo_plugin_features),
    ]
    after = desired_config(before, include_omo_plugin_features=include_omo_plugin_features)
    changed = after != (before if before.endswith("\n") or not before else before + "\n")
    backup_path = None

    if apply and changed:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            backup_path = config_path.with_suffix(f".toml.oag-backup-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
            shutil.copy2(config_path, backup_path)
        tmp = config_path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(after, encoding="utf-8")
        tmp.replace(config_path)

    final_text = after if apply else before
    final_payload, final_parse_issues = try_parse_toml(final_text)
    final_issues = [
        *final_parse_issues,
        *config_status(final_payload, include_omo_plugin_features=include_omo_plugin_features),
    ]
    return {
        "schema_version": "oag_claude_config_doctor.v1",
        "status": "pass" if not final_issues else "fail",
        "config_path": str(config_path),
        "changed": bool(apply and changed),
        "would_change": bool((not apply) and changed),
        "backup_path": str(backup_path) if backup_path else None,
        "before_issues": before_issues,
        "issues": final_issues,
        "note": "Restart Claude Code or open a new trusted project session after applying config changes.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or patch user Claude Code config for OAG subagents.")
    parser.add_argument("--config", default=str(default_config_path()), help="Path to Claude Code config.toml.")
    parser.add_argument("--apply", action="store_true", help="Patch the config file. Default is dry-run.")
    parser.add_argument("--include-omo-plugin-features", action="store_true", help="Also force plugins=true and plugin_hooks=true like OMO Claude Code.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = run(Path(args.config).expanduser(), apply=args.apply, include_omo_plugin_features=args.include_omo_plugin_features)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag claude config doctor")
    else:
        print("FAIL oag claude config doctor")
        for item in result["issues"]:
            print(f"- {item['code']}: {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
