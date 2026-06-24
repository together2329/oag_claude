#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and older
    import tomli as tomllib  # type: ignore[no-redef]


CODEX_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODEX_ROOT.parent
AGENTS_DIR = CODEX_ROOT / "agents"
CATALOG = CODEX_ROOT / "oag" / "agent-catalog.toml"

EXPECTED_CORE = 15
EXPECTED_CUSTOM = 3

REQUIRED_AGENT_FIELDS = {
    "id",
    "source_file",
    "kind",
    "responsibility",
    "may_modify_source",
    "may_write_evidence",
    "may_claim_complete",
    "final_decision_authority",
    "requires_oag_context",
    "allowed_write_paths",
    "required_evidence",
    "forbidden_actions",
    "handoff_targets",
}

CLAUDE_REQUIRED_AGENT_FIELDS = {
    "name",
    "description",
    "tools",
}

CLAUDE_OPTIONAL_STRING_FIELDS = {
    "model",
    "effort",
}

LIST_FIELDS = {
    "allowed_write_paths",
    "required_evidence",
    "forbidden_actions",
    "handoff_targets",
}

BOOL_FIELDS = {
    "may_modify_source",
    "may_write_evidence",
    "may_claim_complete",
    "final_decision_authority",
    "requires_oag_context",
}

WORKSPACE_WRITE_AGENTS = {
    "oag-ontology-curator-agent",
    "oag-rtl-implementation-agent",
    "oag-tb-implementation-agent",
    "oag-sim-execution-agent",
    "oag-custom-worker",
}

XHIGH_REASONING_AGENTS = {
    "oag-requirement-contract-agent",
    "oag-legacy-ip-analyzer",
    "oag-ip-contract-agent",
    "oag-verification-strategy-agent",
    "oag-rtl-implementation-agent",
    "oag-tb-implementation-agent",
    "oag-evidence-validator",
    "oag-gate-reviewer",
    "oag-ip-version-steward-agent",
}

NICKNAME_RE = re.compile(r"^[A-Za-z0-9 _-]+$")
COMPLETION_AUTHORITY_PHRASES = (
    "only role allowed to issue final oag closure",
    "allowed to issue final oag closure",
    "final decision authority",
)


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def issue(code: str, message: str, path: str | None = None) -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def rel_source_path(agent_id: str) -> str:
    return f".claude/agents/{agent_id}.md"


def expected_tools(agent_id: str) -> set[str]:
    read_tools = {"Read", "Glob", "Grep", "Bash"}
    if agent_id in WORKSPACE_WRITE_AGENTS:
        return read_tools | {"Edit", "Write"}
    return read_tools


def parse_frontmatter(path: Path, agent_id: str, issues: list[dict[str, str]]) -> tuple[dict[str, str], str] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        issues.append(issue("AGENT_FRONTMATTER_MISSING", f"{agent_id} must start with YAML frontmatter.", str(path)))
        return None
    try:
        raw_frontmatter, body = text[4:].split("\n---\n", 1)
    except ValueError:
        issues.append(issue("AGENT_FRONTMATTER_CLOSED", f"{agent_id} frontmatter must close with ---.", str(path)))
        return None

    frontmatter: dict[str, str] = {}
    for line in raw_frontmatter.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            issues.append(issue("AGENT_FRONTMATTER_LINE", f"{agent_id} has invalid frontmatter line: {line!r}.", str(path)))
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    return frontmatter, body


def parse_tools(raw_tools: str) -> set[str]:
    return {item.strip() for item in raw_tools.split(",") if item.strip()}


