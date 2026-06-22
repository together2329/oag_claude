#!/usr/bin/env python3
"""Release-oriented validation for the OAG Claude Code pack."""

from __future__ import annotations

import argparse
import json
import py_compile
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and older
    import tomli as tomllib  # type: ignore[no-redef]


CODEX_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODEX_ROOT.parent
SCRIPTS_DIR = CODEX_ROOT / "scripts"
HOOKS_DIR = CODEX_ROOT / "hooks"
SCHEMAS_DIR = CODEX_ROOT / "schemas"

SOURCE_SCAN_EXCLUDED_PARTS = {
    ".cache",
    ".tmp",
    "tmp",
    "runs",
    "sessions",
    "shell_snapshots",
    "__pycache__",
}

OAG_MCP_SERVER_NAMES = ("ip-dev-agent-oag", "ontology" + "-ip-agent-oag")

REQUIRED_FILES = (
    CODEX_ROOT / "AGENTS.md",
    CODEX_ROOT / "config.toml",
    CODEX_ROOT / "hooks.json",
    CODEX_ROOT / "oag" / "agent-catalog.toml",
    CODEX_ROOT / "oag" / "agent-common-preamble.md",
    CODEX_ROOT / "oag" / "contract-projection.md",
    CODEX_ROOT / "oag" / "cdc-rdc-evidence.md",
    CODEX_ROOT / "oag" / "clock-reset-architecture.md",
    CODEX_ROOT / "oag" / "domain-crossing-principles.md",
    CODEX_ROOT / "oag" / "ip-dev-agent.md",
    CODEX_ROOT / "oag" / "modeling-contract-principles.md",
    CODEX_ROOT / "oag" / "modeling-policy.md",
    CODEX_ROOT / "oag" / "deep-semantic-intake-policy.md",
    CODEX_ROOT / "oag" / "requirements-quality-policy.md",
    CODEX_ROOT / "oag" / "requirement-decomposition-principles.md",
    CODEX_ROOT / "oag" / "assume-guarantee-contracts.md",
    CODEX_ROOT / "oag" / "contract-strength-policy.md",
    CODEX_ROOT / "oag" / "phenomena-boundary-model.md",
    CODEX_ROOT / "oag" / "decision-matrix-policy.md",
    CODEX_ROOT / "oag" / "authoring-packet-policy.md",
    CODEX_ROOT / "oag" / "traceability-policy.md",
    CODEX_ROOT / "oag" / "wavefront-policy.md",
    CODEX_ROOT / "oag" / "wavefront-task-graph.md",
    CODEX_ROOT / "oag" / "oag-mode-directive.md",
    CODEX_ROOT / "oag" / "principles.md",
    CODEX_ROOT / "oag" / "recovery-playbook.md",
    CODEX_ROOT / "oag" / "rtl-dialect-policy.md",
    CODEX_ROOT / "oag" / "rtl-implementation.md",
    CODEX_ROOT / "oag" / "rtl-ppa-principles.md",
    CODEX_ROOT / "oag" / "verification-methodology-principles.md",
    CODEX_ROOT / "oag" / "verification-strategy-policy.md",
    CODEX_ROOT / "oag" / "tb-methodology-policy.md",
    CODEX_ROOT / "oag" / "tb-architecture-patterns.md",
    CODEX_ROOT / "oag" / "coverage-closure-policy.md",
    CODEX_ROOT / "oag" / "assertion-formal-policy.md",
    CODEX_ROOT / "oag" / "scoreboard-evidence.md",
    CODEX_ROOT / "oag" / "subagent-workflows.md",
    CODEX_ROOT / "oag" / "wavefront-templates" / "rtl_module_fanout.yaml",
    CODEX_ROOT / "oag" / "wavefront-templates" / "tb_common_then_scenario_fanout.yaml",
    CODEX_ROOT / "oag" / "profiles" / "protocol-packet-ip.yaml",
    CODEX_ROOT / "oag" / "profiles" / "mctp-rx.yaml",
    CODEX_ROOT / "rules" / "oag-invariants.rules.md",
    CODEX_ROOT / "rules" / "oag-rule-index.yaml",
    CODEX_ROOT / "rules" / "oag-requirements-quality.rules.md",
    CODEX_ROOT / "rules" / "oag-requirement-decomposition.rules.md",
    CODEX_ROOT / "rules" / "oag-lock-readiness.rules.md",
    CODEX_ROOT / "rules" / "oag-contract-strength.rules.md",
    CODEX_ROOT / "rules" / "oag-authoring-packet.rules.md",
    CODEX_ROOT / "rules" / "oag-traceability.rules.md",
    CODEX_ROOT / "rules" / "oag-verification-strategy.rules.md",
    CODEX_ROOT / "rules" / "oag-cdc-rdc.rules.md",
    CODEX_ROOT / "rules" / "oag-rtl-ppa.rules.md",
    CODEX_ROOT / "rules" / "oag-tb-methodology.rules.md",
    CODEX_ROOT / "rules" / "oag-wavefront.rules.md",
    CODEX_ROOT / "rules" / "oag-rocev.rules.md",
    CODEX_ROOT / "skills" / "oag-deep-semantic-intake" / "SKILL.md",
    CODEX_ROOT / "skills" / "oag-decision-matrix" / "SKILL.md",
    CODEX_ROOT / "skills" / "oag-contract-projection" / "SKILL.md",
    CODEX_ROOT / "skills" / "oag-authoring-packet" / "SKILL.md",
    CODEX_ROOT / "skills" / "oag-evidence-closure" / "SKILL.md",
    CODEX_ROOT / "skills" / "oag-wavefront" / "SKILL.md",
    CODEX_ROOT / "skills" / "oag-ip-workflow" / "SKILL.md",
    SCRIPTS_DIR / "oag_agent_catalog_check.py",
    SCRIPTS_DIR / "oag_claude_config_doctor.py",
    SCRIPTS_DIR / "oag_closure_check.py",
    SCRIPTS_DIR / "oag_cli.py",
    SCRIPTS_DIR / "oag_dispatch.py",
    SCRIPTS_DIR / "oag_domain_crossing_check.py",
    SCRIPTS_DIR / "oag_exec_auto_research.py",
    SCRIPTS_DIR / "oag_lock_readiness_check.py",
    SCRIPTS_DIR / "oag_main_write_gate.py",
    SCRIPTS_DIR / "oag_ppa_check.py",
    SCRIPTS_DIR / "oag_pyslang_lint.py",
    SCRIPTS_DIR / "oag_protected_receipt_audit.py",
    SCRIPTS_DIR / "oag_req_quality_check.py",
    SCRIPTS_DIR / "oag_requirement_atom_check.py",
    SCRIPTS_DIR / "oag_contract_strength_check.py",
    SCRIPTS_DIR / "oag_authoring_packet_check.py",
    SCRIPTS_DIR / "oag_trace_graph_check.py",
    SCRIPTS_DIR / "oag_wavefront.py",
    SCRIPTS_DIR / "oag_deep_semantic_intake.py",
    SCRIPTS_DIR / "oag_decision_matrix_generate.py",
    SCRIPTS_DIR / "oag_verification_plan_check.py",
    SCRIPTS_DIR / "oag_validate_json.py",
    SCRIPTS_DIR / "oag_workflow_whole_db.py",
    SCRIPTS_DIR / "smoke_test.py",
    HOOKS_DIR / "claude_context_inject.py",
    HOOKS_DIR / "claude_draft_pressure.py",
    HOOKS_DIR / "claude_native_subagent_guard.py",
    HOOKS_DIR / "claude_oag_mode_trigger.py",
    HOOKS_DIR / "claude_oag_session_start.py",
    HOOKS_DIR / "claude_stop_gate.py",
    HOOKS_DIR / "claude_subagent_oag_start.py",
    HOOKS_DIR / "claude_subagent_oag_gate.py",
    SCHEMAS_DIR / "oag_dispatch.schema.json",
    SCHEMAS_DIR / "oag_subagent_receipt.schema.json",
    SCHEMAS_DIR / "oag_validation_report.schema.json",
    SCHEMAS_DIR / "oag_gate_decision.schema.json",
    SCHEMAS_DIR / "oag_closure_report.schema.json",
    SCHEMAS_DIR / "oag_scope_lock.schema.json",
    SCHEMAS_DIR / "oag_source_claims.schema.json",
    SCHEMAS_DIR / "oag_ambiguity_register.schema.json",
    SCHEMAS_DIR / "oag_requirement_atom.schema.json",
    SCHEMAS_DIR / "oag_decision_matrix.schema.json",
    SCHEMAS_DIR / "oag_verification_plan.schema.json",
    SCHEMAS_DIR / "oag_contract_v2.schema.json",
    SCHEMAS_DIR / "oag_rtl_authoring_packet.schema.json",
    SCHEMAS_DIR / "oag_tb_authoring_packet.schema.json",
    SCHEMAS_DIR / "oag_wavefront_task_graph.schema.json",
    SCHEMAS_DIR / "oag_ownership_locks.schema.json",
    SCHEMAS_DIR / "oag_wavefront_event.schema.json",
)

