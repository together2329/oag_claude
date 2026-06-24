#!/usr/bin/env python3
"""Local OAG JSON tool-call gateway for Claude Code-managed IP development."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import oag_paths  # noqa: E402


RESPONSE_SCHEMA = "oag_tool_response.v1"
VALID_COMPLETION_ACTIONS = {"claim_complete", "close_obligation", "merge", "promote", "signoff"}
SCOREBOARD_REQUIRED_FIELDS = {
    "goal_id",
    "scenario_id",
    "cycle",
    "stimulus",
    "expected",
    "observed",
    "observed_source",
    "passed",
    "mismatch",
    "coverage_refs",
}
LEGACY_SCOREBOARD_FIELDS = {"fl_expected", "rtl_observed"}
OBSERVED_SOURCE_KINDS = {
    "dut_signal",
    "monitor",
    "waveform",
    "transaction",
    "assertion",
    "interface_sample",
    "bus_monitor",
}
MODEL_SOURCE_KINDS = {
    "behavior_model",
    "cycle_rules",
    "fl_model",
    "cl_model",
    "golden_model",
    "reference_model",
    "formal_property",
    "approved_equivalent_oracle",
    "model",
}
EXPECTED_ORACLE_SOURCE_KINDS = MODEL_SOURCE_KINDS | {"assertion", "golden_vector", "manual_spec", "reference_log"}
DUT_DERIVED_EXPECTED_SOURCE_KINDS = OBSERVED_SOURCE_KINDS | {
    "dut_output",
    "rtl_expression",
    "rtl_observed",
    "observed_dut_output",
    "post_hoc_simulation",
    "posthoc_simulation",
}
TRUTH_GRAPH_REL = Path("ontology/generated/design_truth_graph.json")
DESIGN_SPEC_REL = Path("ontology/generated/design_spec.json")
DESIGN_FACTS_REL = Path("ontology/generated/design_facts_graph.json")
COMPILE_MANIFEST_REL = Path("ontology/generated/compile_manifest.json")
AUTHORING_PACKETS_REL = Path("ontology/generated/authoring_packets")
STAGE_RECEIPTS_REL = Path("ontology/evidence/stage_runs")
DECISION_RECEIPTS_REL = Path("ontology/validations")
RUNS_REL = Path("ontology/runs")
METRICS_REL = Path("ontology/metrics")
HANDOFF_READINESS_REL = Path("handoff/readiness_handoff.json")
HANDOFF_READINESS_HISTORY_REL = Path("handoff/readiness_history.jsonl")
DESIGN_RULES_REL = Path("ontology/design_rules.yaml")
STRUCTURE_REL = Path("ontology/structure.yaml")
DECOMPOSITION_REL = Path("ontology/decomposition.yaml")
MODELING_REL = Path("ontology/modeling.yaml")
DOMAIN_INTENT_REL = Path("ontology/domain_intent.yaml")
TB_METHODOLOGY_REL = Path("ontology/tb_methodology.yaml")
VERIFICATION_PLAN_REL = Path("ontology/verification_plan.yaml")
POLICIES_REL = Path("ontology/policies.yaml")
EVIDENCE_PLAN_REL = Path("req/evidence_plan.yaml")
SCENARIO_MAPPING_REL = Path("sim/scenario_mapping.json")
SCOREBOARD_REL = Path("sim/scoreboard_events.jsonl")
DOMAIN_CROSSING_MATRIX_REL = Path("ontology/generated/domain_crossing_matrix.json")
TB_METHODOLOGY_MATRIX_REL = Path("ontology/generated/tb_methodology_matrix.json")
DRAFTS_REL = Path("ontology/drafts")
PROTECTION_REL = Path("ontology/protection.yaml")
SCOPE_LOCK_REL = Path("ontology/scope_lock.json")
LEDGER_REL = Path("knowledge/ledger.jsonl")
REQUIRED_DESIGN_RULE_KINDS = {
    "event_state_commit_consistency",
    "same_cycle_priority_declared",
    "scoreboard_evidence_schema",
    "contract_to_proof_coverage",
    "rtl_language_subset",
    "module_file_boundary",
}
FORMAL_CONTRACT_METHODS = {"formal", "assertion", "sva", "property", "proof"}
CLOSED_STATUSES = {"closed", "pass", "passed", "validated", "complete", "done", "signoff", "promoted"}
WEAKER_STATUSES = {"draft", "open", "partial", "pending", "unknown", "stale", "blocked"}
TERMINAL_RUN_STATUSES = {"complete", "parked", "needs_human"}
APPROVAL_ACTIONS = {"protected_change_approved", "human_approval", "approval"}
VALID_STRUCTURE_PROFILES = {"greenfield_modular", "small_leaf_single_file", "legacy_preserve", "wrapper_adapter"}
CURRENT_IP_OWNERSHIPS = {"current_ip", "manifest", "owned"}
EXTERNAL_OWNERSHIPS = {"legacy", "external", "child_ip", "child_ssot"}
VERIFICATION_REQUIRED_ROLES = ("sequence", "driver", "monitor", "reference_model", "scoreboard", "coverage", "env", "test")
SIGNOFF_DESIGN_RULE_KINDS = {
    "cdc_crossing_coverage": "CDC crossing coverage",
    "protocol_compliance": "protocol compliance",
    "timing_closure": "timing closure",
    "functional_coverage_closure": "functional coverage closure",
    "reset_xprop_coverage": "reset/X-prop coverage",
    "rtl_language_subset": "RTL language subset",
}
DOMAIN_CROSSING_CONTRACT_TYPES = {"cdc", "rdc", "cdc_rdc", "domain_crossing", "clock_reset_domain_crossing"}
POST_LOCK_ARTIFACT_PATTERNS = (
    "rtl/*.sv",
    "rtl/*.v",
    "rtl/*.svh",
    "tb/**/*.sv",
    "tb/**/*.v",
    "tb/**/*.py",
    "rtl/rtl_compile.json",
    "lint/dut_lint.json",
    "sim/results.xml",
    "sim/scoreboard_events.jsonl",
    "cov/coverage.json",
    "formal/*.json",
    "sdc/*.sdc",
    "signoff/*.json",
    "signoff/*.yaml",
)
RUN_LIMIT_STAGE_ORDER = {
    "none": -1,
    "requirements": 0,
    "rtl": 10,
    "lint": 15,
    "tb": 20,
    "formal": 25,
    "sim": 30,
    "coverage": 35,
    "signoff": 40,
    "all": 999,
}
RUN_LIMIT_ALIASES = {
    "": "",
    "none": "none",
    "off": "none",
    "disabled": "none",
    "disable": "none",
    "req": "requirements",
    "requirement": "requirements",
    "requirements": "requirements",
    "요구사항": "requirements",
    "rtl": "rtl",
    "lint": "lint",
    "tb": "tb",
    "testbench": "tb",
    "testbench만": "tb",
    "formal": "formal",
    "sim": "sim",
    "simulation": "sim",
    "시뮬": "sim",
    "시뮬레이션": "sim",
    "coverage": "coverage",
    "cov": "coverage",
    "signoff": "signoff",
    "사인오프": "signoff",
    "all": "all",
    "full": "all",
    "끝까지": "all",
}


def _tool_name(value: str) -> str:
    name = str(value or "").strip()
    if name.startswith("oag."):
        name = name[4:]
    if not name:
        raise ValueError("tool is required")
    return name


def _response(tool: str, ok: bool, result: Any = None, errors: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA,
        "ok": ok,
        "tool": f"oag.{_tool_name(tool)}" if tool else "",
        "result": result,
        "errors": errors or [],
    }


def _read_json(args: argparse.Namespace) -> dict[str, Any]:
    if args.json:
        payload = json.loads(args.json)
    elif args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("provide --json, --file, or JSON on stdin")
        payload = json.loads(raw)
    if args.tool:
        payload = {"tool": args.tool, "arguments": payload}
    if not isinstance(payload, dict):
        raise ValueError("tool-call envelope must be a JSON object")
    return payload


def _ip_dir(arguments: dict[str, Any]) -> Path:
    raw = arguments.get("ip_dir") or arguments.get("ip") or arguments.get("ip_root")
    if not raw:
        raise ValueError("arguments.ip_dir is required")
    # Resolve here so the IP base is consistent with oag_paths.* (which resolve
    # internally); otherwise `<resolver_path>.relative_to(ip)` mismatches on
    # platforms where the temp/real root differs (e.g. macOS /var -> /private/var).
    return Path(str(raw)).expanduser().resolve()


def _read_json_file(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_yaml_file(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _str_items(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _node_id_from(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _safe_filename(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return text or "unnamed"


def _structure_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(STRUCTURE_REL)))
    return data if isinstance(data, dict) else {}


def _decomposition_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(DECOMPOSITION_REL)))
    return data if isinstance(data, dict) else {}


def _policy_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(POLICIES_REL)))
    return data if isinstance(data, dict) else {}


def _modeling_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(MODELING_REL)))
    return data if isinstance(data, dict) else {}


def _domain_intent_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(DOMAIN_INTENT_REL)))
    return data if isinstance(data, dict) else {}


def _tb_methodology_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(TB_METHODOLOGY_REL)))
    return data if isinstance(data, dict) else {}


def _verification_plan_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(VERIFICATION_PLAN_REL)))
    return data if isinstance(data, dict) else {}


def _evidence_plan_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(ip / EVIDENCE_PLAN_REL)
    return data if isinstance(data, dict) else {}


def _write_yaml_file(path: Path, payload: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - PyYAML is expected in the OAG pack
        raise ValueError(f"PyYAML is required to write {path}: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _normalize_run_limit(value: Any, *, default: str = "all") -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    raw = re.sub(r"\s+", "", raw)
    if not raw:
        return default
    normalized = RUN_LIMIT_ALIASES.get(raw, raw)
    if normalized not in RUN_LIMIT_STAGE_ORDER:
        raise ValueError(
            "invalid hook_auto_continue_until: "
            f"{value!r}; expected one of {', '.join(RUN_LIMIT_STAGE_ORDER)}"
        )
    return normalized


def _execution_policy(ip: Path) -> dict[str, Any]:
    policies = _policy_doc(ip)
    execution = policies.get("execution_policy")
    return execution if isinstance(execution, dict) else {}


def _graph_policy(ip: Path) -> dict[str, Any]:
    policies = _policy_doc(ip)
    graph = policies.get("graph_policy")
    return graph if isinstance(graph, dict) else {}


def _hook_auto_continue_until(ip: Path) -> str:
    return _normalize_run_limit(_execution_policy(ip).get("hook_auto_continue_until"), default="all")


def _stop_hook_max_repeats(ip: Path, *, default: int = 3) -> int:
    value = _execution_policy(ip).get("stop_hook_max_repeats")
    try:
        repeats = int(value)
    except Exception:
        repeats = default
    return max(repeats, 0)


def _truthy_policy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _structure_profile(ip: Path, *, policies: dict[str, Any] | None = None, decomposition: dict[str, Any] | None = None) -> str:
    policies = policies if policies is not None else _policy_doc(ip)
    decomposition = decomposition if decomposition is not None else _decomposition_doc(ip)
    profile = decomposition.get("profile") if isinstance(decomposition.get("profile"), dict) else {}
    structure_policy = policies.get("structure_policy") if isinstance(policies.get("structure_policy"), dict) else {}
    return str(profile.get("mode") or structure_policy.get("default_profile") or "").strip()


def _structure_namespace_ids(structure: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("signals", "interfaces", "registers", "state", "derived_signals", "clock_domains", "reset_domains"):
        for item in _as_list(structure.get(key)):
            if isinstance(item, dict):
                ident = _node_id_from(item, "id", "name", "signal")
                if ident:
                    ids.add(ident)
            elif str(item).strip():
                ids.add(str(item).strip())
    return ids


def _module_items(decomposition: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _as_list(decomposition.get("modules")) if isinstance(item, dict)]


def _module_id(module: dict[str, Any]) -> str:
    return _node_id_from(module, "id", "name", "module")


def _current_ip_modules(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for module in modules:
        ownership = str(module.get("ownership") or "current_ip").strip()
        if ownership in CURRENT_IP_OWNERSHIPS:
            result.append(module)
    return result


def _decomposition_issues(
    ip: Path,
    *,
    req_ids: set[str] | None = None,
    obl_ids: set[str] | None = None,
    contract_ids: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    req_ids = req_ids or set()
    obl_ids = obl_ids or set()
    contract_ids = contract_ids or set()
    issues: list[str] = []
    policies = _policy_doc(ip)
    structure = _structure_doc(ip)
    domain_intent = _domain_intent_doc(ip)
    decomposition = _decomposition_doc(ip)
    modules = _module_items(decomposition)
    structure_policy = policies.get("structure_policy") if isinstance(policies.get("structure_policy"), dict) else {}
    profile_doc = decomposition.get("profile") if isinstance(decomposition.get("profile"), dict) else {}
    profile = _structure_profile(ip, policies=policies, decomposition=decomposition)

    if not oag_paths.legacy_or_hidden(ip, str(STRUCTURE_REL)).is_file():
        issues.append(f"missing {STRUCTURE_REL}")
    if not oag_paths.legacy_or_hidden(ip, str(DECOMPOSITION_REL)).is_file():
        issues.append(f"missing {DECOMPOSITION_REL}")
    if not structure_policy:
        issues.append("ontology/policies.yaml missing structure_policy")
    if not profile:
        issues.append("decomposition profile missing mode")
    elif profile not in VALID_STRUCTURE_PROFILES:
        issues.append(f"invalid structure profile: {profile}")
    if not str(profile_doc.get("rationale") or "").strip():
        issues.append("decomposition profile requires rationale")
    if not modules:
        issues.append("decomposition requires at least one module")

    namespace_ids = _structure_namespace_ids(structure)
    module_ids: set[str] = set()
    owned_obligations: set[str] = set()
    owned_contracts: set[str] = set()
    current_modules = _current_ip_modules(modules)
    legacy_sources = _as_list(decomposition.get("legacy_sources"))
    preserve_hierarchy = bool(decomposition.get("preserve_existing_hierarchy") or profile_doc.get("preserve_existing_hierarchy"))

    for module in modules:
        mid = _module_id(module)
        if not mid:
            issues.append("decomposition module without id/name")
            continue
        if mid in module_ids:
            issues.append(f"{mid}: duplicate decomposition module id")
        module_ids.add(mid)
        ownership = str(module.get("ownership") or "current_ip").strip()
        if ownership not in CURRENT_IP_OWNERSHIPS | EXTERNAL_OWNERSHIPS:
            issues.append(f"{mid}: invalid ownership {ownership}")
        if ownership in CURRENT_IP_OWNERSHIPS and not str(module.get("file") or "").strip():
            issues.append(f"{mid}: current_ip module requires file")
        if ownership in CURRENT_IP_OWNERSHIPS and str(module.get("edit_policy") or "editable") == "do_not_edit":
            issues.append(f"{mid}: current_ip module cannot be do_not_edit")
        if ownership in EXTERNAL_OWNERSHIPS and str(module.get("edit_policy") or "do_not_edit") == "editable":
            issues.append(f"{mid}: external/legacy/child module must not be editable by default")
        for oid in _str_items(module.get("owned_obligations") or module.get("obligations")):
            owned_obligations.add(oid)
            if obl_ids and oid not in obl_ids:
                issues.append(f"{mid}: owned obligation not found: {oid}")
        for cid in _str_items(module.get("owned_contracts") or module.get("contracts")):
            owned_contracts.add(cid)
            if contract_ids and cid not in contract_ids:
                issues.append(f"{mid}: owned contract not found: {cid}")
        for ref in _str_items(module.get("structure_refs")):
            if namespace_ids and ref not in namespace_ids:
                issues.append(f"{mid}: structure ref not found: {ref}")

    for oid in sorted(obl_ids - owned_obligations):
        issues.append(f"{oid}: obligation has no owning decomposition module")
    for cid in sorted(contract_ids - owned_contracts):
        issues.append(f"{cid}: contract has no owning decomposition module")

    if profile == "greenfield_modular" and len(current_modules) < 2:
        issues.append("greenfield_modular profile requires at least two current_ip modules or use small_leaf_single_file")
    if profile == "greenfield_modular":
        file_to_modules: dict[str, list[str]] = {}
        module_by_id = {_module_id(module): module for module in current_modules if _module_id(module)}
        for module in current_modules:
            rel = str(module.get("file") or "").strip()
            mid = _module_id(module)
            if rel and mid:
                file_to_modules.setdefault(rel, []).append(mid)
        profile_shared_rationale = str(
            profile_doc.get("shared_file_rationale")
            or profile_doc.get("file_boundary_exception")
            or profile_doc.get("module_file_boundary_exception")
            or ""
        ).strip()
        if profile_doc.get("allow_shared_module_files") is True and not profile_shared_rationale:
            issues.append("greenfield_modular shared module files require profile.shared_file_rationale")
        for rel, mids in sorted(file_to_modules.items()):
            if len(mids) < 2:
                continue
            module_rationales = [
                str(
                    module_by_id[mid].get("shared_file_rationale")
                    or module_by_id[mid].get("file_boundary_exception")
                    or module_by_id[mid].get("module_file_boundary_exception")
                    or ""
                ).strip()
                for mid in mids
                if mid in module_by_id
            ]
            has_exception = bool(profile_shared_rationale) or all(module_rationales)
            if not has_exception:
                issues.append(
                    "greenfield_modular module file boundary requires unique file per current_ip module: "
                    f"{rel} shared by {', '.join(mids)}"
                )
    if profile == "small_leaf_single_file" and len(current_modules) > 1:
        issues.append("small_leaf_single_file profile has multiple current_ip modules; use greenfield_modular")
    if profile == "legacy_preserve":
        has_legacy_module = any(str(module.get("ownership") or "") in {"legacy", "external"} for module in modules)
        if not legacy_sources and not has_legacy_module:
            issues.append("legacy_preserve profile requires legacy_sources or a legacy/external module")
        if not preserve_hierarchy:
            issues.append("legacy_preserve profile requires preserve_existing_hierarchy: true")
    if profile == "wrapper_adapter":
        has_wrapper = any(str(module.get("role") or "").lower() in {"wrapper", "adapter", "top_wrapper"} for module in modules)
        has_core = any(str(module.get("ownership") or "") in {"legacy", "external", "child_ip", "child_ssot"} or str(module.get("role") or "").lower() == "legacy_core" for module in modules)
        if not has_wrapper:
            issues.append("wrapper_adapter profile requires a wrapper/adapter module")
        if not has_core:
            issues.append("wrapper_adapter profile requires a legacy/external/child core module")

    summary = {
        "profile": profile,
        "modules": modules,
        "module_count": len(modules),
        "current_ip_module_count": len(current_modules),
        "structure_ids": sorted(namespace_ids),
        "legacy_sources": legacy_sources,
    }
    return issues, summary


def _git_head(ip: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ip), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _relative_to_ip(ip: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ip.resolve()))
    except Exception:
        return str(path)


def _expand_source_pattern(ip: Path, raw: str) -> list[Path]:
    value = os.path.expandvars(raw.strip())
    if not value or value.startswith(("+", "//", "#")):
        return []
    path = Path(value).expanduser()
    if any(ch in value for ch in "*?["):
        if path.is_absolute():
            import glob

            return sorted(Path(item) for item in glob.glob(str(path)))
        return sorted(ip.glob(value))
    return [path if path.is_absolute() else ip / path]


def _read_filelist_sources(ip: Path, filelist: Path, *, seen: set[Path] | None = None) -> list[Path]:
    seen = seen or set()
    filelist = filelist.resolve()
    if filelist in seen or not filelist.is_file():
        return []
    seen.add(filelist)
    sources: list[Path] = []
    for raw_line in filelist.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        idx = 0
        while idx < len(parts):
            token = parts[idx]
            if token in {"-f", "-F"} and idx + 1 < len(parts):
                for nested in _expand_source_pattern(ip, parts[idx + 1]):
                    sources.extend(_read_filelist_sources(ip, nested, seen=seen))
                idx += 2
                continue
            if token.startswith("-f") and len(token) > 2:
                for nested in _expand_source_pattern(ip, token[2:]):
                    sources.extend(_read_filelist_sources(ip, nested, seen=seen))
                idx += 1
                continue
            if token.startswith(("+incdir+", "+define+", "-I", "-D", "-y")):
                idx += 1
                continue
            for source in _expand_source_pattern(ip, token):
                if source.suffix in {".sv", ".v"} and source.is_file():
                    sources.append(source)
            idx += 1
    return sources


def _rtl_source_files(ip: Path, decomposition: dict[str, Any]) -> list[Path]:
    sources: list[Path] = []
    for path in _read_filelist_sources(ip, ip / "list" / "rtl.f"):
        sources.append(path)
    for module in _module_items(decomposition):
        rel = str(module.get("file") or "").strip()
        if rel:
            path = ip / rel
            if path.suffix in {".sv", ".v"} and path.is_file():
                sources.append(path)
    for pattern in ("rtl/**/*.sv", "rtl/**/*.v"):
        sources.extend(path for path in ip.glob(pattern) if path.is_file())
    unique: dict[str, Path] = {}
    for path in sources:
        unique[str(path.resolve())] = path.resolve()
    return [unique[key] for key in sorted(unique)]


def _sv_json_text(value: Any) -> str:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
            for child in item.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _sv_node_name(value: Any) -> str:
    if isinstance(value, dict):
        direct = value.get("text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        for key in ("name", "identifier", "decl"):
            found = _sv_node_name(value.get(key))
            if found:
                return found
    return ""


def _sv_dimensions(value: Any) -> list[str]:
    dims: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            kind = str(item.get("kind") or "")
            if "Dimension" in kind:
                text = _sv_json_text(item)
                if text:
                    dims.append(text)
                return
            for child in item.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return dims


def _extract_sv_with_pyslang(text: str, rel: str) -> tuple[list[dict[str, Any]], list[str]]:
    import pyslang  # type: ignore

    tree = pyslang.SyntaxTree.fromText(text)
    diagnostics = [str(item) for item in tree.diagnostics]
    data = json.loads(tree.to_json())
    root = data.get("root") if isinstance(data.get("root"), dict) else {}
    modules: list[dict[str, Any]] = []
    root_members = [root] if root.get("kind") == "ModuleDeclaration" else _as_list(root.get("members"))
    for member in root_members:
        if not isinstance(member, dict) or member.get("kind") != "ModuleDeclaration":
            continue
        name = _sv_node_name((member.get("header") or {}).get("name"))
        if not name:
            continue
        module = {
            "name": name,
            "source": {"file": rel, "line": None},
            "ports": [],
            "parameters": [],
            "declarations": [],
            "registers": [],
            "memories": [],
            "instances": [],
        }
        port_items = ((member.get("header") or {}).get("ports") or {}).get("ports")
        for port in _as_list(port_items):
            if not isinstance(port, dict) or "Port" not in str(port.get("kind") or ""):
                continue
            header = port.get("header") if isinstance(port.get("header"), dict) else {}
            declarator = port.get("declarator") if isinstance(port.get("declarator"), dict) else {}
            port_name = _sv_node_name(declarator.get("name") or port.get("name"))
            if not port_name:
                continue
            module["ports"].append(
                {
                    "name": port_name,
                    "direction": _sv_json_text(header.get("direction")) or "implicit",
                    "net_type": _sv_json_text(header.get("netType")),
                    "data_type": str((header.get("dataType") or {}).get("kind") or ""),
                    "packed_dimensions": _sv_dimensions(header.get("dataType")),
                    "unpacked_dimensions": _sv_dimensions(declarator),
                }
            )
        for item in _as_list(member.get("members")):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            if kind == "ParameterDeclarationStatement":
                parameter = item.get("parameter") if isinstance(item.get("parameter"), dict) else {}
                for decl in _as_list(parameter.get("declarators")):
                    if isinstance(decl, dict):
                        pname = _sv_node_name(decl.get("name"))
                        if pname:
                            module["parameters"].append({"name": pname, "type": _sv_json_text(parameter.get("type"))})
            elif kind == "DataDeclaration":
                type_text = _sv_json_text(item.get("type"))
                packed = _sv_dimensions(item.get("type"))
                for decl in _as_list(item.get("declarators")):
                    if not isinstance(decl, dict):
                        continue
                    dname = _sv_node_name(decl.get("name"))
                    if not dname:
                        continue
                    unpacked = _sv_dimensions(decl)
                    entry = {
                        "name": dname,
                        "type": type_text,
                        "packed_dimensions": packed,
                        "unpacked_dimensions": unpacked,
                    }
                    module["declarations"].append(entry)
                    if unpacked:
                        module["memories"].append(entry)
                    elif dname.endswith(("_q", "_r")) or "reg" in type_text:
                        module["registers"].append(entry)
            elif kind == "HierarchyInstantiation":
                inst_type = _sv_json_text(item.get("type"))
                for inst in _as_list(item.get("instances")):
                    if not isinstance(inst, dict):
                        continue
                    decl = inst.get("decl") if isinstance(inst.get("decl"), dict) else {}
                    iname = _sv_node_name(decl.get("name"))
                    if iname:
                        module["instances"].append({"name": iname, "module": inst_type, "connections": []})
        modules.append(module)
    return modules, diagnostics


def _find_matching_endmodule(text: str, start: int) -> int:
    match = re.search(r"\bendmodule\b", text[start:], flags=re.IGNORECASE)
    return start + match.end() if match else len(text)


def _extract_sv_with_regex(text: str, rel: str) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for match in re.finditer(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\s*(?:#\s*\((.*?)\)\s*)?\((.*?)\)\s*;", text, re.S):
        name = match.group(1)
        body_end = _find_matching_endmodule(text, match.end())
        body = text[match.end() : body_end]
        ports = []
        for raw_port in re.split(r",", match.group(3) or ""):
            item = raw_port.strip()
            if not item:
                continue
            tokens = item.split()
            port_name = re.sub(r"\W+$", "", tokens[-1]) if tokens else ""
            direction = tokens[0] if tokens and tokens[0] in {"input", "output", "inout", "ref"} else "implicit"
            if port_name:
                ports.append({"name": port_name, "direction": direction, "net_type": "", "data_type": "regex", "packed_dimensions": [], "unpacked_dimensions": []})
        parameters = [{"name": item.group(1), "type": "regex"} for item in re.finditer(r"\bparameter\b[^;]*?\b([A-Za-z_][A-Za-z0-9_$]*)\s*=", body)]
        declarations = []
        registers = []
        memories = []
        for decl in re.finditer(r"\b(?:logic|reg|wire)\b\s*(\[[^\]]+\])?\s*([A-Za-z_][A-Za-z0-9_$]*)\s*(\[[^\]]+\])?\s*;", body):
            entry = {
                "name": decl.group(2),
                "type": decl.group(0).split()[0],
                "packed_dimensions": [decl.group(1)] if decl.group(1) else [],
                "unpacked_dimensions": [decl.group(3)] if decl.group(3) else [],
            }
            declarations.append(entry)
            if entry["unpacked_dimensions"]:
                memories.append(entry)
            elif entry["name"].endswith(("_q", "_r")) or entry["type"] == "reg":
                registers.append(entry)
        instances = []
        for inst in re.finditer(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_$]*)\s*(?:#\s*\([^;]*?\)\s*)?([A-Za-z_][A-Za-z0-9_$]*)\s*\(", body):
            inst_type, inst_name = inst.group(1), inst.group(2)
            if inst_type not in {"if", "for", "while", "case", "assign", "always_ff", "always_comb", "always"}:
                instances.append({"name": inst_name, "module": inst_type, "connections": []})
        modules.append(
            {
                "name": name,
                "source": {"file": rel, "line": _line_number(text, match.start())},
                "ports": ports,
                "parameters": parameters,
                "declarations": declarations,
                "registers": registers,
                "memories": memories,
                "instances": instances,
            }
        )
    return modules


def _extract_design_facts(ip: Path, decomposition: dict[str, Any], profile: str) -> dict[str, Any]:
    source_files = _rtl_source_files(ip, decomposition)
    backend = "regex_fallback"
    backend_errors: list[str] = []
    try:
        import pyslang  # noqa: F401

        backend = "pyslang"
    except Exception as exc:
        backend_errors.append(f"pyslang unavailable: {exc}")

    source_facts: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in source_files:
        rel = _relative_to_ip(ip, path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        source_facts.append({"path": rel, "sha256": _sha256(path), "bytes": path.stat().st_size})
        file_modules: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        if backend == "pyslang":
            try:
                file_modules, diagnostics = _extract_sv_with_pyslang(text, rel)
            except Exception as exc:
                backend_errors.append(f"{rel}: pyslang extraction failed, used regex fallback: {exc}")
                file_modules = _extract_sv_with_regex(text, rel)
        else:
            file_modules = _extract_sv_with_regex(text, rel)
        for module in file_modules:
            if module.get("source", {}).get("line") is None:
                match = re.search(rf"\bmodule\s+{re.escape(str(module.get('name') or ''))}\b", text)
                module["source"]["line"] = _line_number(text, match.start()) if match else 1
        if diagnostics:
            source_facts[-1]["diagnostics"] = diagnostics[:20]
        modules.extend(file_modules)

    modules_by_name: dict[str, list[dict[str, Any]]] = {}
    for module in modules:
        modules_by_name.setdefault(str(module.get("name") or ""), []).append(module)
    for name, items in sorted(modules_by_name.items()):
        if name and len(items) > 1:
            issues.append(f"design_facts: duplicate RTL module extracted: {name}")

    authored_modules = _module_items(decomposition)
    authored_by_id = {_module_id(item): item for item in authored_modules if _module_id(item)}
    authored_names = {str(item.get("name") or _module_id(item) or "").strip() for item in authored_modules}
    authored_names.update(authored_by_id)
    extracted_names = {name for name in modules_by_name if name}
    for mid, module in sorted(authored_by_id.items()):
        ownership = str(module.get("ownership") or "current_ip").strip()
        rel = str(module.get("file") or "").strip()
        if ownership not in CURRENT_IP_OWNERSHIPS or not rel or not (ip / rel).is_file():
            continue
        expected = {mid, str(module.get("name") or mid).strip()}
        found_in_file = {
            str(item.get("name") or "")
            for item in modules
            if str((item.get("source") or {}).get("file") or "") == rel
        }
        if not (expected & found_in_file):
            issues.append(f"design_facts: {mid} not found in extracted RTL facts for {rel}")
    if profile in {"greenfield_modular", "wrapper_adapter"}:
        for name in sorted(extracted_names - {item for item in authored_names if item}):
            issues.append(f"design_facts: extracted RTL module is not mapped in ontology/decomposition.yaml: {name}")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for module in modules:
        name = str(module.get("name") or "")
        if not name:
            continue
        module_node = f"fact::module::{name}"
        nodes.append({"id": module_node, "type": "design_fact_module", "label": name, "source": module.get("source")})
        for port in module.get("ports") or []:
            pname = str(port.get("name") or "")
            if not pname:
                continue
            pid = f"{module_node}::port::{pname}"
            nodes.append({"id": pid, "type": "design_fact_port", "label": pname, "direction": port.get("direction")})
            edges.append({"source": module_node, "target": pid, "type": "has_port"})
        for reg in module.get("registers") or []:
            rname = str(reg.get("name") or "")
            if rname:
                rid = f"{module_node}::register::{rname}"
                nodes.append({"id": rid, "type": "design_fact_register", "label": rname})
                edges.append({"source": module_node, "target": rid, "type": "has_register"})
        for mem in module.get("memories") or []:
            mname = str(mem.get("name") or "")
            if mname:
                mem_id = f"{module_node}::memory::{mname}"
                nodes.append({"id": mem_id, "type": "design_fact_memory", "label": mname})
                edges.append({"source": module_node, "target": mem_id, "type": "has_memory"})
        for inst in module.get("instances") or []:
            iname = str(inst.get("name") or "")
            child = str(inst.get("module") or "")
            if not iname:
                continue
            iid = f"{module_node}::instance::{iname}"
            nodes.append({"id": iid, "type": "design_fact_instance", "label": iname, "module": child})
            edges.append({"source": module_node, "target": iid, "type": "has_instance"})
            if child:
                edges.append({"source": iid, "target": f"fact::module::{child}", "type": "instantiates"})

    stats = {
        "rtl_source_files": len(source_files),
        "modules": len(modules),
        "ports": sum(len(module.get("ports") or []) for module in modules),
        "parameters": sum(len(module.get("parameters") or []) for module in modules),
        "declarations": sum(len(module.get("declarations") or []) for module in modules),
        "registers": sum(len(module.get("registers") or []) for module in modules),
        "memories": sum(len(module.get("memories") or []) for module in modules),
        "instances": sum(len(module.get("instances") or []) for module in modules),
    }
    return {
        "schema_version": "oag_design_facts_graph.v1",
        "generated_by": "oag.compile",
        "generated_at": _now(),
        "ip": ip.name,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "extractor": {
            "backend": backend,
            "backend_errors": backend_errors,
        },
        "source_files": source_facts,
        "stats": stats,
        "modules": modules,
        "nodes": nodes,
        "edges": edges,
    }


def _write_design_facts_graph(ip: Path, decomposition: dict[str, Any], profile: str) -> dict[str, Any]:
    path = oag_paths.state_path(ip, str(DESIGN_FACTS_REL))
    path.parent.mkdir(parents=True, exist_ok=True)
    facts = _extract_design_facts(ip, decomposition, profile)
    return _write_json_semantic_stable(path, facts, volatile_keys={"generated_at"})


def _write_domain_crossing_matrix(ip: Path) -> dict[str, Any]:
    domain_intent = _domain_intent_doc(ip)
    clock_domains = [item for item in _as_list(domain_intent.get("clock_domains")) if isinstance(item, dict)]
    reset_domains = [item for item in _as_list(domain_intent.get("reset_domains")) if isinstance(item, dict)]
    cdc = [item for item in _as_list(domain_intent.get("cdc_crossings")) if isinstance(item, dict)]
    rdc = [item for item in _as_list(domain_intent.get("rdc_crossings")) if isinstance(item, dict)]
    async_inputs = [item for item in _as_list(domain_intent.get("async_inputs")) if isinstance(item, dict)]
    clock_ids = sorted({_domain_item_id(item, "clock") for item in clock_domains if _domain_item_id(item, "clock")})
    reset_ids = sorted({_domain_item_id(item, "reset") for item in reset_domains if _domain_item_id(item, "reset")})
    matrix = {
        "schema_version": "oag_domain_crossing_matrix.v1",
        "generated_by": "oag.compile",
        "generated_at": _now(),
        "ip": ip.name,
        "source": str(DOMAIN_INTENT_REL),
        "status": "present" if domain_intent else "missing",
        "clock_domains": clock_ids,
        "reset_domains": reset_ids,
        "async_inputs": [
            {
                "id": _domain_item_id(item, "signal"),
                "signal": str(item.get("signal") or ""),
                "classification": str(item.get("classification") or ""),
                "required_mitigation": str(item.get("required_mitigation") or item.get("allowed_pattern") or ""),
            }
            for item in async_inputs
        ],
        "cdc_crossings": [
            {
                "id": _domain_item_id(item, "source"),
                "source": str(item.get("source") or ""),
                "source_domain": str(item.get("source_domain") or item.get("source") or ""),
                "destination_domain": str(item.get("destination_domain") or item.get("destination") or ""),
                "crossing_type": str(item.get("crossing_type") or item.get("classification") or ""),
                "allowed_pattern": str(item.get("allowed_pattern") or item.get("mitigation") or ""),
            }
            for item in cdc
        ],
        "rdc_crossings": [
            {
                "id": _domain_item_id(item, "classification"),
                "classification": str(item.get("classification") or ""),
                "source_reset_domain": str(item.get("source_reset_domain") or item.get("source_reset") or ""),
                "destination_reset_domain": str(item.get("destination_reset_domain") or item.get("destination_reset") or ""),
                "mitigation": str(item.get("mitigation") or item.get("reset_sequence") or item.get("isolation") or ""),
            }
            for item in rdc
        ],
        "stats": {
            "clock_domains": len(clock_ids),
            "reset_domains": len(reset_ids),
            "async_inputs": len(async_inputs),
            "cdc_crossings": len(cdc),
            "rdc_crossings": len(rdc),
        },
    }
    path = oag_paths.state_path(ip, str(DOMAIN_CROSSING_MATRIX_REL))
    path.parent.mkdir(parents=True, exist_ok=True)
    return _write_json_semantic_stable(path, matrix, volatile_keys={"generated_at"})


def _write_tb_methodology_matrix(ip: Path) -> dict[str, Any]:
    tb_methodology = _tb_methodology_doc(ip)
    policy = tb_methodology.get("methodology_policy") if isinstance(tb_methodology.get("methodology_policy"), dict) else {}
    roles = tb_methodology.get("architecture_roles") if isinstance(tb_methodology.get("architecture_roles"), dict) else {}
    stimulus = tb_methodology.get("stimulus_strategy") if isinstance(tb_methodology.get("stimulus_strategy"), dict) else {}
    coverage_goals = [item for item in _as_list(tb_methodology.get("coverage_goals")) if isinstance(item, dict)]
    assertion_candidates = [item for item in _as_list(tb_methodology.get("assertion_candidates")) if isinstance(item, dict)]
    formal_candidates = [item for item in _as_list(tb_methodology.get("formal_candidates")) if isinstance(item, dict)]
    matrix = {
        "schema_version": "oag_tb_methodology_matrix.v1",
        "generated_by": "oag.compile",
        "generated_at": _now(),
        "ip": ip.name,
        "source": str(TB_METHODOLOGY_REL),
        "status": "present" if tb_methodology else "missing",
        "profile": str(policy.get("profile") or ""),
        "framework_required": policy.get("framework_required"),
        "full_uvm_required": policy.get("full_uvm_required"),
        "default_depth": str(policy.get("default_depth") or ""),
        "roles": sorted(str(role) for role in roles if str(role).strip()),
        "stimulus": {
            "directed_smoke": stimulus.get("directed_smoke"),
            "table_driven_register_tests": stimulus.get("table_driven_register_tests"),
            "constrained_random": stimulus.get("constrained_random") if isinstance(stimulus.get("constrained_random"), dict) else {},
        },
        "coverage_goals": [
            {
                "id": str(item.get("id") or item.get("name") or item.get("coverage_ref") or ""),
                "requirement": str(item.get("requirement") or item.get("requirement_id") or ""),
                "obligation": str(item.get("obligation") or item.get("obligation_id") or ""),
                "contract": str(item.get("contract") or item.get("contract_id") or ""),
            }
            for item in coverage_goals
        ],
        "assertion_candidates": [
            str(item.get("id") or item.get("property") or item.get("name") or "")
            for item in assertion_candidates
        ],
        "formal_candidates": [
            str(item.get("id") or item.get("property") or item.get("name") or "")
            for item in formal_candidates
        ],
        "stats": {
            "roles": len(roles),
            "coverage_goals": len(coverage_goals),
            "assertion_candidates": len(assertion_candidates),
            "formal_candidates": len(formal_candidates),
        },
    }
    path = oag_paths.state_path(ip, str(TB_METHODOLOGY_MATRIX_REL))
    path.parent.mkdir(parents=True, exist_ok=True)
    return _write_json_semantic_stable(path, matrix, volatile_keys={"generated_at"})


def _write_generated_design_views(
    ip: Path,
    *,
    profile: str,
    structure: dict[str, Any],
    decomposition: dict[str, Any],
    reqs: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    issues: list[str],
) -> dict[str, Any]:
    generated = oag_paths.state_path(ip, "ontology/generated")
    generated.mkdir(parents=True, exist_ok=True)
    modules = _module_items(decomposition)
    req_by_id = {str(item.get("id") or ""): item for item in reqs if item.get("id")}
    obl_by_id = {str(item.get("id") or ""): item for item in obligations if item.get("id")}
    contract_by_id = {str(item.get("id") or ""): item for item in contracts if item.get("id")}
    modeling = _modeling_doc(ip)
    domain_intent = _domain_intent_doc(ip)
    tb_methodology = _tb_methodology_doc(ip)
    verification_plan = _verification_plan_doc(ip)

    def contract_ref_list(contract: dict[str, Any], *keys: str) -> list[str]:
        refs: list[str] = []
        oracle = contract.get("oracle") if isinstance(contract.get("oracle"), dict) else {}
        projection = contract.get("verification_projection") if isinstance(contract.get("verification_projection"), dict) else {}
        for key in keys:
            refs.extend(_str_items(contract.get(key)))
            refs.extend(_str_items(oracle.get(key)))
            refs.extend(_str_items(projection.get(key)))
        return sorted(set(refs))

    all_contract_ids = sorted(str(item.get("id") or item.get("contract_id") or "").strip() for item in contracts if str(item.get("id") or item.get("contract_id") or "").strip())
    all_behavior_refs = sorted(set(ref for contract in contracts for ref in contract_ref_list(contract, "behavior_refs", "fl_model_refs", "cl_model_refs")))
    all_cycle_refs = sorted(set(ref for contract in contracts for ref in contract_ref_list(contract, "cycle_rule_refs", "protocol_refs", "property_refs")))
    all_scenarios = sorted(set(ref for contract in contracts for ref in contract_ref_list(contract, "scenario_refs", "scenarios")))
    all_scoreboard_rows = sorted(set(ref for contract in contracts for ref in contract_ref_list(contract, "scoreboard_row_refs", "scoreboard_rows")))
    all_assertion_candidates = sorted(set(ref for contract in contracts for ref in contract_ref_list(contract, "assertion_refs", "assertion_props", "property_refs")))
    all_formal_goals = sorted(set(ref for contract in contracts for ref in contract_ref_list(contract, "formal_goals")))
    for objective in _as_list(verification_plan.get("verification_objectives")):
        if not isinstance(objective, dict):
            continue
        all_scenarios = sorted(set([*all_scenarios, *_str_items(objective.get("scenarios")), *_str_items(objective.get("negative_scenarios"))]))
        all_assertion_candidates = sorted(set([*all_assertion_candidates, *_str_items(objective.get("assertion_candidates"))]))
        all_formal_goals = sorted(set([*all_formal_goals, *_str_items(objective.get("formal_candidates"))]))
    design_spec = {
        "schema_version": "oag_generated_design_spec.v1",
        "generated_by": "oag.compile",
        "generated_at": _now(),
        "ip": ip.name,
        "source_files": [
            str(STRUCTURE_REL),
            str(DECOMPOSITION_REL),
            "ontology/requirements.yaml",
            "ontology/obligations.yaml",
            "ontology/contracts.yaml",
            "ontology/policies.yaml",
            str(MODELING_REL),
            str(DOMAIN_INTENT_REL),
            str(TB_METHODOLOGY_REL),
            str(VERIFICATION_PLAN_REL),
        ],
        "structure_profile": profile,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "structure": {
            "clock_domains": structure.get("clock_domains") or [],
            "reset_domains": structure.get("reset_domains") or [],
            "signals": structure.get("signals") or [],
            "interfaces": structure.get("interfaces") or [],
            "registers": structure.get("registers") or [],
            "state": structure.get("state") or [],
            "derived_signals": structure.get("derived_signals") or [],
        },
        "modules": modules,
    }
    design_spec_path = oag_paths.state_path(ip, str(DESIGN_SPEC_REL))
    design_spec_path.parent.mkdir(parents=True, exist_ok=True)
    design_spec = _write_json_semantic_stable(design_spec_path, design_spec, volatile_keys={"generated_at"})

    packets_dir = oag_paths.state_path(ip, str(AUTHORING_PACKETS_REL))
    packets_dir.mkdir(parents=True, exist_ok=True)
    packets: list[dict[str, Any]] = []
    live_packet_paths: set[Path] = set()
    for module in modules:
        mid = _module_id(module)
        if not mid:
            continue
        obligation_ids = _str_items(module.get("owned_obligations") or module.get("obligations"))
        contract_ids = _str_items(module.get("owned_contracts") or module.get("contracts"))
        ownership = str(module.get("ownership") or "current_ip").strip()
        editable = ownership in CURRENT_IP_OWNERSHIPS and str(module.get("edit_policy") or "editable") != "do_not_edit"
        packet = {
            "schema_version": "oag_authoring_packet.v1",
            "generated_by": "oag.compile",
            "generated_at": _now(),
            "ip": ip.name,
            "module": {
                "id": mid,
                "name": str(module.get("name") or mid),
                "role": str(module.get("role") or ""),
                "ownership": ownership,
                "file": str(module.get("file") or ""),
                "edit_policy": str(module.get("edit_policy") or ("editable" if editable else "do_not_edit")),
            },
            "structure_profile": profile,
            "source_refs": _str_items(module.get("source_refs")),
            "structure_refs": _str_items(module.get("structure_refs")),
            "obligations": [obl_by_id.get(oid, {"id": oid, "missing": True}) for oid in obligation_ids],
            "contracts": [contract_by_id.get(cid, {"id": cid, "missing": True}) for cid in contract_ids],
            "requirements": [
                req_by_id.get(str(obl_by_id.get(oid, {}).get("requirement") or ""), {})
                for oid in obligation_ids
                if str(obl_by_id.get(oid, {}).get("requirement") or "")
            ],
            "execution_policy": {
                "draft_allowed": editable,
                "pass_allowed": editable,
                "signoff_allowed": False,
                "notes": "Signoff requires oag.check and oag.decide; authoring packets are work inputs, not closure decisions.",
            },
        }
        packet_path = packets_dir / f"module__{_safe_filename(mid)}.json"
        _write_json_semantic_stable(packet_path, packet, volatile_keys={"generated_at"})
        live_packet_paths.add(packet_path)
        packets.append({"module": mid, "path": str(packet_path.relative_to(ip)), "editable": editable})
    rtl_packet = {
        "schema_version": "oag_rtl_authoring_packet.v1",
        "packet_type": "rtl_authoring_packet",
        "generated_by": "oag.compile",
        "generated_at": _now(),
        "ip": ip.name,
        "allowed_truth_sources": [
            "ontology/contracts.yaml",
            str(MODELING_REL),
            str(DOMAIN_INTENT_REL),
            str(STRUCTURE_REL),
            str(DECOMPOSITION_REL),
        ],
        "forbidden_sources": ["tb/", "sim/scoreboard_events.jsonl", "observed DUT behavior"],
        "structure_profile": profile,
        "top_interface_refs": _str_items(structure.get("interfaces")),
        "contract_refs_to_implement": all_contract_ids,
        "behavior_refs_implemented_target": all_behavior_refs,
        "cycle_rule_refs_implemented_target": all_cycle_refs,
        "domain_intent_source": str(DOMAIN_INTENT_REL),
        "ppa_notes_required": True,
        "cdc_rdc_notes_required": True,
        "notes": "RTL implements locked contracts; it must not derive expected behavior from TB or simulation artifacts.",
    }
    tb_packet = {
        "schema_version": "oag_tb_authoring_packet.v1",
        "packet_type": "tb_authoring_packet",
        "generated_by": "oag.compile",
        "generated_at": _now(),
        "ip": ip.name,
        "allowed_truth_sources": [
            "ontology/contracts.yaml",
            str(MODELING_REL),
            str(TB_METHODOLOGY_REL),
            str(VERIFICATION_PLAN_REL),
            "req/evidence_plan.yaml",
        ],
        "expected_source_policy": "contract_oracle_only",
        "forbidden_expected_sources": ["dut_output", "rtl_expression", "post_hoc_simulation", "observed DUT behavior"],
        "scenario_refs": all_scenarios,
        "scoreboard_row_refs": all_scoreboard_rows,
        "coverage_goal_refs": [
            str(item.get("id") or item.get("coverage_ref") or "")
            for item in _as_list(tb_methodology.get("coverage_goals"))
            if isinstance(item, dict) and str(item.get("id") or item.get("coverage_ref") or "").strip()
        ],
        "assertion_candidates": all_assertion_candidates,
        "formal_candidates": all_formal_goals,
        "contract_refs": all_contract_ids,
        "notes": "TB predicts from contracts and modeling truth; DUT output and RTL expressions are forbidden expected sources.",
    }
    evidence_packet = {
        "schema_version": "oag_evidence_authoring_packet.v1",
        "packet_type": "evidence_authoring_packet",
        "generated_by": "oag.compile",
        "generated_at": _now(),
        "ip": ip.name,
        "contract_refs": all_contract_ids,
        "scenario_refs": all_scenarios,
        "scoreboard_row_refs": all_scoreboard_rows,
        "required_artifacts": ["sim/results.xml", "sim/scenario_mapping.json", "sim/scoreboard_events.jsonl", "cov/coverage.json"],
        "validation_policy": "source_to_contract_to_evidence_trace_required",
    }
    for filename, packet in (
        (f"rtl__{_safe_filename(ip.name)}.json", rtl_packet),
        (f"tb__{_safe_filename(ip.name)}.json", tb_packet),
        (f"evidence__{_safe_filename(ip.name)}.json", evidence_packet),
    ):
        packet_path = packets_dir / filename
        _write_json_semantic_stable(packet_path, packet, volatile_keys={"generated_at"})
        live_packet_paths.add(packet_path)
        packets.append({"module": "", "path": str(packet_path.relative_to(ip)), "editable": False, "packet_type": packet.get("packet_type")})
    for stale in packets_dir.glob("*.json"):
        if stale not in live_packet_paths:
            stale.unlink()

    return {
        "design_spec": str(design_spec_path),
        "authoring_packets": packets,
        "authoring_packet_count": len(packets),
    }


def _normal_status(value: Any) -> str:
    return str(value or "").lower().strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_volatile_keys(value: Any, volatile_keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_volatile_keys(item, volatile_keys)
            for key, item in value.items()
            if key not in volatile_keys
        }
    if isinstance(value, list):
        return [_strip_volatile_keys(item, volatile_keys) for item in value]
    return value


def _write_json_semantic_stable(path: Path, payload: dict[str, Any], *, volatile_keys: set[str]) -> dict[str, Any]:
    current = _read_json_file(path)
    if isinstance(current, dict) and _strip_volatile_keys(current, volatile_keys) == _strip_volatile_keys(payload, volatile_keys):
        for key in volatile_keys:
            if key in current and key in payload:
                payload[key] = current[key]
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return payload
        except Exception:
            pass
    path.write_text(text, encoding="utf-8")
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _ledger_path(ip: Path) -> Path:
    return oag_paths.legacy_or_hidden(ip, str(LEDGER_REL))


def _protection_policy(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, str(PROTECTION_REL)))
    return data if isinstance(data, dict) else {}


def _protected_paths(ip: Path) -> list[str]:
    policy = _protection_policy(ip)
    paths = [str(item).strip() for item in _as_list(policy.get("protected_paths")) if str(item).strip()]
    return sorted(dict.fromkeys(paths))


def _resolve_state_rel(ip: Path, rel: str) -> Path:
    """Resolve an IP-relative path: route ontology/ and knowledge/ through the
    .oag-aware resolver, leave all other (top-level) subtrees as ip / rel."""
    try:
        if Path(rel).parts[:1] in (("ontology",), ("knowledge",)):
            return oag_paths.legacy_or_hidden(ip, str(rel))
    except ValueError:
        pass
    return ip / rel


def _protected_snapshot(ip: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for rel in _protected_paths(ip):
        path = _resolve_state_rel(ip, rel)
        snapshot[rel] = _sha256(path) if path.is_file() else "missing"
    return snapshot


def _ledger_entries(ip: Path) -> list[dict[str, Any]]:
    path = _ledger_path(ip)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except Exception:
            entries.append({"_invalid": line})
            continue
        entries.append(data if isinstance(data, dict) else {"_invalid": line})
    return entries


def _last_ledger_entry(ip: Path) -> dict[str, Any] | None:
    entries = [entry for entry in _ledger_entries(ip) if "_invalid" not in entry]
    return entries[-1] if entries else None


@contextmanager
def _ledger_append_lock(ip: Path):
    lock_path = oag_paths.state_path(ip, "knowledge/.ledger.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_human_approved(value: dict[str, Any]) -> bool:
    action = str(value.get("action") or "").lower()
    if action in APPROVAL_ACTIONS:
        return True
    actor = value.get("actor") if isinstance(value.get("actor"), dict) else {}
    if str(actor.get("kind") or "").lower() == "human":
        return True
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else value
    approval = payload.get("approval") if isinstance(payload.get("approval"), dict) else {}
    if str(approval.get("kind") or "").lower() == "human" or approval.get("approved") is True:
        return True
    approved_by = payload.get("approved_by")
    return bool(approved_by and str(approved_by).strip())


def _protected_snapshot_delta(ip: Path) -> list[str]:
    last = _last_ledger_entry(ip)
    if not isinstance(last, dict):
        return []
    previous = last.get("protected_snapshot")
    if not isinstance(previous, dict):
        return []
    current = _protected_snapshot(ip)
    changed: list[str] = []
    for rel in sorted(set(previous) | set(current)):
        if previous.get(rel) != current.get(rel):
            changed.append(rel)
    return changed


def _assert_ledger_append_allowed(ip: Path, *, action: str, actor: dict[str, Any], payload: dict[str, Any]) -> None:
    changed_protected = _protected_snapshot_delta(ip)
    candidate = {"action": action, "actor": actor, "payload": payload}
    if changed_protected and not _is_human_approved(candidate):
        raise ValueError(f"protected fields changed without human approval: {', '.join(changed_protected)}")


def _append_ledger(
    ip: Path,
    *,
    action: str,
    actor: dict[str, Any],
    subject: str,
    payload: dict[str, Any],
    monotonic_subjects: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    _ensure_knowledge(ip)
    with _ledger_append_lock(ip):
        _assert_ledger_append_allowed(ip, action=action, actor=actor, payload=payload)

        path = _ledger_path(ip)
        last = _last_ledger_entry(ip)
        prev_hash = str(last.get("event_hash")) if isinstance(last, dict) and last.get("event_hash") else "GENESIS"
        body = {
            "schema_version": "oag_evidence_ledger_event.v1",
            "event_id": f"LEDGER_{_stamp()}_{_slug(action)}",
            "created_at": _now(),
            "ip": ip.name,
            "action": action,
            "actor": actor,
            "subject": subject,
            "payload": payload,
            "payload_hash": _hash_value(payload),
            "prev_hash": prev_hash,
            "protected_snapshot": _protected_snapshot(ip),
            "monotonic_subjects": monotonic_subjects or [],
        }
        body["event_hash"] = _hash_value({key: value for key, value in body.items() if key != "event_hash"})
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
    return body


def _ledger_issues(ip: Path) -> list[str]:
    path = _ledger_path(ip)
    if not path.is_file():
        return [f"missing append-only ledger: {LEDGER_REL}"]
    issues: list[str] = []
    previous = "GENESIS"
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            issues.append(f"{LEDGER_REL} line {line_no}: invalid JSON")
            continue
        if not isinstance(event, dict):
            issues.append(f"{LEDGER_REL} line {line_no}: event must be an object")
            continue
        if event.get("prev_hash") != previous:
            issues.append(f"{LEDGER_REL} line {line_no}: prev_hash mismatch")
        payload = event.get("payload")
        if event.get("payload_hash") != _hash_value(payload):
            issues.append(f"{LEDGER_REL} line {line_no}: payload_hash mismatch")
        expected = _hash_value({key: value for key, value in event.items() if key != "event_hash"})
        if event.get("event_hash") != expected:
            issues.append(f"{LEDGER_REL} line {line_no}: event_hash mismatch")
        previous = str(event.get("event_hash") or "")
    return issues


def _protection_issues(ip: Path) -> list[str]:
    if not oag_paths.legacy_or_hidden(ip, "ontology").is_dir():
        return []
    policy_path = oag_paths.legacy_or_hidden(ip, str(PROTECTION_REL))
    policy = _protection_policy(ip)
    issues: list[str] = []
    if not policy_path.is_file():
        return [f"missing {PROTECTION_REL}"]
    protected_paths = _as_list(policy.get("protected_paths"))
    protected_fields = _as_list(policy.get("protected_fields"))
    if not protected_paths:
        issues.append(f"{PROTECTION_REL} declares no protected_paths")
    if not protected_fields:
        issues.append(f"{PROTECTION_REL} declares no protected_fields")
    for rel in [str(item).strip() for item in protected_paths if str(item).strip()]:
        if not _resolve_state_rel(ip, rel).exists():
            issues.append(f"{PROTECTION_REL} protected path missing on disk: {rel}")
    changed = _protected_snapshot_delta(ip)
    if changed:
        issues.append(f"protected fields changed without ledger approval: {', '.join(changed)}")
    return issues


def _yaml_items(ip: Path, rel: str, key: str) -> list[dict[str, Any]]:
    if Path(rel).parts[:1] in (("ontology",), ("knowledge",)):
        path = oag_paths.legacy_or_hidden(ip, str(rel))
    else:
        path = ip / rel
    data = _read_yaml_file(path)
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return [item for item in data[key] if isinstance(item, dict)]
    if not path.is_file():
        return []
    items: list[dict[str, Any]] = []
    for match in re.finditer(r"(?m)^\s*-\s*id\s*:\s*([A-Za-z0-9_.:-]+)", path.read_text(encoding="utf-8", errors="ignore")):
        items.append({"id": match.group(1)})
    return items


def _flatten_model_refs(value: Any, prefix: str) -> set[str]:
    refs: set[str] = set()

    def walk(node: Any, path: list[str]) -> None:
        if path:
            refs.add(f"{prefix}.{'.'.join(path)}")
        if isinstance(node, dict):
            for key, child in node.items():
                key_text = str(key).strip()
                if key_text:
                    walk(child, [*path, key_text])
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    item_id = str(item.get("id") or item.get("name") or "").strip()
                    if item_id:
                        walk(item, [*path, item_id])

    walk(value, [])
    return refs


def _model_ref_resolves(ref: str, known_refs: set[str], prefix: str) -> bool:
    ref = str(ref or "").strip()
    if not ref:
        return False
    if ref in known_refs:
        return True
    if ref.startswith(f"{prefix}."):
        return any(item.startswith(f"{ref}.") or ref.startswith(f"{item}.") for item in known_refs)
    return False


def _planned_scenario_ids(ip: Path) -> set[str]:
    plan = _evidence_plan_doc(ip)
    ids: set[str] = set()
    for item in _as_list(plan.get("planned_scenarios")):
        if isinstance(item, dict):
            sid = str(item.get("id") or item.get("scenario_id") or "").strip()
            if sid:
                ids.add(sid)
        else:
            sid = str(item or "").strip()
            if sid:
                ids.add(sid)
    for contract in _as_list(plan.get("contracts")):
        if not isinstance(contract, dict):
            continue
        ids.update(_str_items(contract.get("scenario_refs")))
        for item in _as_list(contract.get("planned_scenarios")):
            if isinstance(item, dict):
                sid = str(item.get("id") or item.get("scenario_id") or "").strip()
                if sid:
                    ids.add(sid)
            else:
                sid = str(item or "").strip()
                if sid:
                    ids.add(sid)
    return ids


def _scenario_mapping_ids(ip: Path) -> set[str]:
    data = _read_json_file(ip / SCENARIO_MAPPING_REL)
    ids: set[str] = set()

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            sid = str(node.get("scenario_id") or node.get("id") or "").strip()
            if sid:
                ids.add(sid)
            for key in ("scenarios", "mappings", "scenario_mapping", "scenario_mappings"):
                collect(node.get(key))
            for key, child in node.items():
                if isinstance(child, dict) and key not in {"expected", "observed"}:
                    if re.match(r"^[A-Za-z0-9_.:-]+$", str(key)):
                        ids.add(str(key))
                    collect(child)
                elif isinstance(child, list):
                    collect(child)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(data)
    return ids


def _scoreboard_rows(ip: Path) -> list[tuple[int, dict[str, Any]]]:
    path = ip / SCOREBOARD_REL
    if not path.is_file():
        return []
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append((line_no, row))
    return rows


def _scoreboard_row_ids(ip: Path) -> set[str]:
    ids: set[str] = set()
    for _line_no, row in _scoreboard_rows(ip):
        for key in ("row_id", "event_id", "id", "goal_id"):
            value = str(row.get(key) or "").strip()
            if value:
                ids.add(value)
    return ids


def _closed_contract_ids(ip: Path, closure_matrix: dict[str, Any] | None = None) -> set[str]:
    closed: set[str] = set()
    for contract in _yaml_items(ip, "ontology/contracts.yaml", "contracts"):
        if _normal_status(contract.get("status")) in CLOSED_STATUSES:
            cid = str(contract.get("id") or "").strip()
            if cid:
                closed.add(cid)
    for link in _closed_record_links(ip):
        cid = str(link.get("contract") or "").strip()
        if cid:
            closed.add(cid)
    if isinstance(closure_matrix, dict):
        for row in _as_list(closure_matrix.get("rows")):
            if not isinstance(row, dict) or not row.get("closed"):
                continue
            closed.update(_str_items(row.get("contracts")))
    return closed


def _closed_records_reference_scoreboard(ip: Path) -> bool:
    for record in _knowledge_records(ip):
        validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
        rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
        rocev_validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else {}
        if _normal_status(validation.get("status") or record.get("status")) not in CLOSED_STATUSES:
            continue
        if _normal_status(rocev_validation.get("status")) not in CLOSED_STATUSES:
            continue
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        if any(str(item).strip() == str(SCOREBOARD_REL) for item in _as_list(evidence.get("files"))):
            return True
    return False


def _domain_item_id(item: dict[str, Any], *fallback_keys: str) -> str:
    for key in ("id", "name", *fallback_keys):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _domain_refs_by_kind(domain_intent: dict[str, Any]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {
        "clock_domains": set(),
        "reset_domains": set(),
        "async_inputs": set(),
        "cdc_crossings": set(),
        "rdc_crossings": set(),
        "sync_structures": set(),
    }
    for key, fallback in (
        ("clock_domains", ("clock",)),
        ("reset_domains", ("reset",)),
        ("async_inputs", ("signal",)),
        ("cdc_crossings", ("source",)),
        ("rdc_crossings", ("classification",)),
        ("sync_structures", ("structure", "signal")),
    ):
        for item in _as_list(domain_intent.get(key)):
            if not isinstance(item, dict):
                continue
            item_id = _domain_item_id(item, *fallback)
            if not item_id:
                continue
            mapping[key].add(item_id)
            mapping[key].add(f"{key}.{item_id}")
    return mapping


def _domain_ref_resolves(ref: str, known: dict[str, set[str]], allowed_kinds: tuple[str, ...]) -> bool:
    text = str(ref or "").strip()
    if not text:
        return False
    for kind in allowed_kinds:
        if text in known.get(kind, set()):
            return True
        prefix = f"{kind}."
        if text.startswith(prefix) and text[len(prefix) :] in known.get(kind, set()):
            return True
    return False


def _domain_evidence_refs(contract: dict[str, Any], prefix: str) -> list[str]:
    refs: list[str] = []
    for key in (
        "evidence_refs",
        f"{prefix}_evidence_refs",
        f"static_{prefix}_report",
        f"static_{prefix}_reports",
        f"{prefix}_report",
        f"{prefix}_reports",
        "formal_refs",
        "tool_report_refs",
        "tool_reports",
    ):
        refs.extend(_str_items(contract.get(key)))
    evidence = contract.get("evidence") if isinstance(contract.get("evidence"), dict) else {}
    for ref in _str_items(evidence.get("files")):
        lower = ref.lower()
        if any(token in lower for token in (prefix, "cdc", "rdc", "formal", "static", "tool", "report", "signoff")):
            refs.append(ref)
    return sorted(dict.fromkeys(refs))


def _domain_contract_type(contract: dict[str, Any]) -> str:
    ctype = str(contract.get("contract_type") or contract.get("type") or "").strip().lower()
    if ctype in DOMAIN_CROSSING_CONTRACT_TYPES:
        return ctype
    if _str_items(contract.get("cdc_crossing_refs") or contract.get("clock_domain_refs")):
        return "cdc"
    if _str_items(contract.get("rdc_crossing_refs") or contract.get("reset_domain_refs")):
        return "rdc"
    return ctype


def _safe_domain_crossing_pattern(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _contract_evidence_refs(contract: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in (
        "assertion_ref",
        "assertion_refs",
        "assertions",
        "proof_ref",
        "proof_refs",
        "proof_files",
        "evidence_file",
        "evidence_files",
        "evidence_refs",
        "files",
    ):
        refs.extend(_str_items(contract.get(key)))
    evidence = contract.get("evidence") if isinstance(contract.get("evidence"), dict) else {}
    refs.extend(_str_items(evidence.get("files")))
    refs.extend(_str_items(evidence.get("proofs")))
    refs.extend(_str_items(evidence.get("assertions")))
    return refs


def _contract_has_evidence_declaration(contract: dict[str, Any]) -> bool:
    if _contract_evidence_refs(contract):
        return True
    for key in ("evidence_kind", "evidence_kinds", "evidence_schema", "evidence_schemas"):
        if _str_items(contract.get(key)):
            return True
    evidence = contract.get("evidence") if isinstance(contract.get("evidence"), dict) else {}
    return bool(evidence)


def _path_like_ref(ref: str) -> bool:
    if not ref or ref.startswith(("pytest::", "node::", "coverage::")):
        return False
    return "/" in ref or bool(Path(ref).suffix)


def _instance_evidence_refs(instance: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in (
        "evidence_ref",
        "evidence_refs",
        "proof_ref",
        "proof_refs",
        "assertion_ref",
        "assertion_refs",
        "artifact",
        "artifacts",
        "file",
        "files",
        "path",
        "paths",
        "report",
        "reports",
        "report_ref",
        "report_refs",
        "log",
        "logs",
    ):
        refs.extend(_str_items(instance.get(key)))
    evidence = instance.get("evidence") if isinstance(instance.get("evidence"), dict) else {}
    refs.extend(_str_items(evidence.get("files")))
    refs.extend(_str_items(evidence.get("artifacts")))
    refs.extend(_str_items(evidence.get("reports")))
    refs.extend(_str_items(evidence.get("logs")))
    refs.extend(_str_items(evidence.get("tests")))
    refs.extend(_str_items(evidence.get("proofs")))
    refs.extend(_str_items(evidence.get("assertions")))
    return sorted(dict.fromkeys(refs))


def _instance_coverage_refs(instance: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("coverage_ref", "coverage_refs", "coverpoint", "coverpoints"):
        refs.extend(_str_items(instance.get(key)))
    evidence = instance.get("evidence") if isinstance(instance.get("evidence"), dict) else {}
    refs.extend(_str_items(evidence.get("coverage_refs")))
    refs.extend(_str_items(evidence.get("coverpoints")))
    return sorted(dict.fromkeys(refs))


def _instance_ref_values(instance: dict[str, Any], *keys: str) -> list[str]:
    refs: list[str] = []
    for key in keys:
        refs.extend(_str_items(instance.get(key)))
    evidence = instance.get("evidence") if isinstance(instance.get("evidence"), dict) else {}
    for key in keys:
        refs.extend(_str_items(evidence.get(key)))
    return sorted(dict.fromkeys(refs))


def _missing_path_refs(ip: Path, refs: list[str]) -> list[str]:
    return [ref for ref in sorted(dict.fromkeys(refs)) if _path_like_ref(ref) and not (ip / ref).exists()]


def _report_status(ip: Path, ref: str) -> str:
    data = _read_json_file(ip / ref)
    if not isinstance(data, dict):
        return ""
    for key in ("status", "result", "validation", "verdict"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    if data.get("pass") is True or data.get("passed") is True:
        return "pass"
    if data.get("fail") is True or data.get("failed") is True:
        return "fail"
    return ""


def _auto_research_report_refs(ip: Path) -> list[str]:
    refs: list[str] = []
    default = "signoff/ip_research_report.json"
    if (ip / default).is_file():
        refs.append(default)

    static_summary = _read_json_file(ip / "signoff" / "static_signoff_summary.json")
    if isinstance(static_summary, dict):
        reports = static_summary.get("reports") if isinstance(static_summary.get("reports"), dict) else {}
        refs.extend(_str_items(reports.get("auto_research") or reports.get("ip_research")))

    truth_coverage = _read_json_file(ip / "signoff" / "truth_coverage.json")
    if isinstance(truth_coverage, dict):
        evidence_summary = truth_coverage.get("evidence_summary") if isinstance(truth_coverage.get("evidence_summary"), dict) else {}
        auto_research = evidence_summary.get("auto_research") if isinstance(evidence_summary.get("auto_research"), dict) else {}
        refs.extend(_str_items(auto_research.get("path") or auto_research.get("report")))
        static_signoff = evidence_summary.get("static_signoff") if isinstance(evidence_summary.get("static_signoff"), dict) else {}
        refs.extend(_str_items(static_signoff.get("auto_research") or static_signoff.get("ip_research")))

    return sorted(dict.fromkeys(refs))


def _auto_research_blocker_text(data: dict[str, Any]) -> str:
    blockers: list[str] = []
    for key in ("signoff_blockers", "remaining_signoff_blockers", "blockers"):
        blockers.extend(_str_items(data.get(key)))
    return "\n".join(blockers).lower()


def _auto_research_development_sta_issues(ip: Path, ref: str, data: dict[str, Any], actions: list[dict[str, Any]]) -> list[str]:
    sta_report = _read_json_file(ip / "signoff" / "implementation_sta_report.json")
    if not isinstance(sta_report, dict) or _normal_status(sta_report.get("status")) != "development_pass":
        return []

    issues: list[str] = []
    implementation_sta_actions = [
        action
        for action in actions
        if str(action.get("id") or "").strip().upper() in {"IMPLEMENTATION_STA", "DEVELOPMENT_IMPLEMENTATION_STA"}
    ]
    if not implementation_sta_actions:
        issues.append(f"auto research report missing implementation STA action after development_pass: {ref}")
    else:
        for action in implementation_sta_actions:
            status = _normal_status(action.get("status"))
            action_id = str(action.get("id") or "IMPLEMENTATION_STA").strip()
            if status != "partially_closed":
                issues.append(
                    f"auto research report must rank development implementation STA as partially_closed after development_pass: "
                    f"{ref} {action_id} status={status or 'missing'}"
                )

    blocker_text = _auto_research_blocker_text(data)
    if "foundry" not in blocker_text and "pvt" not in blocker_text:
        issues.append(f"auto research report missing foundry/PVT blocker after development implementation STA pass: {ref}")
    if not any(token in blocker_text for token in ("gate-level", "gate level", "x-prop", "xprop")):
        issues.append(f"auto research report missing gate-level reset/X-prop blocker after development implementation STA pass: {ref}")
    return issues


def _auto_research_development_gate_reset_issues(
    ip: Path, ref: str, data: dict[str, Any], actions: list[dict[str, Any]]
) -> list[str]:
    gate_report = _read_json_file(ip / "signoff" / "gate_reset_xprop_report.json")
    if not isinstance(gate_report, dict) or _normal_status(gate_report.get("status")) != "development_pass":
        return []

    issues: list[str] = []
    gate_actions = [
        action
        for action in actions
        if str(action.get("id") or "").strip().upper()
        in {"GATE_LEVEL_RESET_XPROP", "GATE_RESET_XPROP", "DEVELOPMENT_GATE_RESET_XPROP"}
    ]
    if not gate_actions:
        issues.append(f"auto research report missing gate reset/X-prop action after development_pass: {ref}")
    else:
        for action in gate_actions:
            status = _normal_status(action.get("status"))
            action_id = str(action.get("id") or "GATE_LEVEL_RESET_XPROP").strip()
            if status != "partially_closed":
                issues.append(
                    f"auto research report must rank development gate reset/X-prop as partially_closed after development_pass: "
                    f"{ref} {action_id} status={status or 'missing'}"
                )

    blocker_text = _auto_research_blocker_text(data)
    if not any(token in blocker_text for token in ("sdf", "foundry", "pvt")):
        issues.append(f"auto research report missing SDF/foundry blocker after development gate reset/X-prop pass: {ref}")
    if not any(token in blocker_text for token in ("gate-level", "gate level", "x-prop", "xprop")):
        issues.append(f"auto research report missing gate-level reset/X-prop blocker after development gate reset/X-prop pass: {ref}")
    return issues


def _auto_research_development_formal_issues(
    ip: Path, ref: str, data: dict[str, Any], actions: list[dict[str, Any]]
) -> list[str]:
    formal_report = _read_json_file(ip / "signoff" / "formal_assertion_report.json")
    if not isinstance(formal_report, dict) or _normal_status(formal_report.get("status")) != "development_pass":
        return []

    issues: list[str] = []
    formal_actions = [
        action
        for action in actions
        if str(action.get("id") or "").strip().upper()
        in {"FORMAL_ASSERTION_OPTION", "FORMAL_ASSERTION", "DEVELOPMENT_FORMAL_ASSERTION", "FORMAL"}
    ]
    if not formal_actions:
        issues.append(f"auto research report missing formal assertion action after development_pass: {ref}")
    else:
        for action in formal_actions:
            status = _normal_status(action.get("status"))
            action_id = str(action.get("id") or "FORMAL_ASSERTION_OPTION").strip()
            if status != "partially_closed":
                issues.append(
                    f"auto research report must rank development formal assertion as partially_closed after development_pass: "
                    f"{ref} {action_id} status={status or 'missing'}"
                )
            reason_text = str(action.get("reason") or "").lower()
            if "development" not in reason_text and "bounded" not in reason_text:
                issues.append(
                    f"auto research formal assertion action missing bounded/development limitation after development_pass: "
                    f"{ref} {action_id}"
                )
            if not any(token in reason_text for token in ("contract", "signoff", "induction", "exhaustive", "review")):
                issues.append(
                    f"auto research formal assertion action missing contract/signoff limitation after development_pass: "
                    f"{ref} {action_id}"
                )
    return issues


def _auto_research_report_issues(ip: Path) -> list[str]:
    issues: list[str] = []
    for ref in _auto_research_report_refs(ip):
        path = ip / ref
        data = _read_json_file(path)
        if not path.is_file():
            issues.append(f"auto research report missing on disk: {ref}")
            continue
        if not isinstance(data, dict):
            issues.append(f"auto research report is not valid JSON object: {ref}")
            continue
        if data.get("schema_version") != "ip_research_report.v1":
            issues.append(f"auto research report schema_version mismatch: {ref}")
        status = _normal_status(data.get("status"))
        if status not in {"pass", "passed", "ok"}:
            issues.append(f"auto research report is not passing: {ref} status={status or 'missing'}")
        if not str(data.get("method") or "").strip():
            issues.append(f"auto research report missing method: {ref}")
        if not str(data.get("automation_boundary") or "").strip():
            issues.append(f"auto research report missing automation_boundary: {ref}")

        checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
        if not checks:
            issues.append(f"auto research report missing checks: {ref}")
        if checks.get("ranked_next_actions_present") is False:
            issues.append(f"auto research report checks say ranked actions are absent: {ref}")
        for check_name, passed in checks.items():
            if passed is False:
                issues.append(f"auto research report check failed: {ref} {check_name}")

        evidence_refs = _str_items(data.get("evidence_refs"))
        if not evidence_refs:
            issues.append(f"auto research report missing evidence_refs: {ref}")
        for missing in _missing_path_refs(ip, evidence_refs):
            issues.append(f"auto research report evidence ref missing on disk: {ref} -> {missing}")

        strengths = [item for item in _as_list(data.get("evidence_strengths")) if isinstance(item, dict)]
        if not strengths:
            issues.append(f"auto research report has no evidence_strengths: {ref}")
        for item in strengths:
            strength_id = str(item.get("id") or "<unnamed>").strip()
            if _normal_status(item.get("status")) not in {"pass", "passed", "ok", "development_pass", "candidate"}:
                issues.append(f"auto research evidence strength is not passing: {ref} {strength_id} status={item.get('status')}")
            for missing in _missing_path_refs(ip, _str_items(item.get("evidence_refs"))):
                issues.append(f"auto research evidence strength ref missing on disk: {ref} {strength_id} -> {missing}")

        actions = [item for item in _as_list(data.get("ranked_next_actions")) if isinstance(item, dict)]
        if not actions:
            issues.append(f"auto research report has no ranked_next_actions: {ref}")
        issues.extend(_auto_research_development_sta_issues(ip, ref, data, actions))
        issues.extend(_auto_research_development_gate_reset_issues(ip, ref, data, actions))
        issues.extend(_auto_research_development_formal_issues(ip, ref, data, actions))
        seen_ranks: set[int] = set()
        for index, action in enumerate(actions, 1):
            action_id = str(action.get("id") or "").strip()
            if not action_id:
                issues.append(f"auto research action missing id: {ref} rank={index}")
            if not str(action.get("status") or "").strip():
                issues.append(f"auto research action missing status: {ref} {action_id or '<unnamed>'}")
            if not str(action.get("reason") or "").strip():
                issues.append(f"auto research action missing reason: {ref} {action_id or '<unnamed>'}")
            try:
                rank = int(action.get("rank"))
            except Exception:
                issues.append(f"auto research action rank is not an integer: {ref} {action_id or '<unnamed>'}")
                continue
            if rank < 1:
                issues.append(f"auto research action rank must be positive: {ref} {action_id or '<unnamed>'}")
            if rank in seen_ranks:
                issues.append(f"auto research action duplicate rank: {ref} rank={rank}")
            seen_ranks.add(rank)
            for missing in _missing_path_refs(ip, _str_items(action.get("evidence_refs"))):
                issues.append(f"auto research action evidence ref missing on disk: {ref} {action_id or '<unnamed>'} -> {missing}")
    return issues


def _rtl_refs_from_reports(ip: Path, refs: list[str]) -> list[str]:
    rtl_refs: list[str] = []
    for ref in refs:
        data = _read_json_file(ip / ref)
        if isinstance(data, dict):
            rtl_refs.extend(_str_items(data.get("files")))
    return sorted(dict.fromkeys(rtl_refs))


def _strip_sv_comments(text: str) -> str:
    def replace_block(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    text = re.sub(r"/\*.*?\*/", replace_block, text, flags=re.DOTALL)
    return re.sub(r"//.*", "", text)


def _outside_generate_blocks(text: str) -> str:
    clean = _strip_sv_comments(text)
    spans: list[tuple[int, int]] = []
    depth = 0
    start: int | None = None
    for match in re.finditer(r"\b(generate|endgenerate)\b", clean):
        token = match.group(1)
        if token == "generate":
            if depth == 0:
                start = match.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, match.end()))
                start = None
    if depth and start is not None:
        spans.append((start, len(clean)))
    if not spans:
        return clean
    pieces: list[str] = []
    cursor = 0
    for begin, end in spans:
        pieces.append(clean[cursor:begin])
        pieces.append("\n" * clean[begin:end].count("\n"))
        cursor = end
    pieces.append(clean[cursor:])
    return "".join(pieces)


def _rtl_language_subset_violations(ip: Path, source_refs: list[str], forbidden: set[str]) -> list[str]:
    patterns = {
        "procedural_for": re.compile(r"\bfor\s*\("),
        "procedural_while": re.compile(r"\bwhile\s*\("),
        "procedural_repeat": re.compile(r"\brepeat\s*\("),
        "procedural_forever": re.compile(r"\bforever\b"),
        "package": re.compile(r"\bpackage\b"),
        "import": re.compile(r"\bimport\b"),
        "interface": re.compile(r"\binterface\b"),
        "modport": re.compile(r"\bmodport\b"),
        "typedef": re.compile(r"\btypedef\b"),
        "enum": re.compile(r"\benum\b"),
        "function": re.compile(r"\bfunction\b"),
        "task": re.compile(r"\btask\b"),
        "always_ff": re.compile(r"\balways_ff\b"),
        "always_comb": re.compile(r"\balways_comb\b"),
        "always_latch": re.compile(r"\balways_latch\b"),
    }
    procedural = {"procedural_for", "procedural_while", "procedural_repeat", "procedural_forever"}
    violations: list[str] = []
    for ref in sorted(dict.fromkeys(source_refs)):
        path = ip / ref
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        clean = _strip_sv_comments(text)
        outside_generate = _outside_generate_blocks(text)
        for construct in sorted(forbidden):
            pattern = patterns.get(construct)
            if not pattern:
                continue
            scan_text = outside_generate if construct in procedural else clean
            if pattern.search(scan_text):
                violations.append(f"{ref}: forbidden RTL construct present: {construct}")
    return violations


def _num_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip().rstrip("%")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _instance_fault_models(instance: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("fault_model", "fault_models", "fault_model_id", "fault_model_ids"):
        value = instance.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    refs.extend(_str_items(item.get("id") or item.get("name") or item.get("fault_model")))
                else:
                    refs.extend(_str_items(item))
        elif isinstance(value, dict):
            refs.extend(_str_items(value.get("id") or value.get("name") or value.get("fault_model")))
        else:
            refs.extend(_str_items(value))
    return sorted(dict.fromkeys(refs))


def _mutation_result_items(instance: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in ("mutation_results", "mutations", "mutation_evidence", "mutation_checks"):
        for item in _as_list(instance.get(key)):
            if isinstance(item, dict):
                items.append(item)
    evidence = instance.get("evidence") if isinstance(instance.get("evidence"), dict) else {}
    for key in ("mutation_results", "mutations", "mutation_evidence", "mutation_checks"):
        for item in _as_list(evidence.get(key)):
            if isinstance(item, dict):
                items.append(item)
    return items


def _mutation_result_fault_refs(result: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("fault_model", "fault_models", "fault_model_id", "fault_model_ids"):
        value = result.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    refs.update(_str_items(item.get("id") or item.get("name") or item.get("fault_model")))
                else:
                    refs.update(_str_items(item))
        elif isinstance(value, dict):
            refs.update(_str_items(value.get("id") or value.get("name") or value.get("fault_model")))
        else:
            refs.update(_str_items(value))
    return refs


def _mutation_result_evidence_refs(result: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("evidence_ref", "evidence_refs", "file", "files", "path", "paths", "summary", "matrix"):
        refs.extend(_str_items(result.get(key)))
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    refs.extend(_str_items(evidence.get("files")))
    refs.extend(_str_items(evidence.get("summaries")))
    refs.extend(_str_items(evidence.get("matrices")))
    return sorted(dict.fromkeys(refs))


def _mutation_result_killed(result: dict[str, Any]) -> bool:
    if result.get("killed") is True:
        return True
    if result.get("survived") is True:
        return False
    status = str(result.get("status") or result.get("result") or result.get("verdict") or "").lower()
    return status in {"killed", "kill", "pass", "passed", "closed", "validated"}


def _fault_model_coverage_issues(
    ip: Path,
    *,
    req_ids: set[str] | None = None,
    obl_ids: set[str] | None = None,
    contract_ids: set[str] | None = None,
) -> list[str]:
    req_ids = req_ids or set()
    obl_ids = obl_ids or set()
    contract_ids = contract_ids or set()
    issues: list[str] = []
    design_rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
    rule_instances = _yaml_items(ip, str(DESIGN_RULES_REL), "instances")
    rule_kind_by_id = {str(item.get("id") or ""): str(item.get("kind") or "") for item in design_rules if item.get("id")}
    observed = _observed_coverage_refs(ip)

    for instance in rule_instances:
        rid = str(instance.get("rule") or instance.get("rule_id") or "")
        if rule_kind_by_id.get(rid) != "fault_model_coverage":
            continue
        iid = str(instance.get("id") or rid or "fault_model_coverage")
        status = _normal_status(instance.get("status") or "open")
        if status in {"template", "draft", "waived"}:
            continue
        req_ref = str(instance.get("requirement") or instance.get("requirement_id") or "")
        obl_ref = str(instance.get("obligation") or instance.get("obligation_id") or "")
        contract_ref = str(instance.get("contract") or instance.get("contract_id") or "")
        if not req_ref:
            issues.append(f"{iid}: fault-model coverage rule missing requirement ref")
        elif req_ids and req_ref not in req_ids:
            issues.append(f"{iid}: requirement ref not found: {req_ref}")
        if not obl_ref:
            issues.append(f"{iid}: fault-model coverage rule missing obligation ref")
        elif obl_ids and obl_ref not in obl_ids:
            issues.append(f"{iid}: obligation ref not found: {obl_ref}")
        if not contract_ref:
            issues.append(f"{iid}: fault-model coverage rule missing contract ref")
        elif contract_ids and contract_ref not in contract_ids:
            issues.append(f"{iid}: contract ref not found: {contract_ref}")

        coverage_refs = _instance_coverage_refs(instance)
        if not coverage_refs:
            issues.append(f"{iid}: fault-model coverage rule missing coverage_refs")
        elif status in CLOSED_STATUSES:
            for ref in coverage_refs:
                if ref not in observed:
                    issues.append(f"{iid}: fault-model coverage ref not observed: {ref}")

        mutation_not_required = instance.get("mutation_not_required") is True
        rationale = str(instance.get("rationale") or instance.get("waiver") or instance.get("reason") or "").strip()
        fault_models = _instance_fault_models(instance)
        if not fault_models and not mutation_not_required:
            issues.append(f"{iid}: fault-model coverage rule missing fault_models")
        if mutation_not_required:
            if not rationale:
                issues.append(f"{iid}: mutation_not_required requires rationale")
            continue

        results = _mutation_result_items(instance)
        if status in CLOSED_STATUSES and not results:
            issues.append(f"{iid}: closed fault-model coverage missing mutation_results")
        for fault_model in fault_models:
            matching = [result for result in results if fault_model in _mutation_result_fault_refs(result)]
            if status in CLOSED_STATUSES and not matching:
                issues.append(f"{iid}: fault model has no mutation result: {fault_model}")
                continue
            if status in CLOSED_STATUSES and not any(_mutation_result_killed(result) for result in matching):
                issues.append(f"{iid}: fault model mutation not killed: {fault_model}")
            for result in matching:
                if not _mutation_result_killed(result):
                    continue
                refs = _mutation_result_evidence_refs(result)
                if not refs:
                    issues.append(f"{iid}: killed mutation missing evidence ref for {fault_model}")
                for ref in refs:
                    if _path_like_ref(ref) and not (ip / ref).is_file():
                        issues.append(f"{iid}: mutation evidence ref missing on disk: {ref}")
    return issues


def _verification_role_artifacts(value: Any) -> list[str]:
    if isinstance(value, dict):
        refs: list[str] = []
        for key in ("artifact", "artifacts", "file", "files", "path", "paths"):
            refs.extend(_str_items(value.get(key)))
        return sorted(dict.fromkeys(refs))
    return _str_items(value)


def _verification_roles(instance: dict[str, Any]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    raw_roles = instance.get("roles")
    if isinstance(raw_roles, dict):
        for role, value in raw_roles.items():
            role_name = str(role or "").strip()
            if role_name:
                roles[role_name] = _verification_role_artifacts(value)
    for role in VERIFICATION_REQUIRED_ROLES:
        if role in roles:
            continue
        direct = instance.get(role)
        if direct:
            roles[role] = _verification_role_artifacts(direct)
    return roles


def _verification_role_decomposition_issues(
    ip: Path,
    *,
    req_ids: set[str] | None = None,
    obl_ids: set[str] | None = None,
    contract_ids: set[str] | None = None,
) -> list[str]:
    req_ids = req_ids or set()
    obl_ids = obl_ids or set()
    contract_ids = contract_ids or set()
    issues: list[str] = []
    design_rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
    rule_instances = _yaml_items(ip, str(DESIGN_RULES_REL), "instances")
    rule_kind_by_id = {str(item.get("id") or ""): str(item.get("kind") or "") for item in design_rules if item.get("id")}

    for instance in rule_instances:
        rid = str(instance.get("rule") or instance.get("rule_id") or "")
        if rule_kind_by_id.get(rid) != "verification_role_decomposition":
            continue
        iid = str(instance.get("id") or rid or "verification_role_decomposition")
        status = _normal_status(instance.get("status") or "open")
        if status in {"template", "draft", "waived"}:
            continue

        req_ref = str(instance.get("requirement") or instance.get("requirement_id") or "")
        obl_ref = str(instance.get("obligation") or instance.get("obligation_id") or "")
        contract_ref = str(instance.get("contract") or instance.get("contract_id") or "")
        if not req_ref:
            issues.append(f"{iid}: verification role decomposition missing requirement ref")
        elif req_ids and req_ref not in req_ids:
            issues.append(f"{iid}: requirement ref not found: {req_ref}")
        if not obl_ref:
            issues.append(f"{iid}: verification role decomposition missing obligation ref")
        elif obl_ids and obl_ref not in obl_ids:
            issues.append(f"{iid}: obligation ref not found: {obl_ref}")
        if not contract_ref:
            issues.append(f"{iid}: verification role decomposition missing contract ref")
        elif contract_ids and contract_ref not in contract_ids:
            issues.append(f"{iid}: contract ref not found: {contract_ref}")

        if status not in CLOSED_STATUSES:
            continue
        style = str(instance.get("style") or "").strip()
        framework = str(instance.get("framework") or "").strip()
        if not style:
            issues.append(f"{iid}: closed verification role decomposition missing style")
        if not framework:
            issues.append(f"{iid}: closed verification role decomposition missing framework")

        required_roles = _str_items(instance.get("required_roles")) or list(VERIFICATION_REQUIRED_ROLES)
        roles = _verification_roles(instance)
        for role in required_roles:
            artifacts = roles.get(role) or []
            if not artifacts:
                issues.append(f"{iid}: verification role missing artifact: {role}")
                continue
            for artifact in artifacts:
                if _path_like_ref(artifact) and not (ip / artifact).exists():
                    issues.append(f"{iid}: verification role artifact missing on disk: {role} -> {artifact}")

        independence = instance.get("independence") if isinstance(instance.get("independence"), dict) else {}
        expected_source = str(independence.get("expected_source") or instance.get("expected_source") or "").strip()
        observed_source = str(independence.get("observed_source") or instance.get("observed_source") or "").strip()
        compare_source = str(independence.get("compare_source") or instance.get("compare_source") or "").strip()
        for field, value in (("expected_source", expected_source), ("observed_source", observed_source), ("compare_source", compare_source)):
            if not value:
                issues.append(f"{iid}: verification role independence missing {field}")
            elif value not in roles:
                issues.append(f"{iid}: verification role independence references unknown role: {field}={value}")
        if expected_source and observed_source and expected_source == observed_source:
            issues.append(f"{iid}: expected_source and observed_source must be separate roles")
        if observed_source and compare_source and observed_source == compare_source:
            issues.append(f"{iid}: observed_source and compare_source must be separate roles")

        shared_rationale = str(instance.get("shared_role_rationale") or instance.get("single_file_rationale") or "").strip()
        artifact_to_roles: dict[str, list[str]] = {}
        for role, artifacts in roles.items():
            if role not in required_roles:
                continue
            for artifact in artifacts:
                if _path_like_ref(artifact):
                    artifact_to_roles.setdefault(artifact, []).append(role)
        shared = {artifact: used_roles for artifact, used_roles in artifact_to_roles.items() if len(used_roles) > 1}
        if shared and not shared_rationale:
            detail = "; ".join(f"{artifact} shared by {', '.join(used_roles)}" for artifact, used_roles in sorted(shared.items()))
            issues.append(f"{iid}: verification roles share artifact without shared_role_rationale: {detail}")
    return issues


def _interleaved_context_issues(
    ip: Path,
    *,
    req_ids: set[str] | None = None,
    obl_ids: set[str] | None = None,
    contract_ids: set[str] | None = None,
) -> list[str]:
    req_ids = req_ids or set()
    obl_ids = obl_ids or set()
    contract_ids = contract_ids or set()
    issues: list[str] = []
    design_rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
    rule_instances = _yaml_items(ip, str(DESIGN_RULES_REL), "instances")
    rule_kind_by_id = {str(item.get("id") or ""): str(item.get("kind") or "") for item in design_rules if item.get("id")}
    observed = _observed_coverage_refs(ip)

    for instance in rule_instances:
        rid = str(instance.get("rule") or instance.get("rule_id") or "")
        if rule_kind_by_id.get(rid) != "interleaved_context_coverage":
            continue
        iid = str(instance.get("id") or rid or "interleaved_context_coverage")
        status = _normal_status(instance.get("status") or "open")
        if status in {"template", "draft", "waived"}:
            continue
        req_ref = str(instance.get("requirement") or instance.get("requirement_id") or "")
        obl_ref = str(instance.get("obligation") or instance.get("obligation_id") or "")
        contract_ref = str(instance.get("contract") or instance.get("contract_id") or "")
        if not req_ref:
            issues.append(f"{iid}: interleaved context coverage rule missing requirement ref")
        elif req_ids and req_ref not in req_ids:
            issues.append(f"{iid}: requirement ref not found: {req_ref}")
        if not obl_ref:
            issues.append(f"{iid}: interleaved context coverage rule missing obligation ref")
        elif obl_ids and obl_ref not in obl_ids:
            issues.append(f"{iid}: obligation ref not found: {obl_ref}")
        if not contract_ref:
            issues.append(f"{iid}: interleaved context coverage rule missing contract ref")
        elif contract_ids and contract_ref not in contract_ids:
            issues.append(f"{iid}: contract ref not found: {contract_ref}")
        raw_context_count = instance.get("context_count") or instance.get("contexts") or instance.get("max_contexts")
        try:
            context_count = int(raw_context_count)
        except Exception:
            context_count = 0
        if context_count < 2:
            issues.append(f"{iid}: interleaved context coverage requires context_count >= 2")
        pattern = instance.get("interleaving_pattern") or instance.get("pattern") or instance.get("scenario_pattern")
        if not _str_items(pattern):
            issues.append(f"{iid}: interleaved context coverage missing interleaving_pattern")
        coverage_refs = _instance_coverage_refs(instance)
        if not coverage_refs:
            issues.append(f"{iid}: interleaved context coverage missing coverage_refs")
        if status in CLOSED_STATUSES:
            for ref in coverage_refs:
                if ref not in observed:
                    issues.append(f"{iid}: interleaved context coverage ref not observed: {ref}")
            evidence_refs = _instance_evidence_refs(instance)
            if not evidence_refs and not coverage_refs:
                issues.append(f"{iid}: closed interleaved context coverage missing evidence ref")
    return issues


def _signoff_design_rule_issues(
    ip: Path,
    *,
    req_ids: set[str] | None = None,
    obl_ids: set[str] | None = None,
    contract_ids: set[str] | None = None,
) -> list[str]:
    req_ids = req_ids or set()
    obl_ids = obl_ids or set()
    contract_ids = contract_ids or set()
    issues: list[str] = []
    design_rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
    rule_instances = _yaml_items(ip, str(DESIGN_RULES_REL), "instances")
    rule_by_id = {str(item.get("id") or ""): item for item in design_rules if item.get("id")}
    rule_kind_by_id = {str(item.get("id") or ""): str(item.get("kind") or "") for item in design_rules if item.get("id")}
    observed = _observed_coverage_refs(ip)

    for instance in rule_instances:
        rid = str(instance.get("rule") or instance.get("rule_id") or "")
        kind = rule_kind_by_id.get(rid, "")
        if kind not in SIGNOFF_DESIGN_RULE_KINDS:
            continue
        iid = str(instance.get("id") or rid or kind)
        label = SIGNOFF_DESIGN_RULE_KINDS[kind]
        status = _normal_status(instance.get("status") or "open")
        if status in {"template", "draft", "waived"}:
            if status == "waived" and not str(instance.get("waiver") or instance.get("reason") or "").strip():
                issues.append(f"{iid}: waived {label} rule requires waiver reason")
            continue

        req_ref = str(instance.get("requirement") or instance.get("requirement_id") or "")
        obl_ref = str(instance.get("obligation") or instance.get("obligation_id") or "")
        contract_ref = str(instance.get("contract") or instance.get("contract_id") or "")
        if not req_ref:
            issues.append(f"{iid}: {label} rule missing requirement ref")
        elif req_ids and req_ref not in req_ids:
            issues.append(f"{iid}: requirement ref not found: {req_ref}")
        if not obl_ref:
            issues.append(f"{iid}: {label} rule missing obligation ref")
        elif obl_ids and obl_ref not in obl_ids:
            issues.append(f"{iid}: obligation ref not found: {obl_ref}")
        if not contract_ref:
            issues.append(f"{iid}: {label} rule missing contract ref")
        elif contract_ids and contract_ref not in contract_ids:
            issues.append(f"{iid}: contract ref not found: {contract_ref}")

        coverage_refs = _instance_coverage_refs(instance)
        evidence_refs = _instance_evidence_refs(instance)
        if status in CLOSED_STATUSES:
            if not evidence_refs:
                issues.append(f"{iid}: closed {label} rule missing evidence_refs")
            for ref in _missing_path_refs(ip, evidence_refs):
                issues.append(f"{iid}: {label} evidence ref missing on disk: {ref}")
            for ref in coverage_refs:
                if ref not in observed:
                    issues.append(f"{iid}: {label} coverage ref not observed: {ref}")

        if kind == "cdc_crossing_coverage":
            no_cdc = instance.get("cdc_required") is False or instance.get("required") is False
            if no_cdc:
                if not str(instance.get("rationale") or instance.get("reason") or "").strip():
                    issues.append(f"{iid}: CDC not-required rule needs rationale")
            elif not (_str_items(instance.get("clock_domains")) or _str_items(instance.get("domains")) or _str_items(instance.get("crossings"))):
                issues.append(f"{iid}: CDC crossing coverage missing clock_domains/crossings")
        elif kind == "protocol_compliance":
            if not str(instance.get("protocol") or instance.get("interface") or "").strip():
                issues.append(f"{iid}: protocol compliance missing protocol")
            protocol_reports = _instance_ref_values(instance, "protocol_report", "protocol_reports", "compliance_report", "compliance_reports")
            phase_traces = _instance_ref_values(instance, "phase_trace", "phase_traces", "protocol_trace", "protocol_traces")
            if status in CLOSED_STATUSES:
                for ref in _missing_path_refs(ip, protocol_reports):
                    issues.append(f"{iid}: protocol compliance report missing on disk: {ref}")
                for ref in _missing_path_refs(ip, phase_traces):
                    issues.append(f"{iid}: protocol phase trace missing on disk: {ref}")
                for ref in protocol_reports:
                    report_status = _report_status(ip, ref)
                    if report_status and report_status not in {"pass", "passed", "ok", "clean", "development_pass"}:
                        issues.append(f"{iid}: protocol compliance report is not passing: {ref} status={report_status}")
        elif kind == "timing_closure":
            sdc_refs = _instance_ref_values(instance, "sdc_ref", "sdc_refs", "sdc", "constraints")
            timing_refs = _instance_ref_values(instance, "timing_report", "timing_reports", "sta_report", "sta_reports", "wns_report", "wns_reports")
            target_freq = _num_value(instance.get("target_frequency_mhz") or instance.get("frequency_mhz") or instance.get("target_mhz"))
            target_period = _num_value(instance.get("target_period_ns") or instance.get("period_ns") or instance.get("period"))
            target_clocks = [item for item in _as_list(instance.get("target_clocks") or instance.get("clocks")) if isinstance(item, dict)]
            clock_targets_valid = False
            target_clock_names: list[str] = []
            for clock in target_clocks:
                clock_name = str(clock.get("name") or clock.get("clock") or "").strip()
                if clock_name:
                    target_clock_names.append(clock_name)
                clock_freq = _num_value(clock.get("frequency_mhz") or clock.get("target_mhz"))
                clock_period = _num_value(clock.get("period_ns") or clock.get("period"))
                if clock_freq is None and clock_period is None:
                    issues.append(f"{iid}: target clock missing frequency_mhz or period_ns: {clock_name or '<unnamed>'}")
                    continue
                if clock_freq is not None and clock_freq <= 0:
                    issues.append(f"{iid}: target clock frequency_mhz must be positive: {clock_name or '<unnamed>'}")
                    continue
                if clock_period is not None and clock_period <= 0:
                    issues.append(f"{iid}: target clock period_ns must be positive: {clock_name or '<unnamed>'}")
                    continue
                clock_targets_valid = True
            if target_freq is not None and target_freq <= 0:
                issues.append(f"{iid}: target_frequency_mhz must be positive")
            if target_period is not None and target_period <= 0:
                issues.append(f"{iid}: target_period_ns/period_ns must be positive")
            has_target = clock_targets_valid or (target_freq is not None and target_freq > 0) or (target_period is not None and target_period > 0)
            if not has_target:
                issues.append(f"{iid}: timing closure missing target_clocks/target_frequency")
            if not sdc_refs:
                issues.append(f"{iid}: timing closure missing sdc_refs")
            if not timing_refs:
                issues.append(f"{iid}: timing closure missing timing_reports")
            cdc_relevant = (
                len(set(target_clock_names)) > 1
                or instance.get("cdc_required") is True
                or instance.get("cdc_based_sdc") is True
                or bool(_str_items(instance.get("clock_domains")) or _str_items(instance.get("crossings")))
            )
            if cdc_relevant and not (
                _str_items(instance.get("async_clock_groups"))
                or _str_items(instance.get("cdc_constraints"))
                or _instance_ref_values(instance, "cdc_sdc_ref", "cdc_sdc_refs", "cdc_constraint_ref", "cdc_constraint_refs")
            ):
                issues.append(f"{iid}: timing closure with CDC/multiple clocks missing async_clock_groups/cdc_constraints")
            for ratio_key in ("io_delay_ratio", "input_delay_ratio", "output_delay_ratio"):
                ratio = _num_value(instance.get(ratio_key))
                if ratio is not None and not 0 <= ratio <= 1:
                    issues.append(f"{iid}: {ratio_key} must be between 0.0 and 1.0")
            if status in CLOSED_STATUSES:
                for ref in _missing_path_refs(ip, sdc_refs + timing_refs):
                    issues.append(f"{iid}: timing closure evidence ref missing on disk: {ref}")
                setup_wns = _num_value(instance.get("setup_wns_ns") or instance.get("setup_wns"))
                hold_wns = _num_value(instance.get("hold_wns_ns") or instance.get("hold_wns"))
                setup_min = _num_value(instance.get("setup_wns_ns_min") or instance.get("setup_min_ns"))
                hold_min = _num_value(instance.get("hold_wns_ns_min") or instance.get("hold_min_ns"))
                setup_min = 0.0 if setup_min is None else setup_min
                hold_min = 0.0 if hold_min is None else hold_min
                if setup_wns is not None and setup_wns < setup_min:
                    issues.append(f"{iid}: setup WNS below minimum: {setup_wns} < {setup_min}")
                if hold_wns is not None and hold_wns < hold_min:
                    issues.append(f"{iid}: hold WNS below minimum: {hold_wns} < {hold_min}")
                if instance.get("all_setup_met") is False:
                    issues.append(f"{iid}: timing closure reports setup not met")
                if instance.get("all_hold_met") is False:
                    issues.append(f"{iid}: timing closure reports hold not met")
        elif kind == "functional_coverage_closure":
            if not coverage_refs:
                issues.append(f"{iid}: functional coverage closure missing coverage_refs")
            goal = _num_value(instance.get("coverage_goal") or instance.get("coverage_target"))
            actual = _num_value(instance.get("coverage_actual") or instance.get("coverage_percent") or instance.get("coverage_score"))
            if status in CLOSED_STATUSES and (goal is None or actual is None):
                issues.append(f"{iid}: closed functional coverage closure missing coverage_goal/coverage_actual")
            if goal is not None and actual is not None and actual < goal:
                issues.append(f"{iid}: functional coverage below goal: {actual} < {goal}")
        elif kind == "reset_xprop_coverage":
            if not (_str_items(instance.get("reset_scenarios")) or _str_items(instance.get("xprop_checks"))):
                issues.append(f"{iid}: reset/X-prop coverage missing reset_scenarios/xprop_checks")
            if status in CLOSED_STATUSES and not coverage_refs:
                issues.append(f"{iid}: closed reset/X-prop coverage missing coverage_refs")
        elif kind == "rtl_language_subset":
            language_policy = str(instance.get("language_policy") or instance.get("policy") or "").strip()
            compile_refs = _instance_ref_values(instance, "rtl_compile_report", "rtl_compile_reports", "compile_report", "compile_reports")
            lint_refs = _instance_ref_values(instance, "lint_report", "lint_reports")
            source_refs = _instance_ref_values(instance, "rtl_source", "rtl_sources", "source_ref", "source_refs", "rtl_ref", "rtl_refs")
            source_refs = sorted(dict.fromkeys(source_refs + _rtl_refs_from_reports(ip, compile_refs)))
            if not language_policy:
                issues.append(f"{iid}: RTL language subset missing language_policy")
            if not compile_refs:
                issues.append(f"{iid}: RTL language subset missing rtl_compile_report")
            if not source_refs:
                issues.append(f"{iid}: RTL language subset missing rtl_sources")
            if status in CLOSED_STATUSES:
                for ref in _missing_path_refs(ip, compile_refs + lint_refs + source_refs):
                    issues.append(f"{iid}: RTL language subset evidence ref missing on disk: {ref}")
                for ref in compile_refs + lint_refs:
                    report_status = _report_status(ip, ref)
                    if report_status and report_status not in {"pass", "passed", "ok", "clean"}:
                        issues.append(f"{iid}: RTL language subset report is not passing: {ref} status={report_status}")
                rule = rule_by_id.get(rid) or {}
                forbidden = {
                    str(item).strip()
                    for item in (
                        _as_list(rule.get("forbidden_constructs") or rule.get("forbidden"))
                        + _as_list(instance.get("forbidden_constructs_absent") or instance.get("forbidden_constructs"))
                    )
                    if str(item).strip()
                }
                issues.extend(f"{iid}: {violation}" for violation in _rtl_language_subset_violations(ip, source_refs, forbidden))
    return issues


def _policy_profile(ip: Path) -> str:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml"))
    if isinstance(data, dict):
        return str(data.get("closure_profile") or "development")
    path = oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml")
    if path.is_file():
        match = re.search(r"(?m)^\s*closure_profile\s*:\s*([A-Za-z0-9_-]+)\s*$", path.read_text(encoding="utf-8", errors="ignore"))
        if match:
            return match.group(1)
    return "development"


def _scope_lock_path(ip: Path) -> Path:
    return oag_paths.legacy_or_hidden(ip, str(SCOPE_LOCK_REL))


def _implementation_artifacts(ip: Path) -> list[str]:
    refs: list[str] = []
    for pattern in POST_LOCK_ARTIFACT_PATTERNS:
        for path in sorted(ip.glob(pattern)):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            try:
                if path.stat().st_size == 0:
                    continue
                refs.append(str(path.relative_to(ip)))
            except Exception:
                refs.append(str(path))
    return sorted(dict.fromkeys(refs))


def _scope_lock_doc(ip: Path) -> dict[str, Any]:
    path = _scope_lock_path(ip)
    data = _read_json_file(path)
    if isinstance(data, dict):
        state = str(data.get("state") or data.get("status") or "draft").strip().lower()
        if state not in {"draft", "locked"}:
            state = "draft"
        data = dict(data)
        data["state"] = state
        data.setdefault("schema_version", "oag_scope_lock.v1")
        data.setdefault("ip", ip.name)
        data.setdefault("path", str(path))
        return data
    return {
        "schema_version": "oag_scope_lock.v1",
        "ip": ip.name,
        "state": "draft",
        "path": str(path),
        "missing": True,
        "summary": "No scope lock file; treating IP as draft.",
    }


def _scope_lock_status(ip: Path) -> dict[str, Any]:
    doc = _scope_lock_doc(ip)
    artifacts = _implementation_artifacts(ip)
    state = str(doc.get("state") or "draft")
    locked = state == "locked"
    blockers: list[str] = []
    if not locked:
        blockers.append("scope is not locked; user must confirm requirements before implementation or closure")
    if artifacts and not locked:
        blockers.append("post-lock artifacts exist while scope is draft")
    return {
        "schema_version": "oag_scope_lock_status.v1",
        "ip": ip.name,
        "state": state,
        "locked": locked,
        "can_implement": locked,
        "can_close": locked,
        "path": str(_scope_lock_path(ip)),
        "missing": bool(doc.get("missing")),
        "lock": doc,
        "implementation_artifacts": artifacts,
        "blockers": blockers,
    }


def _scope_lock_issues(ip: Path, *, require_locked: bool = False) -> list[str]:
    status = _scope_lock_status(ip)
    issues: list[str] = []
    if require_locked and not status["locked"]:
        issues.append("scope lock required before implementation or closure")
    artifacts = [str(item) for item in status.get("implementation_artifacts") or []]
    if artifacts and not status["locked"]:
        issues.append("scope is draft while implementation artifacts exist: " + ", ".join(artifacts[:8]))
    return issues


def _scope_lock_actor(arguments: dict[str, Any], *, surface: str) -> dict[str, str]:
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    return {
        "kind": str(actor.get("kind") or "ai"),
        "id": str(actor.get("id") or os.environ.get("USER") or "unknown"),
        "session": str(actor.get("session") or ""),
        "surface": str(actor.get("surface") or surface),
    }


def _write_scope_lock(ip: Path, payload: dict[str, Any]) -> None:
    path = _scope_lock_path(ip)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _scope_lock(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    actor = _scope_lock_actor(arguments, surface="oag.lock")
    summary = str(arguments.get("summary") or arguments.get("scope_summary") or "").strip()
    confirmed_scope = _str_items(arguments.get("confirmed_scope") or arguments.get("scope"))
    if not summary and confirmed_scope:
        summary = "; ".join(confirmed_scope)
    if not summary:
        raise ValueError("oag.lock requires summary or confirmed_scope")
    payload_for_approval = {
        "approval": arguments.get("approval") if isinstance(arguments.get("approval"), dict) else {},
        "summary": summary,
        "confirmed_scope": confirmed_scope,
    }
    if not _is_human_approved({"action": "scope_lock", "actor": actor, "payload": payload_for_approval}):
        raise ValueError("oag.lock requires explicit human approval; use actor.kind=human or approval.approved=true")
    previous = _scope_lock_doc(ip)
    lock_id = f"LOCK_{_stamp()}_{_slug(summary)}"
    doc = {
        "schema_version": "oag_scope_lock.v1",
        "ip": ip.name,
        "state": "locked",
        "lock_id": lock_id,
        "summary": summary,
        "confirmed_scope": confirmed_scope,
        "source_draft": str(arguments.get("source_draft") or arguments.get("draft_id") or ""),
        "open_questions": _str_items(arguments.get("open_questions")),
        "assumptions": _str_items(arguments.get("assumptions")),
        "locked_by": actor,
        "locked_at": _now(),
        "previous_state": str(previous.get("state") or "draft"),
    }
    _write_scope_lock(ip, doc)
    ledger_event = _append_ledger(
        ip,
        action="scope_lock",
        actor=actor,
        subject=lock_id,
        payload={"path": str(SCOPE_LOCK_REL), "lock": doc},
    )
    return {
        "schema_version": "oag_scope_lock.v1",
        "ip": ip.name,
        "status": "locked",
        "locked": True,
        "path": str(_scope_lock_path(ip)),
        "lock": doc,
        "ledger_event": ledger_event["event_hash"],
    }


def _scope_unlock(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    actor = _scope_lock_actor(arguments, surface="oag.unlock")
    reason = str(arguments.get("reason") or "scope changed").strip()
    payload_for_approval = {
        "approval": arguments.get("approval") if isinstance(arguments.get("approval"), dict) else {},
        "reason": reason,
    }
    if not _is_human_approved({"action": "scope_unlock", "actor": actor, "payload": payload_for_approval}):
        raise ValueError("oag.unlock requires explicit human approval; use actor.kind=human or approval.approved=true")
    previous = _scope_lock_doc(ip)
    doc = {
        "schema_version": "oag_scope_lock.v1",
        "ip": ip.name,
        "state": "draft",
        "summary": str(previous.get("summary") or ""),
        "previous_lock_id": str(previous.get("lock_id") or ""),
        "unlock_reason": reason,
        "unlocked_by": actor,
        "unlocked_at": _now(),
    }
    _write_scope_lock(ip, doc)
    ledger_event = _append_ledger(
        ip,
        action="scope_unlock",
        actor=actor,
        subject=str(previous.get("lock_id") or "scope"),
        payload={"path": str(SCOPE_LOCK_REL), "lock": doc},
    )
    return {
        "schema_version": "oag_scope_unlock.v1",
        "ip": ip.name,
        "status": "draft",
        "locked": False,
        "path": str(_scope_lock_path(ip)),
        "lock": doc,
        "ledger_event": ledger_event["event_hash"],
    }


def _mark_scope_draft_after_interview(ip: Path, *, actor: dict[str, Any], draft_id: str, reason: str) -> dict[str, Any] | None:
    previous = _scope_lock_doc(ip)
    if str(previous.get("state") or "draft") != "locked":
        return None
    doc = {
        "schema_version": "oag_scope_lock.v1",
        "ip": ip.name,
        "state": "draft",
        "summary": str(previous.get("summary") or ""),
        "previous_lock_id": str(previous.get("lock_id") or ""),
        "stale_reason": reason,
        "stale_source_draft": draft_id,
        "updated_by": actor,
        "updated_at": _now(),
    }
    _write_scope_lock(ip, doc)
    ledger_event = _append_ledger(
        ip,
        action="scope_draft",
        actor=actor,
        subject=draft_id,
        payload={"path": str(SCOPE_LOCK_REL), "lock": doc},
    )
    return {"lock": doc, "ledger_event": ledger_event["event_hash"]}


def _truth_graph_path(ip: Path) -> Path:
    return oag_paths.legacy_or_hidden(ip, str(TRUTH_GRAPH_REL))


def _truth_graph_compiled(ip: Path) -> bool:
    data = _read_json_file(_truth_graph_path(ip))
    return (
        isinstance(data, dict)
        and data.get("schema_version") == "oag_design_truth_graph.v1"
        and data.get("compiled_by") == "oag.compile"
        and data.get("status") == "pass"
    )


def _status_from_json(path: Path, default_present: str = "present") -> tuple[bool, str]:
    data = _read_json_file(path)
    if data is None:
        return False, "missing"
    if isinstance(data, dict):
        for key in ("status", "result", "validation", "verdict"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return True, value.lower()
        if data.get("pass") is True or data.get("passed") is True:
            return True, "pass"
        if data.get("fail") is True or data.get("failed") is True:
            return True, "fail"
    return True, default_present


def _simulation_status(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    text = path.read_text(encoding="utf-8", errors="ignore")[:20000]
    for attr in ("failures", "errors"):
        match = re.search(rf'{attr}=["\']?(\d+)', text)
        if match and int(match.group(1)) > 0:
            return True, "fail"
    if "<failure" in text or "<error" in text:
        return True, "fail"
    if "<testcase" in text or "<testsuite" in text:
        return True, "pass"
    return True, "present"


def _scoreboard_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "path": "", "summary": None}
    total = passed = failed = unreadable = schema_failed = standard_rows = legacy_rows = 0
    issues: list[str] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not line.strip():
            continue
        total += 1
        try:
            row = json.loads(line)
        except Exception:
            unreadable += 1
            issues.append(f"line {line_no}: invalid JSON")
            continue
        if not isinstance(row, dict):
            schema_failed += 1
            issues.append(f"line {line_no}: row must be a JSON object")
            continue
        row_issues, row_is_standard, row_is_legacy = _scoreboard_row_issues(row, line_no)
        if row_issues:
            schema_failed += 1
            issues.extend(row_issues)
        if row_is_standard:
            standard_rows += 1
        if row_is_legacy:
            legacy_rows += 1
        mismatch = _scoreboard_row_failed(row)
        if mismatch:
            failed += 1
        else:
            passed += 1
    return {
        "present": True,
        "path": str(path),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "unreadable": unreadable,
            "schema_failed": schema_failed,
            "standard_rows": standard_rows,
            "legacy_rows": legacy_rows,
            "schema": "scoreboard_rows.v1",
        },
        "issues": issues[:20],
    }


def _scoreboard_row_failed(row: dict[str, Any]) -> bool:
    passed = row.get("passed")
    if isinstance(passed, bool):
        return not passed
    mismatch = row.get("mismatch")
    if isinstance(mismatch, str):
        return bool(mismatch.strip())
    return bool(mismatch or row.get("failed") or row.get("fail"))


def _scoreboard_row_issues(row: dict[str, Any], line_no: int) -> tuple[list[str], bool, bool]:
    issues: list[str] = []
    is_standard = SCOREBOARD_REQUIRED_FIELDS.issubset(row)
    is_legacy = bool(LEGACY_SCOREBOARD_FIELDS & set(row))

    if not is_standard:
        missing = sorted(SCOREBOARD_REQUIRED_FIELDS - set(row))
        if is_legacy:
            missing = [field for field in missing if field not in {"expected", "observed"}]
        if missing:
            issues.append(f"line {line_no}: missing scoreboard_rows.v1 field(s): {', '.join(missing)}")

    expected = row.get("expected", row.get("fl_expected"))
    observed = row.get("observed", row.get("rtl_observed"))
    if not isinstance(expected, dict) or not expected:
        issues.append(f"line {line_no}: expected must be a non-empty object")
    if not isinstance(observed, dict) or not observed:
        issues.append(f"line {line_no}: observed must be a non-empty object")
    elif set(observed) == {"model_result"}:
        issues.append(f"line {line_no}: observed must be DUT-observed data, not model_result")

    observed_source = row.get("observed_source")
    if not isinstance(observed_source, dict):
        issues.append(f"line {line_no}: observed_source must name the DUT observation source")
    else:
        kind = str(observed_source.get("kind") or "").strip()
        if kind in MODEL_SOURCE_KINDS or "model" in kind:
            issues.append(f"line {line_no}: observed_source.kind must not be a model source: {kind}")
        elif kind not in OBSERVED_SOURCE_KINDS:
            issues.append(f"line {line_no}: observed_source.kind unsupported: {kind or '<missing>'}")
        locator_keys = {"path", "signal", "signals", "monitor", "wave", "transaction", "assertion"}
        if not any(observed_source.get(key) for key in locator_keys):
            issues.append(f"line {line_no}: observed_source needs path/signal/monitor/wave/transaction/assertion")

    expected_source = row.get("expected_source")
    if expected_source is not None:
        if not isinstance(expected_source, dict):
            issues.append(f"line {line_no}: expected_source must be an object when present")
        else:
            kind = str(expected_source.get("kind") or "").strip()
            if kind in DUT_DERIVED_EXPECTED_SOURCE_KINDS:
                issues.append(f"line {line_no}: expected_source.kind must not be derived from DUT behavior: {kind}")
            elif kind and kind not in EXPECTED_ORACLE_SOURCE_KINDS:
                issues.append(f"line {line_no}: expected_source.kind unsupported: {kind}")
            if kind == "approved_equivalent_oracle" and not str(expected_source.get("decision_receipt_id") or "").strip():
                issues.append(
                    f"line {line_no}: approved_equivalent_oracle expected_source requires decision_receipt_id"
                )

    if not str(row.get("goal_id") or "").strip():
        issues.append(f"line {line_no}: goal_id is required")
    if not str(row.get("scenario_id") or "").strip():
        issues.append(f"line {line_no}: scenario_id is required")
    if isinstance(row.get("cycle"), bool) or not isinstance(row.get("cycle"), (int, float)):
        issues.append(f"line {line_no}: cycle must be numeric")
    if not isinstance(row.get("passed"), bool):
        issues.append(f"line {line_no}: passed must be boolean")
    mismatch = row.get("mismatch")
    if not isinstance(mismatch, (str, bool)) and mismatch is not None:
        issues.append(f"line {line_no}: mismatch must be string, boolean, or null")
    if row.get("passed") is True and bool(mismatch):
        issues.append(f"line {line_no}: passing row must not carry mismatch")
    if row.get("passed") is False and not bool(mismatch):
        issues.append(f"line {line_no}: failing row must explain mismatch")
    if not isinstance(row.get("coverage_refs"), list):
        issues.append(f"line {line_no}: coverage_refs must be a list")
    return issues, is_standard, is_legacy


def _scoreboard_coverage_refs(ip: Path) -> set[str]:
    refs: set[str] = set()
    path = ip / "sim" / "scoreboard_events.jsonl"
    if not path.is_file():
        return refs
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            refs.update(_str_items(row.get("coverage_refs")))
    return refs


def _coverage_json_refs(ip: Path) -> set[str]:
    refs: set[str] = set()
    data = _read_json_file(ip / "cov" / "coverage.json")

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"id", "name", "ref", "coverage_ref", "coverage_refs", "coverpoint", "bin"}:
                    refs.update(_str_items(item))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return refs


def _observed_coverage_refs(ip: Path) -> set[str]:
    return _scoreboard_coverage_refs(ip) | _coverage_json_refs(ip)


def _coverage_status(ip: Path) -> tuple[bool, str]:
    path = ip / "cov" / "coverage.json"
    data = _read_json_file(path)
    if data is None:
        return False, "missing"
    if isinstance(data, dict):
        status = str(data.get("status") or data.get("result") or "").lower()
        if status:
            return True, status
        if data.get("blocked") is True:
            return True, "blocked"
        if data.get("pass") is True or data.get("passed") is True:
            return True, "pass"
    return True, "present"


def _closure_evidence_report(ip: Path, evidence_files: list[str]) -> dict[str, Any]:
    refs = sorted(dict.fromkeys(str(item).strip() for item in evidence_files if str(item).strip()))
    issues: list[str] = []
    facts: dict[str, Any] = {"files": refs}
    has_behavioral_evidence = False

    scoreboard_required = any(ref == str(SCOREBOARD_REL) or ref.endswith("/scoreboard_events.jsonl") for ref in refs)
    if scoreboard_required:
        summary = _scoreboard_summary(ip / SCOREBOARD_REL)
        sb = summary.get("summary") if isinstance(summary.get("summary"), dict) else {}
        facts["scoreboard"] = sb
        total = int(sb.get("total") or 0)
        if not summary.get("present") or total == 0:
            issues.append("scoreboard evidence is missing or empty")
        if int(sb.get("schema_failed") or 0) > 0 or int(sb.get("unreadable") or 0) > 0:
            issues.append("scoreboard evidence has invalid rows")
        if int(sb.get("failed") or 0) > 0:
            issues.append("scoreboard evidence has failing rows")

        live_rows = 0
        manual_spec_rows = 0
        dut_derived_expected_rows = 0
        hdl_not_run_rows = 0
        static_rows = 0
        missing_expected_source_rows = 0
        for line_no, row in _scoreboard_rows(ip):
            expected_source = row.get("expected_source")
            if not isinstance(expected_source, dict):
                missing_expected_source_rows += 1
            else:
                expected_kind = str(expected_source.get("kind") or "").strip()
                if expected_kind == "manual_spec":
                    manual_spec_rows += 1
                elif expected_kind in DUT_DERIVED_EXPECTED_SOURCE_KINDS:
                    dut_derived_expected_rows += 1

            observed_source = row.get("observed_source")
            observed_kind = ""
            if isinstance(observed_source, dict):
                observed_kind = str(observed_source.get("kind") or "").strip()
            if row.get("hdl_simulation_executed") is False:
                hdl_not_run_rows += 1
            strength_text = " ".join(
                str(row.get(key) or "")
                for key in ("evidence_strength", "runner_observation_mode", "observation_mode")
            ).lower()
            if any(token in strength_text for token in ("static", "smoke", "manual_spec", "not_hdl")):
                static_rows += 1
            if observed_kind in {"monitor", "waveform", "transaction", "assertion", "bus_monitor"}:
                live_rows += 1
            elif observed_kind == "interface_sample" and row.get("hdl_simulation_executed") is True:
                live_rows += 1
        facts["scoreboard_detail"] = {
            "live_observation_rows": live_rows,
            "manual_spec_rows": manual_spec_rows,
            "dut_derived_expected_rows": dut_derived_expected_rows,
            "hdl_not_run_rows": hdl_not_run_rows,
            "static_rows": static_rows,
            "missing_expected_source_rows": missing_expected_source_rows,
        }
        if missing_expected_source_rows:
            issues.append(f"{missing_expected_source_rows} scoreboard row(s) lack expected_source")
        if manual_spec_rows:
            issues.append(f"{manual_spec_rows} scoreboard row(s) use manual_spec expected_source")
        if dut_derived_expected_rows:
            issues.append(f"{dut_derived_expected_rows} scoreboard row(s) use DUT-derived expected_source")
        if hdl_not_run_rows:
            issues.append(f"{hdl_not_run_rows} scoreboard row(s) report hdl_simulation_executed=false")
        if static_rows:
            issues.append(f"{static_rows} scoreboard row(s) are marked static/smoke/not-HDL")
        if total and live_rows == 0:
            issues.append("scoreboard has no live DUT monitor/waveform/transaction/assertion observations")
        if total:
            has_behavioral_evidence = True

    coverage_required = any(ref == "cov/coverage.json" or ref.endswith("/coverage.json") for ref in refs)
    if coverage_required:
        coverage = _read_json_file(ip / "cov" / "coverage.json")
        facts["coverage"] = {
            "present": isinstance(coverage, dict),
            "status": str(coverage.get("status") or coverage.get("result") or "") if isinstance(coverage, dict) else "",
            "countable_for_release_closure": coverage.get("countable_for_release_closure") if isinstance(coverage, dict) else None,
            "row_count": len(coverage.get("coverage") or []) if isinstance(coverage, dict) and isinstance(coverage.get("coverage"), list) else 0,
        }
        if not isinstance(coverage, dict):
            issues.append("coverage evidence is missing or unreadable")
        else:
            status = str(coverage.get("status") or coverage.get("result") or "").lower()
            if coverage.get("countable_for_release_closure") is False:
                issues.append("coverage is explicitly non-countable for release closure")
            if status and status not in CLOSED_STATUSES and status not in {"pass", "passed"}:
                issues.append(f"coverage status is not closure-grade: {status}")

    formal_required = any(ref.startswith("formal/") or "/formal/" in ref for ref in refs)
    if formal_required:
        formal = _read_json_file(ip / "formal" / "formal_status.json")
        facts["formal"] = {
            "present": isinstance(formal, dict),
            "status": str(formal.get("status") or formal.get("result") or "") if isinstance(formal, dict) else "",
            "formal_engine_run": formal.get("formal_engine_run") if isinstance(formal, dict) else None,
        }
        if not isinstance(formal, dict):
            issues.append("formal evidence is missing or unreadable")
        else:
            status = str(formal.get("status") or formal.get("result") or "").lower()
            if formal.get("formal_engine_run") is not True:
                issues.append("formal engine was not run")
            if status not in {"pass", "passed", "proven", "closed", "validated"}:
                issues.append(f"formal status is not closure-grade: {status or '<missing>'}")
            if formal.get("formal_engine_run") is True and status in {"pass", "passed", "proven", "closed", "validated"}:
                has_behavioral_evidence = True

    if refs and not has_behavioral_evidence:
        issues.append("closed validation requires behavioral scoreboard or formal evidence, not static files alone")
    if not refs:
        issues.append("closed validation requires evidence files")

    return {
        "schema_version": "oag_closure_evidence_strength.v1",
        "closure_grade": not issues,
        "issues": sorted(dict.fromkeys(issues)),
        "facts": facts,
    }


def _rel_to_ip(ip: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ip.resolve()))
    except Exception:
        return str(path)


def _logical_rel_to_ip(ip: Path, path: Path) -> str:
    """Relative-to-ip path with any leading ``.oag/`` stripped.

    Used wherever a path is RECORDED/STORED as a logical identity so the
    active ``.oag`` layout never leaks into manifests, ledgers, or receipts.
    """
    rel = _rel_to_ip(ip, path)
    prefix = oag_paths.HIDDEN_DIR + "/"
    if rel.startswith(prefix):
        rel = rel[len(prefix):]
    return rel


def _compile_input_fingerprints(ip: Path) -> list[dict[str, str]]:
    # Ontology inputs route to the active layout (.oag or legacy) for the
    # filesystem target, but the fingerprint key stays the LOGICAL rel so the
    # compile manifest never records a ".oag/" prefix.
    ontology_rels = [
        "ontology/requirements.yaml",
        "ontology/obligations.yaml",
        "ontology/contracts.yaml",
        "ontology/stages.yaml",
        str(DESIGN_RULES_REL),
        str(STRUCTURE_REL),
        str(DECOMPOSITION_REL),
        str(MODELING_REL),
        str(DOMAIN_INTENT_REL),
        str(TB_METHODOLOGY_REL),
        str(VERIFICATION_PLAN_REL),
        "ontology/policies.yaml",
        str(PROTECTION_REL),
    ]
    unique: dict[str, Path] = {}
    for rel in ontology_rels:
        unique[rel] = oag_paths.legacy_or_hidden(ip, rel)
    candidates = [
        ip / "list" / "rtl.f",
    ]
    for source in _rtl_source_files(ip, _decomposition_doc(ip)):
        candidates.append(source)
    for source in _compile_approval_record_paths(ip):
        candidates.append(source)
    for pattern in (
        "sim/**/*.json",
        "sim/**/*.jsonl",
        "sim/**/*.xml",
        "cov/**/*.json",
        "mutation/**/*.json",
        "mutation/**/*.jsonl",
        "formal/**/*.json",
        "lint/**/*.json",
        "signoff/**/*",
    ):
        for path in ip.glob(pattern):
            if path.is_file():
                candidates.append(path)
    for path in candidates:
        rel = _rel_to_ip(ip, path)
        # Keep the manifest key logical: never record a ".oag/" prefix.
        if rel.startswith(oag_paths.HIDDEN_DIR + "/"):
            rel = rel[len(oag_paths.HIDDEN_DIR) + 1:]
        unique[rel] = path
    fingerprints: list[dict[str, str]] = []
    for rel, path in sorted(unique.items()):
        fingerprints.append(
            {
                "path": rel,
                "sha256": _sha256(path) if path.is_file() else "missing",
            }
        )
    return fingerprints


def _compile_outputs_present(ip: Path) -> bool:
    required = [
        oag_paths.legacy_or_hidden(ip, str(TRUTH_GRAPH_REL)),
        oag_paths.legacy_or_hidden(ip, str(DESIGN_SPEC_REL)),
        oag_paths.legacy_or_hidden(ip, str(DESIGN_FACTS_REL)),
        oag_paths.legacy_or_hidden(ip, str(DOMAIN_CROSSING_MATRIX_REL)),
        oag_paths.legacy_or_hidden(ip, str(TB_METHODOLOGY_MATRIX_REL)),
    ]
    packets = oag_paths.legacy_or_hidden(ip, str(AUTHORING_PACKETS_REL))
    return all(path.is_file() for path in required) and any(packets.glob("rtl__*.json")) and any(packets.glob("tb__*.json"))


def _compile_manifest_path(ip: Path) -> Path:
    return oag_paths.legacy_or_hidden(ip, str(COMPILE_MANIFEST_REL))


def _compile_approval_record_paths(ip: Path) -> list[Path]:
    records_dir = oag_paths.legacy_or_hidden(ip, "knowledge/records")
    if not records_dir.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(records_dir.glob("*.json")):
        data = _read_json_file(path)
        if not isinstance(data, dict):
            continue
        actor = data.get("actor") if isinstance(data.get("actor"), dict) else {}
        tags = {str(item).lower() for item in _as_list(data.get("tags"))}
        record_type = str(data.get("type") or "").lower()
        claim = str(data.get("claim") or "").lower()
        is_human = str(actor.get("kind") or "").lower() == "human"
        is_protected_decision = (
            record_type == "decision"
            and (
                "human_approval" in tags
                or "protected_truth" in tags
                or "protected_decomposition" in tags
                or "closed_approval" in tags
                or "protected" in claim
            )
        )
        if is_human or is_protected_decision:
            paths.append(path)
    return paths


def _fresh_compile_manifest(ip: Path, inputs: list[dict[str, str]]) -> dict[str, Any] | None:
    manifest = _read_json_file(_compile_manifest_path(ip))
    if not isinstance(manifest, dict):
        return None
    if manifest.get("input_fingerprints") != inputs:
        return None
    if not _compile_outputs_present(ip):
        return None
    outputs = manifest.get("output_fingerprints")
    if isinstance(outputs, list):
        for item in outputs:
            if not isinstance(item, dict):
                return None
            rel = str(item.get("path") or "")
            if not rel:
                return None
            path = ip / rel
            current = _sha256(path) if path.is_file() else "missing"
            if current != str(item.get("sha256") or ""):
                return None
    return manifest


def _write_compile_manifest(ip: Path, *, inputs: list[dict[str, str]], graph: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    outputs = []
    for rel in (TRUTH_GRAPH_REL, DESIGN_SPEC_REL, DESIGN_FACTS_REL, DOMAIN_CROSSING_MATRIX_REL, TB_METHODOLOGY_MATRIX_REL):
        path = oag_paths.legacy_or_hidden(ip, str(rel))
        outputs.append({"path": str(rel), "sha256": _sha256(path) if path.is_file() else "missing"})
    packets = oag_paths.legacy_or_hidden(ip, str(AUTHORING_PACKETS_REL))
    if packets.is_dir():
        for path in sorted(packets.glob("*.json")):
            outputs.append({"path": f"{AUTHORING_PACKETS_REL.as_posix()}/{path.name}", "sha256": _sha256(path) if path.is_file() else "missing"})
    manifest = {
        "schema_version": "oag_compile_manifest.v1",
        "ip": ip.name,
        "compiled_at": _now(),
        "status": graph.get("status"),
        "input_fingerprints": inputs,
        "output_fingerprints": outputs,
        "stats": graph.get("stats") or {},
        "generated": generated,
    }
    path = _compile_manifest_path(ip)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _cached_compile_result(ip: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    graph = _read_json_file(oag_paths.legacy_or_hidden(ip, str(TRUTH_GRAPH_REL)))
    graph = graph if isinstance(graph, dict) else {}
    return {
        "schema_version": "oag_compile.v1",
        "ip": ip.name,
        "path": str(oag_paths.legacy_or_hidden(ip, str(TRUTH_GRAPH_REL))),
        "status": str(graph.get("status") or manifest.get("status") or "pass"),
        "issues": graph.get("issues") if isinstance(graph.get("issues"), list) else [],
        "stats": graph.get("stats") if isinstance(graph.get("stats"), dict) else manifest.get("stats") or {},
        "generated": graph.get("generated") if isinstance(graph.get("generated"), dict) else manifest.get("generated") or {},
        "skipped": True,
        "skip_reason": "fresh_input_fingerprints",
        "manifest": str(_compile_manifest_path(ip)),
    }


def _compile_graph(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    graph_policy = _graph_policy(ip)
    skip_when_fresh = _truthy_policy(graph_policy.get("compile_skip_when_fresh"), default=True)
    force = _truthy_policy(arguments.get("force"), default=False) or _truthy_policy(arguments.get("rebuild"), default=False)
    compile_inputs = _compile_input_fingerprints(ip)
    if skip_when_fresh and not force:
        manifest = _fresh_compile_manifest(ip, compile_inputs)
        if manifest is not None:
            return _cached_compile_result(ip, manifest)
    reqs = _yaml_items(ip, "ontology/requirements.yaml", "requirements")
    obligations = _yaml_items(ip, "ontology/obligations.yaml", "obligations")
    contracts = _yaml_items(ip, "ontology/contracts.yaml", "contracts")
    stages = _yaml_items(ip, "ontology/stages.yaml", "stages")
    design_rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
    rule_instances = _yaml_items(ip, str(DESIGN_RULES_REL), "instances")
    policies = _policy_doc(ip)
    structure = _structure_doc(ip)
    domain_intent = _domain_intent_doc(ip)
    tb_methodology = _tb_methodology_doc(ip)
    decomposition = _decomposition_doc(ip)
    profile = _policy_profile(ip)
    structure_profile = _structure_profile(ip, policies=policies, decomposition=decomposition)

    nodes: list[dict[str, Any]] = [
        {"id": f"ip::{ip.name}", "type": "ip", "label": ip.name, "status": "present"},
        {"id": f"policy::closure_profile::{profile}", "type": "policy", "label": profile, "status": "active"},
    ]
    edges: list[dict[str, Any]] = [
        {"source": f"ip::{ip.name}", "target": f"policy::closure_profile::{profile}", "type": "uses_policy", "load_bearing": False}
    ]
    if structure_profile:
        nodes.append(
            {
                "id": f"policy::structure_profile::{structure_profile}",
                "type": "policy",
                "label": structure_profile,
                "status": "active",
            }
        )
        edges.append(
            {
                "source": f"ip::{ip.name}",
                "target": f"policy::structure_profile::{structure_profile}",
                "type": "uses_structure_profile",
                "load_bearing": True,
            }
        )
    issues: list[str] = []

    req_ids = {str(item.get("id") or "") for item in reqs if item.get("id")}
    obl_ids = {str(item.get("id") or "") for item in obligations if item.get("id")}
    contract_ids = {str(item.get("id") or "") for item in contracts if item.get("id")}
    rule_ids = {str(item.get("id") or "") for item in design_rules if item.get("id")}
    rule_kind_by_id = {str(item.get("id") or ""): str(item.get("kind") or "") for item in design_rules if item.get("id")}
    rule_kinds = {kind for kind in rule_kind_by_id.values() if kind}
    domain_refs = _domain_refs_by_kind(domain_intent)
    if not req_ids:
        issues.append("no requirements in ontology/requirements.yaml")
    if not obl_ids:
        issues.append("no obligations in ontology/obligations.yaml")
    if not contract_ids:
        issues.append("no contracts in ontology/contracts.yaml")
    if not stages:
        issues.append("no stage contracts in ontology/stages.yaml")
    if not rule_ids:
        issues.append(f"no design rules in {DESIGN_RULES_REL}")
    for kind in sorted(REQUIRED_DESIGN_RULE_KINDS - rule_kinds):
        issues.append(f"missing required design rule kind: {kind}")
    if domain_intent and domain_intent.get("schema_version") != "oag_domain_intent.v1":
        issues.append(f"{DOMAIN_INTENT_REL}: schema_version must be oag_domain_intent.v1")
    if tb_methodology and tb_methodology.get("schema_version") != "oag_tb_methodology.v1":
        issues.append(f"{TB_METHODOLOGY_REL}: schema_version must be oag_tb_methodology.v1")
    issues.extend(_protection_issues(ip))
    structure_issues, decomposition_summary = _decomposition_issues(
        ip,
        req_ids=req_ids,
        obl_ids=obl_ids,
        contract_ids=contract_ids,
    )
    issues.extend(structure_issues)
    issues.extend(_fault_model_coverage_issues(ip, req_ids=req_ids, obl_ids=obl_ids, contract_ids=contract_ids))
    issues.extend(_verification_role_decomposition_issues(ip, req_ids=req_ids, obl_ids=obl_ids, contract_ids=contract_ids))
    issues.extend(_interleaved_context_issues(ip, req_ids=req_ids, obl_ids=obl_ids, contract_ids=contract_ids))
    issues.extend(_signoff_design_rule_issues(ip, req_ids=req_ids, obl_ids=obl_ids, contract_ids=contract_ids))
    design_facts = _write_design_facts_graph(ip, decomposition, structure_profile)
    issues.extend(str(issue) for issue in _as_list(design_facts.get("issues")))

    namespace_ids = _structure_namespace_ids(structure)
    if oag_paths.legacy_or_hidden(ip, str(STRUCTURE_REL)).is_file():
        structure_id = f"structure::{ip.name}"
        nodes.append(
            {
                "id": structure_id,
                "type": "structure",
                "label": "structure namespace",
                "status": "declared",
                "stats": {
                    "signals": len(_as_list(structure.get("signals"))),
                    "interfaces": len(_as_list(structure.get("interfaces"))),
                    "registers": len(_as_list(structure.get("registers"))),
                    "state": len(_as_list(structure.get("state"))),
                    "derived_signals": len(_as_list(structure.get("derived_signals"))),
                },
            }
        )
        edges.append({"source": f"ip::{ip.name}", "target": structure_id, "type": "has_structure", "load_bearing": True})
        for sid in sorted(namespace_ids):
            nodes.append({"id": f"structure_ref::{sid}", "type": "structure_ref", "label": sid, "status": "declared"})
            edges.append({"source": structure_id, "target": f"structure_ref::{sid}", "type": "declares", "load_bearing": False})

    for module in decomposition_summary.get("modules") or []:
        if not isinstance(module, dict):
            continue
        mid = _module_id(module)
        if not mid:
            continue
        node_id = f"module::{mid}"
        nodes.append(
            {
                "id": node_id,
                "type": "module",
                "label": mid,
                "status": str(module.get("ownership") or "current_ip"),
                "file": str(module.get("file") or ""),
                "role": str(module.get("role") or ""),
            }
        )
        edges.append({"source": f"ip::{ip.name}", "target": node_id, "type": "has_module", "load_bearing": True})
        for oid in _str_items(module.get("owned_obligations") or module.get("obligations")):
            edges.append({"source": node_id, "target": f"obligation::{oid}", "type": "owns_obligation", "load_bearing": True})
        for cid in _str_items(module.get("owned_contracts") or module.get("contracts")):
            edges.append({"source": node_id, "target": f"contract::{cid}", "type": "owns_contract", "load_bearing": True})
        for sid in _str_items(module.get("structure_refs")):
            edges.append({"source": node_id, "target": f"structure_ref::{sid}", "type": "references_structure", "load_bearing": True})

    fact_artifact = f"artifact::{DESIGN_FACTS_REL}"
    nodes.append(
        {
            "id": fact_artifact,
            "type": "artifact",
            "label": "design facts graph",
            "status": str(design_facts.get("status") or "present"),
            "path": str(DESIGN_FACTS_REL),
            "stats": design_facts.get("stats") or {},
        }
    )
    edges.append({"source": f"ip::{ip.name}", "target": fact_artifact, "type": "has_artifact", "load_bearing": False})
    authored_module_ids = {
        _module_id(module)
        for module in decomposition_summary.get("modules") or []
        if isinstance(module, dict) and _module_id(module)
    }
    for node in _as_list(design_facts.get("nodes")):
        if isinstance(node, dict):
            nodes.append(node)
            edges.append({"source": fact_artifact, "target": str(node.get("id") or ""), "type": "contains_fact", "load_bearing": False})
    for edge in _as_list(design_facts.get("edges")):
        if isinstance(edge, dict):
            merged = dict(edge)
            merged.setdefault("load_bearing", False)
            edges.append(merged)
    for module in _as_list(design_facts.get("modules")):
        if not isinstance(module, dict):
            continue
        name = str(module.get("name") or "")
        if name in authored_module_ids:
            edges.append({"source": f"fact::module::{name}", "target": f"module::{name}", "type": "implements_module", "load_bearing": True})

    for req in reqs:
        rid = str(req.get("id") or "")
        if not rid:
            issues.append("requirement without id")
            continue
        nodes.append({"id": f"requirement::{rid}", "type": "requirement", "label": rid, "status": str(req.get("status") or "open")})
        edges.append({"source": f"ip::{ip.name}", "target": f"requirement::{rid}", "type": "has_requirement", "load_bearing": True})

    for obligation in obligations:
        oid = str(obligation.get("id") or "")
        if not oid:
            issues.append("obligation without id")
            continue
        nodes.append({"id": f"obligation::{oid}", "type": "obligation", "label": oid, "status": str(obligation.get("status") or "open")})
        requirement_refs = [str(item) for item in _as_list(obligation.get("requirement") or obligation.get("requirement_id") or obligation.get("requirement_ids")) if item]
        if not requirement_refs:
            issues.append(f"{oid}: obligation missing requirement ref")
        for rid in requirement_refs:
            if rid not in req_ids:
                issues.append(f"{oid}: requirement ref not found: {rid}")
            edges.append({"source": f"requirement::{rid}", "target": f"obligation::{oid}", "type": "has_obligation", "load_bearing": True})
        for cid in [str(item) for item in _as_list(obligation.get("contracts") or obligation.get("contract") or obligation.get("contract_ids")) if item]:
            if cid not in contract_ids:
                issues.append(f"{oid}: contract ref not found: {cid}")
            edges.append({"source": f"obligation::{oid}", "target": f"contract::{cid}", "type": "closed_by", "load_bearing": True})

    for contract in contracts:
        cid = str(contract.get("id") or "")
        if not cid:
            issues.append("contract without id")
            continue
        nodes.append({"id": f"contract::{cid}", "type": "contract", "label": cid, "status": str(contract.get("status") or "draft")})
        obligation_refs = [str(item) for item in _as_list(contract.get("obligation") or contract.get("obligations") or contract.get("obligation_ids")) if item]
        if not obligation_refs:
            issues.append(f"{cid}: contract missing obligation ref")
        for oid in obligation_refs:
            if oid not in obl_ids:
                issues.append(f"{cid}: obligation ref not found: {oid}")
            edge = {"source": f"obligation::{oid}", "target": f"contract::{cid}", "type": "closed_by", "load_bearing": True}
            if edge not in edges:
                edges.append(edge)
        if not _contract_has_evidence_declaration(contract):
            issues.append(f"{cid}: contract missing evidence declaration")
        method = str(contract.get("method") or "").lower()
        if method in FORMAL_CONTRACT_METHODS:
            refs = _contract_evidence_refs(contract)
            if not refs:
                issues.append(f"{cid}: formal/assertion contract missing assertion/proof reference")
            for ref in refs:
                if _path_like_ref(ref) and not (ip / ref).is_file():
                    issues.append(f"{cid}: proof/evidence ref missing on disk: {ref}")

    for rule in design_rules:
        rid = str(rule.get("id") or "")
        if not rid:
            issues.append("design rule without id")
            continue
        kind = str(rule.get("kind") or "")
        status = str(rule.get("status") or "active")
        if not kind:
            issues.append(f"{rid}: design rule missing kind")
        nodes.append({"id": f"rule::{rid}", "type": "rule", "label": rid, "status": status, "kind": kind})
        edges.append({"source": f"ip::{ip.name}", "target": f"rule::{rid}", "type": "uses_rule", "load_bearing": kind in REQUIRED_DESIGN_RULE_KINDS})

    for instance in rule_instances:
        iid = str(instance.get("id") or "")
        if not iid:
            issues.append("design rule instance without id")
            continue
        rid = str(instance.get("rule") or instance.get("rule_id") or "")
        status = str(instance.get("status") or "open").lower()
        kind = rule_kind_by_id.get(rid, "")
        nodes.append({"id": f"rule_instance::{iid}", "type": "rule_instance", "label": iid, "status": status, "rule": rid})
        edges.append({"source": f"ip::{ip.name}", "target": f"rule_instance::{iid}", "type": "has_rule_instance", "load_bearing": status not in {"template", "draft", "waived"}})
        if rid:
            edges.append({"source": f"rule::{rid}", "target": f"rule_instance::{iid}", "type": "instantiated_by", "load_bearing": False})
        if not rid:
            issues.append(f"{iid}: design rule instance missing rule ref")
        elif rid not in rule_ids:
            issues.append(f"{iid}: design rule ref not found: {rid}")
        if status in {"template", "draft"}:
            continue
        if status == "waived" and not str(instance.get("waiver") or instance.get("reason") or "").strip():
            issues.append(f"{iid}: waived design rule instance requires waiver reason")
            continue

        req_ref = str(instance.get("requirement") or instance.get("requirement_id") or "")
        obl_ref = str(instance.get("obligation") or instance.get("obligation_id") or "")
        contract_ref = str(instance.get("contract") or instance.get("contract_id") or "")
        if req_ref:
            if req_ref not in req_ids:
                issues.append(f"{iid}: requirement ref not found: {req_ref}")
            edges.append({"source": f"requirement::{req_ref}", "target": f"rule_instance::{iid}", "type": "constrains", "load_bearing": True})
        if obl_ref:
            if obl_ref not in obl_ids:
                issues.append(f"{iid}: obligation ref not found: {obl_ref}")
            edges.append({"source": f"obligation::{obl_ref}", "target": f"rule_instance::{iid}", "type": "constrains", "load_bearing": True})
        if contract_ref:
            if contract_ref not in contract_ids:
                issues.append(f"{iid}: contract ref not found: {contract_ref}")
            edges.append({"source": f"rule_instance::{iid}", "target": f"contract::{contract_ref}", "type": "verified_by", "load_bearing": True})

        if kind == "event_state_commit_consistency":
            for field in ("event", "state_update", "commit_condition"):
                if not str(instance.get(field) or "").strip():
                    issues.append(f"{iid}: event/state commit rule missing {field}")
            if not contract_ref:
                issues.append(f"{iid}: event/state commit rule missing contract ref")
        elif kind == "same_cycle_priority_declared":
            for field in ("conflict", "priority"):
                if not instance.get(field):
                    issues.append(f"{iid}: same-cycle priority rule missing {field}")
            for field_name, value in (("requirement", req_ref), ("obligation", obl_ref), ("contract", contract_ref)):
                if not value:
                    issues.append(f"{iid}: same-cycle priority rule missing {field_name} ref")
        elif kind == "contract_to_proof_coverage":
            if not contract_ref:
                issues.append(f"{iid}: contract proof coverage rule missing contract ref")
            evidence_refs = _instance_evidence_refs(instance)
            if profile == "signoff" and not evidence_refs:
                issues.append(f"{iid}: signoff design rule instance missing evidence ref")
            if status in {"closed", "pass", "passed", "validated"}:
                if not evidence_refs:
                    issues.append(f"{iid}: closed design rule instance missing evidence ref")
                for ref in evidence_refs:
                    if _path_like_ref(ref) and not (ip / ref).is_file():
                        issues.append(f"{iid}: design rule evidence ref missing on disk: {ref}")
        elif kind == "fault_model_coverage":
            for fault_model in _instance_fault_models(instance):
                fault_node = f"fault_model::{fault_model}"
                nodes.append({"id": fault_node, "type": "fault_model", "label": fault_model, "status": status})
                edges.append({"source": f"rule_instance::{iid}", "target": fault_node, "type": "targets_fault_model", "load_bearing": True})
            for result in _mutation_result_items(instance):
                mutation_id = str(result.get("id") or result.get("mutation") or result.get("mutant") or result.get("mutation_id") or "")
                if not mutation_id:
                    continue
                mutation_node = f"mutation::{mutation_id}"
                mutation_status = "killed" if _mutation_result_killed(result) else str(result.get("status") or "unknown")
                nodes.append({"id": mutation_node, "type": "mutation", "label": mutation_id, "status": mutation_status})
                edges.append({"source": f"rule_instance::{iid}", "target": mutation_node, "type": "has_mutation_result", "load_bearing": True})
                for fault_model in _mutation_result_fault_refs(result):
                    edges.append({"source": mutation_node, "target": f"fault_model::{fault_model}", "type": "tests_fault_model", "load_bearing": True})
        elif kind == "verification_role_decomposition":
            for role, artifacts in _verification_roles(instance).items():
                role_node = f"verification_role::{iid}::{role}"
                nodes.append({"id": role_node, "type": "verification_role", "label": role, "status": status})
                edges.append({"source": f"rule_instance::{iid}", "target": role_node, "type": "has_verification_role", "load_bearing": True})
                for artifact in artifacts:
                    artifact_node = f"artifact::{artifact}"
                    nodes.append({"id": artifact_node, "type": "artifact", "label": artifact, "status": "declared"})
                    edges.append({"source": role_node, "target": artifact_node, "type": "implemented_by", "load_bearing": True})
        elif kind in SIGNOFF_DESIGN_RULE_KINDS:
            for ref in _instance_evidence_refs(instance):
                artifact_node = f"artifact::{ref}"
                nodes.append({"id": artifact_node, "type": "artifact", "label": ref, "status": "declared"})
                edges.append({"source": f"rule_instance::{iid}", "target": artifact_node, "type": "evidenced_by", "load_bearing": status in CLOSED_STATUSES})
            for ref in _instance_coverage_refs(instance):
                coverage_node = f"coverage::{ref}"
                nodes.append({"id": coverage_node, "type": "coverage_ref", "label": ref, "status": "declared"})
                edges.append({"source": f"rule_instance::{iid}", "target": coverage_node, "type": "covers", "load_bearing": True})
            for ref in _instance_ref_values(instance, "sdc_ref", "sdc_refs", "timing_report", "timing_reports", "sta_report", "sta_reports"):
                artifact_node = f"artifact::{ref}"
                nodes.append({"id": artifact_node, "type": "artifact", "label": ref, "status": "declared"})
                edges.append({"source": f"rule_instance::{iid}", "target": artifact_node, "type": "uses_signoff_artifact", "load_bearing": True})
            if kind == "protocol_compliance" and str(instance.get("protocol") or "").strip():
                protocol = str(instance.get("protocol") or "").strip()
                protocol_node = f"protocol::{protocol}"
                nodes.append({"id": protocol_node, "type": "protocol", "label": protocol, "status": status})
                edges.append({"source": f"rule_instance::{iid}", "target": protocol_node, "type": "checks_protocol", "load_bearing": True})
            if kind == "cdc_crossing_coverage":
                for domain in _str_items(instance.get("clock_domains")) + _str_items(instance.get("domains")):
                    domain_node = f"clock_domain::{domain}"
                    nodes.append({"id": domain_node, "type": "clock_domain", "label": domain, "status": status})
                    edges.append({"source": f"rule_instance::{iid}", "target": domain_node, "type": "covers_domain", "load_bearing": True})

    for rule in design_rules:
        rid = str(rule.get("id") or "")
        if str(rule.get("kind") or "") != "rtl_language_subset":
            continue
        allowed = {str(item).strip() for item in _as_list(rule.get("allowed_constructs") or rule.get("allowed")) if str(item).strip()}
        forbidden = {str(item).strip() for item in _as_list(rule.get("forbidden_constructs") or rule.get("forbidden")) if str(item).strip()}
        if "logic" not in allowed:
            issues.append(f"{rid}: rtl language subset must allow logic")
        if "generate" not in allowed:
            issues.append(f"{rid}: rtl language subset must allow generate")
        if "generate" in forbidden or "generate_for" in forbidden or "genvar" in forbidden:
            issues.append(f"{rid}: rtl language subset must not forbid generate constructs")
        for construct in ("procedural_for", "procedural_while", "function", "task"):
            if construct not in forbidden:
                issues.append(f"{rid}: rtl language subset must forbid {construct}")

    for kind, node_type in (
        ("clock_domains", "clock_domain"),
        ("reset_domains", "reset_domain"),
        ("async_inputs", "async_input"),
        ("cdc_crossings", "cdc_crossing"),
        ("rdc_crossings", "rdc_crossing"),
    ):
        for item in _as_list(domain_intent.get(kind)):
            if not isinstance(item, dict):
                continue
            item_id = _domain_item_id(item, "clock", "reset", "signal", "source", "classification")
            if not item_id:
                issues.append(f"{DOMAIN_INTENT_REL}: {kind} item missing id")
                continue
            node_id = f"{node_type}::{item_id}"
            status = str(item.get("status") or "declared")
            nodes.append({"id": node_id, "type": node_type, "label": item_id, "status": status})
            edges.append({"source": f"ip::{ip.name}", "target": node_id, "type": f"has_{node_type}", "load_bearing": kind in {"cdc_crossings", "rdc_crossings"}})
            for ref_key, target_kind, edge_type in (
                ("clock_domain", "clock_domains", "uses_clock_domain"),
                ("source_domain", "clock_domains", "source_clock_domain"),
                ("destination_domain", "clock_domains", "destination_clock_domain"),
                ("reset_domain", "reset_domains", "uses_reset_domain"),
                ("source_reset_domain", "reset_domains", "source_reset_domain"),
                ("destination_reset_domain", "reset_domains", "destination_reset_domain"),
            ):
                ref = str(item.get(ref_key) or "").strip()
                if ref and _domain_ref_resolves(ref, domain_refs, (target_kind,)):
                    clean_ref = ref.split(".", 1)[1] if ref.startswith(f"{target_kind}.") else ref
                    edges.append({"source": node_id, "target": f"{target_kind[:-1]}::{clean_ref}", "type": edge_type, "load_bearing": True})

    for stage in stages:
        sid = str(stage.get("id") or "")
        if not sid:
            issues.append("stage without id")
            continue
        owner = str(stage.get("owner") or "")
        nodes.append({"id": f"stage::{sid}", "type": "stage", "label": sid, "status": "declared", "owner": owner})
        edges.append({"source": f"ip::{ip.name}", "target": f"stage::{sid}", "type": "has_stage", "load_bearing": False})
        gate = str(stage.get("gate") or "")
        if gate:
            gate_id = f"gate::{gate}"
            nodes.append({"id": gate_id, "type": "gate", "label": gate, "status": "declared"})
            edges.append({"source": f"stage::{sid}", "target": gate_id, "type": "gated_by", "load_bearing": True})

    generated_views = _write_generated_design_views(
        ip,
        profile=structure_profile,
        structure=structure,
        decomposition=decomposition,
        reqs=reqs,
        obligations=obligations,
        contracts=contracts,
        issues=issues,
    )
    generated_views["design_facts_graph"] = str(oag_paths.legacy_or_hidden(ip, str(DESIGN_FACTS_REL)))
    generated_views["design_facts"] = {
        "path": str(oag_paths.legacy_or_hidden(ip, str(DESIGN_FACTS_REL))),
        "status": design_facts.get("status") or "missing",
        "stats": design_facts.get("stats") or {},
        "extractor": design_facts.get("extractor") or {},
    }
    domain_matrix = _write_domain_crossing_matrix(ip)
    generated_views["domain_crossing_matrix"] = {
        "path": str(oag_paths.legacy_or_hidden(ip, str(DOMAIN_CROSSING_MATRIX_REL))),
        "status": domain_matrix.get("status") or "missing",
        "stats": domain_matrix.get("stats") or {},
    }
    tb_matrix = _write_tb_methodology_matrix(ip)
    generated_views["tb_methodology_matrix"] = {
        "path": str(oag_paths.legacy_or_hidden(ip, str(TB_METHODOLOGY_MATRIX_REL))),
        "status": tb_matrix.get("status") or "missing",
        "stats": tb_matrix.get("stats") or {},
    }

    graph = {
        "schema_version": "oag_design_truth_graph.v1",
        "compiled_by": "oag.compile",
        "compiled_at": _now(),
        "ip": ip.name,
        "closure_profile": profile,
        "structure_profile": structure_profile,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "stats": {
            "requirements": len(req_ids),
            "obligations": len(obl_ids),
            "contracts": len(contract_ids),
            "structure_refs": len(namespace_ids),
            "modules": int(decomposition_summary.get("module_count") or 0),
            "design_facts_modules": int((design_facts.get("stats") or {}).get("modules") or 0),
            "design_facts_instances": int((design_facts.get("stats") or {}).get("instances") or 0),
            "domain_clock_domains": int((domain_matrix.get("stats") or {}).get("clock_domains") or 0),
            "domain_reset_domains": int((domain_matrix.get("stats") or {}).get("reset_domains") or 0),
            "domain_cdc_crossings": int((domain_matrix.get("stats") or {}).get("cdc_crossings") or 0),
            "domain_rdc_crossings": int((domain_matrix.get("stats") or {}).get("rdc_crossings") or 0),
            "tb_methodology_roles": int((tb_matrix.get("stats") or {}).get("roles") or 0),
            "tb_coverage_goals": int((tb_matrix.get("stats") or {}).get("coverage_goals") or 0),
            "tb_assertion_candidates": int((tb_matrix.get("stats") or {}).get("assertion_candidates") or 0),
            "tb_formal_candidates": int((tb_matrix.get("stats") or {}).get("formal_candidates") or 0),
            "stages": len(stages),
            "design_rules": len(rule_ids),
            "design_rule_instances": len(rule_instances),
            "authoring_packets": int(generated_views.get("authoring_packet_count") or 0),
            "load_bearing_edges": sum(1 for edge in edges if edge.get("load_bearing")),
        },
        "generated": generated_views,
        "nodes": nodes,
        "edges": edges,
    }
    out = _truth_graph_path(ip)
    out.parent.mkdir(parents=True, exist_ok=True)
    graph = _write_json_semantic_stable(out, graph, volatile_keys={"compiled_at"})
    manifest = _write_compile_manifest(ip, inputs=compile_inputs, graph=graph, generated=generated_views)
    return {
        "schema_version": "oag_compile.v1",
        "ip": ip.name,
        "path": str(out),
        "status": graph["status"],
        "issues": issues,
        "stats": graph["stats"],
        "generated": generated_views,
        "skipped": False,
        "manifest": str(_compile_manifest_path(ip)),
        "manifest_status": manifest.get("status"),
    }


def _stage_receipt_issues(ip: Path, *, require_any: bool = False) -> list[str]:
    receipts_dir = oag_paths.legacy_or_hidden(ip, str(STAGE_RECEIPTS_REL))
    receipts = sorted(receipts_dir.glob("*.json")) if receipts_dir.is_dir() else []
    if require_any and not receipts:
        return [f"missing stage run receipt under {STAGE_RECEIPTS_REL}"]
    issues: list[str] = []
    required = {"stage", "owner", "status", "command", "actor", "started_at", "completed_at", "input_fingerprints", "output_fingerprints"}
    for receipt in receipts:
        data = _read_json_file(receipt)
        if not isinstance(data, dict):
            issues.append(f"{receipt.relative_to(ip)} is not valid JSON")
            continue
        missing = sorted(required - set(data))
        if missing:
            issues.append(f"{receipt.relative_to(ip)} missing fields: {', '.join(missing)}")
        if str(data.get("status") or "").lower() not in {"pass", "passed", "ok"}:
            issues.append(f"{receipt.relative_to(ip)} status is not pass: {data.get('status')}")
        for key in ("input_fingerprints", "output_fingerprints"):
            for item in _as_list(data.get(key)):
                if not isinstance(item, dict):
                    issues.append(f"{receipt.relative_to(ip)} {key} item is not an object")
                    continue
                rel = str(item.get("path") or "")
                expected = str(item.get("sha256") or "")
                if not rel or not expected:
                    issues.append(f"{receipt.relative_to(ip)} {key} item missing path or sha256")
                    continue
                path = ip / rel
                if not path.is_file():
                    issues.append(f"{receipt.relative_to(ip)} fingerprint path missing: {rel}")
                    continue
                actual = _sha256(path)
                if actual != expected:
                    issues.append(f"{receipt.relative_to(ip)} fingerprint mismatch: {rel}")
    return issues


def _evidence_file_hashes(ip: Path, files: list[Any]) -> list[dict[str, str]]:
    hashes: list[dict[str, str]] = []
    for item in files:
        rel = str(item or "").strip()
        if not rel:
            continue
        path = ip / rel
        hashes.append({"path": rel, "sha256": _sha256(path) if path.is_file() else "missing"})
    return hashes


def _knowledge_records(ip: Path) -> list[dict[str, Any]]:
    records_dir = oag_paths.legacy_or_hidden(ip, "knowledge/records")
    records: list[dict[str, Any]] = []
    if not records_dir.is_dir():
        return records
    for path in sorted(records_dir.glob("*.json")):
        data = _read_json_file(path)
        if isinstance(data, dict):
            data["_path"] = str(path)
            records.append(data)
    return records


def _load_knowledge_record_file(path: Path) -> dict[str, Any] | None:
    if path.suffix == ".json":
        data = _read_json_file(path)
    elif path.suffix in {".yaml", ".yml"}:
        data = _read_yaml_file(path)
    else:
        data = None
    return data if isinstance(data, dict) else None


def _record_index_summary(ip: Path, path: Path, record: dict[str, Any]) -> dict[str, Any]:
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    actor = record.get("actor") if isinstance(record.get("actor"), dict) else {}
    rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
    requirement = rocev.get("requirement") if isinstance(rocev.get("requirement"), dict) else {}
    obligation = rocev.get("obligation") if isinstance(rocev.get("obligation"), dict) else {}
    contract = rocev.get("contract") if isinstance(rocev.get("contract"), dict) else {}
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    if not evidence:
        evidence = rocev.get("evidence") if isinstance(rocev.get("evidence"), dict) else {}
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    if not validation:
        validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else {}
    promotion = record.get("promotion") if isinstance(record.get("promotion"), dict) else {}
    record_rel = path.relative_to(ip)
    if record_rel.parts[:1] == (oag_paths.HIDDEN_DIR,):
        record_rel = Path(*record_rel.parts[1:])
    return {
        "id": str(record.get("id") or path.stem),
        "path": str(record_rel),
        "ip": str(scope.get("ip") or ip.name),
        "stage": str(scope.get("stage") or record.get("stage") or "general"),
        "type": str(record.get("type") or "log"),
        "actor_kind": str(actor.get("kind") or record.get("actor_kind") or ""),
        "actor_id": str(actor.get("id") or record.get("actor_id") or ""),
        "actor_surface": str(actor.get("surface") or record.get("actor_surface") or ""),
        "claim": str(record.get("claim") or ""),
        "summary": str(record.get("summary") or ""),
        "tags": record.get("tags") if isinstance(record.get("tags"), list) else [],
        "requirement_id": str(requirement.get("id") or ""),
        "requirement_text": str(requirement.get("text") or ""),
        "obligation_id": str(obligation.get("id") or ""),
        "obligation_text": str(obligation.get("text") or ""),
        "contract_id": str(contract.get("id") or ""),
        "contract_method": str(contract.get("method") or ""),
        "contract_pass_condition": str(contract.get("pass_condition") or ""),
        "validation_status": _normal_status(validation.get("status") or record.get("status") or ""),
        "validation_verdict": str(validation.get("verdict") or ""),
        "promotion_state": str(promotion.get("state") or ""),
        "evidence_files": [str(item) for item in _as_list(evidence.get("files")) if str(item)],
        "evidence_tests": [str(item) for item in _as_list(evidence.get("tests")) if str(item)],
        "commit": str(evidence.get("commit") or ""),
        "created_at": str(record.get("created_at") or ""),
    }


def _rebuild_knowledge_index(ip: Path) -> dict[str, Any]:
    records_dir = oag_paths.legacy_or_hidden(ip, "knowledge/records")
    summaries: list[dict[str, Any]] = []
    if records_dir.is_dir():
        paths = sorted([*records_dir.glob("*.json"), *records_dir.glob("*.yaml"), *records_dir.glob("*.yml")])
        for path in paths:
            record = _load_knowledge_record_file(path)
            if record is not None:
                summaries.append(_record_index_summary(ip, path, record))
    index = {
        "schema_version": "ip_knowledge_index.v1",
        "generated_at": _now(),
        "ip": ip.name,
        "record_count": len(summaries),
        "records": summaries,
    }
    _knowledge_index(ip).write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def _record_supersedes(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
    rocev_validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else {}
    for source in [record.get("supersedes"), validation.get("supersedes"), rocev_validation.get("supersedes")]:
        for item in _as_list(source):
            ref = str(item or "").strip()
            if ref:
                values.append(ref[:-5] if ref.endswith(".json") else ref)
    return sorted(dict.fromkeys(values))


def _superseded_record_ids(records: list[dict[str, Any]]) -> set[str]:
    superseded: set[str] = set()
    for record in records:
        validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
        rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
        rocev_validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else {}
        if _normal_status(validation.get("status") or record.get("status")) not in CLOSED_STATUSES:
            continue
        if _normal_status(rocev_validation.get("status")) not in CLOSED_STATUSES:
            continue
        superseded.update(_record_supersedes(record))
    return superseded


def _record_evidence_issues(ip: Path) -> list[str]:
    issues: list[str] = []
    records = _knowledge_records(ip)
    superseded = _superseded_record_ids(records)
    for record in records:
        if str(record.get("id") or "") in superseded:
            continue
        validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
        status = _normal_status(validation.get("status") or record.get("status"))
        if status not in CLOSED_STATUSES:
            continue
        rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
        rocev_validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else {}
        if _normal_status(rocev_validation.get("status")) not in CLOSED_STATUSES:
            issues.append(f"{Path(str(record.get('_path'))).name}: closed record requires explicit rocev.validation.status")
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        files = [str(item) for item in evidence.get("files", []) if item]
        tests = [str(item) for item in evidence.get("tests", []) if item]
        commit = str(evidence.get("commit") or "")
        if not files and not tests and not commit:
            issues.append(f"{Path(str(record.get('_path'))).name}: closed record without evidence")
        file_hashes = evidence.get("file_hashes") if isinstance(evidence.get("file_hashes"), list) else []
        hash_by_path: dict[str, str] = {}
        if files and not file_hashes:
            issues.append(f"{Path(str(record.get('_path'))).name}: closed record missing evidence file hashes")
        for item in file_hashes:
            if not isinstance(item, dict):
                issues.append(f"{Path(str(record.get('_path'))).name}: evidence file hash item is not an object")
                continue
            rel = str(item.get("path") or "")
            digest = str(item.get("sha256") or "")
            if not rel or not digest:
                issues.append(f"{Path(str(record.get('_path'))).name}: evidence file hash missing path or sha256")
                continue
            hash_by_path[rel] = digest
        for rel in files:
            path = ip / rel
            if not path.is_file():
                issues.append(f"{Path(str(record.get('_path'))).name}: evidence file missing on disk: {rel}")
                continue
            expected = hash_by_path.get(rel)
            if not expected:
                issues.append(f"{Path(str(record.get('_path'))).name}: evidence file missing hash: {rel}")
                continue
            if expected == "missing":
                issues.append(f"{Path(str(record.get('_path'))).name}: evidence file hash recorded missing: {rel}")
                continue
            actual = _sha256(path)
            if actual != expected:
                issues.append(f"{Path(str(record.get('_path'))).name}: evidence file stale: {rel}")
        strength = _closure_evidence_report(ip, files)
        if not strength.get("closure_grade"):
            for issue in _as_list(strength.get("issues"))[:8]:
                issues.append(f"{Path(str(record.get('_path'))).name}: weak closure evidence: {issue}")
    return issues


def _record_subjects(record: dict[str, Any], status: str) -> list[dict[str, str]]:
    subjects: list[dict[str, str]] = []
    rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
    record_validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    default_status = str(status or record_validation.get("status") or "").lower()
    for kind in ("requirement", "obligation", "contract"):
        obj = rocev.get(kind) if isinstance(rocev.get(kind), dict) else {}
        obj_id = str(obj.get("id") or "").strip()
        if not obj_id:
            continue
        obj_status = str(obj.get("status") or default_status or "unknown").lower()
        subjects.append({"kind": kind, "id": obj_id, "status": obj_status})
    validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else record.get("validation") if isinstance(record.get("validation"), dict) else {}
    validation_id = str(validation.get("id") or "").strip()
    if validation_id:
        subjects.append({"kind": "validation", "id": validation_id, "status": str(validation.get("status") or default_status or "unknown").lower()})
    return subjects


def _monotonic_issues(ip: Path) -> list[str]:
    issues: list[str] = []
    last_status: dict[str, str] = {}
    superseded = _superseded_record_ids(_knowledge_records(ip))
    for entry in _ledger_entries(ip):
        if "_invalid" in entry:
            continue
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
        record_id = str(record.get("id") or "").strip()
        if record_id and record_id in superseded:
            continue
        approved = _is_human_approved(entry)
        for subject in _as_list(entry.get("monotonic_subjects")):
            if not isinstance(subject, dict):
                continue
            kind = str(subject.get("kind") or "").strip()
            obj_id = str(subject.get("id") or "").strip()
            status = str(subject.get("status") or "").lower().strip()
            if not kind or not obj_id or not status:
                continue
            key = f"{kind}:{obj_id}"
            previous = last_status.get(key)
            if previous in CLOSED_STATUSES and status in WEAKER_STATUSES and not approved:
                issues.append(
                    f"monotonic closure violation: {key} moved from {previous} to {status} without approved decision"
                )
            last_status[key] = status
    return issues


def _obligation_contract_refs(obligation: dict[str, Any], contracts: list[dict[str, Any]]) -> list[str]:
    oid = str(obligation.get("id") or "").strip()
    refs = _str_items(obligation.get("contracts"))
    refs.extend(_str_items(obligation.get("contract")))
    refs.extend(_str_items(obligation.get("contract_ids")))
    for contract in contracts:
        cid = str(contract.get("id") or "").strip()
        if not cid:
            continue
        obligation_refs = _str_items(contract.get("obligation"))
        obligation_refs.extend(_str_items(contract.get("obligations")))
        obligation_refs.extend(_str_items(contract.get("obligation_ids")))
        if oid in obligation_refs:
            refs.append(cid)
    return sorted(dict.fromkeys(ref for ref in refs if ref))


def _closed_record_links(ip: Path) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    records = _knowledge_records(ip)
    superseded = _superseded_record_ids(records)
    for record in records:
        if str(record.get("id") or "") in superseded:
            continue
        validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
        rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
        rocev_validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else {}
        if _normal_status(validation.get("status") or record.get("status")) not in CLOSED_STATUSES:
            continue
        if _normal_status(rocev_validation.get("status")) not in CLOSED_STATUSES:
            continue
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        if not (_as_list(evidence.get("files")) or _as_list(evidence.get("tests")) or str(evidence.get("commit") or "").strip()):
            continue
        strength = _closure_evidence_report(ip, _str_items(evidence.get("files")))
        if not strength.get("closure_grade"):
            continue
        obligation = rocev.get("obligation") if isinstance(rocev.get("obligation"), dict) else {}
        contract = rocev.get("contract") if isinstance(rocev.get("contract"), dict) else {}
        oid = str(obligation.get("id") or "").strip()
        cid = str(contract.get("id") or "").strip()
        if not oid or not cid:
            continue
        links.append({"record": str(record.get("id") or ""), "obligation": oid, "contract": cid})
    return links


def _closure_matrix(ip: Path) -> dict[str, Any]:
    obligations = _yaml_items(ip, "ontology/obligations.yaml", "obligations")
    contracts = _yaml_items(ip, "ontology/contracts.yaml", "contracts")
    contract_ids = {str(contract.get("id") or "").strip() for contract in contracts if contract.get("id")}
    links = _closed_record_links(ip)
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    if obligations and not contracts:
        issues.append("closure matrix has obligations but no contracts")
    for obligation in obligations:
        oid = str(obligation.get("id") or "").strip()
        if not oid:
            continue
        status = _normal_status(obligation.get("status") or "open")
        if status in {"template", "waived"}:
            rows.append({"obligation": oid, "status": status, "contracts": [], "closed": True, "records": [], "waived": status == "waived"})
            continue
        contract_refs = _obligation_contract_refs(obligation, contracts)
        for cid in contract_refs:
            if cid not in contract_ids:
                issues.append(f"{oid}: closure matrix contract ref not found: {cid}")
        closed_records = [
            link["record"]
            for link in links
            if link["obligation"] == oid and (not contract_refs or link["contract"] in contract_refs)
        ]
        if not contract_refs:
            issues.append(f"{oid}: no contract bound in closure matrix")
        if contract_refs and not closed_records:
            issues.append(f"{oid}: no closed validation record linking obligation to contract")
        rows.append(
            {
                "obligation": oid,
                "status": status,
                "contracts": contract_refs,
                "closed": bool(closed_records),
                "records": closed_records,
            }
        )
    if not obligations:
        issues.append("closure matrix has no obligations")
    return {
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "rows": rows,
        "closed": sum(1 for row in rows if row.get("closed")),
        "total": len(rows),
    }


def _approved_equivalent_oracle_issues(context: str, source: dict[str, Any]) -> list[str]:
    required = [
        "decision_receipt_id",
        "approver",
        "scope",
        "substitute_artifact",
        "reason_full_model_not_required",
        "obligations_covered",
    ]
    missing = [key for key in required if not source.get(key)]
    if missing:
        return [
            f"{context}: approved equivalent oracle requires {', '.join(missing)}"
        ]
    return []


def _tb_coverage_goal_ids(ip: Path, tb_methodology: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for item in _as_list(tb_methodology.get("coverage_goals")):
        if not isinstance(item, dict):
            refs.update(_str_items(item))
            continue
        refs.update(
            _str_items(
                item.get("id")
                or item.get("name")
                or item.get("ref")
                or item.get("coverage_ref")
                or item.get("coverage_refs")
            )
        )
    evidence_plan = _evidence_plan_doc(ip)
    for item in _as_list(evidence_plan.get("coverage_goals")):
        if isinstance(item, dict):
            refs.update(_str_items(item.get("id") or item.get("name") or item.get("coverage_ref") or item.get("coverage_refs")))
        else:
            refs.update(_str_items(item))
    for scenario in _as_list(evidence_plan.get("planned_scenarios")):
        if isinstance(scenario, dict):
            refs.update(_str_items(scenario.get("coverage_refs") or scenario.get("expected_coverage_refs")))
    for instance in _yaml_items(ip, str(DESIGN_RULES_REL), "instances"):
        refs.update(_instance_coverage_refs(instance))
    refs.update(_coverage_json_refs(ip))
    return {ref for ref in refs if ref}


def _tb_random_enabled(tb_methodology: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    policy = tb_methodology.get("methodology_policy") if isinstance(tb_methodology.get("methodology_policy"), dict) else {}
    stimulus = tb_methodology.get("stimulus_strategy") if isinstance(tb_methodology.get("stimulus_strategy"), dict) else {}
    random_cfg = stimulus.get("constrained_random")
    if not isinstance(random_cfg, dict):
        random_cfg = {}
    text = " ".join(
        str(value or "").lower()
        for value in (
            policy.get("default_depth"),
            policy.get("methodology_depth"),
            stimulus.get("methodology_depth"),
            stimulus.get("random_strategy"),
        )
    )
    enabled = bool(random_cfg.get("enabled") is True or "random" in text)
    return enabled, random_cfg


def _tb_methodology_issues(ip: Path, closure_matrix: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    policies = _policy_doc(ip)
    tb_policy = policies.get("tb_methodology_policy") if isinstance(policies.get("tb_methodology_policy"), dict) else {}
    tb_path = oag_paths.legacy_or_hidden(ip, str(TB_METHODOLOGY_REL))
    tb_methodology = _tb_methodology_doc(ip)
    closed_contracts = _closed_contract_ids(ip, closure_matrix)
    scoreboard_rows = _scoreboard_rows(ip)
    closure_uses_tb = bool(closed_contracts) and (
        _closed_records_reference_scoreboard(ip)
        or bool(scoreboard_rows)
        or (ip / SCENARIO_MAPPING_REL).is_file()
        or (ip / "sim" / "results.xml").is_file()
    )

    required = bool(tb_policy) or closure_uses_tb
    if required and not tb_policy:
        issues.append(f"TB_CHECK_METHODOLOGY_POLICY_PRESENT: {POLICIES_REL} missing tb_methodology_policy")
    if required and not tb_path.is_file():
        issues.append(f"TB_CHECK_METHODOLOGY_PRESENT: missing canonical TB methodology file {TB_METHODOLOGY_REL}")
        return issues
    if not tb_path.is_file():
        return issues
    if tb_methodology.get("schema_version") != "oag_tb_methodology.v1":
        issues.append(f"{TB_METHODOLOGY_REL}: schema_version must be oag_tb_methodology.v1")

    goal_ids = _tb_coverage_goal_ids(ip, tb_methodology)
    random_enabled, random_cfg = _tb_random_enabled(tb_methodology)
    if random_enabled:
        constraints = _as_list(random_cfg.get("constraints"))
        if tb_policy.get("random_requires_constraints") is True and not [item for item in constraints if str(item).strip()]:
            issues.append("TB_CHECK_RANDOM_REQUIRES_CONSTRAINTS: constrained-random closure requires named constraints")
        if tb_policy.get("random_requires_coverage_goals") is True and not goal_ids:
            issues.append("TB_CHECK_RANDOM_REQUIRES_COVERAGE_GOALS: constrained-random closure requires coverage_goals")

    if not closure_uses_tb:
        return issues

    if tb_policy.get("results_xml_required_after_sim") is True and not (ip / "sim" / "results.xml").is_file():
        issues.append("TB_CHECK_RESULTS_XML_PRESENT: missing sim/results.xml for closure-grade TB/sim evidence")
    if tb_policy.get("scenario_mapping_required_after_sim") is True and not (ip / SCENARIO_MAPPING_REL).is_file():
        issues.append(
            f"TB_CHECK_SCENARIO_MAPPING_PRESENT_AFTER_SIM: missing {SCENARIO_MAPPING_REL} for closure-grade TB/sim evidence"
        )
    if tb_policy.get("scoreboard_rows_required_after_sim") is True and not scoreboard_rows:
        issues.append(
            f"TB_CHECK_SCOREBOARD_ROWS_PRESENT_AFTER_SIM: missing {SCOREBOARD_REL} rows for closure-grade TB/sim evidence"
        )

    coverage_refs_require_goals = tb_policy.get("coverage_refs_require_goals") is True
    for line_no, row in scoreboard_rows:
        if not str(row.get("contract_id") or "").strip():
            issues.append(f"TB_CHECK_SCOREBOARD_ROWS_HAVE_CONTRACT_AND_OBLIGATION: line {line_no}: missing contract_id")
        if not str(row.get("obligation_id") or "").strip():
            issues.append(f"TB_CHECK_SCOREBOARD_ROWS_HAVE_CONTRACT_AND_OBLIGATION: line {line_no}: missing obligation_id")
        refs = _str_items(row.get("coverage_refs"))
        if _scoreboard_row_failed(row) and refs:
            issues.append(
                f"TB_CHECK_FAILED_ROWS_NOT_COUNTED_FOR_COVERAGE: line {line_no}: failed row carries coverage_refs {', '.join(refs)}"
            )
        if coverage_refs_require_goals:
            for ref in refs:
                if ref not in goal_ids:
                    issues.append(f"TB_CHECK_COVERAGE_REFS_RESOLVE_TO_CONTRACTS: line {line_no}: coverage_ref not resolved: {ref}")

    return issues


def _modeling_oracle_issues(ip: Path, closure_matrix: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    policies = _policy_doc(ip)
    modeling_policy = policies.get("modeling_policy") if isinstance(policies.get("modeling_policy"), dict) else {}
    modeling_path = oag_paths.legacy_or_hidden(ip, str(MODELING_REL))
    modeling = _modeling_doc(ip)

    if not modeling_policy:
        issues.append(f"CHECK_MODELING_POLICY_PRESENT: {POLICIES_REL} missing modeling_policy")
    if not modeling_path.is_file():
        issues.append(f"CHECK_MODELING_POLICY_PRESENT: missing canonical modeling file {MODELING_REL}")
    elif modeling.get("schema_version") != "oag_modeling.v1":
        issues.append(f"{MODELING_REL}: schema_version must be oag_modeling.v1")

    behavior_refs_known = _flatten_model_refs(modeling.get("behavior_model") if isinstance(modeling, dict) else {}, "behavior_model")
    cycle_refs_known = _flatten_model_refs(modeling.get("cycle_rules") if isinstance(modeling, dict) else {}, "cycle_rules")
    planned_scenarios = _planned_scenario_ids(ip)
    actual_scenarios = _scenario_mapping_ids(ip)
    scoreboard_ids = _scoreboard_row_ids(ip)
    closed_contracts = _closed_contract_ids(ip, closure_matrix)
    contracts = _yaml_items(ip, "ontology/contracts.yaml", "contracts")

    for item in _as_list(modeling.get("approved_equivalent_oracles") if isinstance(modeling, dict) else []):
        if isinstance(item, dict):
            oid = str(item.get("id") or item.get("decision_receipt_id") or "approved_equivalent_oracle").strip()
            issues.extend(_approved_equivalent_oracle_issues(f"{MODELING_REL}:{oid}", item))

    for contract in contracts:
        cid = str(contract.get("id") or "").strip()
        if not cid:
            continue
        contract_type = str(contract.get("contract_type") or contract.get("type") or "").strip().lower()
        behavior_refs = _str_items(contract.get("behavior_refs"))
        cycle_rule_refs = _str_items(contract.get("cycle_rule_refs"))
        scenario_refs = _str_items(contract.get("scenario_refs"))
        scoreboard_row_refs = _str_items(contract.get("scoreboard_row_refs"))
        approved_equivalents = [
            item
            for item in _as_list(contract.get("approved_equivalent_oracles"))
            if isinstance(item, dict)
        ]

        for ref in behavior_refs:
            if not _model_ref_resolves(ref, behavior_refs_known, "behavior_model"):
                issues.append(f"CHECK_CONTRACT_REFS_RESOLVE: {cid}: behavior_ref not found: {ref}")
        for ref in cycle_rule_refs:
            if not _model_ref_resolves(ref, cycle_refs_known, "cycle_rules"):
                issues.append(f"CHECK_CONTRACT_REFS_RESOLVE: {cid}: cycle_rule_ref not found: {ref}")
        for ref in scenario_refs:
            if ref not in planned_scenarios and ref not in actual_scenarios:
                issues.append(f"CHECK_CONTRACT_REFS_RESOLVE: {cid}: scenario_ref not found: {ref}")
        if scoreboard_ids:
            for ref in scoreboard_row_refs:
                if ref not in scoreboard_ids:
                    issues.append(f"CHECK_CONTRACT_REFS_RESOLVE: {cid}: scoreboard_row_ref not found: {ref}")
        for item in approved_equivalents:
            issues.extend(_approved_equivalent_oracle_issues(f"{cid}", item))

        if cid not in closed_contracts:
            continue

        has_equivalent = bool(approved_equivalents)
        if contract_type == "behavioral" and not behavior_refs and not has_equivalent:
            issues.append(
                f"CHECK_BEHAVIOR_MODEL_REQUIRED_FOR_BEHAVIORAL_CLOSURE: {cid}: "
                "closed behavioral contract requires behavior_refs or approved equivalent oracle with decision_receipt_id"
            )
        if contract_type == "temporal" and not cycle_rule_refs and not has_equivalent:
            issues.append(
                f"CHECK_CYCLE_RULES_REQUIRED_FOR_TEMPORAL_CLOSURE: {cid}: "
                "closed temporal contract requires cycle_rule_refs or approved equivalent oracle with decision_receipt_id"
            )
        method = str(contract.get("method") or "").strip().lower()
        if method == "scoreboard" and not scenario_refs:
            issues.append(
                f"CHECK_PLANNED_SCENARIOS_EXIST_BEFORE_IMPL_CLOSURE: {cid}: "
                "scoreboard closure requires scenario_refs backed by req/evidence_plan.yaml"
            )

    scoreboard_rows = _scoreboard_rows(ip)
    closure_uses_scoreboard = bool(closed_contracts) and (_closed_records_reference_scoreboard(ip) or bool(scoreboard_rows))
    if closure_uses_scoreboard and not (ip / SCENARIO_MAPPING_REL).is_file():
        issues.append(
            f"CHECK_SCENARIO_MAPPING_EXISTS_AFTER_TB: missing {SCENARIO_MAPPING_REL} for closure-grade TB/sim evidence"
        )

    if closed_contracts:
        for line_no, row in scoreboard_rows:
            expected_source = row.get("expected_source")
            if not isinstance(expected_source, dict):
                issues.append(
                    f"CHECK_SCOREBOARD_EXPECTED_SOURCE_INDEPENDENT: line {line_no}: "
                    "closure-grade scoreboard row requires expected_source"
                )
                continue
            kind = str(expected_source.get("kind") or "").strip()
            if kind in DUT_DERIVED_EXPECTED_SOURCE_KINDS:
                issues.append(
                    f"CHECK_DUT_DERIVED_EXPECTED_BLOCKED: line {line_no}: "
                    f"expected_source.kind must not be derived from DUT behavior: {kind}"
                )
            if kind == "manual_spec":
                issues.append(
                    f"CHECK_MANUAL_SPEC_DOWNGRADED_FOR_CLOSURE: line {line_no}: "
                    "manual_spec expected_source is provisional smoke/debug evidence only"
                )
            if kind == "approved_equivalent_oracle":
                issues.extend(_approved_equivalent_oracle_issues(f"line {line_no}", expected_source))

    return issues


def _domain_intent_issues(ip: Path, closure_matrix: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    policies = _policy_doc(ip)
    domain_policy = policies.get("domain_crossing_policy") if isinstance(policies.get("domain_crossing_policy"), dict) else {}
    structure = _structure_doc(ip)
    domain_path = oag_paths.legacy_or_hidden(ip, str(DOMAIN_INTENT_REL))
    domain_intent = _domain_intent_doc(ip)
    contracts = _yaml_items(ip, "ontology/contracts.yaml", "contracts")
    closed_contracts = _closed_contract_ids(ip, closure_matrix)
    known = _domain_refs_by_kind(domain_intent)
    domain_contracts = [contract for contract in contracts if _domain_contract_type(contract) in DOMAIN_CROSSING_CONTRACT_TYPES]
    closed_domain_contracts = [contract for contract in domain_contracts if str(contract.get("id") or "").strip() in closed_contracts]

    structure_clock_domains = _as_list(structure.get("clock_domains"))
    structure_reset_domains = _as_list(structure.get("reset_domains"))
    intent_required = (
        domain_policy.get("domain_intent_required") is True
        or len(structure_clock_domains) > 1
        or len(structure_reset_domains) > 1
        or bool(closed_domain_contracts)
    )
    if intent_required and not domain_path.is_file():
        issues.append(f"CHECK_DOMAIN_INTENT_PRESENT: missing canonical domain intent file {DOMAIN_INTENT_REL}")
        return issues
    if not domain_path.is_file():
        return issues
    if domain_intent.get("schema_version") != "oag_domain_intent.v1":
        issues.append(f"{DOMAIN_INTENT_REL}: schema_version must be oag_domain_intent.v1")

    for clock in _as_list(domain_intent.get("clock_domains")):
        if not isinstance(clock, dict):
            issues.append(f"{DOMAIN_INTENT_REL}: clock_domains entries must be objects")
            continue
        cid = _domain_item_id(clock, "clock")
        if not cid:
            issues.append(f"{DOMAIN_INTENT_REL}: clock domain missing id")
        if not str(clock.get("clock") or "").strip():
            issues.append(f"{DOMAIN_INTENT_REL}:{cid or '<clock_domain>'}: clock domain missing clock")

    for reset in _as_list(domain_intent.get("reset_domains")):
        if not isinstance(reset, dict):
            issues.append(f"{DOMAIN_INTENT_REL}: reset_domains entries must be objects")
            continue
        rid = _domain_item_id(reset, "reset")
        if not rid:
            issues.append(f"{DOMAIN_INTENT_REL}: reset domain missing id")
        for field in ("reset", "polarity", "assertion", "deassertion"):
            if not str(reset.get(field) or "").strip():
                issues.append(f"{DOMAIN_INTENT_REL}:{rid or '<reset_domain>'}: reset domain missing {field}")

    for async_input in _as_list(domain_intent.get("async_inputs")):
        if not isinstance(async_input, dict):
            issues.append(f"{DOMAIN_INTENT_REL}: async_inputs entries must be objects")
            continue
        signal = str(async_input.get("signal") or async_input.get("id") or "").strip()
        classification = _safe_domain_crossing_pattern(async_input.get("classification"))
        mitigation = _safe_domain_crossing_pattern(async_input.get("required_mitigation") or async_input.get("allowed_pattern"))
        if not signal:
            issues.append(f"{DOMAIN_INTENT_REL}: async input missing signal")
        if not classification:
            issues.append(f"CHECK_ASYNC_INPUT_CLASSIFIED: {signal or '<async_input>'}: async input missing classification")
        if not mitigation and not str(async_input.get("stable_assumption") or async_input.get("decision_receipt_id") or "").strip():
            issues.append(f"CHECK_ASYNC_INPUT_MITIGATION_PRESENT: {signal or '<async_input>'}: async input missing required_mitigation or explicit assumption")

    for crossing in _as_list(domain_intent.get("cdc_crossings")):
        if not isinstance(crossing, dict):
            issues.append(f"{DOMAIN_INTENT_REL}: cdc_crossings entries must be objects")
            continue
        cid = _domain_item_id(crossing, "source")
        ctype = _safe_domain_crossing_pattern(crossing.get("crossing_type") or crossing.get("classification"))
        pattern = _safe_domain_crossing_pattern(crossing.get("allowed_pattern") or crossing.get("mitigation"))
        if not cid:
            issues.append(f"{DOMAIN_INTENT_REL}: CDC crossing missing id")
        for field in ("source_domain", "destination_domain"):
            ref = str(crossing.get(field) or "").strip()
            if not ref:
                issues.append(f"CHECK_CDC_CROSSING_CLASSIFIED: {cid or '<cdc_crossing>'}: CDC crossing missing {field}")
            elif not _domain_ref_resolves(ref, known, ("clock_domains",)):
                issues.append(f"CHECK_CDC_CROSSING_REFS_RESOLVE: {cid}: {field} not found: {ref}")
        if not ctype:
            issues.append(f"CHECK_CDC_CROSSING_CLASSIFIED: {cid or '<cdc_crossing>'}: CDC crossing missing crossing_type")
        if not pattern and not str(crossing.get("stable_assumption") or crossing.get("decision_receipt_id") or "").strip():
            issues.append(f"CHECK_CDC_MITIGATION_PRESENT: {cid or '<cdc_crossing>'}: CDC crossing missing allowed_pattern or explicit assumption")
        if "multi_bit" in ctype:
            safe_multibit = any(token in ctype or token in pattern for token in ("gray", "fifo", "handshake", "mcp", "stable", "sample", "sampled", "approved"))
            if not safe_multibit:
                issues.append(
                    f"CHECK_CDC_MULTIBIT_UNSAFE: {cid or '<cdc_crossing>'}: multi-bit CDC needs Gray, FIFO, handshake, MCP, stable/sample classification, or approved waiver"
                )
        if pattern in {"direct", "none", "no_sync", "unsynchronized"}:
            issues.append(f"CHECK_CDC_MITIGATION_PRESENT: {cid or '<cdc_crossing>'}: CDC crossing uses unsafe mitigation pattern: {pattern}")

    for crossing in _as_list(domain_intent.get("rdc_crossings")):
        if not isinstance(crossing, dict):
            issues.append(f"{DOMAIN_INTENT_REL}: rdc_crossings entries must be objects")
            continue
        rid = _domain_item_id(crossing, "classification")
        classification = _safe_domain_crossing_pattern(crossing.get("classification"))
        no_rdc = classification in {"no_known_rdc", "none", "not_applicable"}
        if not rid:
            issues.append(f"{DOMAIN_INTENT_REL}: RDC crossing missing id")
        if no_rdc:
            if not _str_items(crossing.get("basis")) and not str(crossing.get("rationale") or "").strip():
                issues.append(f"CHECK_RDC_RELATION_PRESENT: {rid or '<rdc_crossing>'}: no-known-RDC classification needs basis")
            continue
        for field in ("source_reset_domain", "destination_reset_domain"):
            ref = str(crossing.get(field) or "").strip()
            if not ref:
                issues.append(f"CHECK_RDC_RELATION_PRESENT: {rid or '<rdc_crossing>'}: RDC crossing missing {field}")
            elif not _domain_ref_resolves(ref, known, ("reset_domains",)):
                issues.append(f"CHECK_RDC_CROSSING_REFS_RESOLVE: {rid}: {field} not found: {ref}")
        mitigation = str(crossing.get("mitigation") or crossing.get("reset_sequence") or crossing.get("isolation") or crossing.get("synchronizer") or crossing.get("qualifier") or "").strip()
        if not mitigation and not str(crossing.get("decision_receipt_id") or "").strip():
            issues.append(f"CHECK_RDC_MITIGATION_PRESENT: {rid or '<rdc_crossing>'}: RDC crossing needs sequencing, isolation, synchronizer, qualifier, or decision receipt")

    for contract in domain_contracts:
        cid = str(contract.get("id") or "").strip()
        if not cid:
            continue
        ctype = _domain_contract_type(contract)
        crossing_refs = _str_items(contract.get("crossing_refs"))
        crossing_refs.extend(_str_items(contract.get("cdc_crossing_refs")))
        rdc_refs = _str_items(contract.get("rdc_crossing_refs"))
        clock_refs = _str_items(contract.get("clock_domain_refs"))
        reset_refs = _str_items(contract.get("reset_domain_refs"))
        mitigation_refs = _str_items(contract.get("mitigation_refs"))
        mitigation_refs.extend(_str_items(contract.get("reset_sequence_or_isolation_or_sync_refs")))

        for ref in clock_refs:
            if not _domain_ref_resolves(ref, known, ("clock_domains",)):
                issues.append(f"CHECK_DOMAIN_CONTRACT_REFS_RESOLVE: {cid}: clock_domain_ref not found: {ref}")
        for ref in reset_refs:
            if not _domain_ref_resolves(ref, known, ("reset_domains",)):
                issues.append(f"CHECK_DOMAIN_CONTRACT_REFS_RESOLVE: {cid}: reset_domain_ref not found: {ref}")
        for ref in crossing_refs:
            if not _domain_ref_resolves(ref, known, ("cdc_crossings",)):
                issues.append(f"CHECK_DOMAIN_CONTRACT_REFS_RESOLVE: {cid}: cdc crossing_ref not found: {ref}")
        for ref in rdc_refs:
            if not _domain_ref_resolves(ref, known, ("rdc_crossings",)):
                issues.append(f"CHECK_DOMAIN_CONTRACT_REFS_RESOLVE: {cid}: rdc_crossing_ref not found: {ref}")
        for ref in mitigation_refs:
            if not _domain_ref_resolves(ref, known, ("sync_structures", "cdc_crossings", "rdc_crossings")) and not ref.startswith(("cycle_rules.", "behavior_model.")):
                issues.append(f"CHECK_DOMAIN_CONTRACT_REFS_RESOLVE: {cid}: mitigation_ref not found: {ref}")

        if cid not in closed_contracts:
            continue
        cdc_like = ctype in {"cdc", "cdc_rdc", "domain_crossing", "clock_reset_domain_crossing"}
        rdc_like = ctype in {"rdc", "cdc_rdc", "clock_reset_domain_crossing"}
        if cdc_like:
            if not crossing_refs:
                issues.append(f"CHECK_CDC_CONTRACT_REFS_REQUIRED: {cid}: closed CDC contract requires crossing_refs or cdc_crossing_refs")
            if not mitigation_refs:
                issues.append(f"CHECK_CDC_MITIGATION_PRESENT: {cid}: closed CDC contract requires mitigation_refs")
            evidence_refs = _domain_evidence_refs(contract, "cdc")
            if not evidence_refs:
                issues.append(f"CHECK_CDC_RDC_SIM_ONLY_CLOSURE_BLOCKED: {cid}: CDC closure requires static/formal/tool or mitigation evidence, not simulation alone")
        if rdc_like:
            if not (rdc_refs or crossing_refs):
                issues.append(f"CHECK_RDC_CONTRACT_REFS_REQUIRED: {cid}: closed RDC contract requires rdc_crossing_refs")
            if not reset_refs:
                issues.append(f"CHECK_RDC_CONTRACT_REFS_REQUIRED: {cid}: closed RDC contract requires reset_domain_refs")
            if not mitigation_refs:
                issues.append(f"CHECK_RDC_MITIGATION_PRESENT: {cid}: closed RDC contract requires reset sequencing/isolation/synchronizer/qualifier refs")
            evidence_refs = _domain_evidence_refs(contract, "rdc")
            if not evidence_refs:
                issues.append(f"CHECK_CDC_RDC_SIM_ONLY_CLOSURE_BLOCKED: {cid}: RDC closure requires static/formal/tool or mitigation evidence, not simulation alone")

    return issues


def _metrics_history_path(ip: Path) -> Path:
    return oag_paths.legacy_or_hidden(ip, str(METRICS_REL / "improvement_history.jsonl"))


def _latest_metrics_snapshot(ip: Path) -> dict[str, Any]:
    path = _metrics_history_path(ip)
    if not path.is_file():
        return {}
    latest: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("schema_version") == "oag_improvement_metrics.v1":
            latest = data
    return latest


def _nested_number(data: dict[str, Any], keys: tuple[str, ...]) -> float:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return 0.0
        value = value.get(key)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _metrics_delta(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return {
            "baseline": True,
            "previous_id": "",
            "closed_obligations_delta": 0,
            "closed_percent_delta": 0.0,
            "check_issue_count_delta": 0,
            "evidence_files_present_delta": 0,
            "stage_receipt_count_delta": 0,
            "ledger_events_delta": 0,
            "decision_receipts_delta": 0,
            "blocked_next_actions_delta": 0,
            "partially_closed_next_actions_delta": 0,
        }
    pairs = {
        "closed_obligations_delta": ("closure", "closed"),
        "closed_percent_delta": ("closure", "closed_percent"),
        "check_issue_count_delta": ("check", "issue_count"),
        "evidence_files_present_delta": ("evidence", "files_present_count"),
        "stage_receipt_count_delta": ("stage_receipts", "count"),
        "ledger_events_delta": ("ledger", "events"),
        "decision_receipts_delta": ("decisions", "receipts"),
        "blocked_next_actions_delta": ("auto_research", "blocked_actions"),
        "partially_closed_next_actions_delta": ("auto_research", "partially_closed_actions"),
    }
    delta: dict[str, Any] = {"baseline": False, "previous_id": str(previous.get("id") or "")}
    for name, keys in pairs.items():
        value = _nested_number(current, keys) - _nested_number(previous, keys)
        delta[name] = round(value, 2) if isinstance(value, float) and not value.is_integer() else int(value)
    return delta


def _record_summary_items(ip: Path) -> list[dict[str, Any]]:
    index = _read_json_file(_knowledge_index(ip))
    if isinstance(index, dict) and isinstance(index.get("records"), list):
        return [item for item in index["records"] if isinstance(item, dict)]
    return []


def _clean_evidence_file_ref(value: Any) -> str:
    ref = str(value or "").strip()
    if not ref or ref.startswith("{") or ref.startswith("["):
        return ""
    if ref.startswith(("pytest::", "node::", "coverage::")):
        return ""
    return ref


def _active_evidence_file_refs(ip: Path) -> list[str]:
    refs: list[str] = []
    records = _knowledge_records(ip)
    superseded = _superseded_record_ids(records)
    for record in records:
        if str(record.get("id") or "") in superseded:
            continue
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        refs.extend(_clean_evidence_file_ref(item) for item in _as_list(evidence.get("files")))
    if not refs:
        for item in _record_summary_items(ip):
            refs.extend(_clean_evidence_file_ref(ref) for ref in _as_list(item.get("evidence_files")))
    return sorted(dict.fromkeys(ref for ref in refs if ref))


def _status_count(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        status = _normal_status(value) or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _auto_research_metrics(ip: Path) -> dict[str, Any]:
    refs = _auto_research_report_refs(ip)
    action_statuses: list[str] = []
    signoff_blockers: list[str] = []
    evidence_strength_count = 0
    for ref in refs:
        data = _read_json_file(ip / ref)
        if not isinstance(data, dict):
            continue
        evidence_strength_count += len([item for item in _as_list(data.get("evidence_strengths")) if isinstance(item, dict)])
        for item in _as_list(data.get("ranked_next_actions")):
            if isinstance(item, dict):
                action_statuses.append(str(item.get("status") or ""))
        for key in ("signoff_blockers", "remaining_signoff_blockers", "blockers"):
            signoff_blockers.extend(_str_items(data.get(key)))
    counts = _status_count(action_statuses)
    return {
        "reports": len(refs),
        "evidence_strengths": evidence_strength_count,
        "actions": len(action_statuses),
        "status_counts": counts,
        "blocked_actions": counts.get("blocked", 0),
        "partially_closed_actions": counts.get("partially_closed", 0) + counts.get("partial", 0),
        "closed_actions": counts.get("closed", 0) + counts.get("pass", 0) + counts.get("passed", 0),
        "signoff_blockers": len(sorted(dict.fromkeys(signoff_blockers))),
    }


def _run_metrics(ip: Path) -> dict[str, Any]:
    states: list[dict[str, Any]] = []
    runs_dir = oag_paths.legacy_or_hidden(ip, str(RUNS_REL))
    if runs_dir.is_dir():
        for path in sorted(runs_dir.glob("RUN_*/run_state.json")):
            data = _read_json_file(path)
            if isinstance(data, dict):
                states.append(data)
    statuses = _status_count([str(state.get("status") or "") for state in states])
    active = _read_json_file(_active_run_path(ip))
    active_run_id = str(active.get("run_id") or "") if isinstance(active, dict) else ""
    return {
        "total": len(states),
        "active_run_id": active_run_id,
        "status_counts": statuses,
        "in_progress": statuses.get("in_progress", 0) + statuses.get("starting", 0),
        "complete": statuses.get("complete", 0),
        "needs_human": statuses.get("needs_human", 0),
    }


def _decision_metrics(ip: Path) -> dict[str, Any]:
    decisions = []
    reviewers = []
    directory = oag_paths.legacy_or_hidden(ip, str(DECISION_RECEIPTS_REL))
    if directory.is_dir():
        for path in sorted(directory.glob("DEC_*.json")):
            data = _read_json_file(path)
            if isinstance(data, dict):
                decisions.append(data)
        for path in sorted(directory.glob("REV_*.json")):
            data = _read_json_file(path)
            if isinstance(data, dict):
                reviewers.append(data)
    independent_passing = [
        item
        for item in reviewers
        if item.get("independent") is True
        and item.get("allowed") is True
        and _normal_status(item.get("verdict") or item.get("status")) in {"pass", "approved", "closed", "validated"}
    ]
    return {
        "receipts": len(decisions),
        "allowed": sum(1 for item in decisions if item.get("allowed") is True),
        "blocked": sum(1 for item in decisions if item.get("allowed") is False),
        "reviewer_receipts": len(reviewers),
        "independent_passing_reviewers": len(independent_passing),
    }


def _improvement_metrics(
    ip: Path,
    *,
    check_issues: list[str] | None = None,
    closure_matrix: dict[str, Any] | None = None,
    snapshot_id: str = "",
    stage: str = "",
    intent: str = "",
) -> dict[str, Any]:
    matrix = closure_matrix if isinstance(closure_matrix, dict) else _closure_matrix(ip)
    obligations = _yaml_items(ip, "ontology/obligations.yaml", "obligations")
    contracts = _yaml_items(ip, "ontology/contracts.yaml", "contracts")
    requirements = _yaml_items(ip, "ontology/requirements.yaml", "requirements")
    records = _knowledge_records(ip)
    summaries = _record_summary_items(ip)
    summary_statuses = [str(item.get("validation_status") or item.get("status") or "") for item in summaries]
    json_statuses = [
        str((record.get("validation") if isinstance(record.get("validation"), dict) else {}).get("status") or record.get("status") or "")
        for record in records
    ]
    statuses = summary_statuses or json_statuses
    status_counts = _status_count(statuses)

    record_issues = _record_evidence_issues(ip)
    stage_issues = _stage_receipt_issues(ip)
    ledger_issues = _ledger_issues(ip)
    protection_issues = _protection_issues(ip)
    monotonic_issues = _monotonic_issues(ip)
    auto_research_issues = _auto_research_report_issues(ip)
    if check_issues is None:
        check_issues = [
            *matrix.get("issues", []),
            *record_issues,
            *stage_issues,
            *ledger_issues,
            *protection_issues,
            *monotonic_issues,
            *auto_research_issues,
        ]

    evidence_refs = _active_evidence_file_refs(ip)
    evidence_hash_count = 0
    records_active = [record for record in records if str(record.get("id") or "") not in _superseded_record_ids(records)]
    for record in records_active:
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        evidence_hash_count += len([item for item in _as_list(evidence.get("file_hashes")) if isinstance(item, dict)])
    present_refs = [ref for ref in evidence_refs if (ip / ref).is_file()]
    missing_refs = [ref for ref in evidence_refs if _path_like_ref(ref) and not (ip / ref).is_file()]

    truth_graph = _read_json_file(_truth_graph_path(ip))
    truth_stats = truth_graph.get("stats") if isinstance(truth_graph, dict) and isinstance(truth_graph.get("stats"), dict) else {}
    design_facts = _read_json_file(oag_paths.legacy_or_hidden(ip, str(DESIGN_FACTS_REL)))
    design_facts_stats = design_facts.get("stats") if isinstance(design_facts, dict) and isinstance(design_facts.get("stats"), dict) else {}
    design_rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
    design_rule_instances = _yaml_items(ip, str(DESIGN_RULES_REL), "instances")
    _stage_receipts_dir = oag_paths.legacy_or_hidden(ip, str(STAGE_RECEIPTS_REL))
    receipts = sorted(_stage_receipts_dir.glob("*.json")) if _stage_receipts_dir.is_dir() else []
    ledger_events = len(_ledger_entries(ip))

    total = int(matrix.get("total") or 0)
    closed = int(matrix.get("closed") or 0)
    closed_percent = round((closed / total) * 100.0, 2) if total else 0.0
    snapshot = {
        "schema_version": "oag_improvement_metrics.v1",
        "id": snapshot_id or f"MET_{_stamp()}_PREVIEW",
        "ip": ip.name,
        "stage": stage,
        "intent": intent,
        "generated_at": _now(),
        "closure_profile": _policy_profile(ip),
        "requirements": {"total": len(requirements)},
        "obligations": {"total": len(obligations)},
        "contracts": {"total": len(contracts)},
        "closure": {
            "status": str(matrix.get("status") or ""),
            "total": total,
            "closed": closed,
            "open": max(total - closed, 0),
            "closed_percent": closed_percent,
            "issue_count": len([item for item in _as_list(matrix.get("issues")) if item]),
        },
        "check": {
            "ok": not check_issues,
            "issue_count": len(check_issues),
            "stale_issue_count": sum(1 for issue in check_issues if "stale" in str(issue).lower() or "fingerprint mismatch" in str(issue).lower()),
        },
        "evidence": {
            "records_total": max(len(summaries), len(records)),
            "json_records_total": len(records),
            "active_json_records": len(records_active),
            "record_status_counts": status_counts,
            "closed_records_total": sum(status_counts.get(status, 0) for status in CLOSED_STATUSES),
            "draft_records_total": status_counts.get("draft", 0),
            "refuted_records_total": status_counts.get("refuted", 0),
            "referenced_file_count": len(evidence_refs),
            "unique_evidence_file_count": len(evidence_refs),
            "files_present_count": len(present_refs),
            "files_missing_count": len(missing_refs),
            "file_hash_count": evidence_hash_count,
            "stale_record_issue_count": sum(1 for issue in record_issues if "evidence file stale" in str(issue)),
        },
        "stage_receipts": {"count": len(receipts), "issue_count": len(stage_issues)},
        "ledger": {"events": ledger_events, "issue_count": len(ledger_issues)},
        "protection": {"issue_count": len(protection_issues)},
        "monotonic_closure": {"issue_count": len(monotonic_issues)},
        "design": {
            "rules": len(design_rules),
            "rule_instances": len(design_rule_instances),
            "truth_graph_status": str(truth_graph.get("status") or "missing") if isinstance(truth_graph, dict) else "missing",
            "truth_graph_nodes": len(truth_graph.get("nodes", [])) if isinstance(truth_graph, dict) and isinstance(truth_graph.get("nodes"), list) else 0,
            "truth_graph_edges": len(truth_graph.get("edges", [])) if isinstance(truth_graph, dict) and isinstance(truth_graph.get("edges"), list) else 0,
            "load_bearing_edges": int(truth_stats.get("load_bearing_edges") or 0),
            "design_facts_modules": int(design_facts_stats.get("modules") or 0),
            "design_facts_rtl_source_files": int(design_facts_stats.get("rtl_source_files") or 0),
        },
        "auto_research": _auto_research_metrics(ip),
        "decisions": _decision_metrics(ip),
        "runs": _run_metrics(ip),
    }
    snapshot["delta"] = _metrics_delta(snapshot, _latest_metrics_snapshot(ip))
    return snapshot


def _metrics_actor(arguments: dict[str, Any]) -> dict[str, str]:
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    return {
        "kind": str(actor.get("kind") or "ai"),
        "id": str(actor.get("id") or os.environ.get("USER") or "unknown"),
        "session": str(actor.get("session") or ""),
        "surface": str(actor.get("surface") or "oag.metrics"),
    }


def _metrics_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    stage = str(arguments.get("stage") or "metrics")
    intent = str(arguments.get("intent") or arguments.get("query") or "")
    check = _check(arguments, include_metrics=False)
    metrics_id = f"MET_{_stamp()}_{_slug(stage or intent or 'METRICS')}"
    metrics = _improvement_metrics(
        ip,
        check_issues=check.get("issues") if isinstance(check.get("issues"), list) else [],
        closure_matrix=check.get("closure_matrix") if isinstance(check.get("closure_matrix"), dict) else None,
        snapshot_id=metrics_id,
        stage=stage,
        intent=intent,
    )
    if arguments.get("record", True) is False:
        return {
            "schema_version": "oag_metrics_snapshot.v1",
            "ip": ip.name,
            "recorded": False,
            "metrics": metrics,
        }

    latest_rel = METRICS_REL / "improvement_metrics.json"
    history_rel = METRICS_REL / "improvement_history.jsonl"
    metrics["artifacts"] = {"latest": str(latest_rel), "history": str(history_rel)}
    actor = _metrics_actor(arguments)
    payload = {
        "metrics_id": metrics_id,
        "latest": str(latest_rel),
        "history": str(history_rel),
        "metrics": metrics,
    }
    _assert_ledger_append_allowed(ip, action="metrics_snapshot", actor=actor, payload=payload)
    ledger_event = _append_ledger(
        ip,
        action="metrics_snapshot",
        actor=actor,
        subject=metrics_id,
        payload=payload,
    )
    previous = _latest_metrics_snapshot(ip)
    ledger_metrics = metrics.get("ledger") if isinstance(metrics.get("ledger"), dict) else {}
    ledger_metrics["events"] = len(_ledger_entries(ip))
    metrics["ledger"] = ledger_metrics
    metrics["ledger_event"] = ledger_event["event_hash"]
    metrics["delta"] = _metrics_delta(metrics, previous)
    _write_json(ip / latest_rel, metrics)
    history_path = ip / history_rel
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "schema_version": "oag_metrics_snapshot.v1",
        "ip": ip.name,
        "id": metrics_id,
        "recorded": True,
        "path": str(ip / latest_rel),
        "history": str(history_path),
        "ledger_event": ledger_event["event_hash"],
        "metrics": metrics,
    }


def _handoff_actor(arguments: dict[str, Any]) -> dict[str, str]:
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    return {
        "kind": str(actor.get("kind") or "ai"),
        "id": str(actor.get("id") or os.environ.get("USER") or "unknown"),
        "session": str(actor.get("session") or ""),
        "surface": str(actor.get("surface") or "oag.handoff"),
    }


def _handoff_auto_research_sources(ip: Path) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    blockers: list[str] = []
    evidence_refs: list[str] = []
    for ref in _auto_research_report_refs(ip):
        data = _read_json_file(ip / ref)
        reports.append(
            {
                "ref": ref,
                "schema_version": data.get("schema_version") if isinstance(data, dict) else "",
                "status": data.get("status") if isinstance(data, dict) else "missing",
                "method": data.get("method") if isinstance(data, dict) else "",
            }
        )
        evidence_refs.append(ref)
        if not isinstance(data, dict):
            continue
        evidence_refs.extend(_str_items(data.get("evidence_refs")))
        for key in ("signoff_blockers", "remaining_signoff_blockers", "blockers"):
            blockers.extend(_str_items(data.get(key)))
        for index, item in enumerate(_as_list(data.get("ranked_next_actions")), 1):
            if not isinstance(item, dict):
                continue
            try:
                rank = int(item.get("rank"))
            except Exception:
                rank = index
            action_refs = _str_items(item.get("evidence_refs"))
            evidence_refs.extend(action_refs)
            actions.append(
                {
                    "rank": rank,
                    "id": str(item.get("id") or "").strip(),
                    "status": _normal_status(item.get("status")),
                    "reason": str(item.get("reason") or "").strip(),
                    "evidence_refs": action_refs,
                    "source_report": ref,
                }
            )
    actions.sort(key=lambda item: (int(item.get("rank") or 0), str(item.get("source_report") or ""), str(item.get("id") or "")))
    return {
        "reports": reports,
        "ranked_next_actions": actions,
        "signoff_blockers": sorted(dict.fromkeys(blockers)),
        "evidence_refs": sorted(dict.fromkeys(ref for ref in evidence_refs if ref)),
    }


def _handoff_truth_evidence_summary(ip: Path) -> dict[str, Any]:
    truth_coverage = _read_json_file(ip / "signoff/truth_coverage.json")
    if isinstance(truth_coverage, dict) and isinstance(truth_coverage.get("evidence_summary"), dict):
        return truth_coverage["evidence_summary"]
    return {}


def _handoff_development_evidence_strength(ip: Path) -> dict[str, Any]:
    summary = _handoff_truth_evidence_summary(ip)

    formal = summary.get("formal_assertion") if isinstance(summary.get("formal_assertion"), dict) else {}
    formal_numeric = formal.get("numeric_summary") if isinstance(formal.get("numeric_summary"), dict) else {}
    mutation = summary.get("mutation") if isinstance(summary.get("mutation"), dict) else {}
    sta = summary.get("implementation_sta") if isinstance(summary.get("implementation_sta"), dict) else {}
    sta_metrics = sta.get("metrics") if isinstance(sta.get("metrics"), dict) else {}
    sta_numeric = sta.get("numeric_summary") if isinstance(sta.get("numeric_summary"), dict) else {}
    sta_corners = _as_list(sta.get("corners"))
    gate = summary.get("gate_reset_xprop") if isinstance(summary.get("gate_reset_xprop"), dict) else {}
    gate_observations = gate.get("observations") if isinstance(gate.get("observations"), dict) else {}
    gate_numeric = gate.get("numeric_summary") if isinstance(gate.get("numeric_summary"), dict) else {}
    protocol = summary.get("protocol_compliance") if isinstance(summary.get("protocol_compliance"), dict) else {}
    protocol_numeric = protocol.get("numeric_summary") if isinstance(protocol.get("numeric_summary"), dict) else {}
    scoreboard = summary.get("scoreboard") if isinstance(summary.get("scoreboard"), dict) else {}
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    direct_scoreboard = _scoreboard_summary(ip / "sim" / "scoreboard_events.jsonl")
    direct_scoreboard_summary = (
        direct_scoreboard.get("summary") if isinstance(direct_scoreboard.get("summary"), dict) else {}
    )
    if int(direct_scoreboard_summary.get("total") or 0) > 0:
        scoreboard = direct_scoreboard_summary
    direct_coverage = _read_json_file(ip / "cov" / "coverage.json")
    if isinstance(direct_coverage, dict):
        coverage = direct_coverage

    mutants_run = int(mutation.get("mutants_run") or 0)
    mutants_killed = int(mutation.get("mutants_killed") or 0)
    mutation_score = round((mutants_killed / mutants_run) * 100.0, 2) if mutants_run else 0.0
    formal_properties = int(formal.get("property_count") or formal_numeric.get("properties_checked") or 0)
    formal_baseline = int(formal_numeric.get("baseline_property_count") or 0)
    formal_added = int(formal_numeric.get("properties_added") or max(formal_properties - formal_baseline, 0))
    formal_bound_cycles = int(formal.get("bound_cycles") or formal_numeric.get("bound_cycles") or 0)
    formal_baseline_bound_cycles = int(formal_numeric.get("baseline_bound_cycles") or 0)
    formal_bound_cycles_added = int(
        formal_numeric.get("bound_cycles_added") or max(formal_bound_cycles - formal_baseline_bound_cycles, 0)
    )
    formal_assertion_site_count = int(
        formal.get("source_assertion_site_count") or formal_numeric.get("source_assertion_site_count") or 0
    )
    formal_baseline_assertion_site_count = int(formal_numeric.get("baseline_assertion_site_count") or 0)
    formal_assertion_sites_added = int(
        formal_numeric.get("assertion_sites_added")
        or max(formal_assertion_site_count - formal_baseline_assertion_site_count, 0)
    )
    scoreboard_rows = int(scoreboard.get("total") or scoreboard.get("rows") or 0)
    scoreboard_passed = int(scoreboard.get("passed") or 0)
    scoreboard_failed = int(scoreboard.get("failed") or 0)
    scoreboard_status = _normal_status(scoreboard.get("status"))
    if not scoreboard_status and scoreboard_rows and scoreboard_passed == scoreboard_rows and scoreboard_failed == 0:
        scoreboard_status = "pass"

    return {
        "schema_version": "oag_evidence_strength_summary.v1",
        "formal": {
            "status": _normal_status(formal.get("status")),
            "property_count": formal_properties,
            "baseline_property_count": formal_baseline,
            "properties_added": formal_added,
            "bound_cycles": formal_bound_cycles,
            "baseline_bound_cycles": formal_baseline_bound_cycles,
            "bound_cycles_added": formal_bound_cycles_added,
            "bounded_steps_checked": int(formal_numeric.get("bounded_steps_checked") or 0),
            "bounded_property_step_checks": int(formal_numeric.get("bounded_property_step_checks") or 0),
            "baseline_bounded_property_step_checks": int(
                formal_numeric.get("baseline_bounded_property_step_checks") or 0
            ),
            "bounded_property_step_checks_added": int(
                formal_numeric.get("bounded_property_step_checks_added") or 0
            ),
            "source_assertion_site_count": formal_assertion_site_count,
            "baseline_assertion_site_count": formal_baseline_assertion_site_count,
            "assertion_sites_added": formal_assertion_sites_added,
            "bounded_assertion_site_step_checks": int(
                formal_numeric.get("bounded_assertion_site_step_checks") or 0
            ),
            "issues_found": int(formal_numeric.get("issues_found") or 0),
        },
        "mutation": {
            "status": _normal_status(mutation.get("status")),
            "mutants_run": mutants_run,
            "mutants_killed": mutants_killed,
            "mutants_survived": int(mutation.get("mutants_survived") or max(mutants_run - mutants_killed, 0)),
            "mutation_score_percent": mutation_score,
            "fault_model_count": len(_as_list(mutation.get("fault_models"))),
        },
        "implementation_sta": {
            "status": _normal_status(sta.get("status")),
            "wns_ns": sta_metrics.get("wns_ns"),
            "tns_ns": sta_metrics.get("tns_ns"),
            "unconstrained_text_seen": bool(sta_metrics.get("unconstrained_text_seen")),
            "target_clock_count": len(_as_list(sta.get("target_clocks"))),
            "baseline_corner_count": int(sta_numeric.get("baseline_corner_count") or 0),
            "corner_count": int(sta_numeric.get("corner_count") or sta_metrics.get("corner_count") or len(sta_corners)),
            "corners_added": int(sta_numeric.get("corners_added") or 0),
            "corners_passed": int(sta_numeric.get("corners_passed") or sta_metrics.get("corners_passed") or 0),
            "corners_failed": int(sta_numeric.get("corners_failed") or sta_metrics.get("corners_failed") or 0),
            "violated_corner_count": int(sta_numeric.get("violated_corner_count") or sta_metrics.get("violated_corner_count") or 0),
            "worst_setup_slack_ns": sta_numeric.get("worst_setup_slack_ns")
            if sta_numeric.get("worst_setup_slack_ns") is not None
            else sta_metrics.get("worst_corner_setup_slack_ns"),
            "worst_hold_slack_ns": sta_numeric.get("worst_hold_slack_ns")
            if sta_numeric.get("worst_hold_slack_ns") is not None
            else sta_metrics.get("worst_corner_hold_slack_ns"),
            "worst_wns_ns": sta_numeric.get("worst_wns_ns")
            if sta_numeric.get("worst_wns_ns") is not None
            else sta_metrics.get("worst_corner_wns_ns"),
            "worst_tns_ns": sta_numeric.get("worst_tns_ns")
            if sta_numeric.get("worst_tns_ns") is not None
            else sta_metrics.get("worst_corner_tns_ns"),
            "timing_analysis_count": int(sta_numeric.get("timing_analysis_count") or sta_metrics.get("timing_analysis_count") or 0),
            "timing_metric_count": int(sta_numeric.get("timing_metric_count") or sta_metrics.get("timing_metric_count") or 0),
            "negative_timing_metric_count": int(
                sta_numeric.get("negative_timing_metric_count") or sta_metrics.get("negative_timing_metric_count") or 0
            ),
            "worst_setup_slack_corner": sta_numeric.get("worst_setup_slack_corner")
            or sta_metrics.get("worst_setup_slack_corner")
            or "",
            "worst_hold_slack_corner": sta_numeric.get("worst_hold_slack_corner")
            or sta_metrics.get("worst_hold_slack_corner")
            or "",
            "worst_setup_slack_margin_percent_of_period": sta_numeric.get("worst_setup_slack_margin_percent_of_period")
            if sta_numeric.get("worst_setup_slack_margin_percent_of_period") is not None
            else sta_metrics.get("worst_setup_slack_margin_percent_of_period"),
            "worst_hold_slack_margin_percent_of_period": sta_numeric.get("worst_hold_slack_margin_percent_of_period")
            if sta_numeric.get("worst_hold_slack_margin_percent_of_period") is not None
            else sta_metrics.get("worst_hold_slack_margin_percent_of_period"),
        },
        "gate_reset_xprop": {
            "status": _normal_status(gate.get("status")),
            "baseline_known_output_check_count": int(gate_numeric.get("baseline_known_output_check_count") or 0),
            "known_output_check_count": int(
                gate_numeric.get("known_output_check_count") or gate_observations.get("known_output_check_count") or 0
            ),
            "known_output_checks_added": int(gate_numeric.get("known_output_checks_added") or 0),
            "baseline_scenario_count": int(gate_numeric.get("baseline_scenario_count") or 0),
            "scenario_count": int(gate_numeric.get("scenario_count") or len(_as_list(gate_observations.get("scenarios")))),
            "scenarios_added": int(gate_numeric.get("scenarios_added") or 0),
            "known_output_bit_check_count": int(
                gate_numeric.get("known_output_bit_check_count")
                or gate_observations.get("known_output_bit_check_count")
                or 0
            ),
            "failures": int(gate_numeric.get("failures") or 0),
        },
        "protocol": {
            "status": _normal_status(protocol.get("status")),
            "baseline_protocol_row_count": int(protocol_numeric.get("baseline_protocol_row_count") or 0),
            "protocol_row_count": int(protocol_numeric.get("protocol_row_count") or 0),
            "protocol_rows_added": int(protocol_numeric.get("protocol_rows_added") or 0),
            "baseline_response_row_count": int(protocol_numeric.get("baseline_response_row_count") or 0),
            "response_row_count": int(protocol_numeric.get("response_row_count") or 0),
            "response_rows_added": int(protocol_numeric.get("response_rows_added") or 0),
            "read_response_row_count": int(protocol_numeric.get("read_response_row_count") or 0),
            "write_response_row_count": int(protocol_numeric.get("write_response_row_count") or 0),
            "invalid_response_row_count": int(protocol_numeric.get("invalid_response_row_count") or 0),
            "invalid_read_response_row_count": int(protocol_numeric.get("invalid_read_response_row_count") or 0),
            "invalid_write_response_row_count": int(protocol_numeric.get("invalid_write_response_row_count") or 0),
            "baseline_phase_row_count": int(protocol_numeric.get("baseline_phase_row_count") or 0),
            "phase_row_count": int(protocol_numeric.get("phase_row_count") or 0),
            "phase_rows_added": int(protocol_numeric.get("phase_rows_added") or 0),
            "baseline_protocol_coverage_ref_count": int(protocol_numeric.get("baseline_protocol_coverage_ref_count") or 0),
            "required_protocol_coverage_ref_count": int(protocol_numeric.get("required_protocol_coverage_ref_count") or 0),
            "protocol_coverage_refs_added": int(protocol_numeric.get("protocol_coverage_refs_added") or 0),
            "observed_protocol_coverage_ref_count": int(protocol_numeric.get("observed_protocol_coverage_ref_count") or 0),
            "baseline_coverage_ref_count": int(protocol_numeric.get("baseline_coverage_ref_count") or 0),
            "coverage_ref_count": int(protocol_numeric.get("coverage_ref_count") or 0),
            "coverage_refs_added": int(protocol_numeric.get("coverage_refs_added") or 0),
            "scoreboard_row_count": int(protocol_numeric.get("scoreboard_row_count") or 0),
            "protocol_check_count": int(protocol_numeric.get("protocol_check_count") or 0),
            "protocol_checks_passed": int(protocol_numeric.get("protocol_checks_passed") or 0),
            "protocol_checks_failed": int(protocol_numeric.get("protocol_checks_failed") or 0),
        },
        "scoreboard": {
            "status": scoreboard_status,
            "rows": scoreboard_rows,
            "passed": scoreboard_passed,
            "failed": scoreboard_failed,
        },
        "coverage": {
            "status": _normal_status(coverage.get("status")),
            "covered_count": len(_as_list(coverage.get("covered"))),
        },
    }


def _metric_int(metrics: dict[str, Any], *keys: str) -> int:
    return int(_nested_number(metrics, tuple(keys)))


def _handoff_numeric_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    evidence_total = _metric_int(metrics, "evidence", "unique_evidence_file_count")
    if not evidence_total:
        evidence_total = _metric_int(metrics, "evidence", "referenced_file_count")
    return {
        "requirements_total": _metric_int(metrics, "requirements", "total"),
        "contracts_total": _metric_int(metrics, "contracts", "total"),
        "obligations_total": _metric_int(metrics, "closure", "total"),
        "obligations_closed": _metric_int(metrics, "closure", "closed"),
        "obligations_open": _metric_int(metrics, "closure", "open"),
        "closure_percent": _nested_number(metrics, ("closure", "closed_percent")),
        "closure_issue_count": _metric_int(metrics, "closure", "issue_count"),
        "check_issue_count": _metric_int(metrics, "check", "issue_count"),
        "stale_issue_count": _metric_int(metrics, "check", "stale_issue_count"),
        "evidence_files_present": _metric_int(metrics, "evidence", "files_present_count"),
        "evidence_files_total": evidence_total,
        "evidence_files_missing": _metric_int(metrics, "evidence", "files_missing_count"),
        "stage_receipts": _metric_int(metrics, "stage_receipts", "count"),
        "ledger_events": _metric_int(metrics, "ledger", "events"),
        "auto_research_reports": _metric_int(metrics, "auto_research", "reports"),
        "ranked_next_actions": _metric_int(metrics, "auto_research", "actions"),
        "blocked_actions": _metric_int(metrics, "auto_research", "blocked_actions"),
        "partially_closed_actions": _metric_int(metrics, "auto_research", "partially_closed_actions"),
        "closed_actions": _metric_int(metrics, "auto_research", "closed_actions"),
        "signoff_blockers": _metric_int(metrics, "auto_research", "signoff_blockers"),
        "decision_receipts": _metric_int(metrics, "decisions", "receipts"),
        "independent_passing_reviewers": _metric_int(metrics, "decisions", "independent_passing_reviewers"),
    }


def _handoff_readiness(metrics: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    profile = str(metrics.get("closure_profile") or "development")
    closure_complete = bool(summary["obligations_total"] and summary["obligations_open"] == 0 and summary["closure_issue_count"] == 0)
    check_clean = summary["check_issue_count"] == 0 and summary["stale_issue_count"] == 0
    evidence_complete = summary["evidence_files_missing"] == 0
    development_ready = closure_complete and check_clean and evidence_complete
    signoff_ready = (
        development_ready
        and profile == "signoff"
        and summary["blocked_actions"] == 0
        and summary["partially_closed_actions"] == 0
        and summary["signoff_blockers"] == 0
        and summary["independent_passing_reviewers"] > 0
    )
    reasons: list[str] = []
    if not closure_complete:
        reasons.append("closure matrix is not fully closed")
    if not check_clean:
        reasons.append("oag.check has open or stale issues")
    if not evidence_complete:
        reasons.append("one or more referenced evidence files are missing")
    if profile != "signoff":
        reasons.append(f"closure_profile is {profile}, not signoff")
    if summary["blocked_actions"]:
        reasons.append(f"{summary['blocked_actions']} ranked next actions are blocked")
    if summary["partially_closed_actions"]:
        reasons.append(f"{summary['partially_closed_actions']} ranked next actions are partially closed")
    if summary["signoff_blockers"]:
        reasons.append(f"{summary['signoff_blockers']} signoff blockers remain")
    if summary["independent_passing_reviewers"] == 0:
        reasons.append("no independent passing reviewer receipt is recorded")
    return {
        "development_ready": development_ready,
        "signoff_ready": signoff_ready,
        "closure_complete": closure_complete,
        "check_clean": check_clean,
        "evidence_complete": evidence_complete,
        "requires_human_signoff_transition": profile != "signoff",
        "requires_independent_review": summary["independent_passing_reviewers"] == 0,
        "not_ready_reasons": [] if signoff_ready else reasons,
    }


def _handoff_checks(report: dict[str, Any]) -> dict[str, bool]:
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    summary = report.get("numeric_summary") if isinstance(report.get("numeric_summary"), dict) else {}
    strength = report.get("evidence_strength_summary") if isinstance(report.get("evidence_strength_summary"), dict) else {}
    formal = strength.get("formal") if isinstance(strength.get("formal"), dict) else {}
    mutation = strength.get("mutation") if isinstance(strength.get("mutation"), dict) else {}
    protocol = strength.get("protocol") if isinstance(strength.get("protocol"), dict) else {}
    signoff_ready = readiness.get("signoff_ready") is True
    return {
        "numeric_summary_present": bool(summary),
        "metrics_embedded": isinstance(report.get("improvement_metrics"), dict),
        "evidence_strength_summary_present": "evidence_strength_summary" in report,
        "evidence_strength_summary_has_formal_count": not strength or _num_value(formal.get("property_count")) is not None,
        "evidence_strength_summary_has_formal_step_count": not strength
        or _num_value(formal.get("bounded_property_step_checks")) is not None,
        "evidence_strength_summary_has_mutation_count": not strength or int(mutation.get("mutants_run") or 0) >= int(mutation.get("mutants_killed") or 0),
        "evidence_strength_summary_has_protocol_count": not strength
        or (
            _num_value(protocol.get("protocol_row_count")) is not None
            and _num_value(protocol.get("protocol_check_count")) is not None
        ),
        "development_ready_requires_closed_clean_evidence": not readiness.get("development_ready")
        or (
            summary.get("obligations_open") == 0
            and summary.get("check_issue_count") == 0
            and summary.get("evidence_files_missing") == 0
        ),
        "signoff_ready_requires_signoff_profile": not signoff_ready or report.get("closure_profile") == "signoff",
        "signoff_ready_requires_no_blockers": not signoff_ready
        or (
            summary.get("blocked_actions") == 0
            and summary.get("partially_closed_actions") == 0
            and summary.get("signoff_blockers") == 0
        ),
        "signoff_ready_requires_independent_review": not signoff_ready or int(summary.get("independent_passing_reviewers") or 0) > 0,
    }


def _build_handoff_report(
    ip: Path,
    *,
    handoff_id: str,
    stage: str,
    intent: str,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    artifacts: dict[str, str] | None = None,
    ledger_event: str = "",
) -> dict[str, Any]:
    summary = _handoff_numeric_summary(metrics)
    readiness = _handoff_readiness(metrics, summary)
    evidence_strength = _handoff_development_evidence_strength(ip)
    evidence_refs = sorted(
        dict.fromkeys(
            [
                str(METRICS_REL / "improvement_metrics.json"),
                *[str(item) for item in _as_list(sources.get("evidence_refs")) if str(item).strip()],
            ]
        )
    )
    report = {
        "schema_version": "oag_readiness_handoff.v1",
        "id": handoff_id,
        "ip": ip.name,
        "stage": stage,
        "intent": intent,
        "generated_at": _now(),
        "closure_profile": str(metrics.get("closure_profile") or _policy_profile(ip)),
        "status": "pass",
        "method": "oag_metrics_plus_auto_research_graph",
        "automation_boundary": "Readiness handoff only; this is not a signoff, waiver, or human approval decision.",
        "progress_denominator": "derived_from_active_ip_obligations",
        "numeric_summary": summary,
        "evidence_strength_summary": evidence_strength,
        "readiness": readiness,
        "auto_research_reports": sources.get("reports") if isinstance(sources.get("reports"), list) else [],
        "ranked_next_actions": sources.get("ranked_next_actions") if isinstance(sources.get("ranked_next_actions"), list) else [],
        "signoff_blockers": sources.get("signoff_blockers") if isinstance(sources.get("signoff_blockers"), list) else [],
        "evidence_refs": evidence_refs,
        "improvement_metrics": metrics,
        "artifacts": artifacts or {},
        "ledger_event": ledger_event,
    }
    report["checks"] = _handoff_checks(report)
    return report


def _handoff_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    stage = str(arguments.get("stage") or "handoff")
    intent = str(arguments.get("intent") or arguments.get("query") or "")
    record = arguments.get("record", True) is not False
    metrics_id = f"MET_{_stamp()}_{_slug(stage or intent or 'HANDOFF')}"
    handoff_id = f"HANDOFF_{_stamp()}_{_slug(stage or intent or 'READINESS')}"
    metrics = _improvement_metrics(ip, snapshot_id=metrics_id, stage=stage, intent=intent)
    sources = _handoff_auto_research_sources(ip)
    if not record:
        report = _build_handoff_report(ip, handoff_id=handoff_id, stage=stage, intent=intent, metrics=metrics, sources=sources)
        return {
            "schema_version": "oag_handoff_snapshot.v1",
            "ip": ip.name,
            "id": handoff_id,
            "recorded": False,
            "handoff": report,
            "metrics": metrics,
        }

    metrics_latest_rel = METRICS_REL / "improvement_metrics.json"
    metrics_history_rel = METRICS_REL / "improvement_history.jsonl"
    artifacts = {
        "latest": str(HANDOFF_READINESS_REL),
        "history": str(HANDOFF_READINESS_HISTORY_REL),
        "metrics_latest": str(metrics_latest_rel),
        "metrics_history": str(metrics_history_rel),
    }
    actor = _handoff_actor(arguments)
    previous_metrics = _latest_metrics_snapshot(ip)
    preview_summary = _handoff_numeric_summary(metrics)
    preview_readiness = _handoff_readiness(metrics, preview_summary)
    payload = {
        "handoff_id": handoff_id,
        "latest": artifacts["latest"],
        "history": artifacts["history"],
        "metrics_id": metrics_id,
        "metrics_latest": artifacts["metrics_latest"],
        "numeric_summary": preview_summary,
        "readiness": preview_readiness,
    }
    _assert_ledger_append_allowed(ip, action="handoff_snapshot", actor=actor, payload=payload)
    ledger_event = _append_ledger(
        ip,
        action="handoff_snapshot",
        actor=actor,
        subject=handoff_id,
        payload=payload,
    )

    metrics["artifacts"] = {"latest": str(metrics_latest_rel), "history": str(metrics_history_rel)}
    ledger_metrics = metrics.get("ledger") if isinstance(metrics.get("ledger"), dict) else {}
    ledger_metrics["events"] = len(_ledger_entries(ip))
    metrics["ledger"] = ledger_metrics
    metrics["ledger_event"] = ledger_event["event_hash"]
    metrics["delta"] = _metrics_delta(metrics, previous_metrics)

    report = _build_handoff_report(
        ip,
        handoff_id=handoff_id,
        stage=stage,
        intent=intent,
        metrics=metrics,
        sources=sources,
        artifacts=artifacts,
        ledger_event=ledger_event["event_hash"],
    )
    _write_json(oag_paths.state_path(ip, str(metrics_latest_rel)), metrics)
    metrics_history_path = oag_paths.state_path(ip, str(metrics_history_rel))
    metrics_history_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics, ensure_ascii=False, sort_keys=True) + "\n")

    _write_json(ip / HANDOFF_READINESS_REL, report)
    handoff_history_path = ip / HANDOFF_READINESS_HISTORY_REL
    handoff_history_path.parent.mkdir(parents=True, exist_ok=True)
    with handoff_history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "schema_version": "oag_handoff_snapshot.v1",
        "ip": ip.name,
        "id": handoff_id,
        "recorded": True,
        "path": str(ip / HANDOFF_READINESS_REL),
        "history": str(handoff_history_path),
        "metrics_path": str(oag_paths.state_path(ip, str(metrics_latest_rel))),
        "metrics_history": str(metrics_history_path),
        "ledger_event": ledger_event["event_hash"],
        "handoff": report,
        "metrics": metrics,
    }


def _handoff_numbers_match(left: Any, right: Any) -> bool:
    l_num = _num_value(left)
    r_num = _num_value(right)
    if l_num is None or r_num is None:
        return left == right
    return abs(l_num - r_num) < 0.001


def _handoff_report_issues(ip: Path) -> list[str]:
    path = ip / HANDOFF_READINESS_REL
    if not path.is_file():
        return []
    rel = str(HANDOFF_READINESS_REL)
    issues: list[str] = []
    data = _read_json_file(path)
    if not isinstance(data, dict):
        return [f"handoff report is not valid JSON object: {rel}"]
    if data.get("schema_version") != "oag_readiness_handoff.v1":
        issues.append(f"handoff report schema_version mismatch: {rel}")
    if _normal_status(data.get("status")) not in {"pass", "passed", "ok"}:
        issues.append(f"handoff report is not passing: {rel} status={data.get('status') or 'missing'}")
    if not str(data.get("method") or "").strip():
        issues.append(f"handoff report missing method: {rel}")
    boundary = str(data.get("automation_boundary") or "").strip().lower()
    if not boundary:
        issues.append(f"handoff report missing automation_boundary: {rel}")
    elif "not a signoff" not in boundary and "not signoff" not in boundary:
        issues.append(f"handoff report automation_boundary must say it is not signoff: {rel}")

    summary = data.get("numeric_summary") if isinstance(data.get("numeric_summary"), dict) else {}
    readiness = data.get("readiness") if isinstance(data.get("readiness"), dict) else {}
    metrics = data.get("improvement_metrics") if isinstance(data.get("improvement_metrics"), dict) else {}
    required_numbers = (
        "requirements_total",
        "contracts_total",
        "obligations_total",
        "obligations_closed",
        "obligations_open",
        "closure_percent",
        "check_issue_count",
        "evidence_files_present",
        "evidence_files_total",
        "evidence_files_missing",
        "stage_receipts",
        "ledger_events",
        "ranked_next_actions",
        "blocked_actions",
        "partially_closed_actions",
        "signoff_blockers",
        "decision_receipts",
        "independent_passing_reviewers",
    )
    if not summary:
        issues.append(f"handoff report missing numeric_summary: {rel}")
    for key in required_numbers:
        if _num_value(summary.get(key)) is None:
            issues.append(f"handoff report numeric_summary missing numeric field: {rel} {key}")
    if not readiness:
        issues.append(f"handoff report missing readiness: {rel}")
    for key in ("development_ready", "signoff_ready", "closure_complete", "check_clean", "evidence_complete"):
        if key in readiness and not isinstance(readiness.get(key), bool):
            issues.append(f"handoff report readiness field must be boolean: {rel} {key}")

    expected_from_metrics = {
        "requirements_total": _metric_int(metrics, "requirements", "total"),
        "contracts_total": _metric_int(metrics, "contracts", "total"),
        "obligations_total": _metric_int(metrics, "closure", "total"),
        "obligations_closed": _metric_int(metrics, "closure", "closed"),
        "obligations_open": _metric_int(metrics, "closure", "open"),
        "closure_percent": _nested_number(metrics, ("closure", "closed_percent")),
        "check_issue_count": _metric_int(metrics, "check", "issue_count"),
        "evidence_files_present": _metric_int(metrics, "evidence", "files_present_count"),
        "evidence_files_missing": _metric_int(metrics, "evidence", "files_missing_count"),
        "stage_receipts": _metric_int(metrics, "stage_receipts", "count"),
        "ledger_events": _metric_int(metrics, "ledger", "events"),
        "ranked_next_actions": _metric_int(metrics, "auto_research", "actions"),
        "blocked_actions": _metric_int(metrics, "auto_research", "blocked_actions"),
        "partially_closed_actions": _metric_int(metrics, "auto_research", "partially_closed_actions"),
        "signoff_blockers": _metric_int(metrics, "auto_research", "signoff_blockers"),
        "decision_receipts": _metric_int(metrics, "decisions", "receipts"),
        "independent_passing_reviewers": _metric_int(metrics, "decisions", "independent_passing_reviewers"),
    }
    if not metrics:
        issues.append(f"handoff report missing improvement_metrics: {rel}")
    else:
        for key, expected in expected_from_metrics.items():
            if key in summary and not _handoff_numbers_match(summary.get(key), expected):
                issues.append(f"handoff report numeric_summary does not match embedded metrics: {rel} {key}")

    evidence_refs = _str_items(data.get("evidence_refs"))
    if not evidence_refs:
        issues.append(f"handoff report missing evidence_refs: {rel}")
    for missing in _missing_path_refs(ip, evidence_refs):
        issues.append(f"handoff report evidence ref missing on disk: {rel} -> {missing}")
    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), dict) else {}
    for name, artifact_ref in sorted(artifacts.items()):
        ref = str(artifact_ref or "").strip()
        if _path_like_ref(ref) and not (ip / ref).exists():
            issues.append(f"handoff report artifact ref missing on disk: {rel} {name} -> {ref}")

    profile = str(data.get("closure_profile") or metrics.get("closure_profile") or _policy_profile(ip))
    expected_development_ready = (
        _num_value(summary.get("obligations_total")) not in {None, 0}
        and int(_num_value(summary.get("obligations_open")) or 0) == 0
        and int(_num_value(summary.get("check_issue_count")) or 0) == 0
        and int(_num_value(summary.get("evidence_files_missing")) or 0) == 0
    )
    expected_signoff_ready = (
        expected_development_ready
        and profile == "signoff"
        and int(_num_value(summary.get("blocked_actions")) or 0) == 0
        and int(_num_value(summary.get("partially_closed_actions")) or 0) == 0
        and int(_num_value(summary.get("signoff_blockers")) or 0) == 0
        and int(_num_value(summary.get("independent_passing_reviewers")) or 0) > 0
    )
    if isinstance(readiness.get("development_ready"), bool) and readiness.get("development_ready") != expected_development_ready:
        issues.append(f"handoff report development_ready does not match numeric_summary: {rel}")
    if isinstance(readiness.get("signoff_ready"), bool) and readiness.get("signoff_ready") != expected_signoff_ready:
        issues.append(f"handoff report signoff_ready does not match numeric_summary: {rel}")
    if readiness.get("signoff_ready") is True and profile != "signoff":
        issues.append(f"handoff report cannot mark signoff_ready=true when closure_profile={profile}: {rel}")
    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    for check_name, passed in sorted(checks.items()):
        if passed is False:
            issues.append(f"handoff report check failed: {rel} {check_name}")
    return issues


def _owner_for_gap(gap: str) -> str:
    lower = gap.lower()
    if "scoreboard" in lower or "tb" in lower:
        return "tb"
    if "rtl" in lower or "lint" in lower:
        return "rtl"
    if "coverage" in lower:
        return "coverage"
    if "simulation" in lower or "sim" in lower:
        return "sim"
    if "requirement" in lower or "obligation" in lower or "contract" in lower:
        return "req"
    return "triage"


def _ticket(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    stage = str(arguments.get("stage") or "triage")
    reason = str(arguments.get("reason") or arguments.get("claim") or "contract evidence gap")
    owner = str(arguments.get("owner_workflow") or _owner_for_gap(reason))
    ticket_id = f"FT_{_stamp()}_{_slug(reason)}"
    ticket = {
        "schema_version": "failure_ticket.v1",
        "id": ticket_id,
        "ip": ip.name,
        "stage": stage,
        "created_at": _now(),
        "owner_workflow": owner,
        "failing_contract": arguments.get("failing_contract") or {},
        "reason": reason,
        "expected": arguments.get("expected") or {},
        "observed": arguments.get("observed") or {},
        "evidence": arguments.get("evidence") or {},
        "editable_files": arguments.get("editable_files") if isinstance(arguments.get("editable_files"), list) else [],
        "forbidden_edits": arguments.get("forbidden_edits") if isinstance(arguments.get("forbidden_edits"), list) else ["req/locked_truth.md", "ontology/requirements.yaml", "ontology/obligations.yaml", "ontology/contracts.yaml"],
        "required_evidence_after_patch": arguments.get("required_evidence_after_patch") if isinstance(arguments.get("required_evidence_after_patch"), list) else [],
        "status": "open",
    }
    path = ip / "handoff" / "failure_tickets" / f"{ticket_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {"kind": "ai", "id": "claude", "surface": "oag.ticket"}
    ledger_payload = {"ticket": ticket, "path": str(path.relative_to(ip))}
    _assert_ledger_append_allowed(ip, action="ticket", actor=actor, payload=ledger_payload)
    path.write_text(json.dumps(ticket, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ledger_event = _append_ledger(
        ip,
        action="ticket",
        actor=actor,
        subject=ticket_id,
        payload=ledger_payload,
    )
    return {
        "schema_version": "oag_failure_ticket.v1",
        "ip": ip.name,
        "id": ticket_id,
        "path": str(path),
        "owner_workflow": owner,
        "ticket": ticket,
        "ledger_event": ledger_event["event_hash"],
    }


def _existing(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.is_file()]


def _yaml_id_count(path: Path) -> int:
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(r"(?m)^\s*-\s*id\s*:\s*\S+", text))


def _inspect(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    requirement_paths = [
        path
        for path in [
            ip / "req" / "locked_truth.md",
            ip / "req" / "requirements.yaml",
            oag_paths.legacy_or_hidden(ip, "ontology/requirements.yaml"),
            *sorted((ip / "req").glob("*requirements*.md")),
        ]
        if path.is_file()
    ]
    obligation_paths = _existing(
        [
            ip / "req" / "obligations.json",
            ip / "req" / "obligations.yaml",
            oag_paths.legacy_or_hidden(ip, "ontology/obligations.yaml"),
        ]
    )
    obligation_path = obligation_paths[0] if obligation_paths else oag_paths.legacy_or_hidden(ip, "ontology/obligations.yaml")
    obligations = _read_json_file(obligation_path) if obligation_path.suffix == ".json" else None
    obligation_count = len(obligations) if isinstance(obligations, list) else 0
    if isinstance(obligations, dict):
        items = obligations.get("obligations")
        obligation_count = len(items) if isinstance(items, list) else 1
    elif obligation_path.suffix in {".yaml", ".yml"}:
        obligation_count = _yaml_id_count(obligation_path)
    contract_paths = _existing(
        [
            ip / "req" / "evidence_plan.json",
            ip / "req" / "evidence_plan.yaml",
            oag_paths.legacy_or_hidden(ip, "ontology/contracts.yaml"),
            ip / "verify" / "equivalence_goals.json",
        ]
    )

    rtl_present, rtl_status = _status_from_json(ip / "rtl" / "rtl_compile.json")
    lint_present, lint_status = _status_from_json(ip / "lint" / "dut_lint.json")
    sim_present, sim_status = _simulation_status(ip / "sim" / "results.xml")
    coverage_present, coverage_status = _coverage_status(ip)
    signoff_present, signoff_status = _status_from_json(ip / "signoff" / "truth_coverage.json")
    scoreboard = _scoreboard_summary(ip / "sim" / "scoreboard_events.jsonl")
    truth_graph = _read_json_file(_truth_graph_path(ip))
    truth_graph_present = isinstance(truth_graph, dict)
    truth_graph_status = str(truth_graph.get("status") or "present").lower() if truth_graph_present else "missing"
    design_facts = _read_json_file(oag_paths.legacy_or_hidden(ip, str(DESIGN_FACTS_REL)))
    design_facts_present = isinstance(design_facts, dict)
    design_facts_status = str(design_facts.get("status") or "present").lower() if design_facts_present else "missing"
    design_rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
    design_rule_instances = _yaml_items(ip, str(DESIGN_RULES_REL), "instances")
    structure_issues, decomposition_summary = _decomposition_issues(
        ip,
        req_ids={str(item.get("id") or "") for item in _yaml_items(ip, "ontology/requirements.yaml", "requirements") if item.get("id")},
        obl_ids={str(item.get("id") or "") for item in _yaml_items(ip, "ontology/obligations.yaml", "obligations") if item.get("id")},
        contract_ids={str(item.get("id") or "") for item in _yaml_items(ip, "ontology/contracts.yaml", "contracts") if item.get("id")},
    )
    design_spec_present = oag_paths.legacy_or_hidden(ip, str(DESIGN_SPEC_REL)).is_file()
    authoring_packets_dir = oag_paths.legacy_or_hidden(ip, str(AUTHORING_PACKETS_REL))
    authoring_packets = sorted(authoring_packets_dir.glob("*.json")) if authoring_packets_dir.is_dir() else []
    receipt_issues = _stage_receipt_issues(ip)
    _receipts_dir = oag_paths.legacy_or_hidden(ip, str(STAGE_RECEIPTS_REL))
    receipt_count = len(sorted(_receipts_dir.glob("*.json"))) if _receipts_dir.is_dir() else 0
    closure_profile = _policy_profile(ip)
    scope_lock = _scope_lock_status(ip)
    protection_issues = _protection_issues(ip)
    ledger_issues = _ledger_issues(ip)
    monotonic_issues = _monotonic_issues(ip)
    ledger_entries = _ledger_entries(ip)
    closure_matrix = _closure_matrix(ip)

    gaps: list[str] = []
    if not requirement_paths:
        gaps.append("missing requirement file")
    if not obligation_paths:
        gaps.append("missing obligation file")
    if not contract_paths:
        gaps.append("missing evidence plan or equivalence goals")
    if not rtl_present:
        gaps.append("rtl_compile is missing")
    elif rtl_status != "pass":
        gaps.append(f"rtl_compile is {rtl_status}")
    if not lint_present:
        gaps.append("lint is missing")
    elif lint_status != "pass":
        gaps.append(f"lint is {lint_status}")
    if not sim_present:
        gaps.append("simulation is missing")
    elif sim_status != "pass":
        gaps.append(f"simulation is {sim_status}")
    sb_summary = scoreboard.get("summary") or {}
    if not scoreboard.get("present") or not sb_summary.get("total"):
        gaps.append("missing scoreboard rows")
    elif int(sb_summary.get("unreadable") or 0) > 0 or int(sb_summary.get("schema_failed") or 0) > 0:
        gaps.append("scoreboard schema has invalid rows")
    elif int(sb_summary.get("failed") or 0) > 0:
        gaps.append("scoreboard has failed rows")
    if not coverage_present:
        gaps.append("coverage is missing")
    elif coverage_status != "pass":
        gaps.append(f"coverage is {coverage_status}")
    if truth_graph_present and truth_graph_status != "pass":
        gaps.append(f"truth graph is {truth_graph_status}")
    if design_facts_present and design_facts_status != "pass":
        gaps.append(f"design facts graph is {design_facts_status}")
    if structure_issues:
        gaps.append("structure/decomposition policy has issues")
    if receipt_issues:
        gaps.append("stage receipt freshness has issues")
    if protection_issues:
        gaps.append("protected fields have issues")
    if ledger_issues:
        gaps.append("append-only ledger has issues")
    if monotonic_issues:
        gaps.append("monotonic closure invariant has issues")
    if closure_matrix["issues"]:
        gaps.append("closure matrix has open obligations")
    if scope_lock.get("implementation_artifacts") and not scope_lock.get("locked"):
        gaps.append("scope is not locked")

    validation = "closed" if not gaps else "partial"
    return {
        "schema_version": "oag_inspect.v1",
        "ip": ip.name,
        "path": str(ip),
        "validation": validation,
        "gaps": gaps,
        "evidence": {
            "requirement": {"present": bool(requirement_paths), "paths": [str(p) for p in requirement_paths]},
            "obligation": {
                "present": bool(obligation_paths),
                "path": str(obligation_path),
                "paths": [str(p) for p in obligation_paths],
                "count": obligation_count,
            },
            "contract": {
                "present": bool(contract_paths),
                "paths": [str(p) for p in contract_paths],
            },
            "rtl_compile": {"present": rtl_present, "status": rtl_status},
            "lint": {"present": lint_present, "status": lint_status},
            "simulation": {"present": sim_present, "status": sim_status},
            "scoreboard": scoreboard,
            "coverage": {"present": coverage_present, "status": coverage_status},
            "signoff": {"present": signoff_present, "status": signoff_status},
            "truth_graph": {
                "present": truth_graph_present,
                "status": truth_graph_status,
                "path": str(_truth_graph_path(ip)),
                "stats": truth_graph.get("stats") if isinstance(truth_graph, dict) else {},
            },
            "design_facts_graph": {
                "present": design_facts_present,
                "status": design_facts_status,
                "path": str(oag_paths.legacy_or_hidden(ip, str(DESIGN_FACTS_REL))),
                "stats": design_facts.get("stats") if isinstance(design_facts, dict) else {},
                "extractor": design_facts.get("extractor") if isinstance(design_facts, dict) else {},
            },
            "design_rules": {
                "present": oag_paths.legacy_or_hidden(ip, str(DESIGN_RULES_REL)).is_file(),
                "path": str(oag_paths.legacy_or_hidden(ip, str(DESIGN_RULES_REL))),
                "count": len(design_rules),
                "instances": len(design_rule_instances),
            },
            "structure": {
                "present": oag_paths.legacy_or_hidden(ip, str(STRUCTURE_REL)).is_file(),
                "path": str(oag_paths.legacy_or_hidden(ip, str(STRUCTURE_REL))),
                "profile": decomposition_summary.get("profile") or "",
                "issues": structure_issues,
            },
            "decomposition": {
                "present": oag_paths.legacy_or_hidden(ip, str(DECOMPOSITION_REL)).is_file(),
                "path": str(oag_paths.legacy_or_hidden(ip, str(DECOMPOSITION_REL))),
                "modules": decomposition_summary.get("module_count") or 0,
                "current_ip_modules": decomposition_summary.get("current_ip_module_count") or 0,
                "legacy_sources": decomposition_summary.get("legacy_sources") or [],
            },
            "design_spec": {"present": design_spec_present, "path": str(oag_paths.legacy_or_hidden(ip, str(DESIGN_SPEC_REL)))},
            "authoring_packets": {
                "present": bool(authoring_packets),
                "path": str(oag_paths.legacy_or_hidden(ip, str(AUTHORING_PACKETS_REL))),
                "count": len(authoring_packets),
                "packets": [str(path) for path in authoring_packets],
            },
            "stage_receipts": {"present": receipt_count > 0, "count": receipt_count, "issues": receipt_issues},
            "scope_lock": scope_lock,
            "protection": {
                "present": oag_paths.legacy_or_hidden(ip, str(PROTECTION_REL)).is_file(),
                "path": str(oag_paths.legacy_or_hidden(ip, str(PROTECTION_REL))),
                "protected_paths": _protected_paths(ip),
                "issues": protection_issues,
            },
            "ledger": {"present": _ledger_path(ip).is_file(), "path": str(_ledger_path(ip)), "events": len(ledger_entries), "issues": ledger_issues},
            "monotonic_closure": {"issues": monotonic_issues},
            "closure_matrix": closure_matrix,
            "policy": {"closure_profile": closure_profile},
        },
        "improvement_metrics": _improvement_metrics(
            ip,
            closure_matrix=closure_matrix,
            stage=str(arguments.get("stage") or ""),
            intent=str(arguments.get("intent") or arguments.get("query") or ""),
        ),
        "suggested_next_actions": _suggest_actions(gaps),
    }


def _scaffold(arguments: dict[str, Any]) -> dict[str, Any]:
    import oag_scaffold_ip

    ip = _ip_dir(arguments)
    manifest = oag_scaffold_ip.scaffold(
        ip,
        force=bool(arguments.get("force")),
        owner=str(arguments.get("owner") or "unassigned"),
        layout=str(arguments.get("layout") or "legacy"),
    )
    return {
        "schema_version": "oag_scaffold_result.v1",
        "ip": manifest["ip"],
        "path": manifest["path"],
        "layout": manifest.get("layout", "legacy"),
        "directories": manifest["directories"],
        "written_files": manifest["written_files"],
        "skipped_files": manifest["skipped_files"],
    }


def _suggest_actions(gaps: list[str]) -> list[str]:
    actions: list[str] = []
    if "missing obligations.json" in gaps or "missing obligation file" in gaps:
        actions.append("derive obligations from locked_truth.md and evidence_plan.json")
    if "missing evidence plan or equivalence goals" in gaps:
        actions.append("write contract/evidence plan before claiming closure")
    if any("scoreboard has failed rows" == gap for gap in gaps):
        actions.append("inspect sim/scoreboard_events.jsonl failed rows")
    if any("scoreboard schema has invalid rows" == gap for gap in gaps):
        actions.append("emit scoreboard_rows.v1 rows with expected, observed, and observed_source")
    if any(gap.startswith("coverage is") and gap != "coverage is missing" for gap in gaps):
        actions.append("inspect cov/coverage.json and close coverage blocker")
    if "coverage is missing" in gaps:
        actions.append("run coverage or attach a justified waiver")
    if "simulation is missing" in gaps:
        actions.append("run simulation and attach sim/results.xml")
    if any(gap.startswith("truth graph is") for gap in gaps):
        actions.append("run oag.compile and resolve truth graph issues")
    if "structure/decomposition policy has issues" in gaps:
        actions.append("fix ontology/structure.yaml, ontology/decomposition.yaml, and policies.yaml structure_policy")
    if "stage receipt freshness has issues" in gaps:
        actions.append("refresh ontology/evidence/stage_runs receipts after rerunning the owning stage")
    if "protected fields have issues" in gaps:
        actions.append("record a human-approved decision before changing locked truth or policy fields")
    if "append-only ledger has issues" in gaps:
        actions.append("inspect knowledge/ledger.jsonl for tampering or invalid hash-chain entries")
    if "monotonic closure invariant has issues" in gaps:
        actions.append("open a refuted/decision record instead of silently weakening a closed object")
    if "closure matrix has open obligations" in gaps:
        actions.append("record explicit ROCEV validation for every obligation-to-contract closure")
    return actions


def _knowledge_index(ip: Path) -> Path:
    return oag_paths.legacy_or_hidden(ip, "knowledge/_index.json")


def _ensure_knowledge(ip: Path) -> dict[str, Any]:
    records = oag_paths.state_path(ip, "knowledge/records")
    records.mkdir(parents=True, exist_ok=True)
    ledger = _ledger_path(ip)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.is_file():
        ledger.write_text("", encoding="utf-8")
    index = _knowledge_index(ip)
    if not index.is_file():
        index.write_text(
            json.dumps(
                {
                    "schema_version": "ip_knowledge_index.v1",
                    "generated_at": _now(),
                    "ip": ip.name,
                    "record_count": 0,
                    "records": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return {"schema_version": "oag_init.v1", "ip": ip.name, "knowledge_dir": str(oag_paths.state_path(ip, "knowledge")), "index": str(index), "ledger": str(ledger)}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value or "").strip("_").upper()
    return (text or "RECORD")[:48].strip("_") or "RECORD"


def _layout_issues(ip: Path) -> list[str]:
    """Reject an unsafe mixed layout where ontology/ or knowledge/ exist BOTH at the
    legacy top level and under <ip>/.oag/. The resolver reads .oag and silently
    shadows the legacy copy, so the two diverge; migration via oag_migrate_layout.py
    is atomic, so a mixed state is always a defect to be reconciled."""
    if not oag_paths.oag_root(ip).is_dir():
        return []
    shadowed = [name for name in ("ontology", "knowledge") if (ip / name).is_dir()]
    if not shadowed:
        return []
    return [
        "mixed OAG layout: "
        + ", ".join(sorted(shadowed))
        + " exist both at the top level and under .oag/; finish the migration (oag_migrate_layout.py) so state is read from one location"
    ]


def _check(arguments: dict[str, Any], *, include_metrics: bool = True) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    issues: list[str] = []
    if not oag_paths.legacy_or_hidden(ip, "knowledge").is_dir():
        issues.append(f"missing knowledge directory: {oag_paths.legacy_or_hidden(ip, 'knowledge')}")
    if not oag_paths.legacy_or_hidden(ip, "knowledge/records").is_dir():
        issues.append(f"missing records directory: {oag_paths.legacy_or_hidden(ip, 'knowledge/records')}")
    index = _knowledge_index(ip)
    if not index.is_file():
        issues.append(f"missing index: {index}")
    else:
        data = _read_json_file(index)
        if not isinstance(data, dict):
            issues.append("index is not valid JSON object")
        elif data.get("schema_version") != "ip_knowledge_index.v1":
            issues.append("index schema_version mismatch")
    policies = oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml")
    if policies.is_file() and _policy_profile(ip) not in {"draft", "development", "signoff"}:
        issues.append("invalid closure_profile in ontology/policies.yaml")
    stages = oag_paths.legacy_or_hidden(ip, "ontology/stages.yaml")
    if stages.is_file() and not _yaml_items(ip, "ontology/stages.yaml", "stages"):
        issues.append("ontology/stages.yaml declares no stages")
    if oag_paths.legacy_or_hidden(ip, "ontology").is_dir():
        design_rules_path = oag_paths.legacy_or_hidden(ip, str(DESIGN_RULES_REL))
        if not design_rules_path.is_file():
            issues.append(f"missing {DESIGN_RULES_REL}")
        else:
            rules = _yaml_items(ip, str(DESIGN_RULES_REL), "rules")
            kinds = {str(item.get("kind") or "") for item in rules if item.get("kind")}
            if not rules:
                issues.append(f"{DESIGN_RULES_REL} declares no rules")
            for kind in sorted(REQUIRED_DESIGN_RULE_KINDS - kinds):
                issues.append(f"{DESIGN_RULES_REL} missing required kind: {kind}")
        reqs = _yaml_items(ip, "ontology/requirements.yaml", "requirements")
        obligations = _yaml_items(ip, "ontology/obligations.yaml", "obligations")
        contracts = _yaml_items(ip, "ontology/contracts.yaml", "contracts")
        issues.extend(
            _decomposition_issues(
                ip,
                req_ids={str(item.get("id") or "") for item in reqs if item.get("id")},
                obl_ids={str(item.get("id") or "") for item in obligations if item.get("id")},
                contract_ids={str(item.get("id") or "") for item in contracts if item.get("id")},
            )[0]
        )
        issues.extend(
            _fault_model_coverage_issues(
                ip,
                req_ids={str(item.get("id") or "") for item in reqs if item.get("id")},
                obl_ids={str(item.get("id") or "") for item in obligations if item.get("id")},
                contract_ids={str(item.get("id") or "") for item in contracts if item.get("id")},
            )
        )
        issues.extend(
            _verification_role_decomposition_issues(
                ip,
                req_ids={str(item.get("id") or "") for item in reqs if item.get("id")},
                obl_ids={str(item.get("id") or "") for item in obligations if item.get("id")},
                contract_ids={str(item.get("id") or "") for item in contracts if item.get("id")},
            )
        )
        issues.extend(
            _interleaved_context_issues(
                ip,
                req_ids={str(item.get("id") or "") for item in reqs if item.get("id")},
                obl_ids={str(item.get("id") or "") for item in obligations if item.get("id")},
                contract_ids={str(item.get("id") or "") for item in contracts if item.get("id")},
            )
        )
        issues.extend(
            _signoff_design_rule_issues(
                ip,
                req_ids={str(item.get("id") or "") for item in reqs if item.get("id")},
                obl_ids={str(item.get("id") or "") for item in obligations if item.get("id")},
                contract_ids={str(item.get("id") or "") for item in contracts if item.get("id")},
            )
        )
        issues.extend(_auto_research_report_issues(ip))
        issues.extend(_handoff_report_issues(ip))
        issues.extend(_protection_issues(ip))
    closure_matrix = _closure_matrix(ip)
    issues.extend(closure_matrix["issues"])
    if oag_paths.legacy_or_hidden(ip, "ontology").is_dir():
        issues.extend(_modeling_oracle_issues(ip, closure_matrix))
        issues.extend(_domain_intent_issues(ip, closure_matrix))
        issues.extend(_tb_methodology_issues(ip, closure_matrix))
    issues.extend(_ledger_issues(ip))
    issues.extend(_monotonic_issues(ip))
    issues.extend(_record_evidence_issues(ip))
    scoreboard = _scoreboard_summary(ip / SCOREBOARD_REL)
    if scoreboard.get("present"):
        issues.extend([f"scoreboard_rows.v1: {issue}" for issue in _as_list(scoreboard.get("issues"))])
    issues.extend(_stage_receipt_issues(ip))
    issues.extend(_scope_lock_issues(ip))
    issues.extend(_layout_issues(ip))
    result = {
        "schema_version": "oag_check.v1",
        "ip": ip.name,
        "ok": not issues,
        "issues": issues,
        "policy": {"closure_profile": _policy_profile(ip)},
        "scope_lock": _scope_lock_status(ip),
        "structure": {"profile": _structure_profile(ip), "path": str(oag_paths.legacy_or_hidden(ip, str(STRUCTURE_REL))), "decomposition": str(oag_paths.legacy_or_hidden(ip, str(DECOMPOSITION_REL)))},
        "truth_graph": {"compiled": _truth_graph_compiled(ip), "path": str(_truth_graph_path(ip))},
        "ledger": {"path": str(_ledger_path(ip)), "events": len(_ledger_entries(ip))},
        "closure_matrix": closure_matrix,
    }
    if include_metrics:
        result["improvement_metrics"] = _improvement_metrics(
            ip,
            check_issues=issues,
            closure_matrix=closure_matrix,
            stage=str(arguments.get("stage") or ""),
            intent=str(arguments.get("intent") or arguments.get("query") or ""),
        )
    return result


def _context(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    stage = str(arguments.get("stage") or "")
    intent = str(arguments.get("intent") or arguments.get("query") or "")
    index = _read_json_file(_knowledge_index(ip))
    records = []
    if isinstance(index, dict):
        records = [item for item in index.get("records", []) if isinstance(item, dict)]
    truth_graph = _read_json_file(_truth_graph_path(ip))
    truth_status = str(truth_graph.get("status") or "missing") if isinstance(truth_graph, dict) else "missing"
    profile = _policy_profile(ip)
    scope_lock = _scope_lock_status(ip)
    structure_issues, decomposition_summary = _decomposition_issues(ip)
    structure_profile = str(decomposition_summary.get("profile") or "")
    ticket_dir = ip / "handoff" / "failure_tickets"
    tickets = sorted(ticket_dir.glob("*.json")) if ticket_dir.is_dir() else []
    ledger_events = len(_ledger_entries(ip))
    protection_issues = _protection_issues(ip)
    metrics = _improvement_metrics(ip, stage=stage, intent=intent)
    closure = metrics.get("closure") if isinstance(metrics.get("closure"), dict) else {}
    check = metrics.get("check") if isinstance(metrics.get("check"), dict) else {}
    evidence_metrics = metrics.get("evidence") if isinstance(metrics.get("evidence"), dict) else {}
    stage_receipts = metrics.get("stage_receipts") if isinstance(metrics.get("stage_receipts"), dict) else {}
    lines = ["=== IP KNOWLEDGE LEDGER (read before acting) ==="]
    lines.append(f"IP={ip.name} stage={stage} intent={intent}")
    lines.append(
        f"closure_profile={profile} truth_graph={truth_status} ledger_events={ledger_events} "
        f"protected_fields={'ok' if not protection_issues else 'issue'} failure_tickets={len(tickets)}"
    )
    lines.append(
        f"scope_lock={scope_lock.get('state')} can_implement={str(scope_lock.get('can_implement')).lower()} "
        f"lock_path={SCOPE_LOCK_REL}"
    )
    if not scope_lock.get("locked"):
        lines.append("lock_rule=No lock, no RTL/TB/closure. Stay in draft/interview mode until the user says lock.")
    lines.append(
        f"structure_profile={structure_profile or 'missing'} modules={decomposition_summary.get('module_count') or 0} "
        f"structure={'ok' if not structure_issues else 'issue'} authoring_packets={len(sorted(oag_paths.legacy_or_hidden(ip, str(AUTHORING_PACKETS_REL)).glob('*.json'))) if oag_paths.legacy_or_hidden(ip, str(AUTHORING_PACKETS_REL)).is_dir() else 0}"
    )
    lines.append(
        "metrics "
        f"closure={closure.get('closed', 0)}/{closure.get('total', 0)} ({closure.get('closed_percent', 0.0)}%) "
        f"check_issues={check.get('issue_count', 0)} "
        f"evidence_files={evidence_metrics.get('files_present_count', 0)}/{evidence_metrics.get('referenced_file_count', 0)} "
        f"stage_receipts={stage_receipts.get('count', 0)}"
    )
    if records:
        for record in records[: int(arguments.get("limit") or 5)]:
            lines.append(f"- {record.get('id')} [{record.get('validation_status')}] {record.get('claim')}")
    else:
        inspect = _inspect(arguments)
        lines.append("No IP knowledge records yet. Read-only inspect summary:")
        lines.append(f"- validation={inspect['validation']} gaps={'; '.join(inspect['gaps']) or 'none'}")
    lines.append("=== END IP KNOWLEDGE LEDGER ===")
    return {
        "schema_version": "oag_context.v1",
        "ip": ip.name,
        "stage": stage,
        "intent": intent,
        "prompt_block": "\n".join(lines),
        "records": records,
        "truth_graph": {"present": isinstance(truth_graph, dict), "status": truth_status, "path": str(_truth_graph_path(ip))},
        "policy": {"closure_profile": profile},
        "scope_lock": scope_lock,
        "structure": {
            "profile": structure_profile,
            "issues": structure_issues,
            "decomposition": decomposition_summary,
            "design_spec": str(oag_paths.legacy_or_hidden(ip, str(DESIGN_SPEC_REL))),
            "authoring_packets": str(oag_paths.legacy_or_hidden(ip, str(AUTHORING_PACKETS_REL))),
            "design_facts_graph": str(oag_paths.legacy_or_hidden(ip, str(DESIGN_FACTS_REL))),
        },
        "improvement_metrics": metrics,
        "failure_tickets": [str(path) for path in tickets],
        "evidence_gaps": [],
    }


def _record(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    claim = str(arguments.get("claim") or arguments.get("title") or "OAG record")
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    rocev = arguments.get("rocev") if isinstance(arguments.get("rocev"), dict) else {}
    evidence = rocev.get("evidence") if isinstance(rocev.get("evidence"), dict) else {}
    validation = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else {}
    files = [str(item).strip() for item in (evidence.get("files") if isinstance(evidence.get("files"), list) else []) if str(item).strip()]
    tests = [str(item).strip() for item in (evidence.get("tests") if isinstance(evidence.get("tests"), list) else []) if str(item).strip()]
    commit = str(evidence.get("commit") or "")
    argument_status = _normal_status(arguments.get("status"))
    validation_status = _normal_status(validation.get("status"))
    if argument_status in CLOSED_STATUSES and validation_status not in CLOSED_STATUSES:
        raise ValueError("closed records require explicit rocev.validation.status")
    status = validation_status or argument_status or "open"
    evidence_file_hashes = _evidence_file_hashes(ip, files)
    supersedes = [str(item).strip() for item in _as_list(arguments.get("supersedes")) if str(item).strip()]
    record_id = f"IKL_{_stamp()}_{_slug(claim)}"
    record = {
        "schema": "ip_knowledge_record.v1",
        "id": record_id,
        "scope": {"ip": ip.name, "stage": str(arguments.get("stage") or "general")},
        "type": str(arguments.get("type") or "log"),
        "actor": {
            "kind": str(actor.get("kind") or "ai"),
            "id": str(actor.get("id") or os.environ.get("USER") or "unknown"),
            "session": str(actor.get("session") or ""),
            "surface": str(actor.get("surface") or "claude-plugin"),
        },
        "claim": claim,
        "summary": str(arguments.get("summary") or arguments.get("body") or ""),
        "tags": arguments.get("tags") if isinstance(arguments.get("tags"), list) else [],
        "rocev": rocev,
        "evidence": {"files": files, "tests": tests, "commit": commit, "file_hashes": evidence_file_hashes},
        "validation": {"status": status, "verdict": str(validation.get("verdict") or "pending"), "rationale": str(validation.get("rationale") or "")},
        "supersedes": supersedes,
        "promotion": {"state": "local"},
        "created_at": _now(),
    }
    record_rel = f"knowledge/records/{record_id}.json"
    path = oag_paths.state_path(ip, record_rel)
    action = str(record["type"] or "record")
    # Keep the ledger-recorded path LOGICAL so the hash chain never captures a
    # ".oag/" prefix regardless of the active layout.
    ledger_payload = {"record": record, "path": record_rel}
    _assert_ledger_append_allowed(ip, action=action, actor=record["actor"], payload=ledger_payload)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rebuild_knowledge_index(ip)
    ledger_event = _append_ledger(
        ip,
        action=action,
        actor=record["actor"],
        subject=record_id,
        payload=ledger_payload,
        monotonic_subjects=_record_subjects(record, status),
    )
    return {
        "schema_version": "oag_record.v1",
        "ip": ip.name,
        "id": record_id,
        "path": str(path),
        "status": status,
        "actor": record["actor"],
        "record": record,
        "ledger_event": ledger_event["event_hash"],
    }


def _markdown_bullets(values: Any) -> list[str]:
    lines: list[str] = []
    for item in _as_list(values):
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("summary") or item.get("id") or json.dumps(item, ensure_ascii=False, sort_keys=True))
        else:
            text = str(item)
        text = text.strip()
        if text:
            lines.append(f"- {text}")
    return lines


def _draft(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    (ip / "req").mkdir(parents=True, exist_ok=True)
    oag_paths.state_path(ip, str(DRAFTS_REL)).mkdir(parents=True, exist_ok=True)

    stage = str(arguments.get("stage") or "req")
    title = str(arguments.get("title") or arguments.get("claim") or "Interview draft")
    summary = str(arguments.get("summary") or arguments.get("body") or "").strip()
    facts = arguments.get("facts") if isinstance(arguments.get("facts"), list) else []
    decisions = arguments.get("decisions") if isinstance(arguments.get("decisions"), list) else []
    assumptions = arguments.get("assumptions") if isinstance(arguments.get("assumptions"), list) else []
    open_questions = arguments.get("open_questions") if isinstance(arguments.get("open_questions"), list) else []
    source = str(arguments.get("source") or "chat_interview")
    tags = ["interview", "draft"]
    if isinstance(arguments.get("tags"), list):
        tags.extend(str(tag) for tag in arguments["tags"] if str(tag).strip())

    record_response = _record(
        {
            "ip_dir": str(ip),
            "stage": stage,
            "type": "interview_draft",
            "claim": title,
            "summary": summary,
            "actor": arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {"kind": "ai", "id": "claude", "surface": "oag.draft"},
            "tags": tags,
            "status": "draft",
            "rocev": {
                "requirement": {"id": "", "source": "req/interview_draft.md", "status": "draft"},
                "obligation": {"id": "", "status": "draft"},
                "contract": {"id": "", "method": "interview", "status": "draft"},
                "evidence": {"files": ["req/interview_draft.md"], "tests": [], "commit": ""},
                "validation": {"verdict": "draft", "status": "draft", "rationale": "Captured during requirement interview; not locked truth."},
            },
        }
    )
    record_id = str(record_response["id"])
    draft = {
        "schema_version": "oag_interview_draft.v1",
        "id": record_id,
        "ip": ip.name,
        "stage": stage,
        "title": title,
        "summary": summary,
        "facts": facts,
        "decisions": decisions,
        "assumptions": assumptions,
        "open_questions": open_questions,
        "source": source,
        "promotion_state": "draft",
        "created_at": _now(),
        "record": _logical_rel_to_ip(ip, Path(record_response["path"])),
    }
    draft_path = oag_paths.state_path(ip, f"ontology/drafts/{record_id}.json")
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_path = ip / "req" / "interview_draft.md"
    sections = [
        f"## {draft['created_at']} {title}",
        "",
        f"- record: `{draft['record']}`",
        f"- source: `{source}`",
        f"- promotion_state: `{draft['promotion_state']}`",
        "",
    ]
    if summary:
        sections.extend(["### Summary", "", summary, ""])
    for heading, values in (
        ("Facts", facts),
        ("Decisions", decisions),
        ("Assumptions", assumptions),
        ("Open Questions", open_questions),
    ):
        bullets = _markdown_bullets(values)
        if bullets:
            sections.extend([f"### {heading}", "", *bullets, ""])
    existing = md_path.read_text(encoding="utf-8") if md_path.is_file() else f"# {ip.name} Interview Drafts\n\n"
    md_path.write_text(existing.rstrip() + "\n\n" + "\n".join(sections).rstrip() + "\n", encoding="utf-8")
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {"kind": "ai", "id": "claude", "surface": "oag.draft"}
    ledger_event = _append_ledger(
        ip,
        action="draft",
        actor=actor,
        subject=record_id,
        payload={
            "draft": draft,
            "draft_path": str(draft_path.relative_to(ip)),
            "markdown_path": str(md_path.relative_to(ip)),
        },
    )
    affects_scope = arguments.get("affects_scope")
    if affects_scope is None:
        affects_scope = stage.lower() in {"req", "requirement", "requirements", "scope", "interview"}
    scope_update = None
    if bool(affects_scope):
        scope_update = _mark_scope_draft_after_interview(
            ip,
            actor=actor,
            draft_id=record_id,
            reason="new requirement draft after scope lock",
        )

    return {
        "schema_version": "oag_draft.v1",
        "ip": ip.name,
        "id": record_id,
        "status": "draft",
        "record_path": record_response["path"],
        "draft_path": str(draft_path),
        "markdown_path": str(md_path),
        "promotion_state": "draft",
        "ledger_event": ledger_event["event_hash"],
        "scope_lock": _scope_lock_status(ip),
        "scope_update": scope_update,
    }


def _review_policy(ip: Path) -> dict[str, Any]:
    policies = _policy_doc(ip)
    value = policies.get("review_policy") if isinstance(policies.get("review_policy"), dict) else {}
    return value


def _reviewer_required(ip: Path, action: str) -> bool:
    if action not in {"signoff", "promote"}:
        return False
    policy = _review_policy(ip)
    if "require_independent_reviewer" in policy:
        return bool(policy.get("require_independent_reviewer"))
    return _policy_profile(ip) == "signoff"


def _reviewer_receipts(ip: Path, action: str = "") -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    directory = oag_paths.legacy_or_hidden(ip, str(DECISION_RECEIPTS_REL))
    if not directory.is_dir():
        return receipts
    for path in sorted(directory.glob("REV_*.json")):
        data = _read_json_file(path)
        if not isinstance(data, dict):
            continue
        if data.get("schema_version") != "oag_reviewer_receipt.v1":
            continue
        if action and str(data.get("action") or "") != action:
            continue
        data["_path"] = str(path)
        receipts.append(data)
    return receipts


def _passing_reviewer_receipts(ip: Path, action: str) -> list[dict[str, Any]]:
    receipts = []
    for receipt in _reviewer_receipts(ip, action):
        verdict = _normal_status(receipt.get("verdict") or receipt.get("status"))
        if (
            receipt.get("allowed") is True
            and receipt.get("independent") is True
            and verdict in {"pass", "approved", "closed", "validated"}
        ):
            receipts.append(receipt)
    return receipts


def _reviewer_receipt_issues(ip: Path, *, action: str, require_any: bool = False) -> list[str]:
    if not require_any:
        return []
    receipts = _passing_reviewer_receipts(ip, action)
    if not receipts:
        return [f"{action}: missing passing independent reviewer receipt under {DECISION_RECEIPTS_REL}/REV_*.json"]
    return []


def _review_actor(arguments: dict[str, Any]) -> dict[str, str]:
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    return {
        "kind": str(actor.get("kind") or "ai"),
        "id": str(actor.get("id") or os.environ.get("USER") or "unknown-reviewer"),
        "session": str(actor.get("session") or ""),
        "surface": str(actor.get("surface") or "oag.review"),
    }


def _same_actor(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left or not right:
        return False
    return str(left.get("kind") or "") == str(right.get("kind") or "") and str(left.get("id") or "") == str(right.get("id") or "")


def _write_reviewer_receipt(
    ip: Path,
    *,
    action: str,
    allowed: bool,
    reason: str,
    actor: dict[str, str],
    producer_actor: dict[str, Any],
    verdict: str,
    findings: list[Any],
    inspect: dict[str, Any],
    check: dict[str, Any],
) -> dict[str, Any]:
    receipt_id = f"REV_{_stamp()}_{_slug(action)}"
    rel = DECISION_RECEIPTS_REL / f"{receipt_id}.json"
    path = oag_paths.state_path(ip, str(rel))
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": "oag_reviewer_receipt.v1",
        "id": receipt_id,
        "ip": ip.name,
        "action": action,
        "allowed": allowed,
        "reason": reason,
        "verdict": verdict,
        "actor": actor,
        "producer_actor": producer_actor,
        "independent": not _same_actor(actor, producer_actor),
        "findings": findings,
        "created_at": _now(),
        "evidence": {
            "inspect_validation": inspect.get("validation"),
            "gaps": inspect.get("gaps") or [],
            "check_ok": check.get("ok"),
            "check_issues": check.get("issues") or [],
            "closure_matrix": check.get("closure_matrix") or {},
        },
    }
    ledger_event = _append_ledger(
        ip,
        action="review",
        actor=actor,
        subject=receipt_id,
        payload={"reviewer_receipt": receipt, "path": str(rel)},
    )
    receipt["ledger_event"] = ledger_event["event_hash"]
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"id": receipt_id, "path": str(path), "ledger_event": ledger_event["event_hash"]}


def _review(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    action = str(arguments.get("action") or "signoff")
    verdict = _normal_status(arguments.get("verdict") or "pass")
    actor = _review_actor(arguments)
    producer_actor = arguments.get("producer_actor") if isinstance(arguments.get("producer_actor"), dict) else {}
    inspect = _inspect(arguments)
    check = _check(arguments)
    allowed = True
    reason = "allowed"
    if _same_actor(actor, producer_actor):
        allowed = False
        reason = "reviewer_not_independent"
    elif verdict not in {"pass", "approved", "closed", "validated"}:
        allowed = False
        reason = "review_verdict_not_pass"
    elif not check.get("ok"):
        allowed = False
        reason = "knowledge_check_failed"
    elif inspect.get("gaps"):
        allowed = False
        reason = "artifact_evidence_gap"
    receipt = None
    if arguments.get("record_review", True) is not False:
        receipt = _write_reviewer_receipt(
            ip,
            action=action,
            allowed=allowed,
            reason=reason,
            actor=actor,
            producer_actor=producer_actor,
            verdict=verdict,
            findings=arguments.get("findings") if isinstance(arguments.get("findings"), list) else [],
            inspect=inspect,
            check=check,
        )
    return {
        "schema_version": "oag_review.v1",
        "ip": ip.name,
        "action": action,
        "allowed": allowed,
        "reason": reason,
        "verdict": verdict,
        "independent": not _same_actor(actor, producer_actor),
        "reviewer_receipt": receipt,
        "inspect": inspect,
        "check": check,
    }


def _decision_actor(arguments: dict[str, Any]) -> dict[str, str]:
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    return {
        "kind": str(actor.get("kind") or "ai"),
        "id": str(actor.get("id") or os.environ.get("USER") or "unknown"),
        "session": str(actor.get("session") or ""),
        "surface": str(actor.get("surface") or "oag.decide"),
    }


def _write_decision_receipt(
    ip: Path,
    *,
    action: str,
    allowed: bool,
    reason: str,
    next_action: str,
    actor: dict[str, str],
    inspect: dict[str, Any],
    check: dict[str, Any],
) -> dict[str, Any]:
    receipt_id = f"DEC_{_stamp()}_{_slug(action)}"
    rel = DECISION_RECEIPTS_REL / f"{receipt_id}.json"
    path = oag_paths.state_path(ip, str(rel))
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": "oag_decision_receipt.v1",
        "id": receipt_id,
        "ip": ip.name,
        "action": action,
        "allowed": allowed,
        "reason": reason,
        "next_action": next_action,
        "actor": actor,
        "created_at": _now(),
        "policy": {"closure_profile": _policy_profile(ip)},
        "evidence": {
            "inspect_validation": inspect.get("validation"),
            "gaps": inspect.get("gaps") or [],
            "check_ok": check.get("ok"),
            "check_issues": check.get("issues") or [],
            "closure_matrix": check.get("closure_matrix") or {},
            "truth_graph": check.get("truth_graph") or {},
            "ledger": check.get("ledger") or {},
            "improvement_metrics": check.get("improvement_metrics") or {},
        },
    }
    ledger_event = _append_ledger(
        ip,
        action="decision",
        actor=actor,
        subject=receipt_id,
        payload={"decision_receipt": receipt, "path": str(rel)},
    )
    receipt["ledger_event"] = ledger_event["event_hash"]
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"id": receipt_id, "path": str(path), "ledger_event": ledger_event["event_hash"]}


def _decide(arguments: dict[str, Any]) -> dict[str, Any]:
    action = str(arguments.get("action") or "")
    ip = _ip_dir(arguments)
    scope_lock = _scope_lock_status(ip)
    inspect = _inspect(arguments)
    check = _check(arguments)
    allowed = True
    reason = "allowed"
    next_action = ""
    if action in VALID_COMPLETION_ACTIONS:
        if not scope_lock["locked"]:
            allowed = False
            reason = "scope_lock_required"
            next_action = "ask the user to confirm scope, then run oag.lock before implementation or closure"
        elif not check["ok"]:
            allowed = False
            reason = "knowledge_check_failed"
            next_action = "run oag.init or oag.record before claiming closure"
        elif inspect["gaps"]:
            allowed = False
            reason = "artifact_evidence_gap"
            next_action = inspect["suggested_next_actions"][0] if inspect["suggested_next_actions"] else "close evidence gaps"
        elif action in {"signoff", "promote"} and _policy_profile(_ip_dir(arguments)) != "signoff":
            allowed = False
            reason = "closure_profile_not_signoff"
            next_action = "set ontology/policies.yaml closure_profile: signoff after human approval"
        elif action in {"signoff", "promote"} and not _truth_graph_compiled(_ip_dir(arguments)):
            allowed = False
            reason = "truth_graph_not_compiled"
            next_action = "run oag.compile and review ontology/generated/design_truth_graph.json"
        elif action in {"signoff", "promote"}:
            receipt_issues = _stage_receipt_issues(_ip_dir(arguments), require_any=True)
            if receipt_issues:
                allowed = False
                reason = "stage_receipts_not_fresh"
                next_action = receipt_issues[0]
        if allowed and action in {"signoff", "promote"}:
            review_issues = _reviewer_receipt_issues(
                _ip_dir(arguments),
                action=action,
                require_any=_reviewer_required(_ip_dir(arguments), action),
            )
            if review_issues:
                allowed = False
                reason = "reviewer_receipt_required"
                next_action = review_issues[0]
        if allowed and arguments.get("record_decision") is not True:
            allowed = False
            reason = "decision_receipt_required"
            next_action = "rerun oag.decide with record_decision=true to write ontology/validations receipt"
    decision_receipt = None
    if arguments.get("record_decision") is True:
        decision_receipt = _write_decision_receipt(
            _ip_dir(arguments),
            action=action,
            allowed=allowed,
            reason=reason,
            next_action=next_action,
            actor=_decision_actor(arguments),
            inspect=inspect,
            check=check,
        )
    return {
        "schema_version": "oag_decision.v1",
        "ip": inspect["ip"],
        "action": action,
        "allowed": allowed,
        "reason": reason,
        "next_action": next_action,
        "policy": {"closure_profile": _policy_profile(_ip_dir(arguments))},
        "scope_lock": scope_lock,
        "inspect": inspect,
        "check": check,
        "decision_receipt": decision_receipt,
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_actor(arguments: dict[str, Any], *, surface: str) -> dict[str, str]:
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    return {
        "kind": str(actor.get("kind") or "ai"),
        "id": str(actor.get("id") or os.environ.get("USER") or "unknown"),
        "session": str(actor.get("session") or ""),
        "surface": str(actor.get("surface") or surface),
    }


def _runs_dir(ip: Path) -> Path:
    return oag_paths.legacy_or_hidden(ip, str(RUNS_REL))


def _active_run_path(ip: Path) -> Path:
    return _runs_dir(ip) / "active_run.json"


def _new_run_id(arguments: dict[str, Any]) -> str:
    supplied = str(arguments.get("run_id") or "").strip()
    if supplied:
        return _safe_filename(supplied)
    intent = str(arguments.get("intent") or arguments.get("stage") or "run")
    return f"RUN_{_stamp()}_{_slug(intent)}"


def _run_dir(ip: Path, run_id: str) -> Path:
    return _runs_dir(ip) / _safe_filename(run_id)


def _run_state_path(ip: Path, run_id: str) -> Path:
    return _run_dir(ip, run_id) / "run_state.json"


def _run_next_action_path(ip: Path, run_id: str) -> Path:
    return _run_dir(ip, run_id) / "next_action.json"


def _run_history_path(ip: Path, run_id: str) -> Path:
    return _run_dir(ip, run_id) / "checkpoint_history.jsonl"


def _load_run_state(ip: Path, run_id: str | None = None) -> dict[str, Any]:
    if not run_id:
        active = _read_json_file(_active_run_path(ip))
        if isinstance(active, dict):
            run_id = str(active.get("run_id") or "")
    if not run_id:
        raise ValueError("no active OAG run; call oag.run.start first")
    state = _read_json_file(_run_state_path(ip, run_id))
    if not isinstance(state, dict):
        raise ValueError(f"missing run state: {_run_state_path(ip, run_id)}")
    return state


def _append_run_history(ip: Path, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    path = _run_history_path(ip, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": "oag_run_history_event.v1",
        "created_at": _now(),
        **event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
    return body


def _run_history(ip: Path, run_id: str) -> list[dict[str, Any]]:
    path = _run_history_path(ip, run_id)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def _save_run_state(ip: Path, state: dict[str, Any]) -> None:
    run_id = str(state.get("run_id") or "")
    if not run_id:
        raise ValueError("run state missing run_id")
    state["updated_at"] = _now()
    _write_json(_run_state_path(ip, run_id), state)
    _write_json(
        _active_run_path(ip),
        {
            "schema_version": "oag_active_run.v1",
            "ip": ip.name,
            "run_id": run_id,
            "status": str(state.get("status") or ""),
            "path": str(_run_state_path(ip, run_id).relative_to(ip)),
            "updated_at": state["updated_at"],
        },
    )
    next_action = state.get("next_action") if isinstance(state.get("next_action"), dict) else {}
    _write_json(_run_next_action_path(ip, run_id), next_action)


def _contracts_by_id(ip: Path) -> dict[str, dict[str, Any]]:
    return {str(item.get("id") or ""): item for item in _yaml_items(ip, "ontology/contracts.yaml", "contracts") if item.get("id")}


def _obligations_by_id(ip: Path) -> dict[str, dict[str, Any]]:
    return {str(item.get("id") or ""): item for item in _yaml_items(ip, "ontology/obligations.yaml", "obligations") if item.get("id")}


def _owner_for_obligation(ip: Path, obligation_id: str) -> dict[str, Any]:
    decomposition = _decomposition_doc(ip)
    for module in _module_items(decomposition):
        owned = set(_str_items(module.get("owned_obligations") or module.get("obligations")))
        if obligation_id in owned:
            return {
                "module": _module_id(module),
                "role": str(module.get("role") or ""),
                "file": str(module.get("file") or ""),
                "ownership": str(module.get("ownership") or "current_ip"),
                "edit_policy": str(module.get("edit_policy") or ""),
            }
    return {"module": "", "role": "", "file": "", "ownership": "", "edit_policy": ""}


def _contract_expected_evidence(contract: dict[str, Any]) -> list[str]:
    refs = _contract_evidence_refs(contract)
    words = " ".join(
        [
            str(contract.get("method") or ""),
            " ".join(_str_items(contract.get("evidence_kind") or contract.get("evidence_kinds"))),
            " ".join(_str_items(contract.get("evidence_schema") or contract.get("evidence_schemas"))),
            str(contract.get("pass_condition") or ""),
        ]
    ).lower()
    if "simulation" in words or "scoreboard" in words or "sim/" in words:
        refs.extend(["sim/results.xml", "sim/scoreboard_events.jsonl"])
    if "coverage" in words:
        refs.append("cov/coverage.json")
    if "lint" in words:
        refs.append("lint/dut_lint.json")
    if "rtl" in words or "compile" in words:
        refs.append("rtl/rtl_compile.json")
    if "formal" in words or "assertion" in words or "sva" in words or "proof" in words:
        refs.append("formal/formal_status.json")
    return sorted(dict.fromkeys(ref for ref in refs if ref))


def _stage_from_text(value: str) -> str:
    text = str(value or "").lower()
    checks = [
        ("signoff", ("signoff/", "sta_", "sta.", "cdc", "rdc", "reset_xprop", "release.yaml", "timing closure")),
        ("coverage", ("cov/", "coverage", "coverpoint")),
        ("formal", ("formal/", "sva", "assertion", "proof")),
        ("sim", ("sim/", "simulation", "results.xml", "scoreboard_events", "protocol_monitor")),
        ("tb", ("tb/", "testbench", "scoreboard", "stimulus")),
        ("lint", ("lint/", "lint")),
        ("rtl", ("rtl/", "list/rtl.f", "rtl_compile", "verilog", "systemverilog")),
        ("requirements", ("req/", "requirement", "requirements.yaml", "obligations.yaml", "contracts.yaml", "locked_truth")),
    ]
    for stage, needles in checks:
        if any(needle in text for needle in needles):
            return stage
    return ""


def _next_action_stage(action: dict[str, Any]) -> str:
    next_action = action.get("next_action") if isinstance(action.get("next_action"), dict) else {}
    evidence_stage = ""
    for ref in _str_items(next_action.get("required_evidence")):
        stage = _stage_from_text(ref)
        if stage and RUN_LIMIT_STAGE_ORDER[stage] > RUN_LIMIT_STAGE_ORDER.get(evidence_stage, -2):
            evidence_stage = stage
    if evidence_stage:
        return evidence_stage
    for value in (
        action.get("stage"),
        next_action.get("kind"),
        next_action.get("summary"),
        " ".join(_str_items(next_action.get("why"))),
    ):
        stage = _stage_from_text(str(value or ""))
        if stage:
            return stage
    try:
        return _normalize_run_limit(action.get("stage"), default="requirements")
    except ValueError:
        return "requirements"


def _policy_allows_action(ip: Path, action: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    limit = _hook_auto_continue_until(ip)
    action_stage = _next_action_stage(action)
    limit_order = RUN_LIMIT_STAGE_ORDER[limit]
    action_order = RUN_LIMIT_STAGE_ORDER.get(action_stage, 0)
    allowed = limit == "all" or (limit_order >= 0 and action_order <= limit_order)
    return allowed, {
        "hook_auto_continue_until": limit,
        "next_action_stage": action_stage,
        "stop_hook_max_repeats": _stop_hook_max_repeats(ip),
    }


def _run_target_row(ip: Path, arguments: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any] | None:
    matrix = _closure_matrix(ip)
    rows = [row for row in matrix.get("rows", []) if isinstance(row, dict)]
    requested = str(arguments.get("target_obligation") or arguments.get("obligation") or "").strip()
    if not requested and isinstance(state, dict):
        requested = str(state.get("active_obligation") or "").strip()
    if requested:
        for row in rows:
            if str(row.get("obligation") or "") == requested and row.get("closed") is not True:
                return row
    for row in rows:
        if row.get("closed") is not True and row.get("waived") is not True:
            return row
    return None


def _run_action_from_state(ip: Path, arguments: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    matrix = _closure_matrix(ip)
    row = _run_target_row(ip, arguments, state)
    run_id = str((state or {}).get("run_id") or arguments.get("run_id") or "")
    stage = str(arguments.get("stage") or (state or {}).get("stage") or "")
    intent = str(arguments.get("intent") or (state or {}).get("intent") or "")
    check_command = (
        "python3 .claude/scripts/oag_cli.py call --json "
        f"'{{\"tool\":\"oag.run.checkpoint\",\"arguments\":{{\"ip_dir\":\"{ip}\",\"run_id\":\"{run_id}\"}}}}'"
    )
    if row is None:
        return {
            "schema_version": "oag_run_next_action.v1",
            "ip": ip.name,
            "run_id": run_id,
            "stage": stage,
            "intent": intent,
            "status": "checkpoint_ready" if matrix.get("total") else "blocked",
            "active_obligation": "",
            "active_contracts": [],
            "owner": {},
            "next_action": {
                "kind": "checkpoint" if matrix.get("total") else "author_obligations",
                "summary": "Run oag.run.checkpoint to request a recorded completion decision."
                if matrix.get("total")
                else "Author at least one requirement, obligation, and contract before running work.",
                "why": ["closure matrix has no open obligations" if matrix.get("total") else "closure matrix has no obligations"],
                "commands": [check_command] if matrix.get("total") else [],
                "required_evidence": [],
            },
            "blockers": [] if matrix.get("total") else [{"id": "BLK_NO_OBLIGATIONS", "text": "closure matrix has no obligations"}],
            "closure_matrix": matrix,
            "stop_condition": "oag.run.checkpoint allowed=true",
            "prompt_block": "",
        }

    oid = str(row.get("obligation") or "")
    obligations = _obligations_by_id(ip)
    contracts_by_id = _contracts_by_id(ip)
    contract_ids = [str(item) for item in _as_list(row.get("contracts")) if str(item).strip()]
    contracts = [contracts_by_id[cid] for cid in contract_ids if cid in contracts_by_id]
    owner = _owner_for_obligation(ip, oid)
    evidence_refs: list[str] = []
    for contract in contracts:
        evidence_refs.extend(_contract_expected_evidence(contract))
    evidence_refs = sorted(dict.fromkeys(evidence_refs))
    missing = [ref for ref in evidence_refs if _path_like_ref(ref) and not (ip / ref).is_file()]
    evidence_strength: dict[str, Any] = {}
    if evidence_refs and not missing:
        evidence_strength = _closure_evidence_report(ip, evidence_refs)
    obligation = obligations.get(oid, {})
    blockers = []
    if not contract_ids:
        blockers.append({"id": "BLK_CONTRACT_MISSING", "text": f"{oid} has no bound contract"})
    if missing:
        blockers.append({"id": "BLK_EVIDENCE_MISSING", "text": "required evidence files are missing", "refs": missing})
    if evidence_strength and not evidence_strength.get("closure_grade"):
        blockers.append(
            {
                "id": "BLK_EVIDENCE_WEAK",
                "text": "evidence files exist but are not closure-grade",
                "issues": _as_list(evidence_strength.get("issues"))[:12],
            }
        )
    if not row.get("records"):
        blockers.append({"id": "BLK_VALIDATION_MISSING", "text": "no closed ROCEV validation record links the obligation to its contract"})

    record_command = (
        "python3 .claude/scripts/oag_cli.py call --json "
        f"'{{\"tool\":\"oag.run.record\",\"arguments\":{{\"ip_dir\":\"{ip}\",\"run_id\":\"{run_id}\","
        f"\"obligation\":\"{oid}\",\"contract\":\"{contract_ids[0] if contract_ids else ''}\"}}}}'"
    )
    summary = f"Close {oid} through explicit ROCEV evidence and validation."
    if missing:
        summary = f"Produce missing evidence for {oid}, then record a closed ROCEV validation."
    elif evidence_strength and not evidence_strength.get("closure_grade"):
        summary = f"Replace weak/static evidence for {oid} with live HDL/formal closure-grade evidence."
    commands = [record_command] if not missing and (not evidence_strength or evidence_strength.get("closure_grade")) else []
    return {
        "schema_version": "oag_run_next_action.v1",
        "ip": ip.name,
        "run_id": run_id,
        "stage": stage,
        "intent": intent,
        "status": "in_progress",
        "active_obligation": oid,
        "active_contracts": contract_ids,
        "owner": owner,
        "next_action": {
            "kind": "close_obligation" if commands else "strengthen_evidence",
            "summary": summary,
            "why": [
                str(obligation.get("text") or ""),
                f"contracts={', '.join(contract_ids) if contract_ids else 'missing'}",
                f"records={', '.join(_str_items(row.get('records'))) if row.get('records') else 'none'}",
            ],
            "commands": commands,
            "required_evidence": evidence_refs,
        },
        "blockers": blockers,
        "evidence_strength": evidence_strength,
        "closure_matrix": matrix,
        "stop_condition": "oag.run.checkpoint allowed=true",
        "prompt_block": "",
    }


def _format_run_prompt_block(action: dict[str, Any]) -> str:
    next_action = action.get("next_action") if isinstance(action.get("next_action"), dict) else {}
    blockers = action.get("blockers") if isinstance(action.get("blockers"), list) else []
    lines = [
        "=== OAG NEXT ACTION ===",
        f"ip={action.get('ip')} run_id={action.get('run_id')} status={action.get('status')}",
    ]
    if action.get("active_obligation"):
        lines.append(f"obligation={action.get('active_obligation')}")
    if action.get("active_contracts"):
        lines.append(f"contracts={', '.join(_str_items(action.get('active_contracts')))}")
    owner = action.get("owner") if isinstance(action.get("owner"), dict) else {}
    if owner:
        lines.append(f"owner_module={owner.get('module') or 'unknown'} file={owner.get('file') or 'unknown'}")
    lines.append(f"next={next_action.get('summary') or ''}")
    required = _str_items(next_action.get("required_evidence"))
    if required:
        lines.append(f"required_evidence={', '.join(required)}")
    if blockers:
        lines.append("blockers=" + "; ".join(str(item.get("text") or item.get("id") or item) for item in blockers if isinstance(item, dict)))
    commands = _str_items(next_action.get("commands"))
    if commands:
        lines.append("commands:")
        lines.extend(f"- {command}" for command in commands)
    lines.append(f"stop_condition={action.get('stop_condition')}")
    lines.append("=== END OAG NEXT ACTION ===")
    return "\n".join(lines)


def _run_start(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    run_id = _new_run_id(arguments)
    stage = str(arguments.get("stage") or "")
    intent = str(arguments.get("intent") or "")
    compile_result = _compile_graph({"ip_dir": str(ip)})
    state = {
        "schema_version": "oag_run_state.v1",
        "ip": ip.name,
        "run_id": run_id,
        "stage": stage,
        "intent": intent,
        "status": "starting",
        "created_at": _now(),
        "updated_at": _now(),
        "iteration": 0,
        "active_obligation": "",
        "active_contracts": [],
        "active_owner": {},
        "next_action": {},
        "last_checkpoint": None,
        "blocker_signature": "",
        "blocker_repeats": 0,
        "artifacts": {
            "run_state": str(_run_state_path(ip, run_id).relative_to(ip)),
            "next_action": str(_run_next_action_path(ip, run_id).relative_to(ip)),
            "checkpoint_history": str(_run_history_path(ip, run_id).relative_to(ip)),
        },
        "compile": {"status": compile_result.get("status"), "issues": compile_result.get("issues") or []},
    }
    action = _run_action_from_state(ip, arguments, state)
    action["prompt_block"] = _format_run_prompt_block(action)
    state["status"] = str(action.get("status") or "in_progress")
    state["active_obligation"] = str(action.get("active_obligation") or "")
    state["active_contracts"] = action.get("active_contracts") if isinstance(action.get("active_contracts"), list) else []
    state["active_owner"] = action.get("owner") if isinstance(action.get("owner"), dict) else {}
    state["next_action"] = action
    _save_run_state(ip, state)
    _append_run_history(ip, run_id, {"event": "start", "status": state["status"], "next_action": action})
    actor = _run_actor(arguments, surface="oag.run.start")
    ledger_event = _append_ledger(
        ip,
        action="run_start",
        actor=actor,
        subject=run_id,
        payload={
            "run_id": run_id,
            "stage": stage,
            "intent": intent,
            "state": str(_run_state_path(ip, run_id).relative_to(ip)),
            "next_action": action,
        },
    )
    return {
        "schema_version": "oag_run_start.v1",
        "ip": ip.name,
        "run_id": run_id,
        "status": state["status"],
        "state_path": str(_run_state_path(ip, run_id)),
        "next_action_path": str(_run_next_action_path(ip, run_id)),
        "history_path": str(_run_history_path(ip, run_id)),
        "next_action": action,
        "ledger_event": ledger_event["event_hash"],
    }


def _run_next(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    state = _load_run_state(ip, str(arguments.get("run_id") or ""))
    status = str(state.get("status") or "")
    if status in TERMINAL_RUN_STATUSES:
        action = state.get("next_action") if isinstance(state.get("next_action"), dict) else {}
        reason_by_status = {
            "complete": "run_complete",
            "parked": "run_parked",
            "needs_human": "needs_human_decision",
        }
        return {
            "schema_version": "oag_run_next.v1",
            "ip": ip.name,
            "run_id": state["run_id"],
            "status": status,
            "state_path": str(_run_state_path(ip, str(state["run_id"]))),
            "next_action_path": str(_run_next_action_path(ip, str(state["run_id"]))),
            "next_action": action,
            "prompt_block": "" if status == "complete" else str(action.get("prompt_block") or ""),
            "terminal": True,
            "reason": reason_by_status.get(status, "run_terminal"),
        }
    action_args = {**state, **arguments, "run_id": state["run_id"]}
    action = _run_action_from_state(ip, action_args, state)
    action["prompt_block"] = _format_run_prompt_block(action)
    state["iteration"] = int(state.get("iteration") or 0) + 1
    state["status"] = str(action.get("status") or "in_progress")
    state["active_obligation"] = str(action.get("active_obligation") or "")
    state["active_contracts"] = action.get("active_contracts") if isinstance(action.get("active_contracts"), list) else []
    state["active_owner"] = action.get("owner") if isinstance(action.get("owner"), dict) else {}
    state["next_action"] = action
    _save_run_state(ip, state)
    _append_run_history(ip, str(state["run_id"]), {"event": "next", "status": state["status"], "next_action": action})
    return {
        "schema_version": "oag_run_next.v1",
        "ip": ip.name,
        "run_id": state["run_id"],
        "status": state["status"],
        "state_path": str(_run_state_path(ip, str(state["run_id"]))),
        "next_action_path": str(_run_next_action_path(ip, str(state["run_id"]))),
        "next_action": action,
        "prompt_block": action["prompt_block"],
    }


def _run_record(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    state = _load_run_state(ip, str(arguments.get("run_id") or ""))
    obligation = str(arguments.get("obligation") or state.get("active_obligation") or "")
    contracts = _str_items(arguments.get("contract") or arguments.get("contracts") or state.get("active_contracts"))
    contract = contracts[0] if contracts else ""
    evidence_files = _str_items(arguments.get("evidence_files") or arguments.get("files"))
    evidence_tests = _str_items(arguments.get("evidence_tests") or arguments.get("tests"))
    rocev_arg = arguments.get("rocev") if isinstance(arguments.get("rocev"), dict) else {}
    rocev_evidence = rocev_arg.get("evidence") if isinstance(rocev_arg.get("evidence"), dict) else {}
    if not evidence_files and rocev_evidence:
        evidence_files = _str_items(rocev_evidence.get("files"))
    if not evidence_tests and rocev_evidence:
        evidence_tests = _str_items(rocev_evidence.get("tests"))
    if not evidence_files:
        action = state.get("next_action") if isinstance(state.get("next_action"), dict) else {}
        next_action = action.get("next_action") if isinstance(action.get("next_action"), dict) else {}
        evidence_files = [ref for ref in _str_items(next_action.get("required_evidence")) if _path_like_ref(ref) and (ip / ref).exists()]
    verdict = str(arguments.get("verdict") or "pass")
    status = _normal_status(arguments.get("status") or "closed")
    summary = str(arguments.get("summary") or f"{obligation} evidence recorded through OAG run loop")
    commit = str(arguments.get("commit") or "")
    if (
        not isinstance(arguments.get("rocev"), dict)
        and status in CLOSED_STATUSES
        and not evidence_files
        and not evidence_tests
        and not commit
    ):
        raise ValueError("oag.run.record closed status requires evidence_files, evidence_tests, commit, or an explicit rocev object")
    if status in CLOSED_STATUSES:
        evidence_strength = _closure_evidence_report(ip, evidence_files)
        if not evidence_strength.get("closure_grade"):
            joined = "; ".join(_str_items(evidence_strength.get("issues"))[:8])
            raise ValueError(f"oag.run.record cannot close weak evidence: {joined}")
    record_response = _record(
        {
            "ip_dir": str(ip),
            "stage": str(arguments.get("stage") or state.get("stage") or ""),
            "type": str(arguments.get("type") or "run_evidence"),
            "claim": str(arguments.get("claim") or f"{obligation} closure evidence"),
            "summary": summary,
            "actor": arguments.get("actor") if isinstance(arguments.get("actor"), dict) else _run_actor(arguments, surface="oag.run.record"),
            "status": status,
            "rocev": arguments.get("rocev")
            if isinstance(arguments.get("rocev"), dict)
            else {
                "obligation": {"id": obligation, "status": status},
                "contract": {"id": contract, "status": status},
                "evidence": {"files": evidence_files, "tests": evidence_tests, "commit": commit},
                "validation": {"status": status, "verdict": verdict, "rationale": summary},
            },
        }
    )
    action_args = {**state, **arguments, "run_id": state["run_id"]}
    action = _run_action_from_state(ip, action_args, state)
    action["prompt_block"] = _format_run_prompt_block(action)
    state["status"] = str(action.get("status") or "in_progress")
    state["active_obligation"] = str(action.get("active_obligation") or "")
    state["active_contracts"] = action.get("active_contracts") if isinstance(action.get("active_contracts"), list) else []
    state["active_owner"] = action.get("owner") if isinstance(action.get("owner"), dict) else {}
    state["next_action"] = action
    _save_run_state(ip, state)
    _append_run_history(
        ip,
        str(state["run_id"]),
        {
            "event": "record",
            "status": state["status"],
            "record": record_response["id"],
            "obligation": obligation,
            "contract": contract,
            "next_action": action,
        },
    )
    return {
        "schema_version": "oag_run_record.v1",
        "ip": ip.name,
        "run_id": state["run_id"],
        "status": state["status"],
        "record": record_response,
        "next_action": action,
        "prompt_block": action["prompt_block"],
    }


def _checkpoint_signature(decision: dict[str, Any], action: dict[str, Any]) -> str:
    check = decision.get("check") if isinstance(decision.get("check"), dict) else {}
    payload = {
        "allowed": decision.get("allowed"),
        "reason": decision.get("reason"),
        "check_issues": check.get("issues") or [],
        "active_obligation": action.get("active_obligation"),
        "blockers": action.get("blockers") or [],
    }
    return _hash_value(payload)[:16]


def _run_checkpoint(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    state = _load_run_state(ip, str(arguments.get("run_id") or ""))
    _compile_graph({"ip_dir": str(ip)})
    decision = _decide(
        {
            "ip_dir": str(ip),
            "stage": str(arguments.get("stage") or state.get("stage") or ""),
            "intent": str(arguments.get("intent") or state.get("intent") or ""),
            "action": str(arguments.get("action") or "claim_complete"),
            "record_decision": arguments.get("record_decision", True),
            "actor": arguments.get("actor") if isinstance(arguments.get("actor"), dict) else _run_actor(arguments, surface="oag.run.checkpoint"),
        }
    )
    action_args = {**state, **arguments, "run_id": state["run_id"]}
    action = _run_action_from_state(ip, action_args, state)
    action["prompt_block"] = _format_run_prompt_block(action)
    signature = _checkpoint_signature(decision, action)
    history = _run_history(ip, str(state["run_id"]))
    repeats = 1
    for event in reversed(history):
        if str(event.get("blocker_signature") or "") == signature:
            repeats += 1
        elif event.get("event") == "checkpoint":
            break
    max_repeats = int(arguments.get("max_blocker_repeats") or _stop_hook_max_repeats(ip))
    if decision.get("allowed") is True:
        run_status = "complete"
    elif repeats >= max_repeats:
        run_status = "needs_human"
    else:
        run_status = "in_progress"
    state["status"] = run_status
    state["last_checkpoint"] = {
        "allowed": bool(decision.get("allowed")),
        "reason": str(decision.get("reason") or ""),
        "decision_receipt": decision.get("decision_receipt"),
        "created_at": _now(),
    }
    state["blocker_signature"] = "" if decision.get("allowed") is True else signature
    state["blocker_repeats"] = 0 if decision.get("allowed") is True else repeats
    state["next_action"] = action
    _save_run_state(ip, state)
    event = _append_run_history(
        ip,
        str(state["run_id"]),
        {
            "event": "checkpoint",
            "status": run_status,
            "allowed": bool(decision.get("allowed")),
            "reason": str(decision.get("reason") or ""),
            "blocker_signature": state["blocker_signature"],
            "blocker_repeats": state["blocker_repeats"],
            "decision_receipt": decision.get("decision_receipt"),
            "next_action": action,
        },
    )
    return {
        "schema_version": "oag_run_checkpoint.v1",
        "ip": ip.name,
        "run_id": state["run_id"],
        "status": run_status,
        "allowed": bool(decision.get("allowed")),
        "reason": str(decision.get("reason") or ""),
        "blocker_repeats": state["blocker_repeats"],
        "needs_human": run_status == "needs_human",
        "decision": decision,
        "history_event": event,
        "next_action": action,
        "prompt_block": action["prompt_block"],
    }


def _stop_check(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    try:
        state = _load_run_state(ip, str(arguments.get("run_id") or ""))
    except ValueError as exc:
        return {
            "schema_version": "oag_stop_check.v1",
            "ip": ip.name,
            "should_continue": False,
            "reason": str(exc),
            "prompt_block": "",
        }
    status = str(state.get("status") or "")
    if status in {"complete", "parked"}:
        return {
            "schema_version": "oag_stop_check.v1",
            "ip": ip.name,
            "run_id": state.get("run_id"),
            "should_continue": False,
            "reason": "run_parked" if status == "parked" else "run_complete",
            "prompt_block": "",
            "policy": {
                "hook_auto_continue_until": _hook_auto_continue_until(ip),
                "stop_hook_max_repeats": _stop_hook_max_repeats(ip),
            },
        }
    if status == "needs_human":
        action = state.get("next_action") if isinstance(state.get("next_action"), dict) else {}
        prompt = _format_run_prompt_block(action)
        prompt += "\nOAG is blocked after repeated checkpoints; ask the human owner before continuing."
        return {
            "schema_version": "oag_stop_check.v1",
            "ip": ip.name,
            "run_id": state.get("run_id"),
            "should_continue": False,
            "reason": "needs_human_decision",
            "prompt_block": prompt,
            "policy": {
                "hook_auto_continue_until": _hook_auto_continue_until(ip),
                "stop_hook_max_repeats": _stop_hook_max_repeats(ip),
            },
        }
    stored_action = state.get("next_action") if isinstance(state.get("next_action"), dict) else {}
    if stored_action:
        allowed, policy = _policy_allows_action(ip, stored_action)
        if not allowed:
            return {
                "schema_version": "oag_stop_check.v1",
                "ip": ip.name,
                "run_id": state.get("run_id"),
                "should_continue": False,
                "reason": "policy_limit_reached",
                "next_action": stored_action,
                "prompt_block": "",
                "policy": policy,
            }
    next_response = _run_next({**arguments, "ip_dir": str(ip), "run_id": str(state.get("run_id") or "")})
    next_action = next_response.get("next_action") if isinstance(next_response.get("next_action"), dict) else {}
    allowed, policy = _policy_allows_action(ip, next_action)
    if not allowed:
        return {
            "schema_version": "oag_stop_check.v1",
            "ip": ip.name,
            "run_id": state.get("run_id"),
            "should_continue": False,
            "reason": "policy_limit_reached",
            "next_action": next_action,
            "prompt_block": "",
            "policy": policy,
        }
    return {
        "schema_version": "oag_stop_check.v1",
        "ip": ip.name,
        "run_id": state.get("run_id"),
        "should_continue": True,
        "reason": "run_incomplete",
        "next_action": next_action,
        "prompt_block": next_response.get("prompt_block") or "",
        "policy": policy,
    }


def _configure(arguments: dict[str, Any]) -> dict[str, Any]:
    ip = _ip_dir(arguments)
    _ensure_knowledge(ip)
    policies_path = oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml")
    policies = _policy_doc(ip)
    if not policies:
        policies = {"schema": "oag_policy.v1", "ip": ip.name}
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {}
    actor = {
        "kind": str(actor.get("kind") or "ai"),
        "id": str(actor.get("id") or os.environ.get("USER") or "unknown"),
        "surface": str(actor.get("surface") or "claude-plugin"),
    }
    requested_limit = (
        arguments.get("hook_auto_continue_until")
        or arguments.get("auto_continue_until")
        or arguments.get("until")
        or arguments.get("stage_limit")
    )
    updates: dict[str, Any] = {}
    changed: dict[str, Any] = {}
    execution = policies.get("execution_policy") if isinstance(policies.get("execution_policy"), dict) else {}
    execution = dict(execution)
    if requested_limit is not None:
        old = execution.get("hook_auto_continue_until")
        execution["hook_auto_continue_until"] = _normalize_run_limit(requested_limit, default="all")
        updates["hook_auto_continue_until"] = execution["hook_auto_continue_until"]
        if old != execution["hook_auto_continue_until"]:
            changed["hook_auto_continue_until"] = execution["hook_auto_continue_until"]
    if "stop_hook_max_repeats" in arguments:
        old = execution.get("stop_hook_max_repeats")
        execution["stop_hook_max_repeats"] = max(int(arguments.get("stop_hook_max_repeats") or 0), 0)
        updates["stop_hook_max_repeats"] = execution["stop_hook_max_repeats"]
        if old != execution["stop_hook_max_repeats"]:
            changed["stop_hook_max_repeats"] = execution["stop_hook_max_repeats"]
    if execution:
        policies["execution_policy"] = execution

    graph = policies.get("graph_policy") if isinstance(policies.get("graph_policy"), dict) else {}
    graph = dict(graph)
    for key in ("context_uses_cached_graph", "compile_skip_when_fresh"):
        if key in arguments:
            old = graph.get(key)
            graph[key] = _truthy_policy(arguments.get(key), default=True)
            updates[key] = graph[key]
            if old != graph[key]:
                changed[key] = graph[key]
    if "strict_fresh_on" in arguments:
        old = graph.get("strict_fresh_on")
        graph["strict_fresh_on"] = _str_items(arguments.get("strict_fresh_on"))
        updates["strict_fresh_on"] = graph["strict_fresh_on"]
        if old != graph["strict_fresh_on"]:
            changed["strict_fresh_on"] = graph["strict_fresh_on"]
    if graph:
        policies["graph_policy"] = graph

    if not updates:
        raise ValueError("no configurable policy fields were provided")
    if not changed:
        return {
            "schema_version": "oag_configure.v1",
            "ip": ip.name,
            "path": str(policies_path),
            "updates": updates,
            "changed": False,
            "execution_policy": policies.get("execution_policy") if isinstance(policies.get("execution_policy"), dict) else {},
            "graph_policy": policies.get("graph_policy") if isinstance(policies.get("graph_policy"), dict) else {},
            "ledger_event": "",
        }
    ledger_payload = {
        "path": _logical_rel_to_ip(ip, policies_path),
        "updates": changed,
        "approval": arguments.get("approval") if isinstance(arguments.get("approval"), dict) else {},
    }
    if not _is_human_approved({"action": "policy_configure", "actor": actor, "payload": ledger_payload}):
        raise ValueError("oag.configure changes protected ontology/policies.yaml and requires a human actor or approval")
    _write_yaml_file(policies_path, policies)
    ledger_event = _append_ledger(
        ip,
        action="policy_configure",
        actor=actor,
        subject=_logical_rel_to_ip(ip, policies_path),
        payload=ledger_payload,
    )
    return {
        "schema_version": "oag_configure.v1",
        "ip": ip.name,
        "path": str(policies_path),
        "updates": changed,
        "changed": True,
        "execution_policy": policies.get("execution_policy") if isinstance(policies.get("execution_policy"), dict) else {},
        "graph_policy": policies.get("graph_policy") if isinstance(policies.get("graph_policy"), dict) else {},
        "ledger_event": ledger_event.get("event_hash"),
    }


def dispatch_call(envelope: dict[str, Any]) -> dict[str, Any]:
    tool = _tool_name(str(envelope.get("tool") or envelope.get("name") or ""))
    arguments = envelope.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    handlers = {
        "scaffold": _scaffold,
        "inspect": _inspect,
        "init": lambda args: _ensure_knowledge(_ip_dir(args)),
        "check": _check,
        "compile": _compile_graph,
        "configure": _configure,
        "context": _context,
        "record": _record,
        "draft": _draft,
        "lock": _scope_lock,
        "unlock": _scope_unlock,
        "lock_status": lambda args: _scope_lock_status(_ip_dir(args)),
        "review": _review,
        "decide": _decide,
        "metrics": _metrics_snapshot,
        "handoff": _handoff_snapshot,
        "ticket": _ticket,
        "run.start": _run_start,
        "run.next": _run_next,
        "run.record": _run_record,
        "run.checkpoint": _run_checkpoint,
        "stop_check": _stop_check,
    }
    if tool == "backlog":
        return _response(tool, True, {"schema_version": "oag_backlog.v1", "records": [], "count": 0})
    if tool not in handlers:
        raise ValueError(f"unknown OAG tool: {tool}")
    return _response(tool, True, handlers[tool](arguments))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    call = sub.add_parser("call")
    call.add_argument("tool", nargs="?")
    call.add_argument("--json", default="")
    call.add_argument("--file", default="")
    args = parser.parse_args(argv)
    try:
        payload = _read_json(args)
        response = dispatch_call(payload)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if response.get("ok") else 1
    except Exception as exc:
        print(json.dumps(_response(getattr(args, "tool", "") or "", False, None, [str(exc)]), ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