def validate_claude_agent(agent_id: str, kind: str, path: Path, issues: list[dict[str, str]]) -> dict[str, str] | None:
    parsed = parse_frontmatter(path, agent_id, issues)
    if parsed is None:
        return None
    frontmatter, instructions = parsed

    missing_fields = CLAUDE_REQUIRED_AGENT_FIELDS - set(frontmatter)
    if missing_fields:
        issues.append(issue("AGENT_FRONTMATTER_FIELD_MISSING", f"{agent_id} missing fields: {sorted(missing_fields)}.", str(path)))

    if frontmatter.get("name") != agent_id:
        issues.append(issue("AGENT_FRONTMATTER_NAME", f"{agent_id}.md name must match catalog id.", str(path)))

    for field in CLAUDE_OPTIONAL_STRING_FIELDS:
        if field in frontmatter and not frontmatter.get(field):
            issues.append(issue("AGENT_FRONTMATTER_OPTIONAL_FIELD", f"{agent_id}.{field} must be a non-empty string when present.", str(path)))

    tools = parse_tools(frontmatter.get("tools", ""))
    missing_tools = expected_tools(agent_id) - tools
    if missing_tools:
        issues.append(issue("AGENT_TOOLS", f"{agent_id}.tools missing expected tools: {sorted(missing_tools)}.", str(path)))
    if agent_id not in WORKSPACE_WRITE_AGENTS and ({"Edit", "Write"} & tools):
        issues.append(issue("AGENT_TOOLS_WRITE_POLICY", f"{agent_id} must not expose Edit or Write tools.", str(path)))

    if agent_id in XHIGH_REASONING_AGENTS and frontmatter.get("effort") != "xhigh":
        issues.append(issue("AGENT_REASONING_EFFORT", f"{agent_id}.effort must be xhigh for OAG critical reasoning lanes.", str(path)))

    if not instructions.strip():
        issues.append(issue("AGENT_INSTRUCTIONS", f"{agent_id} must have body instructions.", str(path)))
        return frontmatter

    lower = instructions.lower()
    if "oag" not in lower and "ontology agent gateway" not in lower:
        issues.append(issue("AGENT_OAG_CONTEXT", f"{agent_id} instructions must mention OAG context.", str(path)))
    if "rocev" not in lower and "requirement -> obligation -> contract -> evidence -> validation -> decision" not in lower:
        issues.append(issue("AGENT_ROCEV_CONTEXT", f"{agent_id} instructions must mention ROCEV traceability.", str(path)))
    if kind == "custom" and "final closure" not in lower:
        issues.append(issue("CUSTOM_FINAL_CLOSURE", f"{agent_id} must state it cannot make final closure claims.", str(path)))
    if agent_id != "oag-gate-reviewer" and any(phrase in lower for phrase in COMPLETION_AUTHORITY_PHRASES):
        issues.append(issue("AGENT_COMPLETION_LANGUAGE", f"{agent_id} instructions must not grant final closure authority.", str(path)))
    if agent_id == "oag-gate-reviewer" and "only role allowed to issue final oag closure" not in lower:
        issues.append(issue("GATE_REVIEWER_AUTHORITY_TEXT", "Gate reviewer must explicitly state sole final OAG closure authority.", str(path)))

    return frontmatter