FORBIDDEN_FILES = (
    PROJECT_ROOT / "AGENTS.md",
    CODEX_ROOT / "mcp.json",
)

JSON_FILES = (
    CODEX_ROOT / "hooks.json",
    CODEX_ROOT / "evals" / "oag_control_cases.json",
    SCHEMAS_DIR / "oag_dispatch.schema.json",
    SCHEMAS_DIR / "oag_subagent_receipt.schema.json",
    SCHEMAS_DIR / "oag_validation_report.schema.json",
    SCHEMAS_DIR / "oag_gate_decision.schema.json",
    SCHEMAS_DIR / "oag_closure_report.schema.json",
    SCHEMAS_DIR / "oag_scope_lock.schema.json",
    SCHEMAS_DIR / "oag_source_claims.schema.json",
    SCHEMAS_DIR / "oag_ambiguity_register.schema.json",
    SCHEMAS_DIR / "oag_requirement_atom.schema.json",
    SCHEMAS_DIR / "oag_decision_matrix.schema.json",
    SCHEMAS_DIR / "oag_verification_plan.schema.json",
    SCHEMAS_DIR / "oag_contract_v2.schema.json",
    SCHEMAS_DIR / "oag_rtl_authoring_packet.schema.json",
    SCHEMAS_DIR / "oag_tb_authoring_packet.schema.json",
    SCHEMAS_DIR / "oag_wavefront_task_graph.schema.json",
    SCHEMAS_DIR / "oag_ownership_locks.schema.json",
    SCHEMAS_DIR / "oag_wavefront_event.schema.json",
)

