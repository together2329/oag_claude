#!/usr/bin/env python3
"""Smoke test for the .claude ontology IP agent pack."""

from __future__ import annotations

import json
import os
import hashlib
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
OAG = ROOT / "scripts" / "oag_cli.py"
GRAPH = ROOT / "scripts" / "oag_graph.py"
MIGRATE_LAYOUT = ROOT / "scripts" / "oag_migrate_layout.py"
PORTABLE_DB = ROOT / "scripts" / "oag_portable_db.py"
OKF = ROOT / "scripts" / "oag_okf.py"
EVAL = ROOT / "scripts" / "oag_eval.py"
ANSWER_KEY_EVAL = ROOT / "scripts" / "oag_answer_key_eval.py"
DEV_VALIDATOR = ROOT / "scripts" / "oag_dev_validator.py"
SPEC_RTL_LOOP = ROOT / "scripts" / "oag_spec_to_rtl_loop.py"
EXEC_AUTO_RESEARCH = ROOT / "scripts" / "oag_exec_auto_research.py"
DISPATCH = ROOT / "scripts" / "oag_dispatch.py"
WAVEFRONT = ROOT / "scripts" / "oag_wavefront.py"
MAIN_WRITE_GATE = ROOT / "scripts" / "oag_main_write_gate.py"
VALIDATE_JSON = ROOT / "scripts" / "oag_validate_json.py"
AGENT_CATALOG_CHECK = ROOT / "scripts" / "oag_agent_catalog_check.py"
CODEX_CONFIG_DOCTOR = ROOT / "scripts" / "oag_claude_config_doctor.py"
CLOSURE_CHECK = ROOT / "scripts" / "oag_closure_check.py"
PACK_RELEASE_CHECK = ROOT / "scripts" / "oag_pack_release_check.py"
DOMAIN_CROSSING_CHECK = ROOT / "scripts" / "oag_domain_crossing_check.py"
PPA_CHECK = ROOT / "scripts" / "oag_ppa_check.py"
OAG_PATHS = ROOT / "scripts" / "oag_paths.py"
PYSLANG_LINT = ROOT / "scripts" / "oag_pyslang_lint.py"
REQ_QUALITY_CHECK = ROOT / "scripts" / "oag_req_quality_check.py"
LOCK_READINESS_CHECK = ROOT / "scripts" / "oag_lock_readiness_check.py"
CONTRACT_STRENGTH_CHECK = ROOT / "scripts" / "oag_contract_strength_check.py"
AUTHORING_PACKET_CHECK = ROOT / "scripts" / "oag_authoring_packet_check.py"
TRACE_GRAPH_CHECK = ROOT / "scripts" / "oag_trace_graph_check.py"
DEEP_SEMANTIC_INTAKE = ROOT / "scripts" / "oag_deep_semantic_intake.py"
DECISION_MATRIX_GENERATE = ROOT / "scripts" / "oag_decision_matrix_generate.py"
LIFECYCLE_CHECK = ROOT / "scripts" / "oag_lifecycle_check.py"
BASELINE_CHECK = ROOT / "scripts" / "oag_baseline_check.py"
STALE_CHECK = ROOT / "scripts" / "oag_stale_check.py"
BASELINE_CUT = ROOT / "scripts" / "oag_baseline_cut.py"
BASELINE_VERIFY = ROOT / "scripts" / "oag_baseline_verify.py"
IP_VERSION_CHECK = ROOT / "scripts" / "oag_ip_version_check.py"
AGENT_CATALOG = ROOT / "oag" / "agent-catalog.toml"
OAG_MODE_DIRECTIVE = ROOT / "oag" / "oag-mode-directive.md"
SUBAGENT_WORKFLOWS = ROOT / "oag" / "subagent-workflows.md"
OAG_RULE_INDEX = ROOT / "rules" / "oag-rule-index.yaml"
OAG_IP_WORKFLOW_SKILL = ROOT / "skills" / "oag-ip-workflow" / "SKILL.md"
OAG_DEEP_SEMANTIC_SKILL = ROOT / "skills" / "oag-deep-semantic-intake" / "SKILL.md"
OAG_DECISION_MATRIX_SKILL = ROOT / "skills" / "oag-decision-matrix" / "SKILL.md"
OAG_CONTRACT_PROJECTION_SKILL = ROOT / "skills" / "oag-contract-projection" / "SKILL.md"
OAG_AUTHORING_PACKET_SKILL = ROOT / "skills" / "oag-authoring-packet" / "SKILL.md"
OAG_EVIDENCE_CLOSURE_SKILL = ROOT / "skills" / "oag-evidence-closure" / "SKILL.md"
OAG_WAVEFRONT_SKILL = ROOT / "skills" / "oag-wavefront" / "SKILL.md"
OAG_WAVEFRONT_TEMPLATE = ROOT / "oag" / "wavefront-templates" / "tb_common_then_scenario_fanout.yaml"
OAG_DATA_LIFECYCLE_POLICY = ROOT / "oag" / "data-lifecycle-policy.md"
OAG_BASELINE_GIT_POLICY = ROOT / "oag" / "baseline-git-policy.md"
OAG_IP_VERSIONING_POLICY = ROOT / "oag" / "ip-versioning-policy.md"
OAG_IP_VERSIONING_SKILL = ROOT / "skills" / "oag-ip-versioning" / "SKILL.md"
OAG_IP_VERSIONING_RULES = ROOT / "rules" / "oag-ip-versioning.rules.md"
STOP_GATE = ROOT / "hooks" / "claude_stop_gate.py"
SUBAGENT_START = ROOT / "hooks" / "claude_subagent_oag_start.py"
SUBAGENT_GATE = ROOT / "hooks" / "claude_subagent_oag_gate.py"
OAG_MODE_TRIGGER = ROOT / "hooks" / "claude_oag_mode_trigger.py"
NATIVE_SUBAGENT_GUARD = ROOT / "hooks" / "claude_native_subagent_guard.py"
OAG_SESSION_START = ROOT / "hooks" / "claude_oag_session_start.py"
CONTEXT_HOOK = ROOT / "hooks" / "claude_context_inject.py"
DRAFT_HOOK = ROOT / "hooks" / "claude_draft_pressure.py"
HOOKS_JSON = ROOT / "hooks.json"
SCHEMA_FILES = [
    ROOT / "schemas" / "oag_dispatch.schema.json",
    ROOT / "schemas" / "oag_subagent_receipt.schema.json",
    ROOT / "schemas" / "oag_validation_report.schema.json",
    ROOT / "schemas" / "oag_gate_decision.schema.json",
    ROOT / "schemas" / "oag_closure_report.schema.json",
    ROOT / "schemas" / "oag_scope_lock.schema.json",
    ROOT / "schemas" / "oag_source_claims.schema.json",
    ROOT / "schemas" / "oag_ambiguity_register.schema.json",
    ROOT / "schemas" / "oag_requirement_atom.schema.json",
    ROOT / "schemas" / "oag_decision_matrix.schema.json",
    ROOT / "schemas" / "oag_verification_plan.schema.json",
    ROOT / "schemas" / "oag_contract_v2.schema.json",
    ROOT / "schemas" / "oag_rtl_authoring_packet.schema.json",
    ROOT / "schemas" / "oag_tb_authoring_packet.schema.json",
    ROOT / "schemas" / "oag_wavefront_task_graph.schema.json",
    ROOT / "schemas" / "oag_ownership_locks.schema.json",
    ROOT / "schemas" / "oag_wavefront_event.schema.json",
    ROOT / "schemas" / "oag_artifact_lifecycle.schema.json",
    ROOT / "schemas" / "oag_baseline_manifest.schema.json",
    ROOT / "schemas" / "oag_ip_version.schema.json",
]

OAG_CALL_TIMEOUT_SECONDS = 180