def check_catalog() -> dict[str, Any]:
    issues: list[dict[str, str]] = []

    if not CATALOG.exists():
        return {
            "schema": "oag_agent_catalog_check.v1",
            "status": "fail",
            "issues": [issue("CATALOG_MISSING", "Missing OAG agent catalog.", str(CATALOG))],
        }

    try:
        catalog = load_toml(CATALOG)
    except tomllib.TOMLDecodeError as exc:
        return {
            "schema": "oag_agent_catalog_check.v1",
            "status": "fail",
            "issues": [issue("CATALOG_TOML_INVALID", str(exc), str(CATALOG))],
        }

    if catalog.get("schema_version") != "oag_agent_catalog.v2":
        issues.append(issue("SCHEMA_VERSION", "Catalog schema_version must be oag_agent_catalog.v2.", str(CATALOG)))
    if catalog.get("product_name") != "IP Dev Agent":
        issues.append(issue("PRODUCT_NAME", "Catalog product_name must be IP Dev Agent.", str(CATALOG)))
    if catalog.get("gateway_short_name") != "OAG":
        issues.append(issue("GATEWAY_SHORT_NAME", "Catalog gateway_short_name must be OAG.", str(CATALOG)))
    if catalog.get("internal_gateway") != "Ontology Agent Gateway":
        issues.append(issue("INTERNAL_GATEWAY", "Catalog internal_gateway must be Ontology Agent Gateway.", str(CATALOG)))

    rocev = catalog.get("rocev_chain")
    if rocev != ["Requirement", "Obligation", "Contract", "Evidence", "Validation", "Decision"]:
        issues.append(issue("ROCEV_CHAIN", "Catalog must declare the ROCEV chain in order.", str(CATALOG)))

    agents = catalog.get("agents")
    if not isinstance(agents, list):
        return {
            "schema": "oag_agent_catalog_check.v1",
            "status": "fail",
            "issues": issues + [issue("AGENTS_TABLE", "Catalog must contain [[agents]] entries.", str(CATALOG))],
        }

    seen: set[str] = set()
    catalog_ids: set[str] = set()
    agent_names: set[str] = set()
    core_count = 0
    custom_count = 0
    completion_authority: list[str] = []
    final_decision_authority: list[str] = []

    for idx, agent in enumerate(agents):
        prefix = f"agents[{idx}]"
        if not isinstance(agent, dict):
            issues.append(issue("AGENT_ENTRY_TYPE", f"{prefix} must be a table.", str(CATALOG)))
            continue

        missing = REQUIRED_AGENT_FIELDS - set(agent)
        if missing:
            issues.append(issue("AGENT_FIELD_MISSING", f"{prefix} missing fields: {sorted(missing)}.", str(CATALOG)))

        agent_id = agent.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            issues.append(issue("AGENT_ID", f"{prefix}.id must be a non-empty string.", str(CATALOG)))
            continue

        if agent_id in seen:
            issues.append(issue("AGENT_ID_DUPLICATE", f"Duplicate agent id: {agent_id}.", str(CATALOG)))
        seen.add(agent_id)
        catalog_ids.add(agent_id)

        kind = agent.get("kind")
        if kind == "core":
            core_count += 1
        elif kind == "custom":
            custom_count += 1
            if not agent_id.startswith("oag-custom-"):
                issues.append(issue("CUSTOM_AGENT_NAME", f"Custom agent id must start with oag-custom-: {agent_id}.", str(CATALOG)))
        else:
            issues.append(issue("AGENT_KIND", f"{agent_id}.kind must be core or custom.", str(CATALOG)))

        source_file = agent.get("source_file")
        expected_source = rel_source_path(agent_id)
        if source_file != expected_source:
            issues.append(issue("SOURCE_FILE", f"{agent_id}.source_file must be {expected_source}, found {source_file!r}.", str(CATALOG)))
        source_path = PROJECT_ROOT / str(source_file or expected_source)
        if not source_path.exists():
            issues.append(issue("AGENT_MARKDOWN_MISSING", f"Missing Claude agent markdown for {agent_id}.", str(source_path)))

        for bool_field in BOOL_FIELDS:
            if not isinstance(agent.get(bool_field), bool):
                issues.append(issue("AGENT_BOOL_FIELD", f"{agent_id}.{bool_field} must be boolean.", str(CATALOG)))

        for list_field in LIST_FIELDS:
            if not isinstance(agent.get(list_field), list):
                issues.append(issue("AGENT_LIST_FIELD", f"{agent_id}.{list_field} must be a list.", str(CATALOG)))

        if agent.get("may_write_evidence") is True and not agent.get("allowed_write_paths"):
            issues.append(issue("AGENT_ALLOWED_PATHS", f"{agent_id} may_write_evidence=true requires allowed_write_paths.", str(CATALOG)))
        if agent.get("may_modify_source") is True and agent_id not in WORKSPACE_WRITE_AGENTS:
            issues.append(issue("AGENT_SOURCE_WRITE_POLICY", f"{agent_id} is not in the workspace-write role allowlist.", str(CATALOG)))
        if agent_id in WORKSPACE_WRITE_AGENTS and agent.get("may_modify_source") is not True and agent_id != "oag-sim-execution-agent":
            issues.append(issue("AGENT_SOURCE_WRITE_POLICY", f"{agent_id} should declare may_modify_source=true.", str(CATALOG)))

        if agent.get("may_claim_complete") is True:
            completion_authority.append(agent_id)
        if agent.get("final_decision_authority") is True:
            final_decision_authority.append(agent_id)
        if kind == "custom" and agent.get("may_claim_complete") is True:
            issues.append(issue("CUSTOM_CLAIM_COMPLETE", f"Custom agent cannot claim completion: {agent_id}.", str(CATALOG)))

        if agent_id == "oag-gate-reviewer":
            if agent.get("decision_types") != ["PASS", "FAIL", "BLOCKED", "WAIVED_WITH_RISK"]:
                issues.append(issue("GATE_DECISION_TYPES", "Gate reviewer must declare expected decision_types.", str(CATALOG)))
        elif "decision_types" in agent:
            issues.append(issue("DECISION_TYPES_SCOPE", f"Only oag-gate-reviewer may declare decision_types: {agent_id}.", str(CATALOG)))

        if source_path.exists():
            frontmatter = validate_claude_agent(agent_id, str(kind), source_path, issues)
            if frontmatter and isinstance(frontmatter.get("name"), str):
                agent_names.add(frontmatter["name"])

    if core_count != EXPECTED_CORE:
        issues.append(issue("CORE_COUNT", f"Expected {EXPECTED_CORE} core agents, found {core_count}.", str(CATALOG)))
    if custom_count != EXPECTED_CUSTOM:
        issues.append(issue("CUSTOM_COUNT", f"Expected {EXPECTED_CUSTOM} custom agents, found {custom_count}.", str(CATALOG)))
    if completion_authority != ["oag-gate-reviewer"]:
        issues.append(issue("COMPLETION_AUTHORITY", f"Only oag-gate-reviewer may claim completion, found {completion_authority}.", str(CATALOG)))
    if final_decision_authority != ["oag-gate-reviewer"]:
        issues.append(issue("FINAL_DECISION_AUTHORITY", f"Only oag-gate-reviewer may have final_decision_authority, found {final_decision_authority}.", str(CATALOG)))

    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("id")
        if not isinstance(agent_id, str):
            continue
        for target in agent.get("handoff_targets", []) if isinstance(agent.get("handoff_targets"), list) else []:
            if target not in catalog_ids:
                issues.append(issue("HANDOFF_TARGET", f"{agent_id} handoff target is not in catalog: {target}.", str(CATALOG)))

    agent_markdowns = sorted(path for path in AGENTS_DIR.glob("*.md"))
    non_markdown_agent_files = sorted(path.name for path in AGENTS_DIR.iterdir() if path.is_file() and path.suffix != ".md")
    if non_markdown_agent_files:
        issues.append(issue("AGENTS_DIR_NON_MARKDOWN", f".claude/agents must contain only Claude Code markdown agent files: {non_markdown_agent_files}.", str(AGENTS_DIR)))
    if len(agent_markdowns) != EXPECTED_CORE + EXPECTED_CUSTOM:
        issues.append(issue("AGENT_MARKDOWN_COUNT", f"Expected {EXPECTED_CORE + EXPECTED_CUSTOM} markdown files, found {len(agent_markdowns)}.", str(AGENTS_DIR)))

    markdown_file_ids = {path.stem for path in agent_markdowns}
    if markdown_file_ids != catalog_ids:
        issues.append(issue("CATALOG_MARKDOWN_SET", f"Catalog ids and markdown filenames differ: catalog={sorted(catalog_ids)} markdown={sorted(markdown_file_ids)}.", str(AGENTS_DIR)))
    if agent_names and agent_names != catalog_ids:
        issues.append(issue("CATALOG_MARKDOWN_NAME_SET", f"Catalog ids and markdown names differ: catalog={sorted(catalog_ids)} agent_names={sorted(agent_names)}.", str(AGENTS_DIR)))

    return {
        "schema": "oag_agent_catalog_check.v1",
        "status": "fail" if issues else "pass",
        "catalog": str(CATALOG),
        "counts": {
            "core": core_count,
            "custom": custom_count,
            "total": core_count + custom_count,
            "markdown_files": len(agent_markdowns),
        },
        "completion_authority": completion_authority,
        "final_decision_authority": final_decision_authority,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate OAG Claude Code agent catalog.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_catalog()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        counts = result["counts"]
        print(f"PASS oag agent catalog: {counts['total']} agents ({counts['core']} core, {counts['custom']} custom)")
    else:
        print("FAIL oag agent catalog", file=sys.stderr)
        for item in result["issues"]:
            print(f"- {item['code']}: {item['message']}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