TOML_FILES = (
    CODEX_ROOT / "config.toml",
    CODEX_ROOT / "oag" / "agent-catalog.toml",
)

FORBIDDEN_STRINGS = (
    "/" + "Users/",
    "Desktop" + "/Project",
    "common_" + "ai_agent",
    "OAG_COMMON_" + "AI_AGENT",
    "COMMON_" + "AI_AGENT_HOME",
    "oag_subagent_" + "registry",
    "ontology_" + "ip_agent",
    "ontology-" + "ip-agent",
    "Ontology " + "IP Agent",
)

REQUIRED_DOC_SNIPPETS = {
    CODEX_ROOT / "AGENTS.md": (
        "oag-mode-directive.md",
        "multi_agent_v1.spawn_agent",
        "native Claude Code collaboration workers",
        "Do not replace the child",
        "enabled = false",
        "oag_agent_catalog_check.py",
        "oag_closure_check.py",
        "oag_claude_config_doctor.py",
        "oag_dispatch.py",
        "oag_domain_crossing_check.py",
        "oag_pyslang_lint.py",
        "oag_workflow_whole_db.py",
        "deep-semantic-intake-policy.md",
        "requirements-quality-policy.md",
        "oag_req_quality_check.py",
        "req/source_claims.yaml",
        "req/ambiguity_register.yaml",
        "requirement-decomposition-principles.md",
        "assume-guarantee-contracts.md",
        "contract-strength-policy.md",
        "phenomena-boundary-model.md",
        "decision-matrix-policy.md",
        "authoring-packet-policy.md",
        "traceability-policy.md",
        "wavefront-policy.md",
        "oag_wavefront.py",
        "oag_requirement_atom_check.py",
        "oag_lock_readiness_check.py",
        "oag_verification_plan_check.py",
        "oag_contract_strength_check.py",
        "oag_authoring_packet_check.py",
        "oag_trace_graph_check.py",
        "oag_deep_semantic_intake.py",
        "oag_decision_matrix_generate.py",
        "oag-deep-semantic-intake",
        "oag-decision-matrix",
        "oag-contract-projection",
        "oag-authoring-packet",
        "oag-wavefront",
        "oag-evidence-closure",
        "oag-rule-index.yaml",
        "RULE-LOCK-003",
        "ontology/decision_matrix.yaml",
        "ontology/verification_plan.yaml",
        "rtl__*.json",
        "tb__*.json",
        "requirement atoms",
        "verification-methodology-principles.md",
        "verification-strategy-policy.md",
        "tb-methodology-policy.md",
        "oag-tb-methodology.rules.md",
        "oag_exec_auto_research.py",
        "oag_main_write_gate.py",
        "ownership locks",
        "oag_validate_json.py",
        "checked_artifact_hashes",
        "scope_lock.json",
        "No lock, no RTL",
        "After user lock, main agent orchestrates",
        "SubagentStart",
        "SubagentStop",
        "schema",
    ),
    CODEX_ROOT / "oag" / "oag-mode-directive.md": (
        "OAG MODE ENABLED!",
        "Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision",
        "multi_agent_v1.spawn_agent",
        "native Claude Code subagents",
        "Do not continue as a manual",
        "oag_dispatch.py",
        "domain-crossing-principles.md",
        "deep-semantic-intake-policy.md",
        "requirements-quality-policy.md",
        "requirement-decomposition-principles.md",
        "assume-guarantee-contracts.md",
        "contract-strength-policy.md",
        "phenomena-boundary-model.md",
        "decision-matrix-policy.md",
        "authoring-packet-policy.md",
        "traceability-policy.md",
        "verification-methodology-principles.md",
        "verification-strategy-policy.md",
        "tb-methodology-policy.md",
        "oag_domain_crossing_check.py",
        "oag_pyslang_lint.py",
        "oag_req_quality_check.py",
        "oag_requirement_atom_check.py",
        "oag_contract_strength_check.py",
        "oag_authoring_packet_check.py",
        "oag_trace_graph_check.py",
        "oag_wavefront.py",
        "oag_deep_semantic_intake.py",
        "oag_decision_matrix_generate.py",
        "oag-deep-semantic-intake",
        "oag-decision-matrix",
        "oag-contract-projection",
        "oag-authoring-packet",
        "oag-wavefront",
        "oag-evidence-closure",
        "oag_lock_readiness_check.py",
        "oag_verification_plan_check.py",
        "ontology/decision_matrix.yaml",
        "ontology/verification_plan.yaml",
        "ontology/generated/authoring_packets",
        "rtl__*.json",
        "tb__*.json",
        "req/source_claims.yaml",
        "req/ambiguity_register.yaml",
        "oag-tb-methodology.rules.md",
        "requirement atoms",
        "dispatch_id",
        "checked_artifact_hashes",
        "generated tool output",
        "STATIC_HANDOFF_PASS",
        "oag.lock_status",
        "No lock, no RTL",
        "After user lock, main agent orchestrates",
        "oag_main_write_gate.py",
        "record_decision=true",
        "CONTEXT -> PIN/RED -> BUILD -> EVIDENCE -> VALIDATE -> DECIDE",
    ),
    CODEX_ROOT / "oag" / "subagent-workflows.md": (
        "multi_agent_v1.spawn_agent",
        "native Claude Code collaboration workers",
        "enabled = false",
        "OAG_EVIDENCE_RECORDED",
        "oag_dispatch.py",
        "oag_domain_crossing_check.py",
        "oag_pyslang_lint.py",
        "oag-verification-strategy-agent",
        "ontology/verification_plan.yaml",
        "tb_methodology_notes",
        "dispatch_id",
        "checked_artifact_hashes",
        "Do not run a Python",
        "generated tool output",
        "STATIC_HANDOFF_PASS",
        "oag.lock_status",
        "No lock, no",
        "After user lock, main agent orchestrates",
        "oag_main_write_gate.py",
        "git status --short -uall -- <ip>",
        "oag_wavefront.py",
        "wavefront_run_id",
        "SubagentStart",
        "oag_exec_auto_research.py",
        "claude exec resume",
        "first attempt a minimal explicit",
        "native spawn",
        "observed",
        "native-spawn blocker",
    ),
    CODEX_ROOT / "skills" / "oag-ip-workflow" / "SKILL.md": (
        "python3 .claude/scripts/oag_cli.py",
        "python3 .claude/scripts/oag_agent_catalog_check.py",
        "python3 .claude/scripts/oag_closure_check.py",
        "python3 .claude/scripts/oag_dispatch.py",
        "oag_domain_crossing_check.py",
        "oag_pyslang_lint.py",
        "oag_req_quality_check.py",
        "oag_requirement_atom_check.py",
        "oag_lock_readiness_check.py",
        "oag_contract_strength_check.py",
        "oag_authoring_packet_check.py",
        "oag_trace_graph_check.py",
        "oag_deep_semantic_intake.py",
        "oag_decision_matrix_generate.py",
        "oag-deep-semantic-intake",
        "oag-decision-matrix",
        "oag-contract-projection",
        "oag-authoring-packet",
        "oag-wavefront",
        "oag-evidence-closure",
        "oag_wavefront.py",
        "oag_verification_plan_check.py",
        "req/source_claims.yaml",
        "req/ambiguity_register.yaml",
        "ontology/decision_matrix.yaml",
        "ontology/verification_plan.yaml",
        "ontology/tb_methodology.yaml",
        "ontology/requirement_atoms.yaml",
        "ontology/generated/authoring_packets",
        "rtl__*.json",
        "tb__*.json",
        "native Claude Code collaboration workers",
        "generated tool output",
        "STATIC_HANDOFF_PASS",
        "oag.lock_status",
        "No lock, no RTL",
        "After user lock, main agent orchestrates",
        "oag_main_write_gate.py",
        "git status --short -uall -- <ip>",
        "dispatch_id",
        "checked artifact hashes",
        "SubagentStart",
        "assume/guarantee",
    ),
}