def call(payload: dict) -> dict:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    try:
        proc = subprocess.run(
            [sys.executable, str(OAG), "call", "--json", json.dumps(payload)],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            env=env,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"oag_cli call timed out after {OAG_CALL_TIMEOUT_SECONDS}s: {payload}") from exc
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def call_process(payload: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(OAG), "call", "--json", json.dumps(payload)],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_dev_validator(ip: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [
            sys.executable,
            str(DEV_VALIDATOR),
            "--ip-dir",
            str(ip),
            "--stage",
            "sim",
            "--intent",
            "smoke development validator",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_spec_to_rtl_loop(ip: Path, spec: Path, *, metrics: bool = False) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    command = [
        sys.executable,
        str(SPEC_RTL_LOOP),
        "--ip-dir",
        str(ip),
        "--spec",
        str(spec),
        "--stage",
        "sim",
        "--intent",
        "smoke spec-to-RTL loop",
        "--write-static-summary",
        "--json",
    ]
    if metrics:
        command.append("--metrics")
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
    )


def run_dispatch(*args: str, project_root: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    if project_root:
        env["OAG_PROJECT_ROOT"] = str(project_root)
    return subprocess.run(
        [sys.executable, str(DISPATCH), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=project_root or ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_wavefront(*args: str, project_root: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    if project_root:
        env["OAG_PROJECT_ROOT"] = str(project_root)
    return subprocess.run(
        [sys.executable, str(WAVEFRONT), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=project_root or ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_lifecycle_check(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(LIFECYCLE_CHECK), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def test_oag_paths_resolver(tmp_root: Path) -> None:
    assert OAG_PATHS.is_file(), OAG_PATHS

    spec = importlib.util.spec_from_file_location("oag_paths_smoke", OAG_PATHS)
    assert spec and spec.loader, spec
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    legacy_ip = tmp_root / "paths_legacy"
    legacy_root = legacy_ip.resolve()
    (legacy_ip / "ontology" / "generated").mkdir(parents=True)
    (legacy_ip / "knowledge").mkdir(parents=True)
    (legacy_ip / "ontology" / "contracts.yaml").write_text("contracts: []\n", encoding="utf-8")

    assert module.state_path(legacy_ip, "knowledge/ledger.jsonl") == legacy_root / "knowledge" / "ledger.jsonl"
    assert module.legacy_or_hidden(legacy_ip, "ontology/contracts.yaml") == legacy_root / "ontology" / "contracts.yaml"
    assert module.generated_path(legacy_ip, "authoring_packets/rtl__demo.json") == legacy_root / "ontology" / "generated" / "authoring_packets" / "rtl__demo.json"

    # anti-escape / normalization guard contract (the security core of the resolver).
    def _expect_value_error(rel: str) -> None:
        try:
            module.state_path(legacy_ip, rel)
        except ValueError:
            return
        raise AssertionError(f"expected ValueError for rel={rel!r}")

    for bad in ("/abs/path", "../escape", "a/../b", "", ".", ".oag"):
        _expect_value_error(bad)
    # a single '.' is normalized away (not rejected) — pin the documented subtlety.
    assert module.state_path(legacy_ip, "a/./b") == legacy_root / "a" / "b"

    # oag_root() is public but otherwise only indirectly exercised via layout_status.
    assert module.oag_root(legacy_ip) == legacy_root / ".oag"

    # prefix-stripping idempotency: the with-prefix and without-prefix forms must agree.
    assert module.ontology_path(legacy_ip, "ontology/scope_lock.json") == module.ontology_path(legacy_ip, "scope_lock.json")
    assert module.evidence_path(legacy_ip, "evidence/sim/results.xml") == module.evidence_path(legacy_ip, "sim/results.xml")
    assert module.generated_path(legacy_ip, "generated/x") == module.generated_path(legacy_ip, "x")
    assert module.generated_path(legacy_ip, "ontology/generated/x") == module.generated_path(legacy_ip, "x")

    # legacy_or_hidden write-base fallback when neither hidden nor legacy file exists (legacy layout).
    assert module.legacy_or_hidden(legacy_ip, "knowledge/missing.txt") == legacy_root / "knowledge" / "missing.txt"

    dot_ip = tmp_root / "paths_dot_oag"
    dot_root = dot_ip.resolve()
    (dot_ip / ".oag" / "ontology" / "generated").mkdir(parents=True)
    (dot_ip / ".oag" / "knowledge").mkdir(parents=True)
    (dot_ip / "ontology").mkdir(parents=True)
    (dot_ip / ".oag" / "ontology" / "contracts.yaml").write_text("contracts: hidden\n", encoding="utf-8")
    (dot_ip / "ontology" / "contracts.yaml").write_text("contracts: legacy\n", encoding="utf-8")

    assert module.state_path(dot_ip, "knowledge/ledger.jsonl") == dot_root / ".oag" / "knowledge" / "ledger.jsonl"
    assert module.legacy_or_hidden(dot_ip, "ontology/contracts.yaml") == dot_root / ".oag" / "ontology" / "contracts.yaml"
    assert module.ontology_path(dot_ip, "scope_lock.json") == dot_root / ".oag" / "ontology" / "scope_lock.json"
    assert module.evidence_path(dot_ip, "sim/results.xml") == dot_root / ".oag" / "evidence" / "sim" / "results.xml"
    # fallback for a not-yet-existing file must resolve under .oag in the dot layout.
    assert module.legacy_or_hidden(dot_ip, "knowledge/missing.txt") == dot_root / ".oag" / "knowledge" / "missing.txt"

    legacy_cli = subprocess.run(
        [sys.executable, str(OAG_PATHS), "--ip-dir", str(legacy_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )
    assert legacy_cli.returncode == 0, legacy_cli.stderr or legacy_cli.stdout
    legacy_result = json.loads(legacy_cli.stdout)
    assert legacy_result["layout"] == "legacy", legacy_result
    assert legacy_result["warnings"] == [], legacy_result
    # lock the layout_status output, not just the layout label.
    assert legacy_result["write_base"] == str(legacy_root), legacy_result
    assert legacy_result["hidden_state"] == [], legacy_result
    assert "knowledge" in legacy_result["legacy_state"] and "ontology" in legacy_result["legacy_state"], legacy_result

    dot_cli = subprocess.run(
        [sys.executable, str(OAG_PATHS), "--ip-dir", str(dot_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )
    assert dot_cli.returncode == 0, dot_cli.stderr or dot_cli.stdout
    dot_result = json.loads(dot_cli.stdout)
    assert dot_result["layout"] == "dot_oag", dot_result
    assert dot_result["warnings"] == ["mixed_layout: .oag exists with legacy top-level OAG state"], dot_result
    # the dot layout must report .oag as the write base and surface hidden state.
    assert dot_result["write_base"] == str(dot_root / ".oag"), dot_result
    assert "knowledge" in dot_result["hidden_state"] and "ontology" in dot_result["hidden_state"], dot_result
    assert dot_result["legacy_state"] == ["ontology"], dot_result


def migrate_ip_to_dot_oag(ip: Path) -> None:
    """Relocate ontology/ and knowledge/ under <ip>/.oag/ to emulate a migrated layout."""
    hidden = ip / ".oag"
    hidden.mkdir(exist_ok=True)
    for sub in ("ontology", "knowledge"):
        src = ip / sub
        if src.exists():
            src.rename(hidden / sub)


def _req_quality_json(ip: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(REQ_QUALITY_CHECK), "--ip-dir", str(ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )
    return {"rc": proc.returncode, "data": json.loads(proc.stdout) if proc.stdout.strip() else {}}


def _run_check_script(script: Path, ip: Path, *extra: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(script), "--ip-dir", str(ip), *extra, "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )
    try:
        status = str(json.loads(proc.stdout).get("status", ""))
    except Exception:
        status = ""
    return proc.returncode, status


def _graph_build_rc(ip: Path, out: Path) -> int:
    return subprocess.run(
        [sys.executable, str(GRAPH), "build", "--ip-dir", str(ip), "--json-out", str(out)],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    ).returncode


def test_dot_oag_layout_state_scripts(tmp_root: Path) -> None:
    """Wave 2 layout transparency: IP-state scripts must behave identically whether
    ontology/ and knowledge/ live at the legacy top level or under <ip>/.oag/.

    Builds a full locked IP (legacy), captures baseline behavior, relocates
    ontology/ + knowledge/ under .oag/, and asserts resolver-routed scripts read
    and write the hidden state with no behavior change. Before Wave 2 conversion
    this fails because scripts hard-code <ip>/ontology and <ip>/knowledge.
    """
    ip = make_ip(tmp_root / "dot_oag_state")

    # Baseline on the legacy layout (assert layout transparency, not closure completeness).
    legacy_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"]
    legacy_ok = legacy_check["ok"]
    legacy_issue_set = sorted(legacy_check.get("issues", []))
    legacy_rq = _req_quality_json(ip)
    legacy_checks = {
        "lock_readiness": _run_check_script(LOCK_READINESS_CHECK, ip),
        "stale": _run_check_script(STALE_CHECK, ip),
    }
    legacy_graph_rc = _graph_build_rc(ip, tmp_root / "graph_legacy.json")

    # Relocate ontology/ + knowledge/ under .oag/.
    migrate_ip_to_dot_oag(ip)
    assert not (ip / "ontology").exists(), "legacy ontology/ should be relocated"
    assert not (ip / "knowledge").exists(), "legacy knowledge/ should be relocated"
    assert (ip / ".oag" / "ontology" / "scope_lock.json").is_file(), "ontology under .oag"
    assert (ip / ".oag" / "knowledge" / "ledger.jsonl").is_file(), "knowledge under .oag"

    # oag.check must produce the SAME verdict + issues under .oag; no missing-state issues (the Wave 2 RED gap).
    dot_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"]
    dot_issues = dot_check.get("issues", [])
    assert dot_check["ok"] == legacy_ok, (legacy_check, dot_check)
    assert sorted(dot_issues) == legacy_issue_set, (legacy_issue_set, dot_issues)
    for needle in ("missing knowledge directory", "missing records directory", "missing index", "missing ontology"):
        assert not any(needle in issue for issue in dot_issues), (needle, dot_issues)

    # req_quality must match legacy status and requirement count across layouts.
    dot_rq = _req_quality_json(ip)
    assert dot_rq["rc"] == legacy_rq["rc"], (legacy_rq, dot_rq)
    assert dot_rq["data"].get("status") == legacy_rq["data"].get("status"), (legacy_rq, dot_rq)
    assert dot_rq["data"].get("counts", {}).get("requirements") == legacy_rq["data"].get("counts", {}).get("requirements"), (legacy_rq, dot_rq)

    # Standalone checkers (incl. requirement_atom + verification_plan via lock_readiness) match across layouts.
    for name, const in (("lock_readiness", LOCK_READINESS_CHECK), ("stale", STALE_CHECK)):
        assert _run_check_script(const, ip) == legacy_checks[name], (name, legacy_checks[name], _run_check_script(const, ip))

    # graph build must read ontology/knowledge under .oag with the same outcome as legacy.
    dot_graph_rc = _graph_build_rc(ip, tmp_root / "graph_dot.json")
    assert dot_graph_rc == legacy_graph_rc, (legacy_graph_rc, dot_graph_rc)

    # oag.inspect must read hidden ontology state.
    inspected = call({"tool": "oag.inspect", "arguments": {"ip_dir": str(ip), "stage": "rtl", "intent": "dot-oag layout inspect"}})
    assert inspected.get("result"), inspected

    # A new ROCEV record must append into .oag/knowledge and keep the ledger chain valid.
    recorded = call(
        {
            "tool": "oag.record",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "claim": "dot-oag layout ledger append",
                "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                "rocev": {
                    "obligation": {"id": "OBL_DOT_OAG_LEDGER", "text": "ledger append under .oag", "status": "open"},
                    "contract": {"id": "CONTRACT_DOT_OAG_LEDGER", "method": "scoreboard"},
                    "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                    "validation": {"status": "open", "verdict": "pending", "rationale": "layout transparency"},
                },
            },
        }
    )
    assert recorded["result"].get("ledger_event"), recorded
    assert (ip / ".oag" / "knowledge" / "ledger.jsonl").is_file(), recorded
    assert not (ip / "knowledge").exists(), "record must not recreate legacy knowledge/"

    # Ledger integrity (hash chain + protected snapshot) must hold under .oag.
    post_issues = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"].get("issues", [])
    for bad in ("mismatch", "missing knowledge", "missing records", "missing ontology", "missing index", "protected fields changed"):
        assert not any(bad in issue.lower() for issue in post_issues), (bad, post_issues)


def test_dot_oag_scaffold_layout(tmp_root: Path) -> None:
    """Wave 3: oag.scaffold with layout=dot_oag creates ontology/ and knowledge/
    under <ip>/.oag/ while human-facing dirs stay top-level, and IP-state scripts
    operate on the freshly scaffolded hidden state via the resolver."""
    ip = tmp_root / "dot_oag_scaffold"
    res = call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(ip), "owner": "smoke", "layout": "dot_oag"}})
    assert res["ok"] is True, res
    assert res["result"].get("layout") == "dot_oag", res

    # ontology/ + knowledge/ live under .oag/ ...
    assert (ip / ".oag" / "ontology" / "ip.yaml").is_file(), res
    assert (ip / ".oag" / "ontology" / "scope_lock.json").is_file(), res
    assert (ip / ".oag" / "ontology" / "contracts.yaml").is_file(), res
    assert (ip / ".oag" / "knowledge" / "ledger.jsonl").is_file(), res
    assert (ip / ".oag" / "knowledge" / "_index.json").is_file(), res
    # ... and not at the legacy top level.
    assert not (ip / "ontology").exists(), "no top-level ontology/ under dot_oag scaffold"
    assert not (ip / "knowledge").exists(), "no top-level knowledge/ under dot_oag scaffold"
    # human-facing surfaces stay top-level.
    for top in ("req", "rtl", "tb", "list", "scripts", "doc", "sdc", "sim"):
        assert (ip / top).is_dir(), f"{top}/ should stay top-level"

    # resolver reports a clean dot_oag layout (no mixed-layout warning).
    layout = json.loads(
        subprocess.run(
            [sys.executable, str(OAG_PATHS), "--ip-dir", str(ip), "--json"],
            text=True, capture_output=True, check=False, cwd=ROOT,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        ).stdout
    )
    assert layout["layout"] == "dot_oag", layout
    assert layout["warnings"] == [], layout

    # IP-state scripts operate on the freshly scaffolded .oag IP via the resolver.
    chk = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"]
    assert not any("missing knowledge directory" in i for i in chk.get("issues", [])), chk
    assert not any("missing ontology" in i for i in chk.get("issues", [])), chk
    assert _req_quality_json(ip)["rc"] == 0, "req_quality runs on the .oag-scaffolded IP"


def _hash_tree(root: Path) -> dict:
    import hashlib

    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _run_migrate(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(MIGRATE_LAYOUT), *args, "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else {"_stderr": proc.stderr[-300:]})


def test_dot_oag_migration_tool(tmp_root: Path) -> None:
    """Wave 4: oag_migrate_layout.py moves ontology/ and knowledge/ into <ip>/.oag/
    (dry-run by default), preserves file hashes, writes a receipt, keeps IP-state
    scripts working, and rolls back losslessly."""
    ip = tmp_root / "mig_ip"
    sc = call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(ip), "owner": "smoke"}})
    assert sc["ok"] is True, sc
    assert (ip / "ontology").is_dir() and (ip / "knowledge").is_dir(), "legacy scaffold expected"
    pre = {"ontology": _hash_tree(ip / "ontology"), "knowledge": _hash_tree(ip / "knowledge")}

    # dry-run must change nothing.
    rc, dry = _run_migrate("--ip-dir", str(ip), "--to-dot-oag")
    assert rc == 0 and dry.get("applied") is False, dry
    assert (ip / "ontology").is_dir() and not (ip / ".oag").exists(), "dry-run must not move"

    # apply moves into .oag, preserves hashes, writes a receipt.
    rc, ap = _run_migrate("--ip-dir", str(ip), "--to-dot-oag", "--apply")
    assert rc == 0 and ap.get("applied") is True, ap
    assert (ip / ".oag" / "ontology").is_dir() and (ip / ".oag" / "knowledge").is_dir(), ap
    assert not (ip / "ontology").exists() and not (ip / "knowledge").exists(), "top-level cleared"
    assert _hash_tree(ip / ".oag" / "ontology") == pre["ontology"], "ontology hashes preserved"
    assert _hash_tree(ip / ".oag" / "knowledge") == pre["knowledge"], "knowledge hashes preserved"
    receipt = ip / ap["receipt"]
    assert receipt.is_file(), ap

    # migrated IP still resolves via the resolver.
    chk = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"]
    assert not any(("missing knowledge" in i) or ("missing ontology" in i) for i in chk.get("issues", [])), chk

    # rollback restores the legacy layout losslessly.
    rc, rb = _run_migrate("--rollback", str(receipt))
    assert rc == 0, rb
    assert (ip / "ontology").is_dir() and (ip / "knowledge").is_dir(), "rollback restores top-level"
    assert not (ip / ".oag" / "ontology").exists(), "rollback clears .oag ontology"
    assert _hash_tree(ip / "ontology") == pre["ontology"], "rollback preserves ontology hashes"


def test_dot_oag_mixed_layout_rejected(tmp_root: Path) -> None:
    """Wave 5 enforcement: oag.check fails on an unsafe mixed layout where
    ontology/ or knowledge/ exist both at the top level and under .oag/. Clean
    legacy and clean .oag layouts do not trip the gate."""
    ip = tmp_root / "mixed_ip"
    assert call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(ip), "owner": "smoke"}})["ok"] is True

    # clean legacy layout: no mixed-layout issue.
    issues = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"].get("issues", [])
    assert not any("mixed OAG layout" in i for i in issues), issues

    # migrate to a clean .oag layout: still no mixed-layout issue.
    rc, ap = _run_migrate("--ip-dir", str(ip), "--to-dot-oag", "--apply")
    assert rc == 0 and ap.get("applied") is True, ap
    issues = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"].get("issues", [])
    assert not any("mixed OAG layout" in i for i in issues), issues

    # a stray legacy top-level ontology/ alongside .oag is an unsafe mixed state.
    (ip / "ontology").mkdir(parents=True, exist_ok=True)
    (ip / "ontology" / "stray.yaml").write_text("stray: true\n", encoding="utf-8")
    res = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"]
    assert res["ok"] is False, res
    assert any(("mixed OAG layout" in i) and ("ontology" in i) for i in res.get("issues", [])), res

    # removing the stray legacy dir clears the gate.
    (ip / "ontology" / "stray.yaml").unlink()
    (ip / "ontology").rmdir()
    issues = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})["result"].get("issues", [])
    assert not any("mixed OAG layout" in i for i in issues), issues


def run_baseline_check(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(BASELINE_CHECK), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_authoring_packet_check(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(AUTHORING_PACKET_CHECK), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_stale_check(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(STALE_CHECK), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_baseline_cut(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(BASELINE_CUT), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd or ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_baseline_verify(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(BASELINE_VERIFY), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd or ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_ip_version_check(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(IP_VERSION_CHECK), *args],
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd or ROOT,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_main_write_gate(ip: Path, *, project_root: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    if project_root:
        env["OAG_PROJECT_ROOT"] = str(project_root)
    return subprocess.run(
        [sys.executable, str(MAIN_WRITE_GATE), "--ip-dir", str(ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=project_root or ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_validate_json(schema: Path, document: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATE_JSON), "--schema", str(schema), "--document", str(document), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_agent_catalog_check() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AGENT_CATALOG_CHECK), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_closure_check(ip: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLOSURE_CHECK), "--ip-dir", str(ip), *extra, "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def run_pack_release_check() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PACK_RELEASE_CHECK), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def stop_gate(payload: dict, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(STOP_GATE)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def subagent_gate(payload: dict, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SUBAGENT_GATE)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def subagent_start(payload: dict, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SUBAGENT_START)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def context_hook(payload: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(CONTEXT_HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def oag_mode_trigger(payload: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(OAG_MODE_TRIGGER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def native_subagent_guard(payload: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    return subprocess.run(
        [sys.executable, str(NATIVE_SUBAGENT_GUARD)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def session_start_hook(payload: dict, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OAG_DISABLE_BACKEND": "1"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OAG_SESSION_START)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT.parent,
        env=env,
        timeout=OAG_CALL_TIMEOUT_SECONDS,
    )


def hook_context(proc: subprocess.CompletedProcess[str]) -> str:
    if not proc.stdout.strip():
        return ""
    payload = json.loads(proc.stdout)
    output = payload.get("hookSpecificOutput") if isinstance(payload, dict) else {}
    return str(output.get("additionalContext") or "") if isinstance(output, dict) else ""


def hook_target_names(project: Path, payload: dict, *, require_signal: bool = True) -> list[str]:
    spec = importlib.util.spec_from_file_location("oag_hook_utils_smoke", ROOT / "hooks" / "oag_hook_utils.py")
    assert spec and spec.loader, spec
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PROJECT = project
    return [path.name for path in module.target_ip_dirs(payload, require_signal=require_signal)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_ip(root: Path) -> Path:
    ip = root / "demo_counter_cx1"
    scaffold = call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(ip), "owner": "smoke"}})
    assert scaffold["ok"] is True, scaffold
    assert scaffold["result"]["schema_version"] == "oag_scaffold_result.v1", scaffold
    assert (ip / "req" / "deep_semantic_intake").is_dir()
    assert (ip / "req" / "source_claims.yaml").is_file()
    assert (ip / "req" / "ambiguity_register.yaml").is_file()
    assert (ip / "ontology" / "ip.yaml").is_file()
    assert (ip / "ontology" / "requirements.yaml").is_file()
    assert (ip / "ontology" / "requirement_atoms.yaml").is_file()
    assert (ip / "ontology" / "decision_matrix.yaml").is_file()
    assert (ip / "ontology" / "obligations.yaml").is_file()
    assert (ip / "ontology" / "contracts.yaml").is_file()
    assert (ip / "ontology" / "modeling.yaml").is_file()
    assert (ip / "ontology" / "domain_intent.yaml").is_file()
    assert (ip / "ontology" / "verification_plan.yaml").is_file()
    assert (ip / "ontology" / "tb_methodology.yaml").is_file()
    assert (ip / "ontology" / "structure.yaml").is_file()
    assert (ip / "ontology" / "decomposition.yaml").is_file()
    assert (ip / "ontology" / "design_rules.yaml").is_file()
    assert (ip / "ontology" / "drafts").is_dir()
    assert (ip / "ontology" / "stages.yaml").is_file()
    assert (ip / "ontology" / "policies.yaml").is_file()
    policy_text = (ip / "ontology" / "policies.yaml").read_text(encoding="utf-8")
    assert "execution_policy:" in policy_text, policy_text
    assert "hook_auto_continue_until: all" in policy_text, policy_text
    assert "graph_policy:" in policy_text, policy_text
    assert "compile_skip_when_fresh: true" in policy_text, policy_text
    assert "requirement_quality_policy:" in policy_text, policy_text
    assert "modeling_policy:" in policy_text, policy_text
    assert "requirement_decomposition_policy:" in policy_text, policy_text
    assert "decision_matrix_policy:" in policy_text, policy_text
    assert "contract_strength_policy:" in policy_text, policy_text
    assert "authoring_packet_policy:" in policy_text, policy_text
    assert "traceability_policy:" in policy_text, policy_text
    assert "verification_strategy_policy:" in policy_text, policy_text
    assert "domain_crossing_policy:" in policy_text, policy_text
    assert "tb_methodology_policy:" in policy_text, policy_text
    assert (ip / "ontology" / "protection.yaml").is_file()
    assert (ip / "ontology" / "evidence" / "scoreboard_rows.v1.yaml").is_file()
    assert (ip / "ontology" / "evidence" / "stage_run_receipt.v1.yaml").is_file()
    assert (ip / "ontology" / "evidence" / "cdc_rdc_report.v1.yaml").is_file()
    assert (ip / "ontology" / "evidence" / "verification_plan_report.v1.yaml").is_file()
    assert (ip / "ontology" / "evidence" / "tb_methodology_report.v1.yaml").is_file()
    assert (ip / "ontology" / "decision_receipt.v1.yaml").is_file()
    assert (ip / "ontology" / "run_state.v1.yaml").is_file()
    assert (ip / "ontology" / "metrics").is_dir()
    assert (ip / "ontology" / "metrics" / "improvement_metrics.v1.yaml").is_file()
    assert (ip / "ontology" / "handoff_readiness.v1.yaml").is_file()
    assert (ip / "ontology" / "gates" / "gate_self_test_registry.yaml").is_file()
    assert (ip / "ontology" / "scope_lock.json").is_file()
    assert (ip / "knowledge" / "_index.json").is_file()
    assert (ip / "knowledge" / "ledger.jsonl").is_file()
    assert (ip / "list" / "rtl.f").is_file()
    run_lint_text = (ip / "scripts" / "run_lint.sh").read_text(encoding="utf-8")
    assert "OAG_LINT_BACKEND" in run_lint_text, run_lint_text
    assert "oag_pyslang_lint.py" in run_lint_text, run_lint_text
    lock_status = call({"tool": "oag.lock_status", "arguments": {"ip_dir": str(ip)}})
    assert lock_status["result"]["state"] == "draft", lock_status
    locked = call(
        {
            "tool": "oag.lock",
            "arguments": {
                "ip_dir": str(ip),
                "summary": "Smoke test locks the demo counter seed scope before implementation evidence.",
                "confirmed_scope": ["demo counter reset/count scoreboard closure"],
                "actor": {"kind": "human", "id": "smoke-owner", "surface": "smoke"},
            },
        }
    )
    assert locked["result"]["locked"] is True, locked
    (ip / "rtl" / "rtl_compile.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    (ip / "lint" / "dut_lint.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    (ip / "sim" / "results.xml").write_text('<testsuite failures="0"/>\n', encoding="utf-8")
    rows = [
        {
            "event_id": "EVT_DEMO_COUNTER_CX1_RESET_DEFAULTS",
            "goal_id": "GOAL_COUNTER_INC",
            "obligation_id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
            "contract_id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
            "contract_refs": ["CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD"],
            "scenario_id": "SC_INC_001",
            "cycle": 1,
            "stimulus": {"valid": 1},
            "expected": {"count": 1},
            "expected_source": {
                "kind": "behavior_model",
                "refs": ["behavior_model.seed_obligations.reset_known_state"],
            },
            "observed": {"count": 1},
            "observed_source": {"kind": "dut_signal", "path": "dut.count"},
            "passed": True,
            "mismatch": "",
            "coverage_refs": ["COV_INC"],
        },
        {
            "event_id": "EVT_DEMO_COUNTER_CX1_RESET_DEFAULTS",
            "goal_id": "GOAL_COUNTER_INC",
            "obligation_id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
            "contract_id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
            "contract_refs": ["CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD"],
            "scenario_id": "SC_INC_002",
            "cycle": 2,
            "stimulus": {"valid": 1},
            "expected": {"count": 2},
            "expected_source": {
                "kind": "behavior_model",
                "refs": ["behavior_model.seed_obligations.reset_known_state"],
            },
            "observed": {"count": 2},
            "observed_source": {"kind": "monitor", "path": "counter_monitor.count"},
            "passed": True,
            "mismatch": "",
            "coverage_refs": ["COV_INC"],
        },
    ]
    (ip / "sim" / "scoreboard_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    (ip / "sim" / "scenario_mapping.json").write_text(
        json.dumps(
            {
                "schema_version": "oag_scenario_mapping.v1",
                "scenarios": [
                    {
                        "id": "SC_INC_001",
                        "contracts": ["CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD"],
                        "scoreboard_rows": ["EVT_DEMO_COUNTER_CX1_RESET_DEFAULTS"],
                    },
                    {
                        "id": "SC_INC_002",
                        "contracts": ["CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD"],
                        "scoreboard_rows": ["EVT_DEMO_COUNTER_CX1_RESET_DEFAULTS"],
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (ip / "cov" / "coverage.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    (ip / "signoff" / "truth_coverage.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    return ip


def test_pyslang_lint_runner() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ip = Path(tmp) / "lint_ip"
        (ip / "rtl").mkdir(parents=True)
        (ip / "list").mkdir()
        (ip / "rtl" / "demo.sv").write_text(
            "\n".join(
                [
                    "module demo(input logic clk, output logic done);",
                    "  assign done = clk;",
                    "endmodule",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (ip / "list" / "rtl.f").write_text("+incdir+rtl\nrtl/*.sv\n", encoding="utf-8")
        (ip / "list" / "lint.f").write_text("-f list/rtl.f\n", encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(PYSLANG_LINT),
                "--ip-dir",
                str(ip),
                "--filelist",
                "list/lint.f",
                "--out",
                "lint/dut_lint.json",
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout
        result = json.loads((ip / "lint" / "dut_lint.json").read_text(encoding="utf-8"))
        assert result["status"] == "pass", result
        assert result["tool"] == "pyslang", result
        assert result["files"] == ["rtl/demo.sv"], result


def test_wavefront_scheduler(tmp_root: Path) -> None:
    project = tmp_root / "wavefront_project"
    project.mkdir(parents=True)
    ip = project / "wave_ip"
    ip.mkdir()
    run_id = "RUN_WAVE_SMOKE"

    plan = run_wavefront(
        "plan",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--template",
        str(OAG_WAVEFRONT_TEMPLATE),
        "--json",
        project_root=project,
    )
    assert plan.returncode == 0, plan.stderr or plan.stdout
    plan_result = json.loads(plan.stdout)
    assert plan_result["status"] == "pass", plan_result
    assert sorted(plan_result["ready_tasks"]) == ["TB_COMMON_API", "TB_SCOREBOARD_SCHEMA"], plan_result

    ready = run_wavefront("ready", "--ip-dir", str(ip), "--run-id", run_id, "--json", project_root=project)
    assert ready.returncode == 0, ready.stderr or ready.stdout
    ready_ids = sorted(task["task_id"] for task in json.loads(ready.stdout)["ready_tasks"])
    assert ready_ids == ["TB_COMMON_API", "TB_SCOREBOARD_SCHEMA"], ready.stdout

    early_scenario = run_wavefront(
        "claim",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_SCENARIO_A",
        "--json",
        project_root=project,
    )
    assert early_scenario.returncode != 0, early_scenario.stdout
    early_result = json.loads(early_scenario.stdout)
    early_codes = {item["code"] for item in early_result["issues"]}
    assert "DEPENDENCY_UNMET" in early_codes and "BARRIER_UNMET" in early_codes, early_result

    claim_common = run_wavefront(
        "claim",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_COMMON_API",
        "--claimed-by",
        "smoke-common",
        "--json",
        project_root=project,
    )
    assert claim_common.returncode == 0, claim_common.stderr or claim_common.stdout
    claim_scoreboard = run_wavefront(
        "claim",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_SCOREBOARD_SCHEMA",
        "--claimed-by",
        "smoke-scoreboard",
        "--json",
        project_root=project,
    )
    assert claim_scoreboard.returncode == 0, claim_scoreboard.stderr or claim_scoreboard.stdout

    active_close = run_wavefront(
        "close",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--allow-open",
        "--json",
        project_root=project,
    )
    assert active_close.returncode != 0, active_close.stdout
    assert any(item["code"] == "ACTIVE_LOCKS" for item in json.loads(active_close.stdout)["issues"]), active_close.stdout

    bad_barrier_record = run_wavefront(
        "record",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_COMMON_API",
        "--status",
        "handoff_pass",
        "--barrier-output",
        "scoreboard_schema_frozen",
        "--json",
        project_root=project,
    )
    assert bad_barrier_record.returncode != 0, bad_barrier_record.stdout
    assert any(
        item["code"] == "BARRIER_OUTPUT_UNDECLARED"
        for item in json.loads(bad_barrier_record.stdout)["issues"]
    ), bad_barrier_record.stdout

    record_common = run_wavefront(
        "record",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_COMMON_API",
        "--status",
        "handoff_pass",
        "--barrier-output",
        "tb_common_import_clean",
        "--barrier-output",
        "helper_api_manifest",
        "--json",
        project_root=project,
    )
    assert record_common.returncode == 0, record_common.stderr or record_common.stdout
    record_scoreboard = run_wavefront(
        "record",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_SCOREBOARD_SCHEMA",
        "--status",
        "handoff_pass",
        "--barrier-output",
        "scoreboard_schema_frozen",
        "--json",
        project_root=project,
    )
    assert record_scoreboard.returncode == 0, record_scoreboard.stderr or record_scoreboard.stdout

    scenario_ready = run_wavefront("ready", "--ip-dir", str(ip), "--run-id", run_id, "--json", project_root=project)
    assert scenario_ready.returncode == 0, scenario_ready.stderr or scenario_ready.stdout
    scenario_ready_ids = [task["task_id"] for task in json.loads(scenario_ready.stdout)["ready_tasks"]]
    assert scenario_ready_ids == ["TB_SCENARIO_A"], scenario_ready.stdout

    claim_scenario = run_wavefront(
        "claim",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_SCENARIO_A",
        "--json",
        project_root=project,
    )
    assert claim_scenario.returncode == 0, claim_scenario.stderr or claim_scenario.stdout
    record_scenario = run_wavefront(
        "record",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--task-id",
        "TB_SCENARIO_A",
        "--status",
        "handoff_pass",
        "--barrier-output",
        "scenario_import_clean",
        "--json",
        project_root=project,
    )
    assert record_scenario.returncode == 0, record_scenario.stderr or record_scenario.stdout
    verify = run_wavefront("verify", "--ip-dir", str(ip), "--run-id", run_id, "--json", project_root=project)
    assert verify.returncode == 0, verify.stderr or verify.stdout

    close = run_wavefront(
        "close",
        "--ip-dir",
        str(ip),
        "--run-id",
        run_id,
        "--allow-open",
        "--json",
        project_root=project,
    )
    assert close.returncode == 0, close.stderr or close.stdout

    conflict_ip = project / "conflict_ip"
    conflict_ip.mkdir()
    conflict_template = project / "conflict_template.json"
    conflict_template.write_text(
        json.dumps(
            {
                "schema_version": "oag_wavefront_template.v1",
                "tasks": [
                    {
                        "task_id": "WRITE_A",
                        "kind": "write",
                        "phase": "rtl",
                        "depends_on": [],
                        "allowed_write_paths": ["rtl/shared.sv"],
                        "ownership_mode": "exclusive_file",
                        "may_claim_complete": False,
                    },
                    {
                        "task_id": "WRITE_B",
                        "kind": "write",
                        "phase": "rtl",
                        "depends_on": [],
                        "allowed_write_paths": ["rtl/shared.sv"],
                        "ownership_mode": "exclusive_file",
                        "may_claim_complete": False,
                    },
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    conflict_run = "RUN_CONFLICT_SMOKE"
    conflict_plan = run_wavefront(
        "plan",
        "--ip-dir",
        str(conflict_ip),
        "--run-id",
        conflict_run,
        "--template",
        str(conflict_template),
        "--json",
        project_root=project,
    )
    assert conflict_plan.returncode == 0, conflict_plan.stderr or conflict_plan.stdout
    claim_a = run_wavefront(
        "claim",
        "--ip-dir",
        str(conflict_ip),
        "--run-id",
        conflict_run,
        "--task-id",
        "WRITE_A",
        "--json",
        project_root=project,
    )
    assert claim_a.returncode == 0, claim_a.stderr or claim_a.stdout
    claim_b = run_wavefront(
        "claim",
        "--ip-dir",
        str(conflict_ip),
        "--run-id",
        conflict_run,
        "--task-id",
        "WRITE_B",
        "--json",
        project_root=project,
    )
    assert claim_b.returncode != 0, claim_b.stdout
    assert any(item["code"] == "OWNERSHIP_CONFLICT" for item in json.loads(claim_b.stdout)["issues"]), claim_b.stdout

    shared_scope_ip = project / "shared_scope_ip"
    shared_scope_ip.mkdir()
    shared_scope_template = project / "shared_scope_template.json"
    shared_scope_template.write_text(
        json.dumps(
            {
                "schema_version": "oag_wavefront_template.v1",
                "tasks": [
                    {
                        "task_id": "BAD_SHARED_WRITER",
                        "kind": "write",
                        "phase": "sim",
                        "depends_on": [],
                        "shared_artifacts": ["sim/results.xml"],
                        "ownership_mode": "exclusive_file",
                        "may_claim_complete": False,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    shared_scope_run = "RUN_SHARED_SCOPE_SMOKE"
    shared_scope_plan = run_wavefront(
        "plan",
        "--ip-dir",
        str(shared_scope_ip),
        "--run-id",
        shared_scope_run,
        "--template",
        str(shared_scope_template),
        "--json",
        project_root=project,
    )
    assert shared_scope_plan.returncode != 0, shared_scope_plan.stdout
    shared_scope_issues = json.loads(shared_scope_plan.stdout)["issues"]
    assert any(item["code"] == "SHARED_ARTIFACT_OWNERSHIP" for item in shared_scope_issues), shared_scope_plan.stdout

    stale_ip = project / "stale_guard_ip"
    stale_ip.mkdir()
    (stale_ip / "rtl").mkdir()
    watched_path = stale_ip / "rtl" / "watched.sv"
    watched_path.write_text("module watched; endmodule\n", encoding="utf-8")
    stale_template = project / "stale_template.json"
    stale_template.write_text(
        json.dumps(
            {
                "schema_version": "oag_wavefront_template.v1",
                "tasks": [
                    {
                        "task_id": "STALE_GUARDED_WRITE",
                        "kind": "write",
                        "phase": "rtl",
                        "depends_on": [],
                        "allowed_write_paths": ["rtl/output.sv"],
                        "stale_if_paths_changed": ["rtl/watched.sv"],
                        "ownership_mode": "exclusive_file",
                        "may_claim_complete": False,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    stale_run = "RUN_STALE_SMOKE"
    stale_plan = run_wavefront(
        "plan",
        "--ip-dir",
        str(stale_ip),
        "--run-id",
        stale_run,
        "--template",
        str(stale_template),
        "--json",
        project_root=project,
    )
    assert stale_plan.returncode == 0, stale_plan.stderr or stale_plan.stdout
    watched_path.write_text("module watched; wire changed; endmodule\n", encoding="utf-8")
    stale_claim = run_wavefront(
        "claim",
        "--ip-dir",
        str(stale_ip),
        "--run-id",
        stale_run,
        "--task-id",
        "STALE_GUARDED_WRITE",
        "--json",
        project_root=project,
    )
    assert stale_claim.returncode != 0, stale_claim.stdout
    assert any(item["code"] == "STALE_PATH_CHANGED" for item in json.loads(stale_claim.stdout)["issues"]), stale_claim.stdout


def test_artifact_lifecycle_checker(tmp_root: Path) -> None:
    ip = tmp_root / "lifecycle_ip"
    (ip / "ontology").mkdir(parents=True)

    missing = run_lifecycle_check("--ip-dir", str(ip), "--require", "--json")
    assert missing.returncode != 0, missing.stdout
    assert any(item["code"] == "LIFECYCLE_MISSING" for item in json.loads(missing.stdout)["issues"]), missing.stdout

    lifecycle = {
        "schema_version": "oag_artifact_lifecycle.v1",
        "artifacts": [
            {
                "id": "ontology/contracts.yaml",
                "path": "ontology/contracts.yaml",
                "granularity": "file",
                "processing_stage": "canonical",
                "approval_state": "approved",
                "validity_state": "current",
                "approval_ref": "ontology/validations/contracts_review.json",
                "derived_from": ["ontology/requirements.yaml"],
                "allowed_consumers": ["rtl_authoring_packet", "tb_authoring_packet"],
            },
            {
                "id": "ontology/decision_matrix.yaml:D001",
                "path": "ontology/decision_matrix.yaml",
                "object_id": "D001",
                "granularity": "object",
                "processing_stage": "canonical",
                "approval_state": "candidate",
                "validity_state": "current",
                "derived_from": ["req/source_claims.yaml:SRC001"],
                "allowed_consumers": ["clarification_agent"],
            },
        ],
    }
    path = ip / "ontology" / "artifact_lifecycle.json"
    path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    valid = run_lifecycle_check("--ip-dir", str(ip), "--consumer", "rtl_authoring_packet", "--json")
    assert valid.returncode == 0, valid.stderr or valid.stdout
    valid_result = json.loads(valid.stdout)
    assert valid_result["status"] == "pass", valid_result

    denied = run_lifecycle_check(
        "--ip-dir",
        str(ip),
        "--artifact-id",
        "ontology/decision_matrix.yaml:D001",
        "--consumer",
        "rtl_authoring_packet",
        "--json",
    )
    assert denied.returncode != 0, denied.stdout
    denied_codes = {item["code"] for item in json.loads(denied.stdout)["issues"]}
    assert "LIFECYCLE_CONSUMER_FORBIDDEN" in denied_codes
    assert "LIFECYCLE_APPROVAL_STATE" in denied_codes

    bad = lifecycle.copy()
    bad["artifacts"] = [
        {
            "id": "ontology/generated/authoring_packets/rtl__demo.json",
            "path": "ontology/generated/authoring_packets/rtl__demo.json",
            "granularity": "file",
            "processing_stage": "serving",
            "approval_state": "approved",
            "validity_state": "current",
            "allowed_consumers": ["rtl_agent"],
        }
    ]
    path.write_text(json.dumps(bad, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bad_result = run_lifecycle_check("--ip-dir", str(ip), "--json")
    assert bad_result.returncode != 0, bad_result.stdout
    bad_codes = {item["code"] for item in json.loads(bad_result.stdout)["issues"]}
    assert "LIFECYCLE_DERIVED_FROM" in bad_codes
    assert "LIFECYCLE_APPROVAL_REF" in bad_codes


def test_authoring_packet_lifecycle_firewall(tmp_root: Path) -> None:
    ip = tmp_root / "packet_lifecycle_ip"
    packet_dir = ip / "ontology" / "generated" / "authoring_packets"
    packet_dir.mkdir(parents=True)
    (ip / "ontology").mkdir(exist_ok=True)
    lifecycle = {
        "schema_version": "oag_artifact_lifecycle.v1",
        "artifacts": [
            {
                "id": "ontology/contracts.yaml",
                "path": "ontology/contracts.yaml",
                "granularity": "file",
                "processing_stage": "canonical",
                "approval_state": "approved",
                "validity_state": "current",
                "approval_ref": "ontology/validations/contracts_review.json",
                "derived_from": ["ontology/requirements.yaml"],
                "allowed_consumers": ["rtl_authoring_packet", "tb_authoring_packet"],
            },
            {
                "id": "ontology/decision_matrix.yaml:D001",
                "path": "ontology/decision_matrix.yaml",
                "object_id": "D001",
                "granularity": "object",
                "processing_stage": "canonical",
                "approval_state": "candidate",
                "validity_state": "current",
                "derived_from": ["req/source_claims.yaml:SRC001"],
                "allowed_consumers": ["clarification_agent"],
            },
            {
                "id": "rtl/top.sv",
                "path": "rtl/top.sv",
                "granularity": "file",
                "processing_stage": "serving",
                "approval_state": "approved",
                "validity_state": "current",
                "approval_ref": "ontology/validations/rtl_review.json",
                "derived_from": ["ontology/generated/authoring_packets/rtl__demo.json"],
                "allowed_consumers": ["rtl_agent"],
            },
        ],
    }
    (ip / "ontology" / "artifact_lifecycle.json").write_text(
        json.dumps(lifecycle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rtl_packet = {
        "schema_version": "oag_rtl_authoring_packet.v1",
        "packet_type": "rtl_authoring_packet",
        "ip": "packet_lifecycle_ip",
        "allowed_truth_sources": ["ontology/contracts.yaml"],
        "forbidden_sources": ["tb", "sim", "dut_output"],
        "contract_refs_to_implement": ["CONTRACT_DEMO"],
        "behavior_refs_implemented_target": ["behavior_model.demo"],
        "ppa_notes_required": True,
        "cdc_rdc_notes_required": True,
        "lifecycle_input_refs": ["ontology/contracts.yaml"],
    }
    tb_packet = {
        "schema_version": "oag_tb_authoring_packet.v1",
        "packet_type": "tb_authoring_packet",
        "ip": "packet_lifecycle_ip",
        "expected_source_policy": "contract_oracle_only",
        "forbidden_expected_sources": ["dut_output", "rtl_expression", "post_hoc_simulation"],
        "contract_refs": ["CONTRACT_DEMO"],
        "scenario_refs": ["SCN_DEMO"],
        "scoreboard_row_refs": ["EVT_DEMO"],
        "lifecycle_input_refs": ["ontology/contracts.yaml"],
    }
    rtl_path = packet_dir / "rtl__demo.json"
    tb_path = packet_dir / "tb__demo.json"
    rtl_path.write_text(json.dumps(rtl_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tb_path.write_text(json.dumps(tb_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    good = run_authoring_packet_check("--ip-dir", str(ip), "--require-packets", "--require-lifecycle", "--json")
    assert good.returncode == 0, good.stderr or good.stdout
    assert json.loads(good.stdout)["status"] == "pass", good.stdout

    rtl_packet["lifecycle_input_refs"] = ["ontology/decision_matrix.yaml:D001"]
    rtl_path.write_text(json.dumps(rtl_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bad_rtl = run_authoring_packet_check("--ip-dir", str(ip), "--require-packets", "--require-lifecycle", "--json")
    assert bad_rtl.returncode != 0, bad_rtl.stdout
    assert any(
        item["code"] == "PACKET_LIFECYCLE_BLOCKED"
        for item in json.loads(bad_rtl.stdout)["issues"]
    ), bad_rtl.stdout

    rtl_packet["lifecycle_input_refs"] = ["ontology/contracts.yaml"]
    rtl_path.write_text(json.dumps(rtl_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tb_packet["lifecycle_input_refs"] = ["rtl/top.sv"]
    tb_path.write_text(json.dumps(tb_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bad_tb = run_authoring_packet_check("--ip-dir", str(ip), "--require-packets", "--require-lifecycle", "--json")
    assert bad_tb.returncode != 0, bad_tb.stdout
    assert any(
        item["code"] == "TB_PACKET_RTL_DERIVED_LIFECYCLE_INPUT"
        for item in json.loads(bad_tb.stdout)["issues"]
    ), bad_tb.stdout


def test_stale_propagation_checker(tmp_root: Path) -> None:
    ip = tmp_root / "stale_ip"
    (ip / "ontology" / "generated" / "authoring_packets").mkdir(parents=True)
    (ip / "sim").mkdir(parents=True)
    req_path = ip / "ontology" / "requirements.yaml"
    contracts_path = ip / "ontology" / "contracts.yaml"
    rtl_packet_path = ip / "ontology" / "generated" / "authoring_packets" / "rtl__demo.json"
    evidence_path = ip / "sim" / "results.xml"
    req_path.write_text("requirements:\n- id: REQ_DEMO\n  text: changed\n", encoding="utf-8")
    contracts_path.write_text("contracts:\n- contract_id: CONTRACT_DEMO\n", encoding="utf-8")
    rtl_packet_path.write_text("{}\n", encoding="utf-8")
    evidence_path.write_text("<testsuite tests=\"1\" failures=\"0\"/>\n", encoding="utf-8")

    lifecycle = {
        "schema_version": "oag_artifact_lifecycle.v1",
        "artifacts": [
            {
                "id": "ontology/requirements.yaml",
                "path": "ontology/requirements.yaml",
                "granularity": "file",
                "processing_stage": "canonical",
                "approval_state": "approved",
                "validity_state": "current",
                "approval_ref": "ontology/validations/req_review.json",
                "derived_from": ["req/source_claims.yaml"],
                "allowed_consumers": ["contract_projection"],
                "hash": {
                    "content_sha256": "sha256:" + ("0" * 64),
                    "hash_mode": "raw_bytes",
                    "size_bytes": 1,
                },
            },
            {
                "id": "ontology/contracts.yaml",
                "path": "ontology/contracts.yaml",
                "granularity": "file",
                "processing_stage": "canonical",
                "approval_state": "approved",
                "validity_state": "current",
                "approval_ref": "ontology/validations/contracts_review.json",
                "derived_from": ["ontology/requirements.yaml"],
                "allowed_consumers": ["rtl_authoring_packet", "tb_authoring_packet"],
            },
            {
                "id": "ontology/generated/authoring_packets/rtl__demo.json",
                "path": "ontology/generated/authoring_packets/rtl__demo.json",
                "granularity": "file",
                "processing_stage": "serving",
                "approval_state": "approved",
                "validity_state": "current",
                "approval_ref": "ontology/validations/rtl_packet_review.json",
                "derived_from": ["ontology/contracts.yaml"],
                "allowed_consumers": ["rtl_agent"],
            },
            {
                "id": "sim/results.xml",
                "path": "sim/results.xml",
                "granularity": "file",
                "processing_stage": "serving",
                "approval_state": "approved",
                "validity_state": "current",
                "approval_ref": "ontology/validations/sim_review.json",
                "derived_from": ["ontology/generated/authoring_packets/rtl__demo.json"],
                "allowed_consumers": ["gate"],
            },
        ],
    }
    lifecycle_path = ip / "ontology" / "artifact_lifecycle.json"
    lifecycle_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    stale = run_stale_check("--ip-dir", str(ip), "--json")
    assert stale.returncode != 0, stale.stdout
    result = json.loads(stale.stdout)
    codes = {item["code"] for item in result["issues"]}
    assert "STALE_HASH_MISMATCH_CURRENT" in codes
    assert "STALE_DEPENDENT_CURRENT" in codes
    stale_ids = set(result["stale_artifacts"])
    assert "ontology/contracts.yaml" in stale_ids
    assert "ontology/generated/authoring_packets/rtl__demo.json" in stale_ids
    assert "sim/results.xml" in stale_ids

    lifecycle["artifacts"][0]["hash"] = {
        "content_sha256": "sha256:" + hashlib.sha256(req_path.read_bytes()).hexdigest(),
        "hash_mode": "raw_bytes",
        "size_bytes": req_path.stat().st_size,
    }
    lifecycle_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    clean = run_stale_check("--ip-dir", str(ip), "--json")
    assert clean.returncode == 0, clean.stderr or clean.stdout
    assert json.loads(clean.stdout)["status"] == "pass", clean.stdout


def test_baseline_manifest_checker(tmp_root: Path) -> None:
    import yaml  # type: ignore

    ip = tmp_root / "baseline_ip"
    for rel in (
        "ontology/baselines",
        "ontology/gates",
        "ontology/validations",
        "ontology",
        "rtl",
        "sim",
    ):
        (ip / rel).mkdir(parents=True, exist_ok=True)
    files = {
        "ontology/contracts.yaml": "schema_version: contracts.v1\ncontracts: []\n",
        "rtl/top.sv": "module top; endmodule\n",
        "sim/results.xml": "<testsuite tests=\"1\" failures=\"0\"/>\n",
        "ontology/validations/validation.json": "{\"status\":\"pass\"}\n",
        "ontology/gates/closure_gate.json": "{\"decision\":\"pass\"}\n",
    }
    for rel, text in files.items():
        (ip / rel).write_text(text, encoding="utf-8")

    def hash_entry(rel: str) -> dict[str, object]:
        data = (ip / rel).read_bytes()
        return {
            "content_sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
            "hash_mode": "raw_bytes",
            "size_bytes": len(data),
        }

    manifest = {
        "schema_version": "oag_baseline_manifest.v1",
        "baseline_id": "baseline_ip.golden.v0.1.0",
        "ip": "baseline_ip",
        "baseline": {"class": "golden", "version": "0.1.0", "state": "active", "supersedes": None},
        "approval": {"state": "approved", "approval_ref": "ontology/gates/closure_gate.json"},
        "git": {"tag": "oag/baseline_ip/v0.1.0", "commit": "resolved_by_tag", "tag_type": "annotated"},
        "tracked_artifacts": {
            "truth": ["ontology/contracts.yaml"],
            "implementation": ["rtl/top.sv"],
            "evidence_summary": ["sim/results.xml"],
            "gate": ["ontology/validations/validation.json", "ontology/gates/closure_gate.json"],
        },
        "hashes": {rel: hash_entry(rel) for rel in files},
        "gate": {
            "gate_ref": "ontology/gates/closure_gate.json",
            "validation_ref": "ontology/validations/validation.json",
            "decision": "pass",
        },
    }
    manifest_path = ip / "ontology" / "baselines" / "baseline_ip_golden_v0.1.0.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    good = run_baseline_check("--manifest", str(manifest_path), "--json")
    assert good.returncode == 0, good.stderr or good.stdout
    assert json.loads(good.stdout)["status"] == "pass", good.stdout

    (ip / "sim/results.xml").write_text("<testsuite tests=\"1\" failures=\"1\"/>\n", encoding="utf-8")
    mismatch = run_baseline_check("--manifest", str(manifest_path), "--json")
    assert mismatch.returncode != 0, mismatch.stdout
    assert any(item["code"] == "BASELINE_HASH_MISMATCH" for item in json.loads(mismatch.stdout)["issues"]), mismatch.stdout

    broken = manifest.copy()
    broken["git"] = {"tag": "", "commit": "abc123", "tag_type": "lightweight"}
    broken["tracked_artifacts"] = {"truth": ["ontology/missing.yaml"]}
    broken_path = ip / "ontology" / "baselines" / "broken.yaml"
    broken_path.write_text(yaml.safe_dump(broken, sort_keys=False), encoding="utf-8")
    bad = run_baseline_check("--manifest", str(broken_path), "--json")
    assert bad.returncode != 0, bad.stdout
    bad_codes = {item["code"] for item in json.loads(bad.stdout)["issues"]}
    assert "BASELINE_GIT_TAG" in bad_codes
    assert "BASELINE_TAG_TYPE" in bad_codes
    assert "BASELINE_SELF_COMMIT" in bad_codes
    assert "BASELINE_TRACKED_FILE_MISSING" in bad_codes

    (ip / "sim" / "waves.fst").write_text("waveform bytes\n", encoding="utf-8")
    forbidden = manifest.copy()
    forbidden["tracked_artifacts"] = {"evidence_summary": ["sim/waves.fst"]}
    forbidden["hashes"] = {"sim/waves.fst": hash_entry("sim/waves.fst")}
    forbidden_path = ip / "ontology" / "baselines" / "forbidden.yaml"
    forbidden_path.write_text(yaml.safe_dump(forbidden, sort_keys=False), encoding="utf-8")
    forbidden_result = run_baseline_check("--manifest", str(forbidden_path), "--json")
    assert forbidden_result.returncode != 0, forbidden_result.stdout
    assert any(
        item["code"] == "BASELINE_TRACKED_FORBIDDEN"
        for item in json.loads(forbidden_result.stdout)["issues"]
    ), forbidden_result.stdout

    external_bad = manifest.copy()
    external_bad["external_artifacts"] = [
        {
            "id": "WAVES",
            "kind": "waveform",
            "uri": "artifacts://baseline_ip/v0.1.0/waves.fst",
            "required_for": "debug_only",
            "retention": "optional",
        }
    ]
    external_path = ip / "ontology" / "baselines" / "external_bad.yaml"
    external_path.write_text(yaml.safe_dump(external_bad, sort_keys=False), encoding="utf-8")
    external_result = run_baseline_check("--manifest", str(external_path), "--json")
    assert external_result.returncode != 0, external_result.stdout
    assert any(
        item["code"] == "BASELINE_EXTERNAL_SHA"
        for item in json.loads(external_result.stdout)["issues"]
    ), external_result.stdout


def test_baseline_cut_helper(tmp_root: Path) -> None:
    ip = tmp_root / "baseline_cut_ip"
    (ip / "ontology" / "baselines").mkdir(parents=True)
    (ip / "ontology" / "gates").mkdir(parents=True)
    (ip / "ontology" / "validations").mkdir(parents=True)
    (ip / "rtl").mkdir()
    (ip / "sim").mkdir()
    (ip / "ontology" / "requirements.yaml").write_text("requirements: []\n", encoding="utf-8")
    (ip / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
    (ip / "sim" / "results.xml").write_text("<testsuite tests=\"1\" failures=\"0\"/>\n", encoding="utf-8")
    (ip / "ontology" / "gates" / "closure_gate.json").write_text("{\"decision\":\"pass\"}\n", encoding="utf-8")
    (ip / "ontology" / "validations" / "validation.json").write_text("{\"status\":\"pass\"}\n", encoding="utf-8")
    manifest = ip / "ontology" / "baselines" / "baseline_cut.yaml"
    cut = run_baseline_cut(
        "--ip-dir",
        str(ip),
        "--baseline-id",
        "baseline_cut_ip.candidate.v0.1.0",
        "--version",
        "0.1.0",
        "--approval-ref",
        "ontology/validations/validation.json",
        "--gate-ref",
        "ontology/gates/closure_gate.json",
        "--validation-ref",
        "ontology/validations/validation.json",
        "--tracked-artifact",
        "truth:ontology/requirements.yaml",
        "--tracked-artifact",
        "implementation:rtl/top.sv",
        "--tracked-artifact",
        "evidence_summary:sim/results.xml",
        "--tracked-artifact",
        "gate:ontology/gates/closure_gate.json",
        "--output",
        str(manifest),
        "--allow-dirty",
        "--json",
    )
    assert cut.returncode == 0, cut.stderr or cut.stdout
    assert json.loads(cut.stdout)["status"] == "pass", cut.stdout
    assert manifest.is_file(), manifest

    generated = run_baseline_check("--manifest", str(manifest), "--json")
    assert generated.returncode == 0, generated.stderr or generated.stdout
    assert json.loads(generated.stdout)["status"] == "pass", generated.stdout

    repo = tmp_root / "dirty_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, text=True, capture_output=True, check=True)
    dirty_ip = repo / "dirty_ip"
    (dirty_ip / "ontology" / "baselines").mkdir(parents=True)
    (dirty_ip / "ontology" / "requirements.yaml").write_text("requirements: []\n", encoding="utf-8")
    dirty = run_baseline_cut(
        "--ip-dir",
        str(dirty_ip),
        "--baseline-id",
        "dirty_ip.candidate.v0.1.0",
        "--version",
        "0.1.0",
        "--approval-ref",
        "ontology/validations/validation.json",
        "--gate-ref",
        "ontology/gates/closure_gate.json",
        "--validation-ref",
        "ontology/validations/validation.json",
        "--tracked-artifact",
        "truth:ontology/requirements.yaml",
        "--output",
        str(dirty_ip / "ontology" / "baselines" / "dirty.yaml"),
        "--json",
        cwd=repo,
    )
    assert dirty.returncode != 0, dirty.stdout
    assert any(
        item["code"] == "BASELINE_CUT_DIRTY_TREE"
        for item in json.loads(dirty.stdout)["issues"]
    ), dirty.stdout


def test_baseline_verify_git_tag(tmp_root: Path) -> None:
    repo = tmp_root / "verify_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, text=True, capture_output=True, check=True)
    ip = repo / "verify_ip"
    (ip / "ontology" / "baselines").mkdir(parents=True)
    (ip / "ontology" / "gates").mkdir(parents=True)
    (ip / "ontology" / "validations").mkdir(parents=True)
    (ip / "rtl").mkdir()
    (ip / "sim").mkdir()
    (ip / "ontology" / "requirements.yaml").write_text("requirements: []\n", encoding="utf-8")
    (ip / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
    (ip / "sim" / "results.xml").write_text("<testsuite tests=\"1\" failures=\"0\"/>\n", encoding="utf-8")
    (ip / "ontology" / "gates" / "closure_gate.json").write_text("{\"decision\":\"pass\"}\n", encoding="utf-8")
    (ip / "ontology" / "validations" / "validation.json").write_text("{\"status\":\"pass\"}\n", encoding="utf-8")
    tag = "oag/verify_ip/v0.1.0"
    manifest = ip / "ontology" / "baselines" / "verify.yaml"
    cut = run_baseline_cut(
        "--ip-dir",
        str(ip),
        "--baseline-id",
        "verify_ip.golden.v0.1.0",
        "--version",
        "0.1.0",
        "--baseline-class",
        "golden",
        "--baseline-state",
        "active",
        "--approval-state",
        "approved",
        "--approval-ref",
        "ontology/validations/validation.json",
        "--gate-ref",
        "ontology/gates/closure_gate.json",
        "--validation-ref",
        "ontology/validations/validation.json",
        "--tag",
        tag,
        "--tracked-artifact",
        "truth:ontology/requirements.yaml",
        "--tracked-artifact",
        "implementation:rtl/top.sv",
        "--tracked-artifact",
        "evidence_summary:sim/results.xml",
        "--tracked-artifact",
        "gate:ontology/gates/closure_gate.json",
        "--tracked-artifact",
        "gate:ontology/validations/validation.json",
        "--output",
        str(manifest),
        "--allow-dirty",
        "--json",
        cwd=repo,
    )
    assert cut.returncode == 0, cut.stderr or cut.stdout
    subprocess.run(["git", "add", "."], cwd=repo, text=True, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Smoke", "-c", "user.email=smoke@example.com", "commit", "-m", "baseline"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    manifest_sha = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
    subprocess.run(["git", "tag", "-a", tag, "-m", f"manifest_sha256: {manifest_sha}"], cwd=repo, text=True, capture_output=True, check=True)

    good = run_baseline_verify("--manifest", str(manifest), "--verify-git-tag", "--json", cwd=repo)
    assert good.returncode == 0, good.stderr or good.stdout
    assert json.loads(good.stdout)["status"] == "pass", good.stdout

    manifest.write_text(manifest.read_text(encoding="utf-8") + "# local edit after tag\n", encoding="utf-8")
    stale = run_baseline_verify("--manifest", str(manifest), "--verify-git-tag", "--json", cwd=repo)
    assert stale.returncode != 0, stale.stdout
    codes = {item["code"] for item in json.loads(stale.stdout)["issues"]}
    assert "BASELINE_VERIFY_MANIFEST_TREE_MISMATCH" in codes


def test_ip_version_policy_checker(tmp_root: Path) -> None:
    ip = tmp_root / "version_ip"
    (ip / "ontology").mkdir(parents=True)
    (ip / "ontology" / "baselines").mkdir(parents=True)
    (ip / "ontology" / "validations").mkdir(parents=True)
    (ip / "ontology" / "baselines" / "version_ip_golden_v0.1.1.yaml").write_text(
        "schema_version: oag_baseline_manifest.v1\n",
        encoding="utf-8",
    )
    (ip / "ontology" / "validations" / "version_review.json").write_text("{\"status\":\"approved\"}\n", encoding="utf-8")
    ledger = {
        "schema_version": "oag_ip_version.v1",
        "ip": "version_ip",
        "current_version": "0.1.1",
        "version_policy": {
            "git_scope": "ip_local_repo",
            "tag_prefix": "oag/version_ip/",
        },
        "versions": [
            {
                "version": "0.1.0",
                "baseline_class": "golden",
                "state": "superseded",
                "change_class": "minor",
                "functional_truth_changed": True,
                "baseline_manifest": "ontology/baselines/version_ip_golden_v0.1.0.yaml",
                "git_tag": "oag/version_ip/v0.1.0",
                "approval_ref": "ontology/validations/version_review.json",
            },
            {
                "version": "0.1.1",
                "baseline_class": "golden",
                "state": "active",
                "change_class": "patch",
                "functional_truth_changed": False,
                "baseline_manifest": "ontology/baselines/version_ip_golden_v0.1.1.yaml",
                "git_tag": "oag/version_ip/v0.1.1",
                "approval_ref": "ontology/validations/version_review.json",
            },
        ],
    }
    version_path = ip / "ontology" / "ip_version.yaml"
    import yaml  # type: ignore

    version_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")

    no_git = run_ip_version_check("--ip-dir", str(ip), "--require-ip-git", "--json")
    assert no_git.returncode != 0, no_git.stdout
    assert any(item["code"] == "IP_VERSION_LOCAL_GIT_MISSING" for item in json.loads(no_git.stdout)["issues"]), no_git.stdout

    subprocess.run(["git", "init"], cwd=ip, text=True, capture_output=True, check=True)
    good = run_ip_version_check("--ip-dir", str(ip), "--require-ip-git", "--json")
    assert good.returncode == 0, good.stderr or good.stdout
    assert json.loads(good.stdout)["status"] == "pass", good.stdout

    ledger["versions"][1]["functional_truth_changed"] = True
    version_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")
    bad_patch = run_ip_version_check("--ip-dir", str(ip), "--require-ip-git", "--json")
    assert bad_patch.returncode != 0, bad_patch.stdout
    assert any(item["code"] == "IP_VERSION_PATCH_TRUTH_CHANGE" for item in json.loads(bad_patch.stdout)["issues"]), bad_patch.stdout


def write_stage_receipt(ip: Path, stage: str) -> None:
    receipt = {
        "schema_version": "stage_run_receipt.v1",
        "stage": stage,
        "owner": stage,
        "status": "pass",
        "command": "smoke-test",
        "actor": {"kind": "tool", "id": "smoke_test"},
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
        "input_fingerprints": [
            {"path": "rtl/rtl_compile.json", "sha256": sha256(ip / "rtl" / "rtl_compile.json")},
            {"path": "lint/dut_lint.json", "sha256": sha256(ip / "lint" / "dut_lint.json")},
        ],
        "output_fingerprints": [
            {"path": "sim/results.xml", "sha256": sha256(ip / "sim" / "results.xml")},
            {"path": "sim/scoreboard_events.jsonl", "sha256": sha256(ip / "sim" / "scoreboard_events.jsonl")},
        ],
    }
    out = ip / "ontology" / "evidence" / "stage_runs" / f"{stage}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def write_ip_validator_report(ip: Path) -> None:
    path = ip / "signoff" / "ip_validator_report.json"
    path.write_text(
        json.dumps({"schema_version": "ip_validator_report.v1", "status": "pass"}) + "\n",
        encoding="utf-8",
    )


def closure_gate_artifacts(ip: Path) -> list[str]:
    candidates = [
        "knowledge/validations/oag_validation_report.json",
        "rtl/rtl_compile.json",
        "lint/dut_lint.json",
        "sim/results.xml",
        "sim/scoreboard_events.jsonl",
        "cov/coverage.json",
        "ontology/generated/design_truth_graph.json",
        "ontology/generated/design_facts_graph.json",
        "signoff/truth_coverage.json",
    ]
    return [rel for rel in candidates if (ip / rel).is_file()]


def close_demo_counter(ip: Path, *, claim: str, evidence_files: list[str] | None = None) -> dict:
    return call(
        {
            "tool": "oag.record",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "type": "finding",
                "claim": claim,
                "summary": "development validator smoke evidence closes the counter scoreboard obligation",
                "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                "rocev": {
                    "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN", "text": "scoreboard has no mismatches"},
                    "contract": {
                        "id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                        "method": "scoreboard",
                        "pass_condition": "mismatch count is zero",
                    },
                    "evidence": {
                        "files": evidence_files or ["sim/results.xml", "sim/scoreboard_events.jsonl"],
                        "tests": [],
                        "commit": "",
                    },
                    "validation": {"status": "closed", "verdict": "pass", "rationale": "all development validator gates have evidence"},
                },
            },
        }
    )


def write_closure_reports(ip: Path, *, gate_decision: str = "PASS") -> None:
    validation_path = ip / "knowledge" / "validations" / "oag_validation_report.json"
    gate_path = ip / "knowledge" / "gate_reviews" / "oag_gate_decision.json"
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(
        json.dumps(
            {
                "schema_version": "oag_validation_report.v1",
                "product_name": "IP Dev Agent",
                "internal_gateway": "Ontology Agent Gateway",
                "ip_id": ip.name,
                "role_name": "oag-evidence-validator",
                "status": "pass",
                "closure_matrix": {"status": "pass", "open_count": 0},
                "evidence": {"status": "pass"},
                "mutation_guard": {"status": "pass"},
                "coverage": {"status": "pass"},
                "issues": [],
                "created_at": "2026-01-01T00:00:00Z",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    checked_artifacts = closure_gate_artifacts(ip)
    gate_path.write_text(
        json.dumps(
            {
                "schema_version": "oag_gate_decision.v1",
                "product_name": "IP Dev Agent",
                "internal_gateway": "Ontology Agent Gateway",
                "ip_id": ip.name,
                "role_name": "oag-gate-reviewer",
                "decision": gate_decision,
                "validation_report": "knowledge/validations/oag_validation_report.json",
                "checked_artifacts": checked_artifacts,
                "checked_artifact_hashes": {rel: sha256(ip / rel) for rel in checked_artifacts},
                "blockers": [] if gate_decision == "PASS" else ["smoke blocker"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        session_start_hooks = hooks["hooks"]["SessionStart"][0]["hooks"]
        assert session_start_hooks[0]["command"] == "python3 .claude/hooks/claude_oag_session_start.py", hooks
        user_hooks = hooks["hooks"]["UserPromptSubmit"][0]["hooks"]
        assert user_hooks[0]["command"] == "python3 .claude/hooks/claude_oag_mode_trigger.py", hooks
        assert user_hooks[1]["command"] == "python3 .claude/hooks/claude_native_subagent_guard.py", hooks
        assert user_hooks[2]["command"] == "python3 .claude/hooks/claude_context_inject.py", hooks
        assert user_hooks[3]["command"] == "python3 .claude/hooks/claude_draft_pressure.py", hooks
        stop_hooks = hooks["hooks"]["Stop"][0]["hooks"]
        stop_command = stop_hooks[0]["command"]
        assert "claude_stop_gate.py" in stop_command, hooks
        assert "PYTHONDONTWRITEBYTECODE=1" in stop_command, hooks
        assert "|| exit 0" in stop_command, hooks
        subagent_start_hooks = hooks["hooks"]["SubagentStart"][0]
        assert subagent_start_hooks["matcher"] == "^oag-", hooks
        assert subagent_start_hooks["hooks"][0]["command"] == "python3 .claude/hooks/claude_subagent_oag_start.py", hooks
        subagent_hooks = hooks["hooks"]["SubagentStop"][0]
        assert "oag-" in subagent_hooks["matcher"], hooks
        assert "evidence-validator" in subagent_hooks["matcher"], hooks
        assert "gate-reviewer" in subagent_hooks["matcher"], hooks
        assert subagent_hooks["hooks"][0]["command"] == "python3 .claude/hooks/claude_subagent_oag_gate.py", hooks
        post_compact_hooks = hooks["hooks"]["PostCompact"][0]["hooks"]
        assert post_compact_hooks[0]["command"] == "python3 .claude/hooks/claude_context_inject.py", hooks
        assert STOP_GATE.is_file(), STOP_GATE
        assert SUBAGENT_START.is_file(), SUBAGENT_START
        assert SUBAGENT_GATE.is_file(), SUBAGENT_GATE
        assert OAG_MODE_TRIGGER.is_file(), OAG_MODE_TRIGGER
        assert NATIVE_SUBAGENT_GUARD.is_file(), NATIVE_SUBAGENT_GUARD
        assert OAG_SESSION_START.is_file(), OAG_SESSION_START
        assert CONTEXT_HOOK.is_file(), CONTEXT_HOOK
        assert DRAFT_HOOK.is_file(), DRAFT_HOOK
        assert PORTABLE_DB.is_file(), PORTABLE_DB
        assert OKF.is_file(), OKF
        assert EVAL.is_file(), EVAL
        assert ANSWER_KEY_EVAL.is_file(), ANSWER_KEY_EVAL
        assert DEV_VALIDATOR.is_file(), DEV_VALIDATOR
        assert SPEC_RTL_LOOP.is_file(), SPEC_RTL_LOOP
        test_pyslang_lint_runner()
        test_wavefront_scheduler(Path(tmp))
        test_artifact_lifecycle_checker(Path(tmp))
        test_authoring_packet_lifecycle_firewall(Path(tmp))
        test_stale_propagation_checker(Path(tmp))
        test_baseline_manifest_checker(Path(tmp))
        test_baseline_cut_helper(Path(tmp))
        test_baseline_verify_git_tag(Path(tmp))
        test_ip_version_policy_checker(Path(tmp))
        assert DISPATCH.is_file(), DISPATCH
        assert WAVEFRONT.is_file(), WAVEFRONT
        assert MAIN_WRITE_GATE.is_file(), MAIN_WRITE_GATE
        assert VALIDATE_JSON.is_file(), VALIDATE_JSON
        assert AGENT_CATALOG_CHECK.is_file(), AGENT_CATALOG_CHECK
        assert CODEX_CONFIG_DOCTOR.is_file(), CODEX_CONFIG_DOCTOR
        assert CLOSURE_CHECK.is_file(), CLOSURE_CHECK
        assert PACK_RELEASE_CHECK.is_file(), PACK_RELEASE_CHECK
        assert DOMAIN_CROSSING_CHECK.is_file(), DOMAIN_CROSSING_CHECK
        test_oag_paths_resolver(Path(tmp))
        test_dot_oag_layout_state_scripts(Path(tmp))
        test_dot_oag_scaffold_layout(Path(tmp))
        test_dot_oag_migration_tool(Path(tmp))
        test_dot_oag_mixed_layout_rejected(Path(tmp))
        assert PYSLANG_LINT.is_file(), PYSLANG_LINT
        assert REQ_QUALITY_CHECK.is_file(), REQ_QUALITY_CHECK
        assert LOCK_READINESS_CHECK.is_file(), LOCK_READINESS_CHECK
        assert CONTRACT_STRENGTH_CHECK.is_file(), CONTRACT_STRENGTH_CHECK
        assert AUTHORING_PACKET_CHECK.is_file(), AUTHORING_PACKET_CHECK
        assert TRACE_GRAPH_CHECK.is_file(), TRACE_GRAPH_CHECK
        assert DEEP_SEMANTIC_INTAKE.is_file(), DEEP_SEMANTIC_INTAKE
        assert DECISION_MATRIX_GENERATE.is_file(), DECISION_MATRIX_GENERATE
        assert LIFECYCLE_CHECK.is_file(), LIFECYCLE_CHECK
        assert BASELINE_CHECK.is_file(), BASELINE_CHECK
        assert STALE_CHECK.is_file(), STALE_CHECK
        assert BASELINE_CUT.is_file(), BASELINE_CUT
        assert BASELINE_VERIFY.is_file(), BASELINE_VERIFY
        assert IP_VERSION_CHECK.is_file(), IP_VERSION_CHECK
        assert AGENT_CATALOG.is_file(), AGENT_CATALOG
        assert OAG_MODE_DIRECTIVE.is_file(), OAG_MODE_DIRECTIVE
        assert SUBAGENT_WORKFLOWS.is_file(), SUBAGENT_WORKFLOWS
        assert OAG_RULE_INDEX.is_file(), OAG_RULE_INDEX
        assert OAG_IP_WORKFLOW_SKILL.is_file(), OAG_IP_WORKFLOW_SKILL
        assert OAG_DEEP_SEMANTIC_SKILL.is_file(), OAG_DEEP_SEMANTIC_SKILL
        assert OAG_DECISION_MATRIX_SKILL.is_file(), OAG_DECISION_MATRIX_SKILL
        assert OAG_CONTRACT_PROJECTION_SKILL.is_file(), OAG_CONTRACT_PROJECTION_SKILL
        assert OAG_AUTHORING_PACKET_SKILL.is_file(), OAG_AUTHORING_PACKET_SKILL
        assert OAG_EVIDENCE_CLOSURE_SKILL.is_file(), OAG_EVIDENCE_CLOSURE_SKILL
        assert OAG_WAVEFRONT_SKILL.is_file(), OAG_WAVEFRONT_SKILL
        assert OAG_WAVEFRONT_TEMPLATE.is_file(), OAG_WAVEFRONT_TEMPLATE
        assert OAG_DATA_LIFECYCLE_POLICY.is_file(), OAG_DATA_LIFECYCLE_POLICY
        assert OAG_BASELINE_GIT_POLICY.is_file(), OAG_BASELINE_GIT_POLICY
        assert OAG_IP_VERSIONING_POLICY.is_file(), OAG_IP_VERSIONING_POLICY
        assert OAG_IP_VERSIONING_SKILL.is_file(), OAG_IP_VERSIONING_SKILL
        assert OAG_IP_VERSIONING_RULES.is_file(), OAG_IP_VERSIONING_RULES
        for schema_file in SCHEMA_FILES:
            assert schema_file.is_file(), schema_file
            schema_payload = json.loads(schema_file.read_text(encoding="utf-8"))
            assert "$schema" in schema_payload and "required" in schema_payload, schema_payload
        assert not (ROOT / "agents" / "oag-agent-catalog.toml").exists()
        assert all(path.suffix == ".md" for path in (ROOT / "agents").iterdir() if path.is_file())
        agent_catalog_check = run_agent_catalog_check()
        assert agent_catalog_check.returncode == 0, agent_catalog_check.stderr or agent_catalog_check.stdout
        agent_catalog_result = json.loads(agent_catalog_check.stdout)
        assert agent_catalog_result["status"] == "pass", agent_catalog_result
        assert agent_catalog_result["counts"] == {"core": 15, "custom": 3, "total": 18, "markdown_files": 18}, agent_catalog_result
        assert agent_catalog_result["completion_authority"] == ["oag-gate-reviewer"], agent_catalog_result
        assert agent_catalog_result["final_decision_authority"] == ["oag-gate-reviewer"], agent_catalog_result
        pack_release_check = run_pack_release_check()
        assert pack_release_check.returncode == 0, pack_release_check.stderr or pack_release_check.stdout
        pack_release_result = json.loads(pack_release_check.stdout)
        assert pack_release_result["status"] == "pass", pack_release_result
        assert pack_release_result["counts"]["agent_markdowns"] == 18, pack_release_result
        assert pack_release_result["counts"]["schemas"] >= 4, pack_release_result
        ppa_bad_ip = Path(tmp) / "ppa_bad_function"
        (ppa_bad_ip / "rtl").mkdir(parents=True)
        (ppa_bad_ip / "list").mkdir(parents=True)
        (ppa_bad_ip / "list" / "rtl.f").write_text("rtl/bad_function.sv\n", encoding="utf-8")
        (ppa_bad_ip / "rtl" / "bad_function.sv").write_text(
            "\n".join(
                [
                    "module bad_function(input logic a, output logic y);",
                    "  function logic helper;",
                    "    input logic in;",
                    "    begin",
                    "      helper = in;",
                    "    end",
                    "  endfunction",
                    "  assign y = helper(a);",
                    "endmodule",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        ppa_bad = subprocess.run(
            [sys.executable, str(PPA_CHECK), "--ip-dir", str(ppa_bad_ip), "--json"],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert ppa_bad.returncode == 1, ppa_bad.stderr or ppa_bad.stdout
        ppa_bad_result = json.loads(ppa_bad.stdout)
        assert ppa_bad_result["status"] == "fail", ppa_bad_result
        assert ppa_bad_result["scanned_files"] == ["rtl/bad_function.sv"], ppa_bad_result
        assert any(issue["code"] == "FUNCTION" for issue in ppa_bad_result["issues"]), ppa_bad_result
        ppa_good_ip = Path(tmp) / "ppa_good_generate"
        (ppa_good_ip / "rtl").mkdir(parents=True)
        (ppa_good_ip / "list").mkdir(parents=True)
        (ppa_good_ip / "list" / "rtl.f").write_text("rtl/good_generate.sv\n", encoding="utf-8")
        (ppa_good_ip / "rtl" / "good_generate.sv").write_text(
            "\n".join(
                [
                    "module good_generate(input logic [1:0] a, output logic [1:0] y);",
                    "  genvar gi;",
                    "  generate",
                    "    for (gi = 0; gi < 2; gi = gi + 1) begin : gen_bits",
                    "      assign y[gi] = a[gi];",
                    "    end",
                    "  endgenerate",
                    "endmodule",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        ppa_good = subprocess.run(
            [sys.executable, str(PPA_CHECK), "--ip-dir", str(ppa_good_ip), "--json"],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert ppa_good.returncode == 0, ppa_good.stderr or ppa_good.stdout
        ppa_good_result = json.loads(ppa_good.stdout)
        assert ppa_good_result["status"] == "pass", ppa_good_result
        subagent_workflows = SUBAGENT_WORKFLOWS.read_text(encoding="utf-8")
        assert "multi_agent_v1.spawn_agent" in subagent_workflows, subagent_workflows
        assert "agent_type" in subagent_workflows, subagent_workflows
        assert "native Claude Code collaboration workers" in subagent_workflows, subagent_workflows
        assert "SubagentStart" in subagent_workflows, subagent_workflows
        assert "generated tool output" in subagent_workflows, subagent_workflows
        assert "STATIC_HANDOFF_PASS" in subagent_workflows, subagent_workflows
        assert "git status --short -uall -- <ip>" in subagent_workflows, subagent_workflows
        assert "After user lock, main agent orchestrates" in subagent_workflows, subagent_workflows
        assert "oag_main_write_gate.py" in subagent_workflows, subagent_workflows
        assert "oag_exec_auto_research.py" in subagent_workflows, subagent_workflows
        assert "claude exec resume" in subagent_workflows, subagent_workflows
        assert "spawn_agent" in subagent_workflows and ".claude/runs/auto_research/" in subagent_workflows, subagent_workflows
        assert "oag-verification-strategy-agent" in subagent_workflows, subagent_workflows
        assert "ontology/verification_plan.yaml" in subagent_workflows, subagent_workflows
        skill_text = OAG_IP_WORKFLOW_SKILL.read_text(encoding="utf-8")
        agents_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        directive_text = OAG_MODE_DIRECTIVE.read_text(encoding="utf-8")
        assert "python3 scripts/" not in skill_text, skill_text
        assert "python3 .claude/scripts/oag_cli.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_agent_catalog_check.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_closure_check.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_req_quality_check.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_lock_readiness_check.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_contract_strength_check.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_authoring_packet_check.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_trace_graph_check.py" in skill_text, skill_text
        assert "oag_deep_semantic_intake.py" in skill_text, skill_text
        assert "oag_decision_matrix_generate.py" in skill_text, skill_text
        assert "python3 .claude/scripts/oag_verification_plan_check.py" in skill_text, skill_text
        assert "oag_pyslang_lint.py" in skill_text, skill_text
        assert "Skill Router" in skill_text, skill_text
        assert "oag-deep-semantic-intake" in skill_text, skill_text
        assert "oag-decision-matrix" in skill_text, skill_text
        assert "oag-contract-projection" in skill_text, skill_text
        assert "oag-authoring-packet" in skill_text, skill_text
        assert "oag-wavefront" in skill_text, skill_text
        assert "oag_wavefront.py" in skill_text, skill_text
        assert "oag-evidence-closure" in skill_text, skill_text
        assert "SubagentStart" in skill_text, skill_text
        assert "generated tool output" in skill_text, skill_text
        assert "STATIC_HANDOFF_PASS" in skill_text, skill_text
        assert "New IP Intake Guard" in skill_text, skill_text
        assert "Scope Lock" in skill_text, skill_text
        assert "oag.lock_status" in skill_text, skill_text
        assert "No lock, no RTL" in skill_text, skill_text
        assert "After user lock, main agent orchestrates" in skill_text, skill_text
        assert "oag_main_write_gate.py" in skill_text, skill_text
        assert "short IP request" in skill_text, skill_text
        assert "do not enrich or rewrite `req/locked_truth.md`" in skill_text, skill_text
        assert "single-packet versus multi-packet" in skill_text, skill_text
        rule_index_text = OAG_RULE_INDEX.read_text(encoding="utf-8")
        assert "RULE-LOCK-003" in rule_index_text, rule_index_text
        assert "RULE-CONTRACT-AG-001" in rule_index_text, rule_index_text
        assert "RULE-PACKET-ROLE-001" in rule_index_text, rule_index_text
        assert "RULE-TRACE-001" in rule_index_text, rule_index_text
        assert "RULE-WAVE-001" in rule_index_text, rule_index_text
        assert "RULE-IPVER-001" in rule_index_text, rule_index_text
        decision_skill_text = OAG_DECISION_MATRIX_SKILL.read_text(encoding="utf-8")
        contract_skill_text = OAG_CONTRACT_PROJECTION_SKILL.read_text(encoding="utf-8")
        packet_skill_text = OAG_AUTHORING_PACKET_SKILL.read_text(encoding="utf-8")
        wavefront_skill_text = OAG_WAVEFRONT_SKILL.read_text(encoding="utf-8")
        ip_versioning_skill_text = OAG_IP_VERSIONING_SKILL.read_text(encoding="utf-8")
        closure_skill_text = OAG_EVIDENCE_CLOSURE_SKILL.read_text(encoding="utf-8")
        assert "oag_decision_matrix_generate.py" in decision_skill_text, decision_skill_text
        assert "lock_required: true" in decision_skill_text, decision_skill_text
        assert "assume" in contract_skill_text and "guarantee" in contract_skill_text, contract_skill_text
        assert "oag_contract_strength_check.py" in contract_skill_text, contract_skill_text
        assert "rtl__*.json" in packet_skill_text and "tb__*.json" in packet_skill_text, packet_skill_text
        assert "oag_authoring_packet_check.py" in packet_skill_text, packet_skill_text
        assert "dependency" in wavefront_skill_text and "ownership" in wavefront_skill_text, wavefront_skill_text
        assert "oag_wavefront.py" in wavefront_skill_text, wavefront_skill_text
        assert "oag_ip_version_check.py" in ip_versioning_skill_text, ip_versioning_skill_text
        assert "IP-local" in ip_versioning_skill_text, ip_versioning_skill_text
        assert "oag_closure_check.py" in closure_skill_text, closure_skill_text
        assert "claim_complete" in closure_skill_text, closure_skill_text
        assert "Short IP requests are not implementation authorization" in agents_text, agents_text
        assert "scope_lock.json" in agents_text, agents_text
        assert "No lock, no RTL" in agents_text, agents_text
        assert "oag_req_quality_check.py" in agents_text, agents_text
        assert "req/source_claims.yaml" in agents_text, agents_text
        assert "req/ambiguity_register.yaml" in agents_text, agents_text
        assert "oag_lock_readiness_check.py" in agents_text, agents_text
        assert "oag_contract_strength_check.py" in agents_text, agents_text
        assert "oag_authoring_packet_check.py" in agents_text, agents_text
        assert "oag_wavefront.py" in agents_text, agents_text
        assert "oag_ip_version_check.py" in agents_text, agents_text
        assert "oag_trace_graph_check.py" in agents_text, agents_text
        assert "oag_deep_semantic_intake.py" in agents_text, agents_text
        assert "oag_decision_matrix_generate.py" in agents_text, agents_text
        assert "oag_verification_plan_check.py" in agents_text, agents_text
        assert "ontology/verification_plan.yaml" in agents_text, agents_text
        assert "After user lock, main agent orchestrates" in agents_text, agents_text
        assert "oag_main_write_gate.py" in agents_text, agents_text
        assert "oag_exec_auto_research.py" in agents_text, agents_text
        assert "A short IP request is requirement-interview input" in directive_text, directive_text
        assert "oag.lock_status" in directive_text, directive_text
        assert "No lock, no RTL" in directive_text, directive_text
        assert "oag_req_quality_check.py" in directive_text, directive_text
        assert "req/source_claims.yaml" in directive_text, directive_text
        assert "req/ambiguity_register.yaml" in directive_text, directive_text
        assert "oag_lock_readiness_check.py" in directive_text, directive_text
        assert "oag_contract_strength_check.py" in directive_text, directive_text
        assert "oag_authoring_packet_check.py" in directive_text, directive_text
        assert "oag_ip_version_check.py" in directive_text, directive_text
        assert "oag_trace_graph_check.py" in directive_text, directive_text
        assert "oag_deep_semantic_intake.py" in directive_text, directive_text
        assert "oag_decision_matrix_generate.py" in directive_text, directive_text
        assert "oag_verification_plan_check.py" in directive_text, directive_text
        assert "ontology/verification_plan.yaml" in directive_text, directive_text
        assert "ontology/generated/authoring_packets" in directive_text, directive_text
        assert "rtl__*.json" in directive_text, directive_text
        assert "tb__*.json" in directive_text, directive_text
        assert "After user lock, main agent orchestrates" in directive_text, directive_text
        assert "oag_main_write_gate.py" in directive_text, directive_text
        assert "find .. -name AGENTS.md" in skill_text, skill_text
        assert "Do not run a Python" in subagent_workflows and "manual role-play substitute" in subagent_workflows, subagent_workflows
        assert "first attempt a minimal explicit" in subagent_workflows and "native spawn" in subagent_workflows, subagent_workflows
        assert "observed" in subagent_workflows and "native-spawn blocker" in subagent_workflows, subagent_workflows
        assert "BLOCKED: native Claude Code subagent unavailable in this surface" not in subagent_workflows, subagent_workflows
        config_text = (ROOT / "config.toml").read_text(encoding="utf-8")
        user_home_prefix = "/" + "Users/"
        assert user_home_prefix not in config_text, config_text
        assert 'multi_agent = true' in config_text, config_text
        assert 'child_agents_md = true' in config_text, config_text
        assert 'enabled = false' in config_text, config_text
        assert 'max_concurrent_threads_per_session = 10000' in config_text, config_text
        assert 'max_depth = 1' in config_text, config_text
        assert "mcp_servers" not in config_text, config_text

        dry_run_root = Path(tmp) / "exec_auto_research_runs"
        exec_auto_research = subprocess.run(
            [
                sys.executable,
                str(EXEC_AUTO_RESEARCH),
                "--ip-dir",
                "timer_ip",
                "--objective",
                "dry-run wrapper contract check",
                "--run-root",
                str(dry_run_root),
                "--dry-run",
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=PROJECT_ROOT,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert exec_auto_research.returncode == 0, exec_auto_research.stderr or exec_auto_research.stdout
        exec_auto_research_result = json.loads(exec_auto_research.stdout)
        assert exec_auto_research_result["status"] == "dry_run", exec_auto_research_result
        assert exec_auto_research_result["dry_run"] is True, exec_auto_research_result
        assert exec_auto_research_result["prompt_sha256"], exec_auto_research_result
        prompt_text = Path(exec_auto_research_result["prompt_path"]).read_text(encoding="utf-8")
        assert "claude exec" in " ".join(exec_auto_research_result["command_preview"]), exec_auto_research_result
        assert "spawn_agent" in prompt_text, prompt_text
        assert "Use a native Claude Code subagent. Spawn one built-in explorer subagent." in prompt_text, prompt_text
        assert "Do not run parent-side shell commands before the native spawn attempt" in prompt_text, prompt_text
        assert "Product root:" in prompt_text, prompt_text
        assert "from the product root, not from inside the IP directory" in prompt_text, prompt_text
        assert "Do not decide native-spawn availability from the visible callable tool namespace alone" in prompt_text, prompt_text
        assert "built-in explorer-style native subagent" in prompt_text, prompt_text
        assert "not an OAG custom/write-capable role" in prompt_text, prompt_text
        assert "FINAL_AUTO_RESEARCH_SUMMARY" in prompt_text, prompt_text
        gitignore_path = PROJECT_ROOT / ".gitignore"
        if gitignore_path.is_file():
            gitignore_text = gitignore_path.read_text(encoding="utf-8")
            assert ".claude/runs/" in gitignore_text, gitignore_text

        claude_home = Path(tmp) / "claude_home"
        claude_home.mkdir(parents=True, exist_ok=True)
        user_config = claude_home / "config.toml"
        legacy_oag_mcp_server = "ontology" + "-ip-agent-oag"
        legacy_oag_mcp_path = "/old/" + "ontology" + "_ip_agent/.claude/scripts/oag_mcp_server.py"
        user_config.write_text(
            "\n".join(
                [
                    "[features]",
                    "multi_agent = false",
                    "child_agents_md = false",
                    "hooks = false",
                    "multi_agent_v2 = true",
                    "",
                    "[features.multi_agent_v2]",
                    "enabled = true",
                    "max_concurrent_threads_per_session = 1",
                    "",
                    "[agents]",
                    "max_depth = 0",
                    "",
                    "[mcp_servers.ip-dev-agent-oag]",
                    'command = "python3"',
                    'args = [".claude/scripts/oag_mcp_server.py"]',
                    "",
                    "[mcp_servers.ip-dev-agent-oag.env]",
                    'OAG_ACTOR_SURFACE = "claude-mcp"',
                    "",
                    f"[mcp_servers.{legacy_oag_mcp_server}]",
                    'command = "python3"',
                    f'args = ["{legacy_oag_mcp_path}"]',
                    "",
                    "[mcp_servers.node_repl]",
                    'command = "/Applications/Claude Code.app/Contents/Resources/cua_node/bin/node_repl"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        session_migration = session_start_hook({"hook_event_name": "SessionStart"}, {"CODEX_HOME": str(claude_home)})
        assert session_migration.returncode == 0, session_migration.stderr or session_migration.stdout
        migrated_config = user_config.read_text(encoding="utf-8")
        assert "multi_agent = true" in migrated_config, migrated_config
        assert "child_agents_md = true" in migrated_config, migrated_config
        assert "hooks = true" in migrated_config, migrated_config
        assert "plugins = true" in migrated_config, migrated_config
        assert "plugin_hooks = true" in migrated_config, migrated_config
        assert "multi_agent_v2 = true" not in migrated_config, migrated_config
        assert "enabled = false" in migrated_config, migrated_config
        assert "max_concurrent_threads_per_session = 10000" in migrated_config, migrated_config
        assert "max_depth = 1" in migrated_config, migrated_config
        assert "openai/claude#26753" in migrated_config, migrated_config
        assert "ip-dev-agent-oag" not in migrated_config, migrated_config
        assert legacy_oag_mcp_server not in migrated_config, migrated_config
        assert "oag_mcp_server.py" not in migrated_config, migrated_config
        assert "[mcp_servers.node_repl]" in migrated_config, migrated_config
        assert "OAG CODEX CONFIG MIGRATION" in hook_context(session_migration), session_migration.stdout

        session_idempotent = session_start_hook({"hook_event_name": "SessionStart"}, {"CODEX_HOME": str(claude_home)})
        assert session_idempotent.returncode == 0, session_idempotent.stderr or session_idempotent.stdout
        assert session_idempotent.stdout == "", session_idempotent.stdout

        trigger_silent = oag_mode_trigger({"prompt": "rtl work"})
        assert trigger_silent.returncode == 0, trigger_silent.stderr or trigger_silent.stdout
        assert trigger_silent.stdout == "", trigger_silent.stdout
        for prompt in ("ipdev use subagent for timer", "auto research timer", "subagent for timer", "signoff timer", "rocev timer"):
            non_oag_trigger = oag_mode_trigger({"prompt": prompt})
            assert non_oag_trigger.returncode == 0, non_oag_trigger.stderr or non_oag_trigger.stdout
            assert non_oag_trigger.stdout == "", non_oag_trigger.stdout
        guard_silent = native_subagent_guard({"prompt": "auto research timer"})
        assert guard_silent.returncode == 0, guard_silent.stderr or guard_silent.stdout
        assert guard_silent.stdout == "", guard_silent.stdout
        guard_on = native_subagent_guard({"prompt": "Use sub agent to make req in detail"})
        assert guard_on.returncode == 0, guard_on.stderr or guard_on.stdout
        guard_context = hook_context(guard_on)
        assert "NATIVE CODEX SUBAGENT GUARD" in guard_context, guard_on.stdout
        assert "first attempt a minimal read-only native spawn" in guard_context, guard_on.stdout
        assert "Do not answer BLOCKED or report an observed native-spawn blocker before an actual `spawn_agent` attempt fails" in guard_context, guard_on.stdout
        assert "Do not decide native-spawn availability from the visible callable tool namespace alone" in guard_context, guard_on.stdout
        assert "explicitly request the native `spawn_agent` collaboration event" in guard_context, guard_on.stdout
        assert "Do not run `omo run --agent`" in guard_context, guard_on.stdout
        assert "observed native-spawn blocker" in guard_context, guard_on.stdout
        assert "BLOCKED: native Claude Code subagent unavailable in this surface" not in guard_context, guard_on.stdout
        assert "OAG MODE ENABLED!" not in guard_context, guard_on.stdout
        trigger_on = oag_mode_trigger({"prompt": "oag use subagent for timer"})
        assert trigger_on.returncode == 0, trigger_on.stderr or trigger_on.stdout
        trigger_context = hook_context(trigger_on)
        assert "OAG MODE ENABLED!" in trigger_context, trigger_on.stdout
        assert "Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision" in trigger_context, trigger_on.stdout
        assert "short IP request is requirement-interview input" in trigger_context, trigger_on.stdout
        assert "multi_agent_v1.spawn_agent" in trigger_context, trigger_on.stdout
        assert "oag.lock_status" in trigger_context, trigger_on.stdout
        assert "No lock, no RTL" in trigger_context, trigger_on.stdout
        assert "record_decision=true" in trigger_context, trigger_on.stdout

        hook_cwd = Path(tmp) / "subagent_hook_project"
        hook_cwd.mkdir(parents=True, exist_ok=True)
        start_cache = Path(tmp) / "subagent_start_events.jsonl"
        start_payload = {
            "hook_event_name": "SubagentStart",
            "agent_type": "oag-rtl-implementation-agent",
            "agent_id": "rtl-worker-1",
            "session_id": "smoke-session",
            "cwd": str(hook_cwd),
            "model": "gpt-5.5",
            "permission_mode": "default",
        }
        start_hook = subagent_start(start_payload, {"OAG_SUBAGENT_START_CACHE": str(start_cache)})
        assert start_hook.returncode == 0, start_hook.stderr or start_hook.stdout
        start_context = hook_context(start_hook)
        assert "OAG SUBAGENT START CONTRACT" in start_context, start_hook.stdout
        assert "STATIC_HANDOFF_PASS" in start_context, start_hook.stdout
        assert "Short IP intake guard" in start_context, start_hook.stdout
        assert "single-packet versus multi-packet" in start_context, start_hook.stdout
        assert "Scope lock guard" in start_context, start_hook.stdout
        assert "scope_lock.json state=locked" in start_context, start_hook.stdout
        assert "OAG_EVIDENCE_RECORDED" in start_context, start_hook.stdout
        assert start_cache.is_file(), start_cache
        start_event = json.loads(start_cache.read_text(encoding="utf-8").splitlines()[-1])
        assert start_event["schema_version"] == "oag_subagent_start_event.v1", start_event
        assert start_event["agent_type"] == "oag-rtl-implementation-agent", start_event
        transcript_path = Path(tmp) / "subagent_transcript.txt"
        transcript_path.write_text("normal transcript\n", encoding="utf-8")
        invalid_payload = {
            "hook_event_name": "SubagentStop",
            "agent_type": "oag-custom-worker",
            "agent_id": "worker-1",
            "session_id": "smoke-session",
            "cwd": str(hook_cwd),
            "transcript_path": str(transcript_path),
            "model": "gpt-5.5",
            "permission_mode": "default",
            "stop_hook_active": False,
            "last_assistant_message": "done without receipt",
        }
        invalid_gate = subagent_gate(invalid_payload, {"OAG_SUBAGENT_GATE_CACHE": str(Path(tmp) / "subagent_gate_cache.json")})
        assert invalid_gate.returncode == 0, invalid_gate.stderr or invalid_gate.stdout
        invalid_gate_payload = json.loads(invalid_gate.stdout)
        assert invalid_gate_payload["decision"] == "block", invalid_gate_payload
        assert "OAG_EVIDENCE_RECORDED" in invalid_gate_payload["reason"], invalid_gate_payload
        subprocess.run(["git", "init"], cwd=hook_cwd, text=True, capture_output=True, check=True)
        unlocked_hook_ip = hook_cwd / "unlocked_smoke_ip"
        (unlocked_hook_ip / "rtl").mkdir(parents=True, exist_ok=True)
        (unlocked_hook_ip / "knowledge" / "subagents").mkdir(parents=True, exist_ok=True)
        unlocked_dispatch = run_dispatch(
            "create",
            "--ip-dir",
            str(unlocked_hook_ip),
            "--agent-type",
            "oag-custom-worker",
            "--role-kind",
            "custom",
            "--stage",
            "rtl",
            "--allowed-write-path",
            str(unlocked_hook_ip / "rtl" / "smoke.sv"),
            "--receipt-path",
            str(unlocked_hook_ip / "knowledge" / "subagents" / "smoke.json"),
            "--json",
            project_root=hook_cwd,
        )
        assert unlocked_dispatch.returncode != 0, unlocked_dispatch.stdout
        assert "scope lock required" in (unlocked_dispatch.stderr + unlocked_dispatch.stdout), unlocked_dispatch.stderr or unlocked_dispatch.stdout
        main_gate_ip = hook_cwd / "main_gate_ip"
        (main_gate_ip / "ontology").mkdir(parents=True, exist_ok=True)
        (main_gate_ip / "rtl").mkdir(parents=True, exist_ok=True)
        (main_gate_ip / "ontology" / "scope_lock.json").write_text(
            json.dumps(
                {
                    "schema_version": "oag_scope_lock.v1",
                    "ip": "main_gate_ip",
                    "state": "locked",
                    "summary": "Smoke scope is locked before implementation.",
                    "confirmed_scope": ["main write gate smoke"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (main_gate_ip / "rtl" / "direct_main.sv").write_text("module direct_main; endmodule\n", encoding="utf-8")
        main_gate_blocked = run_main_write_gate(main_gate_ip, project_root=hook_cwd)
        assert main_gate_blocked.returncode != 0, main_gate_blocked.stdout
        main_gate_payload = json.loads(main_gate_blocked.stdout)
        assert main_gate_payload["status"] == "fail", main_gate_payload
        assert main_gate_payload["issues"][0]["code"] == "MAIN_AGENT_WRITE_WITHOUT_SUBAGENT", main_gate_payload
        stop_gate_blocked = stop_gate({"ip_dir": str(main_gate_ip)}, {"OAG_PROJECT_ROOT": str(hook_cwd)})
        assert stop_gate_blocked.returncode == 0, stop_gate_blocked.stderr or stop_gate_blocked.stdout
        stop_gate_payload = json.loads(stop_gate_blocked.stdout)
        assert stop_gate_payload["decision"] == "block", stop_gate_payload
        assert "locked implementation write requires native subagent evidence" in stop_gate_payload["reason"], stop_gate_payload
        hook_ip = hook_cwd / "smoke_ip"
        (hook_ip / "rtl").mkdir(parents=True, exist_ok=True)
        (hook_ip / "ontology").mkdir(parents=True, exist_ok=True)
        (hook_ip / "knowledge" / "subagents").mkdir(parents=True, exist_ok=True)
        (hook_ip / "ontology" / "scope_lock.json").write_text(
            json.dumps(
                {
                    "schema_version": "oag_scope_lock.v1",
                    "ip": "smoke_ip",
                    "state": "locked",
                    "summary": "Smoke dispatch scope is locked.",
                    "confirmed_scope": ["rtl smoke dispatch"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        dispatch_create = run_dispatch(
            "create",
            "--ip-dir",
            str(hook_ip),
            "--agent-type",
            "oag-custom-worker",
            "--role-kind",
            "custom",
            "--stage",
            "rtl",
            "--owned-obligation",
            "OBL_SMOKE",
            "--contract",
            "CONTRACT_SMOKE",
            "--allowed-write-path",
            str(hook_ip / "rtl" / "smoke.sv"),
            "--allowed-write-path",
            str(hook_ip / "knowledge" / "subagents"),
            "--allowed-tool-side-effect",
            str(hook_ip / "ontology" / "generated"),
            "--receipt-path",
            str(hook_ip / "knowledge" / "subagents" / "smoke.json"),
            "--wavefront-run-id",
            "RUN_DISPATCH_SMOKE",
            "--task-id",
            "RTL_SMOKE_TASK",
            "--ownership-mode",
            "exclusive_file",
            "--json",
            project_root=hook_cwd,
        )
        assert dispatch_create.returncode == 0, dispatch_create.stderr or dispatch_create.stdout
        dispatch_result = json.loads(dispatch_create.stdout)
        dispatch = dispatch_result["dispatch"]
        assert dispatch["schema_version"] == "oag_dispatch.v1", dispatch
        assert "prompt_contract" in dispatch and "dispatch_id" in dispatch["prompt_contract"], dispatch
        assert dispatch["wavefront_run_id"] == "RUN_DISPATCH_SMOKE", dispatch
        assert dispatch["task_id"] == "RTL_SMOKE_TASK", dispatch
        assert "wavefront_run_id" in dispatch["prompt_contract"], dispatch
        dispatch_nonce = dispatch["dispatch_id"].rsplit("_", 1)[-1]
        assert len(dispatch_nonce) == 8 and all(char in "0123456789ABCDEF" for char in dispatch_nonce), dispatch
        (hook_ip / "rtl" / "smoke.sv").write_text("module smoke; endmodule\n", encoding="utf-8")
        receipt = hook_ip / "knowledge" / "subagents" / "smoke.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": "oag_subagent_receipt.v1",
                    "product_name": "IP Dev Agent",
                    "internal_gateway": "Ontology Agent Gateway",
                    "dispatch_id": dispatch["dispatch_id"],
                    "dispatch_path": dispatch["dispatch_path"],
                    "wavefront_run_id": "RUN_DISPATCH_SMOKE",
                    "task_id": "RTL_SMOKE_TASK",
                    "ownership_mode": "exclusive_file",
                    "role_name": "oag-custom-worker",
                    "shard_scope": "smoke",
                    "stage": "rtl",
                    "status": "STATIC_HANDOFF_PASS",
                    "owned_obligations": [],
                    "contracts": [],
                    "allowed_write_paths": dispatch["allowed_write_paths"],
                    "changed_paths": ["smoke_ip/rtl/smoke.sv"],
                    "generated_side_effects": [],
                    "evidence_outputs": [dispatch["receipt_path"]],
                    "may_claim_complete": False,
                    "created_at": "2026-01-01T00:00:00Z",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        receipt_validation = run_validate_json(ROOT / "schemas" / "oag_subagent_receipt.schema.json", receipt)
        assert receipt_validation.returncode == 0, receipt_validation.stderr or receipt_validation.stdout
        dispatch_verify = run_dispatch(
            "verify",
            "--dispatch",
            str(hook_cwd / dispatch["dispatch_path"]),
            "--receipt",
            str(receipt),
            "--json",
            project_root=hook_cwd,
        )
        assert dispatch_verify.returncode == 0, dispatch_verify.stderr or dispatch_verify.stdout
        main_gate_allowed = run_main_write_gate(hook_ip, project_root=hook_cwd)
        assert main_gate_allowed.returncode == 0, main_gate_allowed.stderr or main_gate_allowed.stdout
        main_gate_allowed_payload = json.loads(main_gate_allowed.stdout)
        assert main_gate_allowed_payload["status"] == "pass", main_gate_allowed_payload
        dispatch_verify_result = json.loads(dispatch_verify.stdout)
        assert dispatch_verify_result["status"] == "pass", dispatch_verify_result
        valid_payload = {**invalid_payload, "last_assistant_message": "OAG_EVIDENCE_RECORDED: smoke_ip/knowledge/subagents/smoke.json"}
        valid_gate = subagent_gate(valid_payload, {"OAG_SUBAGENT_GATE_CACHE": str(Path(tmp) / "subagent_gate_cache_valid.json")})
        assert valid_gate.returncode == 0, valid_gate.stderr or valid_gate.stdout
        assert valid_gate.stdout == "", valid_gate.stdout
        bad_receipt = hook_ip / "knowledge" / "subagents" / "bad_scope.json"
        bad_payload = json.loads(receipt.read_text(encoding="utf-8"))
        bad_payload["changed_paths"] = ["smoke_ip/list/rtl.f"]
        bad_payload["evidence_outputs"] = ["smoke_ip/knowledge/subagents/bad_scope.json"]
        bad_receipt.write_text(json.dumps(bad_payload, sort_keys=True) + "\n", encoding="utf-8")
        bad_verify = run_dispatch(
            "verify",
            "--dispatch",
            str(hook_cwd / dispatch["dispatch_path"]),
            "--receipt",
            str(bad_receipt),
            "--json",
            project_root=hook_cwd,
        )
        assert bad_verify.returncode != 0, bad_verify.stdout
        bad_verify_result = json.loads(bad_verify.stdout)
        assert any(item["code"] == "RECEIPT_PATH_MISMATCH" for item in bad_verify_result["issues"]), bad_verify_result
        assert any(item["code"] == "OWNED_PATH_OUT_OF_SCOPE" for item in bad_verify_result["issues"]), bad_verify_result
        (hook_ip / "rtl" / "unrelated_concurrent.sv").write_text("module unrelated_concurrent; endmodule\n", encoding="utf-8")
        concurrent_blocked_payload = json.loads(receipt.read_text(encoding="utf-8"))
        concurrent_blocked_payload["status"] = "BLOCKED"
        concurrent_blocked_payload["blockers"] = [
            "oag_dispatch.py verify reports only ACTUAL_PATH_OUT_OF_SCOPE deltas from unrelated concurrent workspace edits."
        ]
        receipt.write_text(json.dumps(concurrent_blocked_payload, sort_keys=True) + "\n", encoding="utf-8")
        concurrent_verify = run_dispatch(
            "verify",
            "--dispatch",
            str(hook_cwd / dispatch["dispatch_path"]),
            "--receipt",
            str(receipt),
            "--json",
            project_root=hook_cwd,
        )
        assert concurrent_verify.returncode != 0, concurrent_verify.stdout
        concurrent_verify_result = json.loads(concurrent_verify.stdout)
        concurrent_codes = {item["code"] for item in concurrent_verify_result["issues"]}
        assert concurrent_codes == {"ACTUAL_PATH_OUT_OF_SCOPE"}, concurrent_verify_result
        concurrent_gate = subagent_gate(valid_payload, {"OAG_SUBAGENT_GATE_CACHE": str(Path(tmp) / "subagent_gate_cache_concurrent.json")})
        assert concurrent_gate.returncode == 0, concurrent_gate.stderr or concurrent_gate.stdout
        assert concurrent_gate.stdout == "", concurrent_gate.stdout
        concurrent_unblocked_payload = {**concurrent_blocked_payload, "status": "RTL_HANDOFF_PASS"}
        concurrent_unblocked_payload.pop("blockers", None)
        receipt.write_text(json.dumps(concurrent_unblocked_payload, sort_keys=True) + "\n", encoding="utf-8")
        unblocked_status_gate = subagent_gate(valid_payload, {"OAG_SUBAGENT_GATE_CACHE": str(Path(tmp) / "subagent_gate_cache_concurrent_bad_status.json")})
        assert unblocked_status_gate.returncode == 0, unblocked_status_gate.stderr or unblocked_status_gate.stdout
        unblocked_status_payload = json.loads(unblocked_status_gate.stdout)
        assert unblocked_status_payload["decision"] == "block", unblocked_status_payload
        assert "BLOCKED, INCONCLUSIVE, or FAIL" in unblocked_status_payload["reason"], unblocked_status_payload

        closure_ip = make_ip(Path(tmp) / "closure_check")
        close_demo_counter(closure_ip, claim="closure check smoke counter closed")
        write_closure_reports(closure_ip)
        closure_pass = run_closure_check(closure_ip)
        assert closure_pass.returncode == 0, closure_pass.stderr or closure_pass.stdout
        closure_pass_result = json.loads(closure_pass.stdout)
        assert closure_pass_result["status"] == "pass", closure_pass_result

        stale_gate_ip = make_ip(Path(tmp) / "stale_gate_closure")
        close_demo_counter(stale_gate_ip, claim="stale gate smoke counter closed")
        write_closure_reports(stale_gate_ip)
        (stale_gate_ip / "cov" / "coverage.json").write_text(json.dumps({"status": "pass", "post_gate": True}), encoding="utf-8")
        stale_gate = run_closure_check(stale_gate_ip)
        assert stale_gate.returncode != 0, stale_gate.stdout
        stale_gate_result = json.loads(stale_gate.stdout)
        assert any(item["code"] == "GATE_ARTIFACT_STALE" for item in stale_gate_result["issues"]), stale_gate_result

        missing_closure_ip = make_ip(Path(tmp) / "missing_closure")
        closure_missing = run_closure_check(missing_closure_ip)
        assert closure_missing.returncode != 0, closure_missing.stdout
        closure_missing_result = json.loads(closure_missing.stdout)
        missing_codes = {item["code"] for item in closure_missing_result["issues"]}
        assert {"VALIDATION_REPORT_MISSING", "GATE_REPORT_MISSING"}.issubset(missing_codes), closure_missing_result

        bad_gate_ip = make_ip(Path(tmp) / "bad_gate_closure")
        close_demo_counter(bad_gate_ip, claim="bad gate smoke counter closed")
        write_closure_reports(bad_gate_ip, gate_decision="FAIL")
        closure_bad_gate = run_closure_check(bad_gate_ip)
        assert closure_bad_gate.returncode != 0, closure_bad_gate.stdout
        closure_bad_gate_result = json.loads(closure_bad_gate.stdout)
        assert any(item["code"] == "GATE_DECISION" for item in closure_bad_gate_result["issues"]), closure_bad_gate_result

        custom_claim_ip = make_ip(Path(tmp) / "custom_claim_closure")
        close_demo_counter(custom_claim_ip, claim="custom claim smoke counter closed")
        write_closure_reports(custom_claim_ip)
        custom_receipt = custom_claim_ip / "knowledge" / "subagents" / "custom_worker.json"
        custom_receipt.parent.mkdir(parents=True, exist_ok=True)
        custom_receipt.write_text(
            json.dumps(
                {
                    "schema_version": "oag_subagent_receipt.v1",
                    "product_name": "IP Dev Agent",
                    "internal_gateway": "Ontology Agent Gateway",
                    "role_name": "oag-custom-worker",
                    "shard_scope": "rtl_timer",
                    "stage": "rtl",
                    "status": "STATIC_HANDOFF_PASS",
                    "owned_obligations": [],
                    "contracts": [],
                    "allowed_write_paths": ["rtl/"],
                    "evidence_outputs": [],
                    "may_claim_complete": True,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        closure_custom_claim = run_closure_check(custom_claim_ip)
        assert closure_custom_claim.returncode != 0, closure_custom_claim.stdout
        closure_custom_claim_result = json.loads(closure_custom_claim.stdout)
        assert any(item["code"] == "CUSTOM_COMPLETION_CLAIM" for item in closure_custom_claim_result["issues"]), closure_custom_claim_result

        ip = make_ip(Path(tmp))
        compiled = call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
        assert compiled["result"]["status"] == "pass", compiled
        assert compiled["result"]["stats"]["design_rules"] >= 13, compiled
        assert compiled["result"]["stats"]["modules"] >= 1, compiled
        assert compiled["result"]["stats"]["design_facts_modules"] == 0, compiled
        assert compiled["result"]["stats"]["domain_rdc_crossings"] >= 1, compiled
        assert compiled["result"]["stats"]["tb_methodology_roles"] >= 6, compiled
        assert compiled["result"]["stats"]["tb_coverage_goals"] >= 1, compiled
        assert compiled["result"]["stats"]["authoring_packets"] >= 1, compiled
        assert (ip / "ontology" / "generated" / "design_truth_graph.json").is_file()
        assert (ip / "ontology" / "generated" / "design_spec.json").is_file()
        assert (ip / "ontology" / "generated" / "domain_crossing_matrix.json").is_file()
        assert (ip / "ontology" / "generated" / "tb_methodology_matrix.json").is_file()
        assert (ip / "ontology" / "generated" / "compile_manifest.json").is_file()
        compile_cached = call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
        assert compile_cached["result"]["status"] == "pass", compile_cached
        assert compile_cached["result"]["skipped"] is True, compile_cached
        compile_forced = call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip), "force": True}})
        assert compile_forced["result"]["status"] == "pass", compile_forced
        assert compile_forced["result"]["skipped"] is False, compile_forced
        design_facts_path = ip / "ontology" / "generated" / "design_facts_graph.json"
        assert design_facts_path.is_file()
        design_facts = json.loads(design_facts_path.read_text(encoding="utf-8"))
        assert design_facts["schema_version"] == "oag_design_facts_graph.v1", design_facts
        assert design_facts["status"] == "pass", design_facts
        assert design_facts["stats"]["rtl_source_files"] == 0, design_facts
        assert "git_head" not in (design_facts.get("extractor") or {}), design_facts
        truth_graph = json.loads((ip / "ontology" / "generated" / "design_truth_graph.json").read_text(encoding="utf-8"))
        truth_facts = truth_graph.get("generated", {}).get("design_facts", {})
        assert "git_head" not in (truth_facts.get("extractor") or {}), truth_graph
        domain_matrix = json.loads((ip / "ontology" / "generated" / "domain_crossing_matrix.json").read_text(encoding="utf-8"))
        assert domain_matrix["schema_version"] == "oag_domain_crossing_matrix.v1", domain_matrix
        assert domain_matrix["status"] == "present", domain_matrix
        assert (ip / "ontology" / "generated" / "authoring_packets" / "module__demo_counter_cx1.json").is_file()
        assert (ip / "ontology" / "runs").is_dir()
        inspect = call({"tool": "oag.inspect", "arguments": {"ip_dir": str(ip), "stage": "sim"}})
        assert inspect["result"]["validation"] == "partial", inspect
        assert "closure matrix has open obligations" in inspect["result"]["gaps"], inspect
        assert inspect["result"]["evidence"]["truth_graph"]["status"] == "pass", inspect
        assert inspect["result"]["evidence"]["design_facts_graph"]["status"] == "pass", inspect
        assert inspect["result"]["evidence"]["design_rules"]["count"] >= 13, inspect
        assert inspect["result"]["evidence"]["structure"]["profile"] == "small_leaf_single_file", inspect
        assert inspect["result"]["evidence"]["decomposition"]["modules"] >= 1, inspect
        assert inspect["result"]["evidence"]["authoring_packets"]["count"] >= 1, inspect
        scoreboard = inspect["result"]["evidence"]["scoreboard"]["summary"]
        assert scoreboard["schema"] == "scoreboard_rows.v1", scoreboard
        assert scoreboard["standard_rows"] == 2, scoreboard
        assert scoreboard["schema_failed"] == 0, scoreboard
        init = call({"tool": "oag.init", "arguments": {"ip_dir": str(ip)}})
        assert init["ok"] is True, init
        limit_ip = make_ip(Path(tmp) / "policy_limit")
        limit_run = call(
            {
                "tool": "oag.run.start",
                "arguments": {
                    "ip_dir": str(limit_ip),
                    "stage": "sim",
                    "intent": "smoke stage-limit policy",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        limit_run_id = limit_run["result"]["run_id"]
        limit_config = call(
            {
                "tool": "oag.configure",
                "arguments": {
                    "ip_dir": str(limit_ip),
                    "hook_auto_continue_until": "rtl",
                    "actor": {"kind": "human", "id": "smoke-owner", "surface": "smoke"},
                    "approval": {"kind": "human", "approved": True, "reason": "smoke limit"},
                },
            }
        )
        assert limit_config["result"]["updates"]["hook_auto_continue_until"] == "rtl", limit_config
        limited_stop = call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(limit_ip), "run_id": limit_run_id}})
        assert limited_stop["result"]["should_continue"] is False, limited_stop
        assert limited_stop["result"]["reason"] == "policy_limit_reached", limited_stop
        assert limited_stop["result"]["policy"]["next_action_stage"] == "sim", limited_stop
        limited_hook = stop_gate({"ip_dir": str(limit_ip), "run_id": limit_run_id})
        assert limited_hook.returncode == 0, limited_hook.stderr or limited_hook.stdout
        assert limited_hook.stdout == "", limited_hook.stdout
        sim_config = call(
            {
                "tool": "oag.configure",
                "arguments": {
                    "ip_dir": str(limit_ip),
                    "hook_auto_continue_until": "sim",
                    "actor": {"kind": "human", "id": "smoke-owner", "surface": "smoke"},
                    "approval": {"kind": "human", "approved": True, "reason": "smoke limit"},
                },
            }
        )
        assert sim_config["result"]["updates"]["hook_auto_continue_until"] == "sim", sim_config
        sim_stop = call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(limit_ip), "run_id": limit_run_id}})
        assert sim_stop["result"]["should_continue"] is True, sim_stop
        none_config = call(
            {
                "tool": "oag.configure",
                "arguments": {
                    "ip_dir": str(limit_ip),
                    "hook_auto_continue_until": "none",
                    "actor": {"kind": "human", "id": "smoke-owner", "surface": "smoke"},
                    "approval": {"kind": "human", "approved": True, "reason": "smoke limit"},
                },
            }
        )
        assert none_config["result"]["updates"]["hook_auto_continue_until"] == "none", none_config
        none_stop = call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(limit_ip), "run_id": limit_run_id}})
        assert none_stop["result"]["should_continue"] is False, none_stop
        command_ip = make_ip(Path(tmp) / "command_limit")
        command_run = call(
            {
                "tool": "oag.run.start",
                "arguments": {
                    "ip_dir": str(command_ip),
                    "stage": "sim",
                    "intent": "smoke short chat run-limit command",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        command_hook = context_hook({"ip_dir": str(command_ip), "prompt": "rtl까지만"})
        assert command_hook.returncode == 0, command_hook.stderr or command_hook.stdout
        assert "OAG RUN LIMIT CONFIGURED" in hook_context(command_hook), command_hook.stdout
        command_stop = call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(command_ip), "run_id": command_run["result"]["run_id"]}})
        assert command_stop["result"]["should_continue"] is False, command_stop
        assert command_stop["result"]["policy"]["hook_auto_continue_until"] == "rtl", command_stop
        run_start = call(
            {
                "tool": "oag.run.start",
                "arguments": {
                    "ip_dir": str(ip),
                    "stage": "sim",
                    "intent": "smoke close reset scoreboard obligation",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert run_start["result"]["schema_version"] == "oag_run_start.v1", run_start
        run_id = run_start["result"]["run_id"]
        assert run_start["result"]["status"] == "in_progress", run_start
        assert run_start["result"]["next_action"]["active_obligation"] == "OBL_DEMO_COUNTER_CX1_RESET_KNOWN", run_start
        assert "OAG NEXT ACTION" in run_start["result"]["next_action"]["prompt_block"], run_start
        assert (ip / "ontology" / "runs" / run_id / "run_state.json").is_file(), run_start
        assert (ip / "ontology" / "runs" / run_id / "next_action.json").is_file(), run_start
        assert (ip / "ontology" / "runs" / run_id / "checkpoint_history.jsonl").is_file(), run_start
        stop_before = call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(ip), "run_id": run_id}})
        assert stop_before["result"]["should_continue"] is True, stop_before
        assert "OAG NEXT ACTION" in stop_before["result"]["prompt_block"], stop_before
        stop_hook_before = stop_gate({"ip_dir": str(ip), "run_id": run_id})
        assert stop_hook_before.returncode == 0, stop_hook_before.stderr or stop_hook_before.stdout
        stop_hook_block = json.loads(stop_hook_before.stdout)
        assert stop_hook_block["decision"] == "block", stop_hook_block
        assert "OAG NEXT ACTION" in stop_hook_block["reason"], stop_hook_block
        assert "run incomplete" in stop_hook_block["reason"], stop_hook_block
        stop_cache = Path(tmp) / "stop_gate_cache.json"
        limited_env = {"OAG_STOP_GATE_CACHE": str(stop_cache), "OAG_STOP_GATE_MAX_BLOCK_REPEATS": "1"}
        stop_hook_limited_first = stop_gate({"ip_dir": str(ip), "run_id": run_id}, limited_env)
        assert stop_hook_limited_first.returncode == 0, stop_hook_limited_first.stderr or stop_hook_limited_first.stdout
        assert json.loads(stop_hook_limited_first.stdout)["decision"] == "block", stop_hook_limited_first.stdout
        stop_hook_limited_second = stop_gate({"ip_dir": str(ip), "run_id": run_id}, limited_env)
        assert stop_hook_limited_second.returncode == 0, stop_hook_limited_second.stderr or stop_hook_limited_second.stdout
        assert stop_hook_limited_second.stdout == "", stop_hook_limited_second.stdout
        run_loop_record = call(
            {
                "tool": "oag.run.record",
                "arguments": {
                    "ip_dir": str(ip),
                    "run_id": run_id,
                    "stage": "sim",
                    "summary": "run-loop smoke scoreboard evidence closes the reset obligation",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert run_loop_record["result"]["record"]["status"] == "closed", run_loop_record
        assert run_loop_record["result"]["status"] == "checkpoint_ready", run_loop_record
        run_checkpoint = call(
            {
                "tool": "oag.run.checkpoint",
                "arguments": {
                    "ip_dir": str(ip),
                    "run_id": run_id,
                    "stage": "sim",
                    "intent": "smoke close reset scoreboard obligation",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert run_checkpoint["result"]["allowed"] is True, run_checkpoint
        assert run_checkpoint["result"]["status"] == "complete", run_checkpoint
        assert run_checkpoint["result"]["decision"]["decision_receipt"], run_checkpoint
        run_state_path = ip / "ontology" / "runs" / run_id / "run_state.json"
        run_history_path = ip / "ontology" / "runs" / run_id / "checkpoint_history.jsonl"
        complete_state = json.loads(run_state_path.read_text(encoding="utf-8"))
        complete_history = run_history_path.read_text(encoding="utf-8")
        terminal_next = call({"tool": "oag.run.next", "arguments": {"ip_dir": str(ip), "run_id": run_id}})
        assert terminal_next["result"]["status"] == "complete", terminal_next
        assert terminal_next["result"]["terminal"] is True, terminal_next
        assert terminal_next["result"]["reason"] == "run_complete", terminal_next
        assert json.loads(run_state_path.read_text(encoding="utf-8"))["iteration"] == complete_state["iteration"], terminal_next
        assert run_history_path.read_text(encoding="utf-8") == complete_history, terminal_next
        stop_after = call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(ip), "run_id": run_id}})
        assert stop_after["result"]["should_continue"] is False, stop_after
        assert stop_after["result"]["reason"] == "run_complete", stop_after
        stop_hook_after = stop_gate({"ip_dir": str(ip), "run_id": run_id})
        assert stop_hook_after.returncode == 0, stop_hook_after.stderr or stop_hook_after.stdout
        assert stop_hook_after.stdout == "", stop_hook_after.stdout
        record = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(ip),
                    "stage": "sim",
                    "type": "finding",
                    "claim": "counter scoreboard closed",
                    "summary": "scoreboard rows are clean",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "rocev": {
                        "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN", "text": "scoreboard has no mismatches"},
                        "contract": {
                            "id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                            "method": "scoreboard",
                            "pass_condition": "mismatch count is zero",
                        },
                        "evidence": {"files": ["sim/results.xml", "sim/scoreboard_events.jsonl"], "tests": [], "commit": ""},
                        "validation": {"status": "closed", "verdict": "pass", "rationale": "all scoreboard rows have mismatch=false"},
                    },
                },
            }
        )
        assert record["result"]["status"] == "closed", record
        assert len(record["result"]["record"]["evidence"]["file_hashes"]) == 2, record
        assert record["result"]["ledger_event"], record
        assert (ip / "knowledge" / "ledger.jsonl").read_text(encoding="utf-8").strip(), record
        index_body = json.loads((ip / "knowledge" / "_index.json").read_text(encoding="utf-8"))
        record_files = [
            *sorted((ip / "knowledge" / "records").glob("*.json")),
            *sorted((ip / "knowledge" / "records").glob("*.yaml")),
            *sorted((ip / "knowledge" / "records").glob("*.yml")),
        ]
        assert index_body["record_count"] == len(record_files), index_body
        indexed_record = next(item for item in index_body["records"] if item["id"] == record["result"]["id"])
        assert indexed_record["obligation_id"] == "OBL_DEMO_COUNTER_CX1_RESET_KNOWN", indexed_record
        assert indexed_record["contract_id"] == "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", indexed_record
        assert indexed_record["validation_status"] == "closed", indexed_record
        assert indexed_record["evidence_files"] == ["sim/results.xml", "sim/scoreboard_events.jsonl"], indexed_record
        metrics = call(
            {
                "tool": "oag.metrics",
                "arguments": {
                    "ip_dir": str(ip),
                    "stage": "sim",
                    "intent": "smoke numeric improvement snapshot",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert metrics["result"]["recorded"] is True, metrics
        assert Path(metrics["result"]["path"]).is_file(), metrics
        assert Path(metrics["result"]["history"]).is_file(), metrics
        metric_body = metrics["result"]["metrics"]
        assert metric_body["schema_version"] == "oag_improvement_metrics.v1", metric_body
        assert metric_body["closure"]["closed"] == metric_body["closure"]["total"], metric_body
        assert metric_body["closure"]["closed_percent"] == 100.0, metric_body
        assert metric_body["check"]["issue_count"] == 0, metric_body
        assert metric_body["evidence"]["files_present_count"] >= 2, metric_body
        metrics_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip), "stage": "sim"}})
        assert metrics_check["result"]["improvement_metrics"]["closure"]["closed_percent"] == 100.0, metrics_check
        metrics_context = call({"tool": "oag.context", "arguments": {"ip_dir": str(ip), "stage": "sim", "intent": "metrics"}})
        assert "metrics closure=1/1 (100.0%)" in metrics_context["result"]["prompt_block"], metrics_context
        (ip / "signoff").mkdir(parents=True, exist_ok=True)
        (ip / "signoff" / "truth_coverage.json").write_text(
            json.dumps(
                {
                    "schema_version": "truth_coverage.v1",
                    "evidence_summary": {
                        "formal_assertion": {
                            "status": "development_pass",
                            "property_count": 3,
                            "bound_cycles": 8,
                            "numeric_summary": {
                                "baseline_property_count": 1,
                                "properties_checked": 3,
                                "properties_added": 2,
                                "baseline_bound_cycles": 4,
                                "bound_cycles": 8,
                                "bound_cycles_added": 4,
                                "bounded_steps_checked": 8,
                                "baseline_assertion_site_count": 2,
                                "source_assertion_site_count": 5,
                                "assertion_sites_added": 3,
                                "bounded_property_step_checks": 24,
                                "baseline_bounded_property_step_checks": 4,
                                "bounded_property_step_checks_added": 20,
                                "bounded_assertion_site_step_checks": 40,
                                "issues_found": 0,
                            },
                        },
                        "mutation": {
                            "status": "pass",
                            "mutants_run": 2,
                            "mutants_killed": 2,
                            "mutants_survived": 0,
                            "fault_models": ["reset_missing", "count_stuck"],
                        },
                        "implementation_sta": {
                            "status": "development_pass",
                            "target_clocks": [{"name": "clk", "period_ns": 10.0}],
                            "metrics": {
                                "wns_ns": 0.0,
                                "tns_ns": 0.0,
                                "unconstrained_text_seen": False,
                                "corner_count": 3,
                                "corners_passed": 3,
                                "corners_failed": 0,
                                "violated_corner_count": 0,
                            },
                            "numeric_summary": {
                                "baseline_corner_count": 1,
                                "corner_count": 3,
                                "corners_added": 2,
                                "corners_passed": 3,
                                "corners_failed": 0,
                                "worst_setup_slack_ns": 1.25,
                                "worst_hold_slack_ns": 0.12,
                                "worst_wns_ns": 0.0,
                                "worst_tns_ns": 0.0,
                                "violated_corner_count": 0,
                                "timing_analysis_count": 6,
                                "timing_metric_count": 12,
                                "negative_timing_metric_count": 0,
                                "worst_setup_slack_corner": "slow",
                                "worst_hold_slack_corner": "fast",
                                "worst_setup_slack_margin_percent_of_period": 12.5,
                                "worst_hold_slack_margin_percent_of_period": 1.2,
                            },
                        },
                        "gate_reset_xprop": {
                            "status": "development_pass",
                            "numeric_summary": {
                                "baseline_known_output_check_count": 2,
                                "known_output_check_count": 4,
                                "known_output_checks_added": 2,
                                "baseline_scenario_count": 1,
                                "scenario_count": 2,
                                "scenarios_added": 1,
                                "known_output_bit_check_count": 136,
                                "failures": 0,
                            },
                            "observations": {
                                "known_output_check_count": 4,
                                "known_output_bit_check_count": 136,
                                "scenarios": ["reset", "readback"],
                            },
                        },
                        "protocol_compliance": {
                            "status": "pass",
                            "protocol": "APB4",
                            "interface": "if_apb4_slave",
                            "method": "scoreboard_rows_v1_protocol_observation",
                            "numeric_summary": {
                                "baseline_protocol_row_count": 3,
                                "protocol_row_count": 5,
                                "protocol_rows_added": 2,
                                "baseline_response_row_count": 3,
                                "response_row_count": 5,
                                "response_rows_added": 2,
                                "read_response_row_count": 3,
                                "write_response_row_count": 2,
                                "invalid_response_row_count": 2,
                                "invalid_read_response_row_count": 1,
                                "invalid_write_response_row_count": 1,
                                "baseline_phase_row_count": 3,
                                "phase_row_count": 5,
                                "phase_rows_added": 2,
                                "baseline_protocol_coverage_ref_count": 4,
                                "required_protocol_coverage_ref_count": 6,
                                "protocol_coverage_refs_added": 2,
                                "observed_protocol_coverage_ref_count": 6,
                                "baseline_coverage_ref_count": 2,
                                "coverage_ref_count": 4,
                                "coverage_refs_added": 2,
                                "scoreboard_row_count": 6,
                                "protocol_check_count": 20,
                                "protocol_checks_passed": 20,
                                "protocol_checks_failed": 0,
                            },
                        },
                        "scoreboard": {"total": 2, "passed": 2, "failed": 0},
                        "coverage": {"status": "pass", "covered": ["reset", "count"]},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        handoff = call(
            {
                "tool": "oag.handoff",
                "arguments": {
                    "ip_dir": str(ip),
                    "stage": "handoff",
                    "intent": "smoke numeric readiness handoff",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert handoff["result"]["recorded"] is True, handoff
        assert Path(handoff["result"]["path"]).is_file(), handoff
        assert Path(handoff["result"]["history"]).is_file(), handoff
        assert Path(handoff["result"]["metrics_path"]).is_file(), handoff
        handoff_body = handoff["result"]["handoff"]
        assert handoff_body["schema_version"] == "oag_readiness_handoff.v1", handoff_body
        assert handoff_body["progress_denominator"] == "derived_from_active_ip_obligations", handoff_body
        assert handoff_body["numeric_summary"]["obligations_closed"] == 1, handoff_body
        assert handoff_body["numeric_summary"]["obligations_total"] == 1, handoff_body
        assert handoff_body["numeric_summary"]["closure_percent"] == 100.0, handoff_body
        strength = handoff_body["evidence_strength_summary"]
        assert strength["formal"]["property_count"] == 3, strength
        assert strength["formal"]["properties_added"] == 2, strength
        assert strength["formal"]["bound_cycles"] == 8, strength
        assert strength["formal"]["bound_cycles_added"] == 4, strength
        assert strength["formal"]["bounded_property_step_checks"] == 24, strength
        assert strength["formal"]["source_assertion_site_count"] == 5, strength
        assert strength["formal"]["assertion_sites_added"] == 3, strength
        assert strength["mutation"]["mutation_score_percent"] == 100.0, strength
        assert strength["implementation_sta"]["corner_count"] == 3, strength
        assert strength["implementation_sta"]["corners_passed"] == 3, strength
        assert strength["implementation_sta"]["violated_corner_count"] == 0, strength
        assert strength["implementation_sta"]["worst_setup_slack_ns"] == 1.25, strength
        assert strength["implementation_sta"]["timing_metric_count"] == 12, strength
        assert strength["implementation_sta"]["negative_timing_metric_count"] == 0, strength
        assert strength["implementation_sta"]["worst_setup_slack_corner"] == "slow", strength
        assert strength["implementation_sta"]["worst_setup_slack_margin_percent_of_period"] == 12.5, strength
        assert strength["gate_reset_xprop"]["known_output_check_count"] == 4, strength
        assert strength["gate_reset_xprop"]["known_output_checks_added"] == 2, strength
        assert strength["gate_reset_xprop"]["scenario_count"] == 2, strength
        assert strength["gate_reset_xprop"]["known_output_bit_check_count"] == 136, strength
        assert strength["protocol"]["protocol_row_count"] == 5, strength
        assert strength["protocol"]["protocol_rows_added"] == 2, strength
        assert strength["protocol"]["invalid_write_response_row_count"] == 1, strength
        assert strength["protocol"]["protocol_checks_passed"] == 20, strength
        assert strength["scoreboard"]["status"] == "pass", strength
        assert handoff_body["checks"]["evidence_strength_summary_has_formal_count"] is True, handoff_body
        assert handoff_body["checks"]["evidence_strength_summary_has_formal_step_count"] is True, handoff_body
        assert handoff_body["checks"]["evidence_strength_summary_has_protocol_count"] is True, handoff_body
        assert handoff_body["readiness"]["development_ready"] is True, handoff_body
        assert handoff_body["readiness"]["signoff_ready"] is False, handoff_body
        assert "closure_profile is development, not signoff" in handoff_body["readiness"]["not_ready_reasons"], handoff_body
        handoff_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(ip), "stage": "handoff"}})
        assert handoff_check["result"]["ok"] is True, handoff_check
        zero_strength_ip = make_ip(Path(tmp) / "zero_strength")
        zero_handoff = call(
            {
                "tool": "oag.handoff",
                "arguments": {
                    "ip_dir": str(zero_strength_ip),
                    "stage": "handoff",
                    "intent": "smoke zero-count development handoff",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert zero_handoff["result"]["recorded"] is True, zero_handoff
        zero_body = zero_handoff["result"]["handoff"]
        assert zero_body["evidence_strength_summary"]["formal"]["property_count"] == 0, zero_body
        assert zero_body["evidence_strength_summary"]["formal"]["bounded_property_step_checks"] == 0, zero_body
        assert zero_body["evidence_strength_summary"]["protocol"]["protocol_row_count"] == 0, zero_body
        assert zero_body["evidence_strength_summary"]["protocol"]["protocol_check_count"] == 0, zero_body
        assert zero_body["checks"]["evidence_strength_summary_has_formal_count"] is True, zero_body
        assert zero_body["checks"]["evidence_strength_summary_has_formal_step_count"] is True, zero_body
        assert zero_body["checks"]["evidence_strength_summary_has_protocol_count"] is True, zero_body
        zero_handoff_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(zero_strength_ip), "stage": "handoff"}})
        assert not any("handoff report check failed" in issue for issue in zero_handoff_check["result"]["issues"]), zero_handoff_check
        draft = call(
            {
                "tool": "oag.draft",
                "arguments": {
                    "ip_dir": str(ip),
                    "stage": "req",
                    "title": "counter requirement interview round 1",
                    "summary": "Captured draft requirement facts before locked-truth promotion.",
                    "facts": ["AXI data width is 256 bits"],
                    "open_questions": ["Which reset value is architecturally locked?"],
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert draft["result"]["status"] == "draft", draft
        assert Path(draft["result"]["draft_path"]).is_file(), draft
        assert Path(draft["result"]["markdown_path"]).is_file(), draft
        assert draft["result"]["scope_lock"]["state"] == "draft", draft
        assert draft["result"]["scope_update"], draft
        unlocked_decide = call({"tool": "oag.decide", "arguments": {"ip_dir": str(ip), "action": "claim_complete", "stage": "sim"}})
        assert unlocked_decide["result"]["allowed"] is False, unlocked_decide
        assert unlocked_decide["result"]["reason"] == "scope_lock_required", unlocked_decide
        relocked = call(
            {
                "tool": "oag.lock",
                "arguments": {
                    "ip_dir": str(ip),
                    "summary": "Smoke owner reconfirmed scope after the interview draft.",
                    "confirmed_scope": ["demo counter reset/count scoreboard closure remains approved"],
                    "source_draft": draft["result"]["id"],
                    "actor": {"kind": "human", "id": "smoke-owner", "surface": "smoke"},
                },
            }
        )
        assert relocked["result"]["locked"] is True, relocked
        context = call({"tool": "oag.context", "arguments": {"ip_dir": str(ip), "stage": "sim", "intent": "scoreboard"}})
        assert "IP KNOWLEDGE LEDGER" in context["result"]["prompt_block"], context
        assert "scope_lock=locked" in context["result"]["prompt_block"], context
        cache_path = ROOT / ".cache" / "context_inject.json"
        cache_path.unlink(missing_ok=True)
        context_payload = {"ip_dir": str(ip), "stage": "sim", "prompt": f"Continue sim work for {ip.name}"}
        context_first = context_hook(context_payload)
        assert context_first.returncode == 0, context_first.stderr or context_first.stdout
        assert "OAG CONTEXT INJECTION" in hook_context(context_first), context_first.stdout
        context_duplicate = context_hook(context_payload)
        assert context_duplicate.returncode == 0, context_duplicate.stderr or context_duplicate.stdout
        assert context_duplicate.stdout == "", context_duplicate.stdout
        context_high_pressure = context_hook({**context_payload, "context_pressure": "high"})
        assert context_high_pressure.returncode == 0, context_high_pressure.stderr or context_high_pressure.stdout
        if context_high_pressure.stdout:
            assert "OAG CONTEXT INJECTION" in hook_context(context_high_pressure), context_high_pressure.stdout
        context_post_compact = context_hook({**context_payload, "hook_event_name": "PostCompact"})
        assert context_post_compact.returncode == 0, context_post_compact.stderr or context_post_compact.stdout
        assert context_post_compact.stdout == "", context_post_compact.stdout
        context_recovery = context_hook(context_payload)
        assert context_recovery.returncode == 0, context_recovery.stderr or context_recovery.stdout
        recovery_payload = json.loads(context_recovery.stdout)
        assert recovery_payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit", recovery_payload
        assert "OAG CONTEXT INJECTION" in hook_context(context_recovery), context_recovery.stdout
        route_root = Path(tmp) / "hook_route_project"
        for name, run_id in (("route_alpha", "RUN_ALPHA"), ("route_beta", "RUN_BETA")):
            route_ip = route_root / name
            (route_ip / "ontology" / "runs").mkdir(parents=True)
            (route_ip / "ontology" / "ip.yaml").write_text(f"ip: {name}\n", encoding="utf-8")
            (route_ip / "ontology" / "runs" / "active_run.json").write_text(
                json.dumps({"run_id": run_id, "status": "in_progress"}) + "\n",
                encoding="utf-8",
            )
        assert hook_target_names(route_root, {"prompt": "승인", "context_pressure": "critical"}, require_signal=False) == []
        assert hook_target_names(route_root, {"prompt": "oag context"}, require_signal=True) == []
        assert hook_target_names(route_root, {"prompt": "route OAG"}, require_signal=True) == []
        assert hook_target_names(route_root, {"prompt": "continue route_alpha OAG"}, require_signal=True) == ["route_alpha"]
        assert hook_target_names(route_root, {"prompt": "compare route_alpha and route_beta OAG"}, require_signal=True) == []
        assert hook_target_names(route_root, {"ip_dir": str(route_root / "route_beta"), "prompt": "승인"}, require_signal=False) == ["route_beta"]
        single_route_root = Path(tmp) / "single_hook_route_project"
        single_route_ip = single_route_root / "solo_route"
        (single_route_ip / "ontology" / "runs").mkdir(parents=True)
        (single_route_ip / "ontology" / "ip.yaml").write_text("ip: solo_route\n", encoding="utf-8")
        (single_route_ip / "ontology" / "runs" / "active_run.json").write_text(
            json.dumps({"run_id": "RUN_SOLO", "status": "in_progress"}) + "\n",
            encoding="utf-8",
        )
        assert hook_target_names(single_route_root, {"prompt": "rtl work"}, require_signal=True) == []
        assert hook_target_names(single_route_root, {"prompt": "ipdev rtl work"}, require_signal=True) == []
        assert hook_target_names(single_route_root, {"prompt": "oag rtl work"}, require_signal=True) == ["solo_route"]
        undecided = call({"tool": "oag.decide", "arguments": {"ip_dir": str(ip), "action": "claim_complete", "stage": "sim"}})
        assert undecided["result"]["allowed"] is False, undecided
        assert undecided["result"]["reason"] == "decision_receipt_required", undecided
        decide = call(
            {
                "tool": "oag.decide",
                "arguments": {
                    "ip_dir": str(ip),
                    "action": "claim_complete",
                    "stage": "sim",
                    "record_decision": True,
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert decide["result"]["allowed"] is True, decide
        assert Path(decide["result"]["decision_receipt"]["path"]).is_file(), decide
        signoff_blocked = call({"tool": "oag.decide", "arguments": {"ip_dir": str(ip), "action": "signoff", "stage": "signoff"}})
        assert signoff_blocked["result"]["allowed"] is False, signoff_blocked
        assert signoff_blocked["result"]["reason"] == "closure_profile_not_signoff", signoff_blocked
        policies = ip / "ontology" / "policies.yaml"
        policies.write_text(policies.read_text(encoding="utf-8").replace("closure_profile: development", "closure_profile: signoff"), encoding="utf-8")
        approval = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(ip),
                    "stage": "signoff",
                    "type": "decision",
                    "claim": "human approval to enter signoff closure profile",
                    "summary": "Human owner approved the protected policy transition to signoff.",
                    "actor": {"kind": "human", "id": "smoke-owner", "surface": "smoke"},
                    "approval": {"kind": "human", "approved": True, "reason": "smoke signoff path"},
                    "status": "open",
                },
            }
        )
        assert approval["result"]["ledger_event"], approval
        compiled = call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
        assert compiled["result"]["status"] == "pass", compiled
        write_stage_receipt(ip, "sim")
        signoff_without_review = call({"tool": "oag.decide", "arguments": {"ip_dir": str(ip), "action": "signoff", "stage": "signoff"}})
        assert signoff_without_review["result"]["allowed"] is False, signoff_without_review
        assert signoff_without_review["result"]["reason"] == "reviewer_receipt_required", signoff_without_review
        fake_review_path = ip / "ontology" / "validations" / "REV_SELF_ALLOWED.json"
        fake_review_path.write_text(
            json.dumps(
                {
                    "schema_version": "oag_reviewer_receipt.v1",
                    "id": "REV_SELF_ALLOWED",
                    "ip": ip.name,
                    "action": "signoff",
                    "allowed": True,
                    "reason": "allowed",
                    "verdict": "pass",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "producer_actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "independent": False,
                    "findings": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        signoff_with_non_independent_review = call({"tool": "oag.decide", "arguments": {"ip_dir": str(ip), "action": "signoff", "stage": "signoff"}})
        assert signoff_with_non_independent_review["result"]["allowed"] is False, signoff_with_non_independent_review
        assert signoff_with_non_independent_review["result"]["reason"] == "reviewer_receipt_required", signoff_with_non_independent_review
        review = call(
            {
                "tool": "oag.review",
                "arguments": {
                    "ip_dir": str(ip),
                    "action": "signoff",
                    "stage": "signoff",
                    "verdict": "pass",
                    "actor": {"kind": "ai", "id": "smoke-reviewer", "surface": "smoke"},
                    "producer_actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "findings": [],
                },
            }
        )
        assert review["result"]["allowed"] is True, review
        assert Path(review["result"]["reviewer_receipt"]["path"]).is_file(), review
        signoff = call(
            {
                "tool": "oag.decide",
                "arguments": {
                    "ip_dir": str(ip),
                    "action": "signoff",
                    "stage": "signoff",
                    "record_decision": True,
                    "actor": {"kind": "human", "id": "smoke-owner", "surface": "smoke"},
                },
            }
        )
        assert signoff["result"]["allowed"] is True, signoff
        assert Path(signoff["result"]["decision_receipt"]["path"]).is_file(), signoff
        ticket = call(
            {
                "tool": "oag.ticket",
                "arguments": {
                    "ip_dir": str(ip),
                    "stage": "sim",
                    "reason": "scoreboard mismatch example",
                    "failing_contract": {"id": "CONTRACT_SIM_SCOREBOARD"},
                    "expected": {"count": 3},
                    "observed": {"count": 2},
                    "evidence": {"files": ["sim/scoreboard_events.jsonl"]},
                    "editable_files": ["rtl/demo_counter_cx1.sv"],
                    "required_evidence_after_patch": ["sim/results.xml", "sim/scoreboard_events.jsonl"],
                },
            }
        )
        assert ticket["result"]["owner_workflow"] == "tb", ticket
        assert Path(ticket["result"]["path"]).is_file(), ticket
        graph_json = Path(tmp) / "ontology_graph.json"
        graph_html = Path(tmp) / "ontology_graph.html"
        graph_proc = subprocess.run(
            [
                sys.executable,
                str(GRAPH),
                "build",
                "--ip-dir",
                str(ip),
                "--stage",
                "sim",
                "--intent",
                "scoreboard",
                "--json-out",
                str(graph_json),
                "--html-out",
                str(graph_html),
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert graph_proc.returncode == 0, graph_proc.stderr or graph_proc.stdout
        graph_data = json.loads(graph_json.read_text(encoding="utf-8"))
        assert graph_data["schema_version"] == "oag_ontology_graph.v1", graph_data
        assert graph_data["stats"]["record_count"] >= 1, graph_data
        assert any(node["type"] == "obligation" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "structure" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "module" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "authoring_packet" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "rule" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "rule_instance" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "draft" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "protection" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "ledger" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "stage" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "decision" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "run" for node in graph_data["graph"]["nodes"]), graph_data
        assert any(node["type"] == "ticket" for node in graph_data["graph"]["nodes"]), graph_data
        assert "OAG Ontology Graph" in graph_html.read_text(encoding="utf-8")
        portable_archive = Path(tmp) / "oag_portable_smoke.tar.gz"
        portable_export = subprocess.run(
            [
                sys.executable,
                str(PORTABLE_DB),
                "export",
                "--root",
                tmp,
                "--ip",
                ip.name,
                "--out",
                str(portable_archive),
                "--no-artifacts",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert portable_export.returncode == 0, portable_export.stderr or portable_export.stdout
        portable_summary = json.loads(portable_export.stdout)
        assert portable_summary["status"] == "pass", portable_summary
        assert portable_summary["file_count"] > 0, portable_summary
        portable_inspect = subprocess.run(
            [sys.executable, str(PORTABLE_DB), "inspect", str(portable_archive)],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert portable_inspect.returncode == 0, portable_inspect.stderr or portable_inspect.stdout
        portable_manifest = json.loads(portable_inspect.stdout)
        assert portable_manifest["schema_version"] == "oag_portable_db.v1", portable_manifest
        import_dest = Path(tmp) / "portable_import"
        portable_import = subprocess.run(
            [
                sys.executable,
                str(PORTABLE_DB),
                "import",
                str(portable_archive),
                "--dest",
                str(import_dest),
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert portable_import.returncode == 0, portable_import.stderr or portable_import.stdout
        assert json.loads(portable_import.stdout)["changed"] == portable_summary["file_count"], portable_import.stdout
        okf_dir = Path(tmp) / "okf_bundle"
        okf_export = subprocess.run(
            [
                sys.executable,
                str(OKF),
                "export",
                "--ip-dir",
                str(ip),
                "--out",
                str(okf_dir),
                "--force",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert okf_export.returncode == 0, okf_export.stderr or okf_export.stdout
        okf_summary = json.loads(okf_export.stdout)
        assert okf_summary["status"] == "pass", okf_summary
        assert okf_summary["counts"]["requirements"] >= 1, okf_summary
        assert (okf_dir / "index.md").is_file(), okf_summary
        assert (okf_dir / "requirements").is_dir(), okf_summary
        okf_validate = subprocess.run(
            [sys.executable, str(OKF), "validate", str(okf_dir)],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert okf_validate.returncode == 0, okf_validate.stderr or okf_validate.stdout
        okf_validation = json.loads(okf_validate.stdout)
        assert okf_validation["ok"] is True, okf_validation
        assert okf_validation["concept_count"] >= okf_summary["counts"]["requirements"], okf_validation
        okf_obsidian_dir = Path(tmp) / "okf_obsidian_bundle"
        okf_obsidian_export = subprocess.run(
            [
                sys.executable,
                str(OKF),
                "export",
                "--profile",
                "obsidian",
                "--ip-dir",
                str(ip),
                "--out",
                str(okf_obsidian_dir),
                "--force",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert okf_obsidian_export.returncode == 0, okf_obsidian_export.stderr or okf_obsidian_export.stdout
        okf_obsidian_summary = json.loads(okf_obsidian_export.stdout)
        assert okf_obsidian_summary["profile"] == "obsidian", okf_obsidian_summary
        assert (okf_obsidian_dir / "OAG Knowledge.base").is_file(), okf_obsidian_summary
        obsidian_index = (okf_obsidian_dir / "index.md").read_text(encoding="utf-8")
        assert "[[OAG Knowledge.base|OAG Knowledge Base views]]" in obsidian_index, obsidian_index
        obsidian_requirement = next(
            path for path in (okf_obsidian_dir / "requirements").glob("*.md") if path.name != "index.md"
        )
        obsidian_requirement_text = obsidian_requirement.read_text(encoding="utf-8")
        assert "aliases:" in obsidian_requirement_text, obsidian_requirement_text
        assert "oag_kind: \"requirement\"" in obsidian_requirement_text, obsidian_requirement_text
        obsidian_obligation = next(
            path for path in (okf_obsidian_dir / "obligations").glob("*.md") if path.name != "index.md"
        )
        assert "[[contracts/" in obsidian_obligation.read_text(encoding="utf-8"), obsidian_obligation
        okf_obsidian_validate = subprocess.run(
            [sys.executable, str(OKF), "validate", str(okf_obsidian_dir)],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert okf_obsidian_validate.returncode == 0, okf_obsidian_validate.stderr or okf_obsidian_validate.stdout
        okf_obsidian_validation = json.loads(okf_obsidian_validate.stdout)
        assert okf_obsidian_validation["ok"] is True, okf_obsidian_validation
        okf_import_ip = make_ip(Path(tmp) / "okf_import")
        okf_locked_truth_before = sha256(okf_import_ip / "req" / "locked_truth.md")
        okf_ontology_before = sha256(okf_import_ip / "ontology" / "requirements.yaml")
        okf_import = subprocess.run(
            [
                sys.executable,
                str(OKF),
                "import-draft",
                str(okf_dir),
                "--ip-dir",
                str(okf_import_ip),
                "--title",
                "smoke OKF import draft",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert okf_import.returncode == 0, okf_import.stderr or okf_import.stdout
        okf_import_summary = json.loads(okf_import.stdout)
        assert okf_import_summary["status"] == "pass", okf_import_summary
        assert okf_import_summary["canonical_sources_preserved"] is True, okf_import_summary
        assert okf_import_summary["draft"]["status"] == "draft", okf_import_summary
        assert Path(okf_import_summary["draft"]["draft_path"]).is_file(), okf_import_summary
        assert sha256(okf_import_ip / "req" / "locked_truth.md") == okf_locked_truth_before, okf_import_summary
        assert sha256(okf_import_ip / "ontology" / "requirements.yaml") == okf_ontology_before, okf_import_summary
        okf_rtl_ip = make_ip(Path(tmp) / "okf_rtl")
        (okf_rtl_ip / "list" / "rtl.f").write_text("rtl/demo_counter_cx1.sv\n", encoding="utf-8")
        (okf_rtl_ip / "rtl" / "demo_counter_cx1.sv").write_text(
            "\n".join(
                [
                    "module demo_counter_cx1(",
                    "    input logic clk_i,",
                    "    input logic rst_ni,",
                    "    output logic [7:0] count_o",
                    ");",
                    "    assign count_o = rst_ni ? 8'h01 : 8'h00;",
                    "endmodule",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        okf_rtl_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(okf_rtl_ip)}})
        assert okf_rtl_compile["result"]["stats"]["design_facts_modules"] >= 1, okf_rtl_compile
        okf_rtl_dir = Path(tmp) / "okf_rtl_bundle"
        okf_rtl_export = subprocess.run(
            [
                sys.executable,
                str(OKF),
                "export",
                "--ip-dir",
                str(okf_rtl_ip),
                "--out",
                str(okf_rtl_dir),
                "--force",
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert okf_rtl_export.returncode == 0, okf_rtl_export.stderr or okf_rtl_export.stdout
        okf_rtl_validate = subprocess.run(
            [sys.executable, str(OKF), "validate", str(okf_rtl_dir)],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert okf_rtl_validate.returncode == 0, okf_rtl_validate.stderr or okf_rtl_validate.stdout
        module_page = okf_rtl_dir / "design" / "modules" / "demo_counter_cx1.md"
        assert module_page.is_file(), module_page
        assert "source_file: \"rtl/demo_counter_cx1.sv\"" in module_page.read_text(encoding="utf-8"), module_page
        assert "- Source: `rtl/demo_counter_cx1.sv`" in module_page.read_text(encoding="utf-8"), module_page
        eval_proc = subprocess.run(
            [sys.executable, str(EVAL), "--json"],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert eval_proc.returncode == 0, eval_proc.stderr or eval_proc.stdout
        eval_report = json.loads(eval_proc.stdout)
        assert eval_report["schema_version"] == "oag_evaluation_report.v1", eval_report
        assert eval_report["ok"] is True, eval_report
        assert eval_report["passed"] == eval_report["total"], eval_report
        assert eval_report["total"] >= 14, eval_report
        answer_key_proc = subprocess.run(
            [sys.executable, str(ANSWER_KEY_EVAL), "--json", "--speed-scale", "5"],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT.parent,
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            timeout=OAG_CALL_TIMEOUT_SECONDS,
        )
        assert answer_key_proc.returncode == 0, answer_key_proc.stderr or answer_key_proc.stdout
        answer_key_report = json.loads(answer_key_proc.stdout)
        assert answer_key_report["schema_version"] == "oag_answer_key_report.v1", answer_key_report
        assert answer_key_report["ok"] is True, answer_key_report
        assert answer_key_report["score"] == 1.0, answer_key_report
        needs_human_ip = make_ip(Path(tmp) / "needs_human_run")
        needs_human_run = call(
            {
                "tool": "oag.run.start",
                "arguments": {
                    "ip_dir": str(needs_human_ip),
                    "stage": "sim",
                    "intent": "smoke repeated blocker",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        needs_human_run_id = needs_human_run["result"]["run_id"]
        needs_human_checkpoint = call(
            {
                "tool": "oag.run.checkpoint",
                "arguments": {
                    "ip_dir": str(needs_human_ip),
                    "run_id": needs_human_run_id,
                    "stage": "sim",
                    "intent": "smoke repeated blocker",
                    "max_blocker_repeats": 1,
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                },
            }
        )
        assert needs_human_checkpoint["result"]["status"] == "needs_human", needs_human_checkpoint
        stop_hook_human = stop_gate({"ip_dir": str(needs_human_ip), "run_id": needs_human_run_id})
        assert stop_hook_human.returncode == 0, stop_hook_human.stderr or stop_hook_human.stdout
        assert stop_hook_human.stdout == "", stop_hook_human.stdout
        explicit_ip = make_ip(Path(tmp) / "bad_explicit_validation")
        draftish = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(explicit_ip),
                    "stage": "sim",
                    "claim": "evidence without explicit validation status",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "rocev": {
                        "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN"},
                        "contract": {"id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", "method": "scoreboard"},
                        "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                        "validation": {"verdict": "pass", "rationale": "missing explicit status"},
                    },
                },
            }
        )
        assert draftish["result"]["status"] == "open", draftish
        explicit_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(explicit_ip)}})
        assert explicit_check["result"]["ok"] is False, explicit_check
        assert any("no closed validation record linking obligation to contract" in issue for issue in explicit_check["result"]["issues"]), explicit_check
        rejected_closed = call_process(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(explicit_ip),
                    "stage": "sim",
                    "status": "closed",
                    "claim": "top-level closed without validation status",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "rocev": {
                        "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN"},
                        "contract": {"id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", "method": "scoreboard"},
                        "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                        "validation": {"verdict": "pass", "rationale": "top-level close only"},
                    },
                },
            }
        )
        assert rejected_closed.returncode != 0, rejected_closed.stdout
        assert "closed records require explicit rocev.validation.status" in json.loads(rejected_closed.stdout)["errors"][0], rejected_closed.stdout
        freshness_ip = make_ip(Path(tmp) / "bad_freshness")
        fresh_record = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(freshness_ip),
                    "stage": "sim",
                    "claim": "fresh evidence baseline",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "rocev": {
                        "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN"},
                        "contract": {"id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", "method": "scoreboard"},
                        "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                        "validation": {"status": "closed", "verdict": "pass", "rationale": "hash baseline"},
                    },
                },
            }
        )
        assert fresh_record["result"]["status"] == "closed", fresh_record
        (freshness_ip / "sim" / "results.xml").write_text('<testsuite failures="1"/>\n', encoding="utf-8")
        freshness_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(freshness_ip)}})
        assert freshness_check["result"]["ok"] is False, freshness_check
        assert any("evidence file stale: sim/results.xml" in issue for issue in freshness_check["result"]["issues"]), freshness_check
        bad_ip = make_ip(Path(tmp) / "bad")
        bad_row = {
            "goal_id": "GOAL_BAD",
            "scenario_id": "SC_BAD",
            "cycle": 1,
            "stimulus": {},
            "expected": {"count": 1},
            "observed": {"count": 1},
            "passed": True,
            "mismatch": "",
            "coverage_refs": [],
        }
        (bad_ip / "sim" / "scoreboard_events.jsonl").write_text(json.dumps(bad_row) + "\n", encoding="utf-8")
        bad_inspect = call({"tool": "oag.inspect", "arguments": {"ip_dir": str(bad_ip), "stage": "sim"}})
        assert bad_inspect["result"]["validation"] == "partial", bad_inspect
        assert "scoreboard schema has invalid rows" in bad_inspect["result"]["gaps"], bad_inspect
        dev_validator_ip = make_ip(Path(tmp) / "dev_validator")
        write_ip_validator_report(dev_validator_ip)
        write_stage_receipt(dev_validator_ip, "sim")
        dev_validator_record = close_demo_counter(
            dev_validator_ip,
            claim="development validator positive smoke",
            evidence_files=[
                "rtl/rtl_compile.json",
                "lint/dut_lint.json",
                "sim/results.xml",
                "sim/scoreboard_events.jsonl",
                "cov/coverage.json",
                "signoff/ip_validator_report.json",
                "ontology/evidence/stage_runs/sim.json",
            ],
        )
        assert dev_validator_record["result"]["status"] == "closed", dev_validator_record
        dev_validator_proc = run_dev_validator(dev_validator_ip)
        assert dev_validator_proc.returncode == 0, dev_validator_proc.stderr or dev_validator_proc.stdout
        dev_validator_report = json.loads(dev_validator_proc.stdout)
        assert dev_validator_report["status"] == "pass", dev_validator_report
        assert dev_validator_report["failed_gates"] == [], dev_validator_report
        dev_validator_gates = {gate["id"]: gate for gate in dev_validator_report["gates"]}
        assert dev_validator_gates["scoreboard_rows_v1"]["status"] == "pass", dev_validator_report
        assert dev_validator_gates["stage_run_receipts"]["status"] == "pass", dev_validator_report
        assert dev_validator_gates["oag_check"]["status"] == "pass", dev_validator_report
        bad_validator_ip = make_ip(Path(tmp) / "bad_dev_validator")
        bad_validator_row = {
            "goal_id": "GOAL_BAD_VALIDATOR",
            "scenario_id": "SC_BAD_VALIDATOR",
            "cycle": 1,
            "stimulus": {},
            "expected": {"count": 1},
            "observed": {"count": 1},
            "passed": True,
            "mismatch": "",
            "coverage_refs": [],
        }
        (bad_validator_ip / "sim" / "scoreboard_events.jsonl").write_text(json.dumps(bad_validator_row) + "\n", encoding="utf-8")
        write_ip_validator_report(bad_validator_ip)
        write_stage_receipt(bad_validator_ip, "sim")
        bad_validator_proc = run_dev_validator(bad_validator_ip)
        assert bad_validator_proc.returncode != 0, bad_validator_proc.stdout
        bad_validator_report = json.loads(bad_validator_proc.stdout)
        assert bad_validator_report["status"] == "fail", bad_validator_report
        assert "scoreboard_rows_v1" in bad_validator_report["failed_gates"], bad_validator_report
        bad_validator_gates = {gate["id"]: gate for gate in bad_validator_report["gates"]}
        assert any("observed_source" in issue for issue in bad_validator_gates["scoreboard_rows_v1"]["issues"]), bad_validator_report
        loop_spec = Path(tmp) / "loop_spec.md"
        loop_spec.write_text(
            "\n".join(
                [
                    "# Demo counter spec",
                    "",
                    "- Reset drives count to zero.",
                    "- Valid cycles increment count.",
                    "- Scoreboard evidence must be DUT-facing.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        spec_loop_ip = make_ip(Path(tmp) / "spec_to_rtl_loop")
        write_ip_validator_report(spec_loop_ip)
        write_stage_receipt(spec_loop_ip, "sim")
        spec_loop_record = close_demo_counter(
            spec_loop_ip,
            claim="spec-to-RTL loop positive smoke",
            evidence_files=[
                "rtl/rtl_compile.json",
                "lint/dut_lint.json",
                "sim/results.xml",
                "sim/scoreboard_events.jsonl",
                "cov/coverage.json",
                "signoff/ip_validator_report.json",
                "ontology/evidence/stage_runs/sim.json",
            ],
        )
        assert spec_loop_record["result"]["status"] == "closed", spec_loop_record
        spec_loop_proc = run_spec_to_rtl_loop(spec_loop_ip, loop_spec, metrics=True)
        assert spec_loop_proc.returncode == 0, spec_loop_proc.stderr or spec_loop_proc.stdout
        spec_loop_result = json.loads(spec_loop_proc.stdout)
        assert spec_loop_result["validator"]["status"] == "pass", spec_loop_result
        assert spec_loop_result["auto_research"]["ranked_next_actions"] >= 1, spec_loop_result
        spec_loop_report_path = spec_loop_ip / "signoff" / "ip_research_report.json"
        assert spec_loop_report_path.is_file(), spec_loop_result
        spec_loop_report = json.loads(spec_loop_report_path.read_text(encoding="utf-8"))
        assert spec_loop_report["schema_version"] == "ip_research_report.v1", spec_loop_report
        assert spec_loop_report["checks"]["ranked_next_actions_present"] is True, spec_loop_report
        assert spec_loop_report["ranked_next_actions"][0]["id"] == "SIGNOFF_PROMOTION_REVIEW", spec_loop_report
        spec_loop_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(spec_loop_ip)}})
        assert spec_loop_check["result"]["ok"] is True, spec_loop_check
        spec_loop_metrics = spec_loop_check["result"]["improvement_metrics"]["auto_research"]
        assert spec_loop_metrics["reports"] >= 1, spec_loop_metrics
        assert spec_loop_metrics["actions"] >= 1, spec_loop_metrics
        partial_loop_ip = make_ip(Path(tmp) / "partial_spec_to_rtl_loop")
        partial_loop_proc = run_spec_to_rtl_loop(partial_loop_ip, loop_spec)
        assert partial_loop_proc.returncode == 0, partial_loop_proc.stderr or partial_loop_proc.stdout
        partial_loop_result = json.loads(partial_loop_proc.stdout)
        assert partial_loop_result["validator"]["status"] == "fail", partial_loop_result
        partial_loop_report = json.loads((partial_loop_ip / "signoff" / "ip_research_report.json").read_text(encoding="utf-8"))
        partial_actions = {action["id"]: action for action in partial_loop_report["ranked_next_actions"]}
        assert "IP_SPECIFIC_VALIDATOR" in partial_actions, partial_loop_report
        assert "ROCEV_INSPECT_CLOSURE" in partial_actions or "ROCEV_CHECK" in partial_actions, partial_loop_report
        partial_loop_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(partial_loop_ip)}})
        assert partial_loop_check["result"]["ok"] is False, partial_loop_check
        assert not any(issue.startswith("auto research report") for issue in partial_loop_check["result"]["issues"]), partial_loop_check
        empty_ip = Path(tmp) / "empty_vacuous"
        empty_ip.mkdir()
        empty_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(empty_ip)}})
        assert empty_compile["result"]["status"] == "fail", empty_compile
        assert "no requirements in ontology/requirements.yaml" in empty_compile["result"]["issues"], empty_compile
        bad_rules_ip = make_ip(Path(tmp) / "bad_rules")
        (bad_rules_ip / "ontology" / "design_rules.yaml").write_text(
            "\n".join(
                [
                    "schema: oag_design_rules.v1",
                    f"ip: {bad_rules_ip.name}",
                    "rules:",
                    "  - id: RULE_ONLY_SCOREBOARD",
                    "    kind: scoreboard_evidence_schema",
                    "    status: active",
                    "instances: []",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        bad_rules_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(bad_rules_ip)}})
        assert bad_rules_compile["result"]["status"] == "fail", bad_rules_compile
        assert "missing required design rule kind: same_cycle_priority_declared" in bad_rules_compile["result"]["issues"], bad_rules_compile
        bad_lang_ip = make_ip(Path(tmp) / "bad_language_policy")
        bad_lang_rules = (bad_lang_ip / "ontology" / "design_rules.yaml").read_text(encoding="utf-8")
        bad_lang_rules = bad_lang_rules.replace(
            "    allowed_constructs: [logic, generate, genvar, generate_for]",
            "    allowed_constructs: [logic]",
            1,
        )
        bad_lang_rules = bad_lang_rules.replace(
            "    forbidden_constructs: [procedural_for, procedural_while, procedural_repeat, procedural_forever, function, task, always_ff, always_comb, always_latch, package, import, interface, modport, typedef, enum, struct, class, program, clocking, bind, dpi, randomization, constraints, unique_priority, assertions, covergroups]",
            "    forbidden_constructs: [procedural_for, procedural_while, generate_for]",
            1,
        )
        (bad_lang_ip / "ontology" / "design_rules.yaml").write_text(bad_lang_rules, encoding="utf-8")
        bad_lang_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(bad_lang_ip)}})
        assert bad_lang_compile["result"]["status"] == "fail", bad_lang_compile
        assert "RULE_RTL_LANGUAGE_SUBSET: rtl language subset must allow generate" in bad_lang_compile["result"]["issues"], bad_lang_compile
        assert "RULE_RTL_LANGUAGE_SUBSET: rtl language subset must not forbid generate constructs" in bad_lang_compile["result"]["issues"], bad_lang_compile
        bad_subset_ip = make_ip(Path(tmp) / "bad_rtl_subset_instance")
        (bad_subset_ip / "rtl").mkdir(exist_ok=True)
        (bad_subset_ip / "rtl" / "demo_counter_cx1.sv").write_text(
            "\n".join(
                [
                    "module demo_counter_cx1(input logic clk);",
                    "  function logic bad_helper;",
                    "    input logic in;",
                    "    begin",
                    "      bad_helper = in;",
                    "    end",
                    "  endfunction",
                    "  always_ff @(posedge clk) begin",
                    "  end",
                    "endmodule",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (bad_subset_ip / "rtl" / "rtl_compile.json").write_text(
            json.dumps(
                {
                    "schema": "rtl_compile_report.v1",
                    "status": "pass",
                    "files": ["rtl/demo_counter_cx1.sv"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        bad_subset_rules_path = bad_subset_ip / "ontology" / "design_rules.yaml"
        bad_subset_rules = bad_subset_rules_path.read_text(encoding="utf-8")
        if not bad_subset_rules.endswith("\n"):
            bad_subset_rules += "\n"
        bad_subset_rules += "\n".join(
            [
                "  - id: INST_BAD_RTL_LANGUAGE_SUBSET",
                "    rule: RULE_RTL_LANGUAGE_SUBSET",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    language_policy: smoke_negative_subset",
                "    rtl_compile_report: rtl/rtl_compile.json",
                "    rtl_sources: [rtl/demo_counter_cx1.sv]",
                "    forbidden_constructs_absent: [always_ff, function]",
                "    evidence_refs:",
                "      - rtl/demo_counter_cx1.sv",
                "      - rtl/rtl_compile.json",
                "",
            ]
        )
        bad_subset_rules_path.write_text(bad_subset_rules, encoding="utf-8")
        bad_subset_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(bad_subset_ip)}})
        assert bad_subset_compile["result"]["status"] == "fail", bad_subset_compile
        assert "INST_BAD_RTL_LANGUAGE_SUBSET: rtl/demo_counter_cx1.sv: forbidden RTL construct present: always_ff" in bad_subset_compile["result"]["issues"], bad_subset_compile
        assert "INST_BAD_RTL_LANGUAGE_SUBSET: rtl/demo_counter_cx1.sv: forbidden RTL construct present: function" in bad_subset_compile["result"]["issues"], bad_subset_compile
        bad_protocol_ip = make_ip(Path(tmp) / "bad_protocol_report")
        (bad_protocol_ip / "signoff").mkdir(exist_ok=True)
        (bad_protocol_ip / "signoff" / "protocol_compliance_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "protocol_compliance_report.v1",
                    "status": "fail",
                    "issues": ["smoke negative"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        bad_protocol_rules_path = bad_protocol_ip / "ontology" / "design_rules.yaml"
        bad_protocol_rules = bad_protocol_rules_path.read_text(encoding="utf-8")
        if not bad_protocol_rules.endswith("\n"):
            bad_protocol_rules += "\n"
        bad_protocol_rules += "\n".join(
            [
                "  - id: INST_BAD_PROTOCOL_REPORT",
                "    rule: RULE_PROTOCOL_COMPLIANCE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    protocol: APB4",
                "    compliance_report: signoff/protocol_compliance_report.json",
                "    evidence_refs:",
                "      - signoff/protocol_compliance_report.json",
                "",
            ]
        )
        bad_protocol_rules_path.write_text(bad_protocol_rules, encoding="utf-8")
        bad_protocol_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(bad_protocol_ip)}})
        assert bad_protocol_compile["result"]["status"] == "fail", bad_protocol_compile
        assert (
            "INST_BAD_PROTOCOL_REPORT: protocol compliance report is not passing: signoff/protocol_compliance_report.json status=fail"
            in bad_protocol_compile["result"]["issues"]
        ), bad_protocol_compile
        missing_phase_ip = make_ip(Path(tmp) / "missing_protocol_phase_trace")
        (missing_phase_ip / "signoff").mkdir(exist_ok=True)
        (missing_phase_ip / "signoff" / "protocol_compliance_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "protocol_compliance_report.v1",
                    "status": "pass",
                    "issues": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        missing_phase_rules_path = missing_phase_ip / "ontology" / "design_rules.yaml"
        missing_phase_rules = missing_phase_rules_path.read_text(encoding="utf-8")
        if not missing_phase_rules.endswith("\n"):
            missing_phase_rules += "\n"
        missing_phase_rules += "\n".join(
            [
                "  - id: INST_MISSING_PROTOCOL_PHASE_TRACE",
                "    rule: RULE_PROTOCOL_COMPLIANCE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    protocol: APB4",
                "    compliance_report: signoff/protocol_compliance_report.json",
                "    phase_trace: sim/missing_apb_phase_trace.jsonl",
                "    evidence_refs:",
                "      - signoff/protocol_compliance_report.json",
                "",
            ]
        )
        missing_phase_rules_path.write_text(missing_phase_rules, encoding="utf-8")
        missing_phase_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(missing_phase_ip)}})
        assert missing_phase_compile["result"]["status"] == "fail", missing_phase_compile
        assert (
            "INST_MISSING_PROTOCOL_PHASE_TRACE: protocol phase trace missing on disk: sim/missing_apb_phase_trace.jsonl"
            in missing_phase_compile["result"]["issues"]
        ), missing_phase_compile
        bad_research_ip = make_ip(Path(tmp) / "bad_auto_research_report")
        (bad_research_ip / "signoff" / "static_signoff_summary.json").write_text(
            json.dumps(
                {
                    "schema_version": "static_signoff_summary.v1",
                    "status": "pass",
                    "reports": {"auto_research": "signoff/ip_research_report.json"},
                    "checks": {"auto_research_next_actions": "pass"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (bad_research_ip / "signoff" / "ip_research_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "ip_research_report.v1",
                    "status": "pass",
                    "method": "smoke_negative",
                    "automation_boundary": "test-only report",
                    "checks": {"ranked_next_actions_present": False},
                    "evidence_refs": ["sim/results.xml"],
                    "evidence_strengths": [
                        {
                            "id": "SMOKE_STRENGTH",
                            "status": "pass",
                            "evidence_refs": ["sim/results.xml"],
                        }
                    ],
                    "ranked_next_actions": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        bad_research_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(bad_research_ip)}})
        assert bad_research_check["result"]["ok"] is False, bad_research_check
        assert (
            "auto research report has no ranked_next_actions: signoff/ip_research_report.json"
            in bad_research_check["result"]["issues"]
        ), bad_research_check
        unsafe_sta_research_ip = make_ip(Path(tmp) / "unsafe_sta_auto_research_report")
        (unsafe_sta_research_ip / "signoff" / "implementation_sta_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "implementation_sta_report.v1",
                    "status": "development_pass",
                    "method": "smoke_development_sta",
                    "metrics": {"wns_ns": 0.0, "tns_ns": 0.0},
                    "issues": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (unsafe_sta_research_ip / "signoff" / "static_signoff_summary.json").write_text(
            json.dumps(
                {
                    "schema_version": "static_signoff_summary.v1",
                    "status": "pass",
                    "reports": {"auto_research": "signoff/ip_research_report.json"},
                    "checks": {"auto_research_next_actions": "pass"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (unsafe_sta_research_ip / "signoff" / "ip_research_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "ip_research_report.v1",
                    "status": "pass",
                    "method": "smoke_unsafe_development_sta_closure",
                    "automation_boundary": "test-only report",
                    "checks": {"ranked_next_actions_present": True},
                    "evidence_refs": ["signoff/implementation_sta_report.json"],
                    "evidence_strengths": [
                        {
                            "id": "DEVELOPMENT_IMPLEMENTATION_STA_EXECUTION",
                            "status": "pass",
                            "evidence_refs": ["signoff/implementation_sta_report.json"],
                        }
                    ],
                    "ranked_next_actions": [
                        {
                            "rank": 1,
                            "id": "IMPLEMENTATION_STA",
                            "status": "closed",
                            "reason": "Development STA passed, incorrectly treated as signoff closure.",
                            "evidence_refs": ["signoff/implementation_sta_report.json"],
                        }
                    ],
                    "signoff_blockers": ["Independent reviewer receipt is still required for signoff/promote."],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        unsafe_sta_research_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(unsafe_sta_research_ip)}})
        assert unsafe_sta_research_check["result"]["ok"] is False, unsafe_sta_research_check
        assert any(
            issue.startswith(
                "auto research report must rank development implementation STA as partially_closed after development_pass"
            )
            for issue in unsafe_sta_research_check["result"]["issues"]
        ), unsafe_sta_research_check
        assert (
            "auto research report missing foundry/PVT blocker after development implementation STA pass: signoff/ip_research_report.json"
            in unsafe_sta_research_check["result"]["issues"]
        ), unsafe_sta_research_check
        assert (
            "auto research report missing gate-level reset/X-prop blocker after development implementation STA pass: signoff/ip_research_report.json"
            in unsafe_sta_research_check["result"]["issues"]
        ), unsafe_sta_research_check
        unsafe_gate_research_ip = make_ip(Path(tmp) / "unsafe_gate_auto_research_report")
        (unsafe_gate_research_ip / "signoff" / "gate_reset_xprop_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "gate_reset_xprop_report.v1",
                    "status": "development_pass",
                    "method": "smoke_development_gate_reset_xprop",
                    "issues": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (unsafe_gate_research_ip / "signoff" / "static_signoff_summary.json").write_text(
            json.dumps(
                {
                    "schema_version": "static_signoff_summary.v1",
                    "status": "pass",
                    "reports": {"auto_research": "signoff/ip_research_report.json"},
                    "checks": {"auto_research_next_actions": "pass"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (unsafe_gate_research_ip / "signoff" / "ip_research_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "ip_research_report.v1",
                    "status": "pass",
                    "method": "smoke_unsafe_development_gate_closure",
                    "automation_boundary": "test-only report",
                    "checks": {"ranked_next_actions_present": True},
                    "evidence_refs": ["signoff/gate_reset_xprop_report.json"],
                    "evidence_strengths": [
                        {
                            "id": "DEVELOPMENT_GATE_RESET_XPROP_EXECUTION",
                            "status": "development_pass",
                            "evidence_refs": ["signoff/gate_reset_xprop_report.json"],
                        }
                    ],
                    "ranked_next_actions": [
                        {
                            "rank": 1,
                            "id": "GATE_LEVEL_RESET_XPROP",
                            "status": "closed",
                            "reason": "Development mapped-netlist smoke passed, incorrectly treated as production closure.",
                            "evidence_refs": ["signoff/gate_reset_xprop_report.json"],
                        }
                    ],
                    "signoff_blockers": ["Independent reviewer receipt is still required for signoff/promote."],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        unsafe_gate_research_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(unsafe_gate_research_ip)}})
        assert unsafe_gate_research_check["result"]["ok"] is False, unsafe_gate_research_check
        assert any(
            issue.startswith(
                "auto research report must rank development gate reset/X-prop as partially_closed after development_pass"
            )
            for issue in unsafe_gate_research_check["result"]["issues"]
        ), unsafe_gate_research_check
        assert (
            "auto research report missing SDF/foundry blocker after development gate reset/X-prop pass: signoff/ip_research_report.json"
            in unsafe_gate_research_check["result"]["issues"]
        ), unsafe_gate_research_check
        unsafe_formal_research_ip = make_ip(Path(tmp) / "unsafe_formal_auto_research_report")
        (unsafe_formal_research_ip / "signoff" / "formal_assertion_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "formal_assertion_report.v1",
                    "status": "development_pass",
                    "method": "smoke_bounded_formal",
                    "bound_cycles": 8,
                    "issues": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (unsafe_formal_research_ip / "signoff" / "static_signoff_summary.json").write_text(
            json.dumps(
                {
                    "schema_version": "static_signoff_summary.v1",
                    "status": "pass",
                    "reports": {"auto_research": "signoff/ip_research_report.json"},
                    "checks": {"auto_research_next_actions": "pass"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (unsafe_formal_research_ip / "signoff" / "ip_research_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "ip_research_report.v1",
                    "status": "pass",
                    "method": "smoke_unsafe_development_formal_closure",
                    "automation_boundary": "test-only report",
                    "checks": {"ranked_next_actions_present": True},
                    "evidence_refs": ["signoff/formal_assertion_report.json"],
                    "evidence_strengths": [
                        {
                            "id": "DEVELOPMENT_FORMAL_ASSERTION_EXECUTION",
                            "status": "development_pass",
                            "evidence_refs": ["signoff/formal_assertion_report.json"],
                        }
                    ],
                    "ranked_next_actions": [
                        {
                            "rank": 1,
                            "id": "FORMAL_ASSERTION_OPTION",
                            "status": "closed",
                            "reason": "Formal proof passed.",
                            "evidence_refs": ["signoff/formal_assertion_report.json"],
                        }
                    ],
                    "signoff_blockers": ["Independent reviewer receipt is still required for signoff/promote."],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        unsafe_formal_research_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(unsafe_formal_research_ip)}})
        assert unsafe_formal_research_check["result"]["ok"] is False, unsafe_formal_research_check
        assert any(
            issue.startswith(
                "auto research report must rank development formal assertion as partially_closed after development_pass"
            )
            for issue in unsafe_formal_research_check["result"]["issues"]
        ), unsafe_formal_research_check
        assert any(
            issue.startswith(
                "auto research formal assertion action missing bounded/development limitation after development_pass"
            )
            for issue in unsafe_formal_research_check["result"]["issues"]
        ), unsafe_formal_research_check
        assert any(
            issue.startswith(
                "auto research formal assertion action missing contract/signoff limitation after development_pass"
            )
            for issue in unsafe_formal_research_check["result"]["issues"]
        ), unsafe_formal_research_check
        unsafe_handoff_ip = make_ip(Path(tmp) / "unsafe_handoff_report")
        bad_metrics = {
            "schema_version": "oag_improvement_metrics.v1",
            "closure_profile": "development",
            "requirements": {"total": 1},
            "contracts": {"total": 1},
            "closure": {"total": 1, "closed": 1, "open": 0, "closed_percent": 100.0, "issue_count": 0},
            "check": {"issue_count": 0, "stale_issue_count": 0},
            "evidence": {"files_present_count": 2, "files_missing_count": 0},
            "stage_receipts": {"count": 0},
            "ledger": {"events": 0},
            "auto_research": {
                "reports": 0,
                "actions": 0,
                "blocked_actions": 0,
                "partially_closed_actions": 0,
                "closed_actions": 0,
                "signoff_blockers": 0,
            },
            "decisions": {"receipts": 0, "independent_passing_reviewers": 0},
        }
        (unsafe_handoff_ip / "handoff" / "readiness_handoff.json").write_text(
            json.dumps(
                {
                    "schema_version": "oag_readiness_handoff.v1",
                    "id": "HANDOFF_UNSAFE_DEVELOPMENT_SIGNOFF_READY",
                    "ip": unsafe_handoff_ip.name,
                    "stage": "handoff",
                    "intent": "smoke unsafe handoff",
                    "generated_at": "2026-06-19T00:00:00Z",
                    "closure_profile": "development",
                    "status": "pass",
                    "method": "smoke_negative",
                    "automation_boundary": "Readiness handoff only; this is not a signoff decision.",
                    "progress_denominator": "derived_from_active_ip_obligations",
                    "numeric_summary": {
                        "requirements_total": 1,
                        "contracts_total": 1,
                        "obligations_total": 1,
                        "obligations_closed": 1,
                        "obligations_open": 0,
                        "closure_percent": 100.0,
                        "closure_issue_count": 0,
                        "check_issue_count": 0,
                        "stale_issue_count": 0,
                        "evidence_files_present": 2,
                        "evidence_files_total": 2,
                        "evidence_files_missing": 0,
                        "stage_receipts": 0,
                        "ledger_events": 0,
                        "auto_research_reports": 0,
                        "ranked_next_actions": 0,
                        "blocked_actions": 0,
                        "partially_closed_actions": 0,
                        "closed_actions": 0,
                        "signoff_blockers": 0,
                        "decision_receipts": 0,
                        "independent_passing_reviewers": 0,
                    },
                    "readiness": {
                        "development_ready": True,
                        "signoff_ready": True,
                        "closure_complete": True,
                        "check_clean": True,
                        "evidence_complete": True,
                    },
                    "ranked_next_actions": [],
                    "signoff_blockers": [],
                    "evidence_refs": ["sim/results.xml"],
                    "improvement_metrics": bad_metrics,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        unsafe_handoff_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(unsafe_handoff_ip)}})
        assert unsafe_handoff_check["result"]["ok"] is False, unsafe_handoff_check
        assert (
            "handoff report cannot mark signoff_ready=true when closure_profile=development: handoff/readiness_handoff.json"
            in unsafe_handoff_check["result"]["issues"]
        ), unsafe_handoff_check
        formal_ip = make_ip(Path(tmp) / "bad_formal")
        contract_text = (formal_ip / "ontology" / "contracts.yaml").read_text(encoding="utf-8")
        contract_text += "\n".join(
            [
                "  - id: CONTRACT_BAD_FORMAL",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    method: formal",
                "    pass_condition: register map is proven",
                "    evidence_kinds: [formal]",
                "",
            ]
        )
        (formal_ip / "ontology" / "contracts.yaml").write_text(contract_text, encoding="utf-8")
        formal_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(formal_ip)}})
        assert formal_compile["result"]["status"] == "fail", formal_compile
        assert "CONTRACT_BAD_FORMAL: formal/assertion contract missing assertion/proof reference" in formal_compile["result"]["issues"], formal_compile
        bad_decomp_ip = make_ip(Path(tmp) / "bad_decomposition")
        (bad_decomp_ip / "ontology" / "decomposition.yaml").write_text(
            "\n".join(
                [
                    "schema: oag_decomposition.v1",
                    f"ip: {bad_decomp_ip.name}",
                    "profile:",
                    "  mode: greenfield_modular",
                    "  rationale: one module is intentionally invalid for this negative test",
                    "modules:",
                    f"  - id: {bad_decomp_ip.name}",
                    "    ownership: current_ip",
                    f"    file: rtl/{bad_decomp_ip.name}.sv",
                    "    owned_obligations: [OBL_DEMO_COUNTER_CX1_RESET_KNOWN]",
                    "    owned_contracts: [CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD]",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        bad_decomp_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(bad_decomp_ip)}})
        assert bad_decomp_compile["result"]["status"] == "fail", bad_decomp_compile
        assert "greenfield_modular profile requires at least two current_ip modules or use small_leaf_single_file" in bad_decomp_compile["result"]["issues"], bad_decomp_compile
        bad_file_boundary_ip = make_ip(Path(tmp) / "bad_file_boundary")
        (bad_file_boundary_ip / "ontology" / "decomposition.yaml").write_text(
            "\n".join(
                [
                    "schema: oag_decomposition.v1",
                    f"ip: {bad_file_boundary_ip.name}",
                    "profile:",
                    "  mode: greenfield_modular",
                    "  rationale: duplicate physical files are intentionally invalid for this negative test",
                    "modules:",
                    f"  - id: {bad_file_boundary_ip.name}_top",
                    "    ownership: current_ip",
                    f"    file: rtl/{bad_file_boundary_ip.name}.sv",
                    "    role: top",
                    "    owned_obligations: [OBL_DEMO_COUNTER_CX1_RESET_KNOWN]",
                    "    owned_contracts: [CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD]",
                    f"  - id: {bad_file_boundary_ip.name}_core",
                    "    ownership: current_ip",
                    f"    file: rtl/{bad_file_boundary_ip.name}.sv",
                    "    role: core",
                    "    owned_obligations: []",
                    "    owned_contracts: []",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        bad_file_boundary_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(bad_file_boundary_ip)}})
        assert bad_file_boundary_compile["result"]["status"] == "fail", bad_file_boundary_compile
        assert any(
            "greenfield_modular module file boundary requires unique file per current_ip module" in issue
            for issue in bad_file_boundary_compile["result"]["issues"]
        ), bad_file_boundary_compile
        priority_ip = make_ip(Path(tmp) / "bad_priority")
        rules_path = priority_ip / "ontology" / "design_rules.yaml"
        rules_text = rules_path.read_text(encoding="utf-8").replace(
            "instances:\n",
            "\n".join(
                [
                    "instances:",
                    "  - id: BAD_PRIORITY_INSTANCE",
                    "    rule: RULE_SAME_CYCLE_PRIORITY_DECLARED",
                    "    status: active",
                    "    conflict: [ctrl_disable_write, terminal_tick]",
                    "    requirement: REQ_DEMO_COUNTER_CX1_001",
                    "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                    "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                    "",
                ]
            ),
            1,
        )
        rules_path.write_text(rules_text, encoding="utf-8")
        priority_compile = call({"tool": "oag.compile", "arguments": {"ip_dir": str(priority_ip)}})
        assert priority_compile["result"]["status"] == "fail", priority_compile
        assert "BAD_PRIORITY_INSTANCE: same-cycle priority rule missing priority" in priority_compile["result"]["issues"], priority_compile
        protection_ip = make_ip(Path(tmp) / "bad_protection")
        baseline = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(protection_ip),
                    "stage": "req",
                    "type": "decision",
                    "claim": "baseline protected truth snapshot",
                    "summary": "Establish protected field snapshot before edits.",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "status": "open",
                },
            }
        )
        assert baseline["result"]["ledger_event"], baseline
        locked_truth = protection_ip / "req" / "locked_truth.md"
        locked_truth.write_text(locked_truth.read_text(encoding="utf-8") + "\n- Unauthorized semantic edit.\n", encoding="utf-8")
        before_records = sorted((protection_ip / "knowledge" / "records").glob("*.json"))
        rejected = call_process(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(protection_ip),
                    "stage": "req",
                    "claim": "unauthorized protected edit record",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "status": "open",
                },
            }
        )
        assert rejected.returncode != 0, rejected.stdout
        rejected_response = json.loads(rejected.stdout)
        assert "protected fields changed without human approval" in rejected_response["errors"][0], rejected_response
        after_records = sorted((protection_ip / "knowledge" / "records").glob("*.json"))
        assert after_records == before_records, [before_records, after_records]
        protection_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(protection_ip)}})
        assert protection_check["result"]["ok"] is False, protection_check
        assert any("protected fields changed without ledger approval" in issue for issue in protection_check["result"]["issues"]), protection_check
        ledger_ip = make_ip(Path(tmp) / "bad_ledger")
        ledger_record = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(ledger_ip),
                    "stage": "sim",
                    "claim": "ledger tamper baseline",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "status": "open",
                },
            }
        )
        assert ledger_record["result"]["ledger_event"], ledger_record
        ledger_path = ledger_ip / "knowledge" / "ledger.jsonl"
        ledger_path.write_text(ledger_path.read_text(encoding="utf-8").replace('"action": "log"', '"action": "tampered"', 1), encoding="utf-8")
        ledger_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(ledger_ip)}})
        assert ledger_check["result"]["ok"] is False, ledger_check
        assert any("event_hash mismatch" in issue for issue in ledger_check["result"]["issues"]), ledger_check
        monotonic_ip = make_ip(Path(tmp) / "bad_monotonic")
        closed = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(monotonic_ip),
                    "stage": "sim",
                    "claim": "monotonic obligation closed",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "rocev": {
                        "obligation": {"id": "OBL_MONO_SCOREBOARD", "text": "closed once"},
                        "contract": {"id": "CONTRACT_MONO_SCOREBOARD", "method": "scoreboard"},
                        "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                        "validation": {"status": "closed", "verdict": "pass", "rationale": "baseline close"},
                    },
                },
            }
        )
        assert closed["result"]["status"] == "closed", closed
        reopened = call(
            {
                "tool": "oag.record",
                "arguments": {
                    "ip_dir": str(monotonic_ip),
                    "stage": "sim",
                    "claim": "monotonic obligation silently reopened",
                    "actor": {"kind": "ai", "id": "claude", "surface": "smoke"},
                    "status": "open",
                    "rocev": {
                        "obligation": {"id": "OBL_MONO_SCOREBOARD", "text": "reopened without decision", "status": "open"},
                        "contract": {"id": "CONTRACT_MONO_SCOREBOARD", "method": "scoreboard", "status": "open"},
                        "validation": {"status": "open", "verdict": "pending", "rationale": "silent downgrade"},
                    },
                },
            }
        )
        assert reopened["result"]["status"] == "open", reopened
        monotonic_check = call({"tool": "oag.check", "arguments": {"ip_dir": str(monotonic_ip)}})
        assert monotonic_check["result"]["ok"] is False, monotonic_check
        assert any("monotonic closure violation" in issue for issue in monotonic_check["result"]["issues"]), monotonic_check
        print(json.dumps({"ok": True, "ip": str(ip), "runtime": "script_skill_hooks"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