def issue(code: str, message: str, path: Path | None = None) -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = str(path.relative_to(PROJECT_ROOT) if path.is_absolute() and PROJECT_ROOT in path.parents else path)
    return payload


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_required_files(issues: list[dict[str, str]]) -> None:
    for path in REQUIRED_FILES:
        if not path.is_file():
            issues.append(issue("REQUIRED_FILE_MISSING", "Required OAG pack file is missing.", path))


def check_forbidden_files(issues: list[dict[str, str]]) -> None:
    for path in FORBIDDEN_FILES:
        if path.exists():
            issues.append(issue("FORBIDDEN_FILE_PRESENT", "Root AGENTS.md is intentionally absent; keep OAG pack guidance in .claude/AGENTS.md.", path))


def check_json_files(issues: list[dict[str, str]]) -> None:
    for path in JSON_FILES:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append(issue("JSON_INVALID", f"Invalid JSON: {exc}", path))
            continue
        if path.name.endswith(".schema.json"):
            if not isinstance(payload, dict) or "$schema" not in payload or "required" not in payload:
                issues.append(issue("JSON_SCHEMA_SHAPE", "Schema JSON must declare $schema and required fields.", path))


def check_toml_files(issues: list[dict[str, str]]) -> None:
    for path in TOML_FILES:
        if not path.exists():
            continue
        try:
            with path.open("rb") as fh:
                tomllib.load(fh)
        except Exception as exc:
            issues.append(issue("TOML_INVALID", f"Invalid TOML: {exc}", path))
    for path in sorted((CODEX_ROOT / "agents").glob("*.toml")):
        try:
            with path.open("rb") as fh:
                payload = tomllib.load(fh)
        except Exception as exc:
            issues.append(issue("AGENT_TOML_INVALID", f"Invalid agent TOML: {exc}", path))
            continue
        for field in ("name", "description", "developer_instructions", "sandbox_mode"):
            if field not in payload:
                issues.append(issue("AGENT_TOML_FIELD", f"Agent TOML missing {field}.", path))


def check_python_compile(issues: list[dict[str, str]]) -> None:
    with tempfile.TemporaryDirectory(prefix="oag-pack-pycompile-") as tmp:
        tmp_dir = Path(tmp)
        for path in [*sorted(SCRIPTS_DIR.glob("*.py")), *sorted(HOOKS_DIR.glob("*.py"))]:
            try:
                py_compile.compile(str(path), cfile=str(tmp_dir / f"{path.stem}.pyc"), doraise=True)
            except py_compile.PyCompileError as exc:
                issues.append(issue("PY_COMPILE", str(exc), path))


def check_catalog(issues: list[dict[str, str]]) -> dict[str, Any]:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from oag_agent_catalog_check import check_catalog as catalog_check  # pylint: disable=import-outside-toplevel

    result = catalog_check()
    if result.get("status") != "pass":
        issues.append(issue("AGENT_CATALOG_CHECK", "Agent catalog checker failed.", CODEX_ROOT / "oag" / "agent-catalog.toml"))
        for item in result.get("issues", []):
            if isinstance(item, dict):
                issues.append({"code": f"CATALOG_{item.get('code', 'ISSUE')}", "message": str(item.get("message") or item)})
    return result


def check_agent_loader_boundary(issues: list[dict[str, str]]) -> None:
    agents_dir = CODEX_ROOT / "agents"
    for path in sorted(agents_dir.iterdir()):
        if path.is_file() and path.suffix != ".md":
            issues.append(issue("AGENTS_DIR_NON_MARKDOWN", ".claude/agents must contain only Claude Code markdown agent files.", path))
    if (agents_dir / "oag-agent-catalog.toml").exists() or (agents_dir / "agent-catalog.toml").exists():
        issues.append(issue("CATALOG_IN_AGENT_LOADER_PATH", "OAG catalog must stay outside .claude/agents.", agents_dir))


def check_hooks_policy(issues: list[dict[str, str]]) -> None:
    try:
        hooks = json.loads((CODEX_ROOT / "hooks.json").read_text(encoding="utf-8"))
    except Exception:
        return
    session_start = (((hooks.get("hooks") or {}).get("SessionStart") or [{}])[0])
    session_start_hooks = session_start.get("hooks") if isinstance(session_start, dict) else []
    session_start_commands = [str(item.get("command") or "") for item in session_start_hooks if isinstance(item, dict)]
    if "python3 .claude/hooks/claude_oag_session_start.py" not in session_start_commands:
        issues.append(issue("SESSION_START_CONFIG_GUARD_MISSING", "SessionStart must run the OAG Claude Code config guard.", CODEX_ROOT / "hooks.json"))
    user_prompt = (((hooks.get("hooks") or {}).get("UserPromptSubmit") or [{}])[0])
    user_prompt_hooks = user_prompt.get("hooks") if isinstance(user_prompt, dict) else []
    user_prompt_commands = [str(item.get("command") or "") for item in user_prompt_hooks if isinstance(item, dict)]
    if "python3 .claude/hooks/claude_native_subagent_guard.py" not in user_prompt_commands:
        issues.append(issue("NATIVE_SUBAGENT_GUARD_MISSING", "UserPromptSubmit must enforce native-only subagent requests.", CODEX_ROOT / "hooks.json"))
    subagent_start = (((hooks.get("hooks") or {}).get("SubagentStart") or [{}])[0])
    start_matcher = str(subagent_start.get("matcher") or "")
    start_hooks = subagent_start.get("hooks") if isinstance(subagent_start, dict) else []
    start_commands = [str(item.get("command") or "") for item in start_hooks if isinstance(item, dict)]
    if start_matcher != "^oag-":
        issues.append(issue("SUBAGENT_START_MATCHER", "SubagentStart must match OAG child agents.", CODEX_ROOT / "hooks.json"))
    if "python3 .claude/hooks/claude_subagent_oag_start.py" not in start_commands:
        issues.append(issue("SUBAGENT_START_HOOK_MISSING", "SubagentStart must inject the OAG child-work contract.", CODEX_ROOT / "hooks.json"))
    subagent = (((hooks.get("hooks") or {}).get("SubagentStop") or [{}])[0])
    matcher = str(subagent.get("matcher") or "")
    if "custom-researcher" in matcher or "custom-reviewer" in matcher:
        issues.append(issue("SUBAGENT_MATCHER_TOO_BROAD", "SubagentStop should only require receipts from write-capable evidence producers.", CODEX_ROOT / "hooks.json"))
    required_agents = ("rtl-implementation-agent", "tb-implementation-agent", "evidence-validator", "gate-reviewer")
    missing_agents = [agent for agent in required_agents if agent not in matcher]
    if missing_agents:
        issues.append(issue("SUBAGENT_MATCHER_MISSING_AGENT", f"SubagentStop matcher must include: {', '.join(missing_agents)}.", CODEX_ROOT / "hooks.json"))
    mode_trigger = CODEX_ROOT / "hooks" / "claude_oag_mode_trigger.py"
    if mode_trigger.is_file():
        text = read_text(mode_trigger)
        if "oag-mode-directive.md" not in text:
            issues.append(issue("OAG_DIRECTIVE_FILE_POLICY", "OAG mode trigger must load the file-backed directive.", mode_trigger))
        for stale_trigger in ("ipdev", "auto research", "autores", "multi-agent", "rocev"):
            if stale_trigger in text:
                issues.append(issue("OAG_TRIGGER_TOO_BROAD", f"OAG mode trigger must not match {stale_trigger!r}.", mode_trigger))


def check_config_policy(issues: list[dict[str, str]]) -> None:
    path = CODEX_ROOT / "config.toml"
    try:
        with path.open("rb") as fh:
            config = tomllib.load(fh)
    except Exception:
        return
    features = config.get("features") if isinstance(config.get("features"), dict) else {}
    agents = config.get("agents") if isinstance(config.get("agents"), dict) else {}
    if features.get("multi_agent") is not True:
        issues.append(issue("MULTI_AGENT_NOT_ENABLED", ".claude/config.toml must set [features].multi_agent = true.", path))
    if features.get("child_agents_md") is not True:
        issues.append(issue("CHILD_AGENTS_MD_NOT_ENABLED", ".claude/config.toml must set [features].child_agents_md = true.", path))
    if features.get("hooks") is not True:
        issues.append(issue("HOOKS_NOT_ENABLED", ".claude/config.toml must set [features].hooks = true.", path))
    multi_agent_v2 = features.get("multi_agent_v2")
    if isinstance(multi_agent_v2, bool):
        issues.append(issue("MULTI_AGENT_V2_BOOLEAN_POLICY", ".claude/config.toml must not use [features].multi_agent_v2 boolean shorthand.", path))
    if not isinstance(multi_agent_v2, dict) or multi_agent_v2.get("enabled") is not False:
        issues.append(issue("MULTI_AGENT_V2_ENABLED_POLICY", ".claude/config.toml must set [features.multi_agent_v2].enabled = false.", path))
    if not isinstance(multi_agent_v2, dict) or int(multi_agent_v2.get("max_concurrent_threads_per_session") or 0) < 10000:
        issues.append(issue("MULTI_AGENT_V2_LIMIT", ".claude/config.toml should set [features.multi_agent_v2].max_concurrent_threads_per_session = 10000.", path))
    if int(agents.get("max_depth") or 0) != 1:
        issues.append(issue("AGENT_DEPTH_POLICY", ".claude/config.toml should keep [agents].max_depth = 1 for predictable team release behavior.", path))


def check_mcp_policy(issues: list[dict[str, str]]) -> None:
    config_path = CODEX_ROOT / "config.toml"
    try:
        with config_path.open("rb") as fh:
            config = tomllib.load(fh)
    except Exception:
        config = {}
    mcp_servers = config.get("mcp_servers") if isinstance(config.get("mcp_servers"), dict) else {}
    for server_name in OAG_MCP_SERVER_NAMES:
        if server_name in mcp_servers:
            issues.append(issue("MCP_ENABLED_BY_DEFAULT", f"OAG must use scripts/skills by default; do not auto-register {server_name} MCP in config.toml.", config_path))

    mcp_path = CODEX_ROOT / "mcp.json"
    try:
        mcp_json = json.loads(mcp_path.read_text(encoding="utf-8"))
    except Exception:
        return
    configured = mcp_json.get("mcpServers") if isinstance(mcp_json.get("mcpServers"), dict) else {}
    for server_name in OAG_MCP_SERVER_NAMES:
        if server_name in configured:
            issues.append(issue("MCP_ENABLED_BY_DEFAULT", f"OAG must use scripts/skills by default; keep {server_name} out of mcp.json.", mcp_path))


def check_docs(issues: list[dict[str, str]]) -> None:
    for path, snippets in REQUIRED_DOC_SNIPPETS.items():
        if not path.is_file():
            continue
        text = read_text(path)
        for snippet in snippets:
            if snippet not in text:
                issues.append(issue("DOC_SNIPPET_MISSING", f"Document must mention {snippet!r}.", path))
        if "python3 scripts/" in text:
            issues.append(issue("DOC_STALE_SCRIPT_PATH", "Executable examples must use project-root .claude/scripts/... paths.", path))
        if re.search(r"\.claude/agents/[^\s`\"']+\.toml", text):
            issues.append(issue("DOC_STALE_AGENT_PATH", "Claude Code subagent docs must refer to .claude/agents/*.md markdown frontmatter files, not TOML agents.", path))


def check_forbidden_strings(issues: list[dict[str, str]]) -> None:
    roots = [CODEX_ROOT]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and not (SOURCE_SCAN_EXCLUDED_PARTS & set(path.relative_to(CODEX_ROOT).parts))
            )
    for path in files:
        if path.suffix in {".pyc"}:
            continue
        text = read_text(path)
        for forbidden in FORBIDDEN_STRINGS:
            if forbidden in text:
                issues.append(issue("FORBIDDEN_STRING", f"Forbidden workspace-specific or removed integration string: {forbidden}", path))


def build_result(issues: list[dict[str, str]], catalog: dict[str, Any]) -> dict[str, Any]:
    agent_markdowns = sorted((CODEX_ROOT / "agents").glob("*.md"))
    return {
        "schema_version": "oag_pack_release_check.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "status": "fail" if issues else "pass",
        "counts": {
            "agent_markdowns": len(agent_markdowns),
            "schemas": len(list(SCHEMAS_DIR.glob("*.schema.json"))) if SCHEMAS_DIR.is_dir() else 0,
            "issues": len(issues),
        },
        "catalog": {
            "status": catalog.get("status"),
            "counts": catalog.get("counts"),
            "completion_authority": catalog.get("completion_authority"),
            "final_decision_authority": catalog.get("final_decision_authority"),
        },
        "issues": issues,
    }


def check_pack() -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    check_required_files(issues)
    check_forbidden_files(issues)
    check_json_files(issues)
    check_toml_files(issues)
    check_python_compile(issues)
    catalog = check_catalog(issues)
    check_agent_loader_boundary(issues)
    check_hooks_policy(issues)
    check_config_policy(issues)
    check_mcp_policy(issues)
    check_docs(issues)
    check_forbidden_strings(issues)
    return build_result(issues, catalog)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the OAG Claude Code pack for team release.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    result = check_pack()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag pack release check")
    else:
        print("FAIL oag pack release check", file=sys.stderr)
        for item in result["issues"]:
            suffix = f" ({item['path']})" if "path" in item else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
