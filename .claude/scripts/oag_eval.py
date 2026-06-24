#!/usr/bin/env python3
"""Evaluation runner for OAG run-loop and Claude Code hook gates.

Unlike smoke_test.py, this script reports scenario-level observations. It is
intended for quickly checking whether the OAG gates behave like an agent harness:
incomplete work blocks stop, complete work passes, repeated blockers ask for a
human decision without trapping Stop in a loop, completion still requires a
decision receipt, stale evidence is invalidated, vacuous closure is blocked, and
greenfield module boundaries are enforced.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import oag_paths  # noqa: E402
import smoke_test  # noqa: E402


CaseFn = Callable[[Path], dict[str, Any]]
HOOKS_DIR = smoke_test.ROOT / "hooks"
PROJECT = smoke_test.ROOT.parent


def _approve_eval_protected_update(ip: Path, *, summary: str) -> dict[str, Any]:
    response = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "protected_ontology_eval_update",
                "stage": "ontology",
                "record_decision": True,
                "actor": {"kind": "human", "id": "eval-owner", "surface": "eval"},
                "summary": summary,
            },
        }
    )
    assert response["result"]["decision_receipt"], response
    return response["result"]


def _start_run(ip: Path, *, intent: str) -> tuple[str, dict[str, Any]]:
    response = smoke_test.call(
        {
            "tool": "oag.run.start",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "intent": intent,
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
            },
        }
    )
    return str(response["result"]["run_id"]), response["result"]


def _close_run(ip: Path, run_id: str, *, intent: str) -> dict[str, Any]:
    _close_run_graph_prerequisites(ip, run_id)
    record = smoke_test.call(
        {
            "tool": "oag.run.record",
            "arguments": {
                "ip_dir": str(ip),
                "run_id": run_id,
                "stage": "sim",
                "summary": "evaluation evidence closes the active obligation",
                "evidence_files": ["sim/results.xml", "sim/scoreboard_events.jsonl"],
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
            },
        }
    )
    checkpoint = smoke_test.call(
        {
            "tool": "oag.run.checkpoint",
            "arguments": {
                "ip_dir": str(ip),
                "run_id": run_id,
                "stage": "sim",
                "intent": intent,
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
            },
        }
    )
    return {"record": record["result"], "checkpoint": checkpoint["result"]}


def _close_run_graph_prerequisites(ip: Path, run_id: str) -> None:
    shard = ip / "sim" / "slices" / "OBL_DEMO_COUNTER_CX1_RESET_KNOWN" / "scoreboard_events.jsonl"
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text((ip / "sim" / "scoreboard_events.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    for task_id in (
        "triage.OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
        "evidence.sim.OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
        "merge.sim.aggregate",
    ):
        graph_record = smoke_test.run_wavefront("record", "--ip-dir", str(ip), "--run-id", run_id, "--task-id", task_id, "--status", "closed", "--json", project_root=ip.parent)
        assert graph_record.returncode == 0, graph_record.stderr or graph_record.stdout


def _hook_json(ip: Path, run_id: str) -> tuple[int, dict[str, Any] | None, str]:
    proc = smoke_test.stop_gate({"ip_dir": str(ip), "run_id": run_id})
    if not proc.stdout.strip():
        return proc.returncode, None, proc.stderr
    return proc.returncode, json.loads(proc.stdout), proc.stderr


def _run_hook(script: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
        env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
    )
    if not proc.stdout.strip():
        return proc.returncode, None, proc.stderr
    return proc.returncode, json.loads(proc.stdout), proc.stderr


def _additional_context(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    output = payload.get("hookSpecificOutput")
    if not isinstance(output, dict):
        return ""
    return str(output.get("additionalContext") or "")


def _human_approve_signoff_profile(ip: Path) -> None:
    policies = oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml")
    policies.write_text(policies.read_text(encoding="utf-8").replace("closure_profile: development", "closure_profile: signoff"), encoding="utf-8")
    approval = smoke_test.call(
        {
            "tool": "oag.record",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "signoff",
                "type": "decision",
                "claim": "human approval to enter signoff closure profile",
                "summary": "Human owner approved the protected policy transition to signoff.",
                "actor": {"kind": "human", "id": "eval-owner", "surface": "eval"},
                "approval": {"kind": "human", "approved": True, "reason": "eval signoff path"},
                "status": "open",
            },
        }
    )
    assert approval["result"]["ledger_event"], approval


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml  # type: ignore

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(data, dict), path
    return data


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml  # type: ignore

    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _check_issues(ip: Path) -> list[str]:
    response = smoke_test.call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})
    return [str(item) for item in response["result"]["issues"]]


def _record_closed_validation(ip: Path, *, surface: str = "eval") -> dict[str, Any]:
    response = smoke_test.call(
        {
            "tool": "oag.record",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "claim": "evaluation closes reset obligation",
                "summary": "Evaluation closes the scaffold reset obligation through scoreboard evidence.",
                "actor": {"kind": "ai", "id": "producer", "surface": surface},
                "rocev": {
                    "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN", "status": "closed"},
                    "contract": {"id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", "method": "scoreboard", "status": "closed"},
                    "evidence": {"files": ["sim/results.xml", "sim/scoreboard_events.jsonl"], "tests": [], "commit": ""},
                    "validation": {"status": "closed", "verdict": "pass", "rationale": "scoreboard evidence passed"},
                },
            },
        }
    )
    assert response["result"]["status"] == "closed", response
    return response["result"]


def case_stop_gate_blocks_incomplete(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "blocks_incomplete")
    run_id, started = _start_run(ip, intent="eval incomplete run blocks stop")
    rc, payload, stderr = _hook_json(ip, run_id)
    assert rc == 0, stderr
    assert payload is not None, "expected Claude Code hook block JSON"
    assert payload.get("decision") == "block", payload
    reason = str(payload.get("reason") or "")
    assert "OAG NEXT ACTION" in reason, payload
    assert "run incomplete" in reason, payload
    return {
        "ip": str(ip),
        "run_id": run_id,
        "active_obligation": started["next_action"]["active_obligation"],
        "hook_decision": payload["decision"],
        "contains_next_action": "OAG NEXT ACTION" in reason,
    }


def case_stop_gate_obeys_policy_limit(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "policy_limited")
    run_id, _started = _start_run(ip, intent="eval policy-limited run")
    configured = smoke_test.call(
        {
            "tool": "oag.configure",
            "arguments": {
                "ip_dir": str(ip),
                "hook_auto_continue_until": "rtl",
                "actor": {"kind": "human", "id": "eval-owner", "surface": "eval"},
                "approval": {"kind": "human", "approved": True, "reason": "eval policy limit"},
            },
        }
    )
    stop = smoke_test.call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(ip), "run_id": run_id}})
    rc, payload, stderr = _hook_json(ip, run_id)
    assert rc == 0, stderr
    assert payload is None, payload
    assert stop["result"]["should_continue"] is False, stop
    assert stop["result"]["reason"] == "policy_limit_reached", stop
    return {
        "ip": str(ip),
        "run_id": run_id,
        "configured": configured["result"]["updates"],
        "reason": stop["result"]["reason"],
        "next_action_stage": stop["result"]["policy"]["next_action_stage"],
    }


def case_compile_skips_fresh_graph(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "fresh_compile")
    first = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    second = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert first["result"]["status"] == "pass", first
    assert second["result"]["status"] == "pass", second
    assert first["result"]["skipped"] is False, first
    assert second["result"]["skipped"] is True, second
    manifest = oag_paths.legacy_or_hidden(ip, "ontology/generated/compile_manifest.json")
    assert manifest.is_file(), manifest
    assert oag_paths.legacy_or_hidden(ip, f"ontology/generated/authoring_packets/rtl__{ip.name}.json").is_file()
    assert oag_paths.legacy_or_hidden(ip, f"ontology/generated/authoring_packets/tb__{ip.name}.json").is_file()
    return {
        "ip": str(ip),
        "first_skipped": first["result"]["skipped"],
        "second_skipped": second["result"]["skipped"],
        "manifest": str(manifest),
    }


def case_modeling_scaffold_seed(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "modeling_seed")
    policies = _read_yaml(oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml"))
    modeling = _read_yaml(oag_paths.legacy_or_hidden(ip, "ontology/modeling.yaml"))
    modeling_policy = policies.get("modeling_policy") if isinstance(policies.get("modeling_policy"), dict) else {}
    assert modeling_policy.get("canonical_modeling_file") == "ontology/modeling.yaml", policies
    assert modeling_policy.get("full_fl_model_required") is False, policies
    assert modeling_policy.get("full_cl_model_required") is False, policies
    assert modeling.get("schema_version") == "oag_modeling.v1", modeling
    assert isinstance(modeling.get("behavior_model"), dict) and modeling["behavior_model"], modeling
    assert isinstance(modeling.get("cycle_rules"), dict) and modeling["cycle_rules"], modeling
    return {
        "ip": str(ip),
        "profile": modeling_policy.get("profile"),
        "full_fl_model_required": modeling_policy.get("full_fl_model_required"),
        "full_cl_model_required": modeling_policy.get("full_cl_model_required"),
    }


def case_requirement_atom_scaffold_seed(root: Path) -> dict[str, Any]:
    draft_ip = root / "requirement_atom_draft" / "demo_counter_cx1"
    scaffold = smoke_test.call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(draft_ip), "owner": "eval"}})
    assert scaffold["ok"] is True, scaffold
    policies = _read_yaml(oag_paths.legacy_or_hidden(draft_ip, "ontology/policies.yaml"))
    atoms = _read_yaml(oag_paths.legacy_or_hidden(draft_ip, "ontology/requirement_atoms.yaml"))
    decomposition_policy = policies.get("requirement_decomposition_policy") if isinstance(policies.get("requirement_decomposition_policy"), dict) else {}
    assert decomposition_policy.get("canonical_requirement_atom_file") == "ontology/requirement_atoms.yaml", policies
    assert decomposition_policy.get("require_atoms_after_lock") is True, policies
    assert atoms.get("schema_version") == "oag_requirement_atoms.v1", atoms
    assert isinstance(atoms.get("requirement_atoms"), list) and atoms["requirement_atoms"], atoms

    draft_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_requirement_atom_check.py"), "--ip-dir", str(draft_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert draft_proc.returncode == 0, draft_proc.stdout + draft_proc.stderr
    draft = json.loads(draft_proc.stdout)
    assert draft["status"] == "pass", draft

    locked_ip = smoke_test.make_ip(root / "requirement_atom_locked")
    locked_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_requirement_atom_check.py"), "--ip-dir", str(locked_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert locked_proc.returncode != 0, locked_proc.stdout + locked_proc.stderr
    locked = json.loads(locked_proc.stdout)
    codes = {item["code"] for item in locked["issues"]}
    assert "ATOM_AMBIGUITY" in codes, locked
    assert "CONTRACT_ASSUME_MISSING" in codes, locked
    assert "CONTRACT_GUARANTEE_MISSING" in codes, locked
    return {
        "draft_ip": str(draft_ip),
        "locked_ip": str(locked_ip),
        "draft_status": draft["status"],
        "locked_status": locked["status"],
        "locked_issue_codes": sorted(codes),
    }


def case_lock_readiness_scaffold_seed(root: Path) -> dict[str, Any]:
    draft_ip = root / "lock_readiness_draft" / "demo_counter_cx1"
    scaffold = smoke_test.call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(draft_ip), "owner": "eval"}})
    assert scaffold["ok"] is True, scaffold
    decisions = _read_yaml(oag_paths.legacy_or_hidden(draft_ip, "ontology/decision_matrix.yaml"))
    policies = _read_yaml(oag_paths.legacy_or_hidden(draft_ip, "ontology/policies.yaml"))
    decision_policy = policies.get("decision_matrix_policy") if isinstance(policies.get("decision_matrix_policy"), dict) else {}
    assert decisions.get("schema_version") == "oag_decision_matrix.v1", decisions
    assert isinstance(decisions.get("decisions"), list) and decisions["decisions"], decisions
    assert decision_policy.get("canonical_decision_matrix_file") == "ontology/decision_matrix.yaml", policies

    draft_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_lock_readiness_check.py"), "--ip-dir", str(draft_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert draft_proc.returncode == 0, draft_proc.stdout + draft_proc.stderr
    draft = json.loads(draft_proc.stdout)
    assert draft["status"] == "pass", draft
    assert draft["hard_gate"] is False, draft
    assert draft["counts"]["unresolved_lock_blockers"] >= 1, draft

    hard_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_lock_readiness_check.py"), "--ip-dir", str(draft_ip), "--require-locked", "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert hard_proc.returncode != 0, hard_proc.stdout + hard_proc.stderr
    hard = json.loads(hard_proc.stdout)
    hard_codes = {item["code"] for item in hard["issues"]}
    assert "DECISION_LOCK_BLOCKER" in hard_codes, hard
    assert "AMBIGUITY_LOCK_BLOCKER" in hard_codes, hard
    assert "REQ_STATUS_DRAFT" in hard_codes, hard
    assert "REQ_AMBIGUITY_STATUS" in hard_codes, hard
    assert "ATOM_AMBIGUITY" in hard_codes, hard
    assert "CONTRACT_VARIABLES_MISSING" in hard_codes, hard
    assert "VPLAN_OPEN_BLOCKERS" in hard_codes, hard
    assert "VOBJ_NOT_READY" in hard_codes, hard
    assert "VOBJ_OPEN_RISK" in hard_codes, hard

    locked_ip = smoke_test.make_ip(root / "lock_readiness_locked")
    locked_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_lock_readiness_check.py"), "--ip-dir", str(locked_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert locked_proc.returncode != 0, locked_proc.stdout + locked_proc.stderr
    locked = json.loads(locked_proc.stdout)
    locked_codes = {item["code"] for item in locked["issues"]}
    assert "DECISION_LOCK_BLOCKER" in locked_codes, locked
    assert "AMBIGUITY_LOCK_BLOCKER" in locked_codes, locked
    assert "REQ_STATUS_DRAFT" in locked_codes, locked
    assert "CONTRACT_VARIABLES_MISSING" in locked_codes, locked
    assert "REQ_AMBIGUITY_STATUS" in locked_codes, locked
    assert "CONTRACT_ASSUME_MISSING" in locked_codes, locked
    assert "CONTRACT_GUARANTEE_MISSING" in locked_codes, locked
    assert "VPLAN_OPEN_BLOCKERS" in locked_codes, locked
    assert "VOBJ_NOT_READY" in locked_codes, locked
    assert "VOBJ_OPEN_RISK" in locked_codes, locked
    return {
        "draft_ip": str(draft_ip),
        "locked_ip": str(locked_ip),
        "draft_status": draft["status"],
        "hard_status": hard["status"],
        "locked_status": locked["status"],
        "hard_issue_codes": sorted(hard_codes),
        "locked_issue_codes": sorted(locked_codes),
    }


def case_requirement_quality_scaffold_seed(root: Path) -> dict[str, Any]:
    draft_ip = root / "requirement_quality_draft" / "demo_counter_cx1"
    scaffold = smoke_test.call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(draft_ip), "owner": "eval"}})
    assert scaffold["ok"] is True, scaffold
    policies = _read_yaml(oag_paths.legacy_or_hidden(draft_ip, "ontology/policies.yaml"))
    source_claims = _read_yaml(draft_ip / "req" / "source_claims.yaml")
    ambiguities = _read_yaml(draft_ip / "req" / "ambiguity_register.yaml")
    quality_policy = policies.get("requirement_quality_policy") if isinstance(policies.get("requirement_quality_policy"), dict) else {}
    assert quality_policy.get("canonical_source_claims_file") == "req/source_claims.yaml", policies
    assert quality_policy.get("canonical_ambiguity_register_file") == "req/ambiguity_register.yaml", policies
    assert source_claims.get("schema_version") == "oag_source_claims.v1", source_claims
    assert ambiguities.get("schema_version") == "oag_ambiguity_register.v1", ambiguities
    assert isinstance(source_claims.get("claims"), list) and source_claims["claims"], source_claims
    assert isinstance(ambiguities.get("ambiguities"), list) and ambiguities["ambiguities"], ambiguities

    draft_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_req_quality_check.py"), "--ip-dir", str(draft_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert draft_proc.returncode == 0, draft_proc.stdout + draft_proc.stderr
    draft = json.loads(draft_proc.stdout)
    assert draft["status"] == "pass", draft
    assert draft["hard_gate"] is False, draft
    assert draft["counts"]["unresolved_lock_ambiguities"] >= 1, draft

    hard_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_req_quality_check.py"), "--ip-dir", str(draft_ip), "--require-locked", "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert hard_proc.returncode != 0, hard_proc.stdout + hard_proc.stderr
    hard = json.loads(hard_proc.stdout)
    hard_codes = {item["code"] for item in hard["issues"]}
    assert "AMBIGUITY_LOCK_BLOCKER" in hard_codes, hard
    assert "REQ_STATUS_DRAFT" in hard_codes, hard
    assert "REQ_AMBIGUITY_STATUS" in hard_codes, hard
    return {
        "draft_ip": str(draft_ip),
        "draft_status": draft["status"],
        "hard_status": hard["status"],
        "hard_issue_codes": sorted(hard_codes),
    }


def case_verification_plan_scaffold_seed(root: Path) -> dict[str, Any]:
    draft_ip = root / "verification_plan_draft" / "demo_counter_cx1"
    scaffold = smoke_test.call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(draft_ip), "owner": "eval"}})
    assert scaffold["ok"] is True, scaffold
    policies = _read_yaml(oag_paths.legacy_or_hidden(draft_ip, "ontology/policies.yaml"))
    vplan = _read_yaml(oag_paths.legacy_or_hidden(draft_ip, "ontology/verification_plan.yaml"))
    strategy_policy = policies.get("verification_strategy_policy") if isinstance(policies.get("verification_strategy_policy"), dict) else {}
    assert strategy_policy.get("canonical_verification_plan_file") == "ontology/verification_plan.yaml", policies
    assert strategy_policy.get("owner_role") == "oag-verification-strategy-agent", policies
    assert strategy_policy.get("tb_writer_may_define_strategy") is False, policies
    assert vplan.get("schema_version") == "oag_verification_plan.v1", vplan
    assert isinstance(vplan.get("verification_objectives"), list) and vplan["verification_objectives"], vplan

    draft_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_verification_plan_check.py"), "--ip-dir", str(draft_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert draft_proc.returncode == 0, draft_proc.stdout + draft_proc.stderr
    draft = json.loads(draft_proc.stdout)
    assert draft["status"] == "pass", draft
    assert draft["hard_gate"] is False, draft

    hard_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_verification_plan_check.py"), "--ip-dir", str(draft_ip), "--require-locked", "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert hard_proc.returncode != 0, hard_proc.stdout + hard_proc.stderr
    hard = json.loads(hard_proc.stdout)
    hard_codes = {item["code"] for item in hard["issues"]}
    assert "VPLAN_OPEN_BLOCKERS" in hard_codes, hard
    assert "VOBJ_NOT_READY" in hard_codes, hard
    assert "VOBJ_OPEN_RISK" in hard_codes, hard
    return {
        "draft_ip": str(draft_ip),
        "draft_status": draft["status"],
        "hard_status": hard["status"],
        "hard_issue_codes": sorted(hard_codes),
    }


def case_contract_strength_scaffold_seed(root: Path) -> dict[str, Any]:
    draft_ip = root / "contract_strength_draft" / "demo_counter_cx1"
    scaffold = smoke_test.call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(draft_ip), "owner": "eval"}})
    assert scaffold["ok"] is True, scaffold
    draft_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_contract_strength_check.py"), "--ip-dir", str(draft_ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert draft_proc.returncode == 0, draft_proc.stdout + draft_proc.stderr
    draft = json.loads(draft_proc.stdout)
    assert draft["status"] == "pass", draft

    hard_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_contract_strength_check.py"), "--ip-dir", str(draft_ip), "--require-locked", "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert hard_proc.returncode != 0, hard_proc.stdout + hard_proc.stderr
    hard = json.loads(hard_proc.stdout)
    codes = {item["code"] for item in hard["issues"]}
    assert "CONTRACT_VARIABLES_MISSING" in codes, hard
    assert "CONTRACT_ASSUME_MISSING" in codes, hard
    assert "CONTRACT_GUARANTEE_MISSING" in codes, hard
    return {"draft_status": draft["status"], "hard_status": hard["status"], "hard_issue_codes": sorted(codes)}


def case_authoring_packet_scaffold_seed(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "authoring_packet_seed")
    compile_result = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert compile_result["result"]["status"] == "pass", compile_result
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_authoring_packet_check.py"), "--ip-dir", str(ip), "--require-packets", "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "pass", result
    assert result["counts"]["rtl_packets"] >= 1, result
    assert result["counts"]["tb_packets"] >= 1, result
    return {"ip": str(ip), "counts": result["counts"]}


def case_trace_graph_scaffold_seed(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "trace_graph_seed")
    draft_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_trace_graph_check.py"), "--ip-dir", str(ip), "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert draft_proc.returncode == 0, draft_proc.stdout + draft_proc.stderr
    draft = json.loads(draft_proc.stdout)
    assert draft["status"] == "pass", draft
    hard_proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_trace_graph_check.py"), "--ip-dir", str(ip), "--require-locked", "--json"],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert hard_proc.returncode == 0, hard_proc.stdout + hard_proc.stderr
    hard = json.loads(hard_proc.stdout)
    assert hard["status"] == "pass", hard
    return {"ip": str(ip), "draft_counts": draft["counts"], "hard_counts": hard["counts"]}


def case_decision_matrix_generator_mctp_profile(root: Path) -> dict[str, Any]:
    ip = root / "mctp_profile_seed" / "mctp_rx"
    scaffold = smoke_test.call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(ip), "owner": "eval"}})
    assert scaffold["ok"] is True, scaffold
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "oag_decision_matrix_generate.py"),
            "--ip-dir",
            str(ip),
            "--profile",
            "mctp-rx",
            "--owner",
            "eval",
            "--write",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["counts"]["added"] >= 13, result
    matrix = _read_yaml(oag_paths.legacy_or_hidden(ip, "ontology/decision_matrix.yaml"))
    rows = {item["id"]: item for item in matrix["decisions"]}
    assert rows["D003_TLP_BOUNDARY"]["status"] == "unresolved", rows["D003_TLP_BOUNDARY"]
    assert rows["D003_TLP_BOUNDARY"]["decision"] is None, rows["D003_TLP_BOUNDARY"]
    assert "WLAST" in rows["D003_TLP_BOUNDARY"]["recommended"], rows["D003_TLP_BOUNDARY"]
    return {"ip": str(ip), "added": result["counts"]["added"], "decision_count": len(rows)}


def case_deep_semantic_intake_mctp_profile(root: Path) -> dict[str, Any]:
    ip = root / "mctp_intake_seed" / "mctp_rx"
    scaffold = smoke_test.call({"tool": "oag.scaffold", "arguments": {"ip_dir": str(ip), "owner": "eval"}})
    assert scaffold["ok"] is True, scaffold
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "oag_deep_semantic_intake.py"),
            "--ip-dir",
            str(ip),
            "--topic",
            "mctp rx request",
            "--prompt",
            "I need mctp rx ip. AXI WDATA carries full PCIe TLP and completed messages are stored in SRAM.",
            "--profile",
            "mctp-rx",
            "--owner",
            "eval",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
        cwd=PROJECT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    report = Path(result["path"])
    assert report.is_file(), report
    assert any("TLP boundary" in item for item in result["hidden_implications"]), result
    decision_ids = {row["id"] for row in result["decision_seed"]["rows"]}
    assert "D007_CONTEXT_KEY" in decision_ids, result
    return {"ip": str(ip), "report": str(report), "decision_count": len(decision_ids)}


def case_skill_router_split_contract(root: Path) -> dict[str, Any]:
    del root
    skill_root = smoke_test.ROOT / "skills"
    skill_names = [
        "oag-deep-semantic-intake",
        "oag-decision-matrix",
        "oag-contract-projection",
        "oag-authoring-packet",
        "oag-evidence-closure",
    ]
    umbrella = (skill_root / "oag-ip-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "Skill Router" in umbrella, umbrella
    for name in skill_names:
        assert name in umbrella, umbrella
        assert (skill_root / name / "SKILL.md").is_file(), name
    rule_index = (smoke_test.ROOT / "rules" / "oag-rule-index.yaml").read_text(encoding="utf-8")
    for rule_id in ("RULE-LOCK-003", "RULE-CONTRACT-AG-001", "RULE-PACKET-ROLE-001", "RULE-TRACE-001"):
        assert rule_id in rule_index, rule_index
    assert "scripts/oag_lock_readiness_check.py" in rule_index, rule_index
    assert "scripts/oag_contract_strength_check.py" in rule_index, rule_index
    return {"skills": skill_names, "rule_index": "rules/oag-rule-index.yaml"}


def _domain_intent_template(ip: Path, *, crossing_type: str = "multi_bit_level_sample", pattern: str = "per_bit_two_stage_sync") -> dict[str, Any]:
    return {
        "schema_version": "oag_domain_intent.v1",
        "ip": ip.name,
        "policy": {
            "profile": "simple_leaf_peripheral",
            "development_static_check_required": True,
            "release_requires_static_or_formal_cdc_rdc": True,
        },
        "clock_domains": [
            {"id": "external_async_domain", "clock": "external_async", "kind": "external"},
            {"id": "pclk_domain", "clock": "PCLK", "kind": "primary", "reset_domain": "presetn_domain"},
        ],
        "reset_domains": [
            {
                "id": "presetn_domain",
                "reset": "PRESETn",
                "polarity": "active_low",
                "assertion": "asynchronous",
                "deassertion": "synchronous",
                "clock_domain": "pclk_domain",
            }
        ],
        "async_inputs": [
            {
                "id": "GPIO_I_ASYNC",
                "signal": "gpio_i",
                "source_domain": "external_async_domain",
                "destination_domain": "pclk_domain",
                "classification": crossing_type,
                "required_mitigation": pattern,
            }
        ],
        "cdc_crossings": [
            {
                "id": "CDC_GPIO_I_TO_PCLK",
                "source": "gpio_i",
                "source_domain": "external_async_domain",
                "destination_domain": "pclk_domain",
                "crossing_type": crossing_type,
                "allowed_pattern": pattern,
            }
        ],
        "rdc_crossings": [
            {
                "id": "RDC_NONE_SINGLE_RESET_DOMAIN",
                "classification": "no_known_rdc",
                "basis": ["single reset domain PRESETn"],
            }
        ],
        "sync_structures": [
            {
                "id": "gpio_i_two_stage_sync",
                "crossing": "CDC_GPIO_I_TO_PCLK",
                "pattern": "per_bit_two_stage_sync",
            }
        ],
    }


def case_domain_intent_scaffold_seed(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "domain_intent_seed")
    policies = _read_yaml(oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml"))
    domain_intent = _read_yaml(oag_paths.legacy_or_hidden(ip, "ontology/domain_intent.yaml"))
    domain_policy = policies.get("domain_crossing_policy") if isinstance(policies.get("domain_crossing_policy"), dict) else {}
    assert domain_policy.get("canonical_domain_intent_file") == "ontology/domain_intent.yaml", policies
    assert domain_policy.get("domain_intent_required") is True, policies
    assert domain_intent.get("schema_version") == "oag_domain_intent.v1", domain_intent
    compiled = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip), "force": True}})
    assert compiled["result"]["status"] == "pass", compiled
    matrix = json.loads(oag_paths.legacy_or_hidden(ip, "ontology/generated/domain_crossing_matrix.json").read_text(encoding="utf-8"))
    assert matrix["schema_version"] == "oag_domain_crossing_matrix.v1", matrix
    return {
        "ip": str(ip),
        "domain_intent": domain_intent.get("schema_version"),
        "domain_crossing_policy": domain_policy.get("profile"),
        "matrix_status": matrix["status"],
    }


def case_tb_methodology_scaffold_seed(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "tb_methodology_seed")
    policies = _read_yaml(oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml"))
    tb_methodology = _read_yaml(oag_paths.legacy_or_hidden(ip, "ontology/tb_methodology.yaml"))
    tb_policy = policies.get("tb_methodology_policy") if isinstance(policies.get("tb_methodology_policy"), dict) else {}
    assert tb_policy.get("canonical_tb_methodology_file") == "ontology/tb_methodology.yaml", policies
    assert tb_policy.get("framework_required") is False, policies
    assert tb_policy.get("full_uvm_required") is False, policies
    assert tb_methodology.get("schema_version") == "oag_tb_methodology.v1", tb_methodology
    assert isinstance(tb_methodology.get("architecture_roles"), dict) and tb_methodology["architecture_roles"], tb_methodology
    assert isinstance(tb_methodology.get("coverage_goals"), list) and tb_methodology["coverage_goals"], tb_methodology
    compiled = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip), "force": True}})
    assert compiled["result"]["status"] == "pass", compiled
    matrix = json.loads(oag_paths.legacy_or_hidden(ip, "ontology/generated/tb_methodology_matrix.json").read_text(encoding="utf-8"))
    assert matrix["schema_version"] == "oag_tb_methodology_matrix.v1", matrix
    assert matrix["stats"]["coverage_goals"] >= 1, matrix
    return {
        "ip": str(ip),
        "tb_methodology": tb_methodology.get("schema_version"),
        "tb_methodology_policy": tb_policy.get("profile"),
        "matrix_status": matrix["status"],
    }


def case_random_without_coverage_goals_fails(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "random_without_coverage")
    path = oag_paths.legacy_or_hidden(ip, "ontology/tb_methodology.yaml")
    tb_methodology = _read_yaml(path)
    tb_methodology["coverage_goals"] = []
    tb_methodology["stimulus_strategy"]["constrained_random"] = {
        "enabled": True,
        "constraints": [],
        "seed_strategy": "fixed_seed",
    }
    _write_yaml(path, tb_methodology)
    _approve_eval_protected_update(ip, summary="eval enables random TB methodology without constraints or coverage goals")
    issues = _check_issues(ip)
    assert any("TB_CHECK_RANDOM_REQUIRES_CONSTRAINTS" in issue for issue in issues), issues
    assert any("TB_CHECK_RANDOM_REQUIRES_COVERAGE_GOALS" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issues": ["TB_CHECK_RANDOM_REQUIRES_CONSTRAINTS", "TB_CHECK_RANDOM_REQUIRES_COVERAGE_GOALS"]}


def case_failed_scoreboard_row_with_coverage_ref_fails(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "failed_row_coverage")
    rows = []
    for line in (ip / "sim" / "scoreboard_events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append(row)
    rows[0]["passed"] = False
    rows[0]["mismatch"] = "intentional eval mismatch"
    rows[0]["coverage_refs"] = ["COV_INC"]
    (ip / "sim" / "scoreboard_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    _record_closed_validation(ip)
    issues = _check_issues(ip)
    matched = "weak closure evidence: scoreboard evidence has failing rows"
    assert any(matched in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": matched}


def case_unresolved_scoreboard_coverage_ref_fails(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "unresolved_coverage_ref")
    rows = []
    for line in (ip / "sim" / "scoreboard_events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row["coverage_refs"] = ["COV_UNKNOWN_METHOD"]
        rows.append(row)
    (ip / "sim" / "scoreboard_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    _record_closed_validation(ip)
    issues = _check_issues(ip)
    assert any("TB_CHECK_COVERAGE_REFS_RESOLVE_TO_CONTRACTS" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "TB_CHECK_COVERAGE_REFS_RESOLVE_TO_CONTRACTS"}


def case_missing_results_xml_after_tb_closure_fails(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "missing_results_xml")
    _record_closed_validation(ip)
    (ip / "sim" / "results.xml").unlink()
    issues = _check_issues(ip)
    assert any("TB_CHECK_RESULTS_XML_PRESENT" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "TB_CHECK_RESULTS_XML_PRESENT"}


def case_missing_domain_intent_blocks_cdc_closure(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "missing_domain_intent")
    oag_paths.legacy_or_hidden(ip, "ontology/domain_intent.yaml").unlink()
    contracts_path = oag_paths.legacy_or_hidden(ip, "ontology/contracts.yaml")
    contracts = _read_yaml(contracts_path)
    contract = contracts["contracts"][0]
    contract["status"] = "closed"
    contract["contract_type"] = "cdc"
    contract["clock_domain_refs"] = ["clock_domains.pclk_domain"]
    contract["crossing_refs"] = ["cdc_crossings.CDC_GPIO_I_TO_PCLK"]
    contract["mitigation_refs"] = ["sync_structures.gpio_i_two_stage_sync"]
    _write_yaml(contracts_path, contracts)
    _approve_eval_protected_update(ip, summary="eval removes domain intent while claiming CDC closure")
    issues = _check_issues(ip)
    assert any("CHECK_DOMAIN_INTENT_PRESENT" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "CHECK_DOMAIN_INTENT_PRESENT"}


def case_cdc_sim_only_closure_fails(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "cdc_sim_only")
    _write_yaml(oag_paths.ontology_path(ip, "domain_intent.yaml"), _domain_intent_template(ip))
    contracts_path = oag_paths.legacy_or_hidden(ip, "ontology/contracts.yaml")
    contracts = _read_yaml(contracts_path)
    contract = contracts["contracts"][0]
    contract["status"] = "closed"
    contract["contract_type"] = "cdc"
    contract["clock_domain_refs"] = ["clock_domains.pclk_domain"]
    contract["crossing_refs"] = ["cdc_crossings.CDC_GPIO_I_TO_PCLK"]
    contract["mitigation_refs"] = ["sync_structures.gpio_i_two_stage_sync"]
    contract.pop("cdc_evidence_refs", None)
    _write_yaml(contracts_path, contracts)
    _approve_eval_protected_update(ip, summary="eval claims CDC closure without CDC evidence refs")
    issues = _check_issues(ip)
    assert any("CHECK_CDC_RDC_SIM_ONLY_CLOSURE_BLOCKED" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "CHECK_CDC_RDC_SIM_ONLY_CLOSURE_BLOCKED"}


def case_multibit_cdc_direct_sample_fails(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "multibit_cdc_direct")
    _write_yaml(
        oag_paths.ontology_path(ip, "domain_intent.yaml"),
        _domain_intent_template(ip, crossing_type="multi_bit_data", pattern="direct"),
    )
    _approve_eval_protected_update(ip, summary="eval declares unsafe direct multi-bit CDC")
    issues = _check_issues(ip)
    assert any("CHECK_CDC_MULTIBIT_UNSAFE" in issue for issue in issues), issues
    assert any("CHECK_CDC_MITIGATION_PRESENT" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issues": ["CHECK_CDC_MULTIBIT_UNSAFE", "CHECK_CDC_MITIGATION_PRESENT"]}


def case_rdc_contract_requires_reset_relation(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "rdc_requires_relation")
    domain_intent = _domain_intent_template(ip)
    domain_intent["reset_domains"].append(
        {
            "id": "por_domain",
            "reset": "PORn",
            "polarity": "active_low",
            "assertion": "asynchronous",
            "deassertion": "asynchronous",
            "clock_domain": "pclk_domain",
        }
    )
    domain_intent["rdc_crossings"] = [
        {
            "id": "RDC_POR_TO_PRESETN",
            "classification": "async_reset_crossing",
            "source_reset_domain": "por_domain",
            "destination_reset_domain": "presetn_domain",
        }
    ]
    _write_yaml(oag_paths.ontology_path(ip, "domain_intent.yaml"), domain_intent)
    contracts_path = oag_paths.legacy_or_hidden(ip, "ontology/contracts.yaml")
    contracts = _read_yaml(contracts_path)
    contract = contracts["contracts"][0]
    contract["status"] = "closed"
    contract["contract_type"] = "rdc"
    contract["reset_domain_refs"] = ["reset_domains.presetn_domain", "reset_domains.por_domain"]
    contract["rdc_crossing_refs"] = ["rdc_crossings.RDC_POR_TO_PRESETN"]
    contract["reset_sequence_or_isolation_or_sync_refs"] = []
    _write_yaml(contracts_path, contracts)
    _approve_eval_protected_update(ip, summary="eval claims RDC closure without mitigation evidence")
    issues = _check_issues(ip)
    assert any("CHECK_RDC_MITIGATION_PRESENT" in issue for issue in issues), issues
    assert any("CHECK_CDC_RDC_SIM_ONLY_CLOSURE_BLOCKED" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issues": ["CHECK_RDC_MITIGATION_PRESENT", "CHECK_CDC_RDC_SIM_ONLY_CLOSURE_BLOCKED"]}


def case_missing_behavior_model_blocks_behavioral_closure(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "missing_behavior_model")
    contracts_path = oag_paths.legacy_or_hidden(ip, "ontology/contracts.yaml")
    contracts = _read_yaml(contracts_path)
    contracts["contracts"][0]["status"] = "closed"
    contracts["contracts"][0]["contract_type"] = "behavioral"
    contracts["contracts"][0]["behavior_refs"] = []
    _write_yaml(contracts_path, contracts)
    _approve_eval_protected_update(ip, summary="eval removes behavior_refs from a closed behavioral contract")
    issues = _check_issues(ip)
    assert any("CHECK_BEHAVIOR_MODEL_REQUIRED_FOR_BEHAVIORAL_CLOSURE" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "CHECK_BEHAVIOR_MODEL_REQUIRED_FOR_BEHAVIORAL_CLOSURE"}


def case_missing_cycle_rules_blocks_temporal_closure(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "missing_cycle_rules")
    contracts_path = oag_paths.legacy_or_hidden(ip, "ontology/contracts.yaml")
    contracts = _read_yaml(contracts_path)
    contracts["contracts"][0]["status"] = "closed"
    contracts["contracts"][0]["contract_type"] = "temporal"
    contracts["contracts"][0]["cycle_rule_refs"] = []
    _write_yaml(contracts_path, contracts)
    _approve_eval_protected_update(ip, summary="eval removes cycle_rule_refs from a closed temporal contract")
    issues = _check_issues(ip)
    assert any("CHECK_CYCLE_RULES_REQUIRED_FOR_TEMPORAL_CLOSURE" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "CHECK_CYCLE_RULES_REQUIRED_FOR_TEMPORAL_CLOSURE"}


def case_prose_only_contract_fails_closure_grade_check(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "prose_only_contract")
    contracts_path = oag_paths.legacy_or_hidden(ip, "ontology/contracts.yaml")
    contracts = _read_yaml(contracts_path)
    contract = contracts["contracts"][0]
    contract["status"] = "closed"
    contract["contract_type"] = "behavioral"
    contract["behavior_refs"] = []
    contract["cycle_rule_refs"] = []
    contract["scenario_refs"] = []
    contract["scoreboard_row_refs"] = []
    contract["pass_condition"] = "simulation passes"
    _write_yaml(contracts_path, contracts)
    _approve_eval_protected_update(ip, summary="eval downgrades a contract to prose-only closure")
    issues = _check_issues(ip)
    assert any("CHECK_BEHAVIOR_MODEL_REQUIRED_FOR_BEHAVIORAL_CLOSURE" in issue for issue in issues), issues
    assert any("CHECK_PLANNED_SCENARIOS_EXIST_BEFORE_IMPL_CLOSURE" in issue for issue in issues), issues
    return {
        "ip": str(ip),
        "matched_issues": [
            "CHECK_BEHAVIOR_MODEL_REQUIRED_FOR_BEHAVIORAL_CLOSURE",
            "CHECK_PLANNED_SCENARIOS_EXIST_BEFORE_IMPL_CLOSURE",
        ],
    }


def case_scoreboard_without_scenario_id_fails_check(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "scoreboard_missing_scenario")
    rows = [
        {
            "event_id": "EVT_DEMO_COUNTER_CX1_RESET_DEFAULTS",
            "goal_id": "GOAL_COUNTER_INC",
            "cycle": 3,
            "stimulus": {"valid": 1},
            "expected": {"count": 3},
            "expected_source": {"kind": "behavior_model", "refs": ["behavior_model.seed_obligations.reset_known_state"]},
            "observed": {"count": 3},
            "observed_source": {"kind": "dut_signal", "path": "dut.count"},
            "passed": True,
            "mismatch": "",
            "coverage_refs": ["COV_INC"],
        }
    ]
    (ip / "sim" / "scoreboard_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    issues = _check_issues(ip)
    assert any("scoreboard_rows.v1: line 1: missing scoreboard_rows.v1 field(s): scenario_id" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "missing scoreboard_rows.v1 field(s): scenario_id"}


def case_scoreboard_dut_derived_expected_source_fails_check(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "scoreboard_dut_expected")
    rows = []
    for line in (ip / "sim" / "scoreboard_events.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    rows[0]["expected_source"] = {"kind": "dut_signal", "signal": "dut.count"}
    (ip / "sim" / "scoreboard_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    issues = _check_issues(ip)
    assert any("expected_source.kind must not be derived from DUT behavior" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "expected_source.kind must not be derived from DUT behavior"}


def case_manual_spec_expected_source_blocks_closure(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "manual_spec_closure")
    rows = []
    for line in (ip / "sim" / "scoreboard_events.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            row["expected_source"] = {"kind": "manual_spec", "status": "provisional", "ref": "req/locked_truth.md"}
            rows.append(row)
    (ip / "sim" / "scoreboard_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    _record_closed_validation(ip)
    issues = _check_issues(ip)
    matched = "weak closure evidence: 2 scoreboard row(s) use manual_spec expected_source"
    assert any(matched in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": matched}


def case_scenario_mapping_required_after_tb_closure(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "missing_scenario_mapping")
    (ip / "sim" / "scenario_mapping.json").unlink()
    _record_closed_validation(ip)
    issues = _check_issues(ip)
    assert any("CHECK_SCENARIO_MAPPING_EXISTS_AFTER_TB" in issue for issue in issues), issues
    return {"ip": str(ip), "matched_issue": "CHECK_SCENARIO_MAPPING_EXISTS_AFTER_TB"}


def case_stop_gate_allows_complete(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "allows_complete")
    intent = "eval complete run passes stop"
    run_id, _started = _start_run(ip, intent=intent)
    closed = _close_run(ip, run_id, intent=intent)
    rc, payload, stderr = _hook_json(ip, run_id)
    assert rc == 0, stderr
    assert payload is None, payload
    assert closed["checkpoint"]["allowed"] is True, closed
    assert closed["checkpoint"]["status"] == "complete", closed
    return {
        "ip": str(ip),
        "run_id": run_id,
        "checkpoint_status": closed["checkpoint"]["status"],
        "hook_stdout": "",
    }


def case_stop_gate_allows_needs_human(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "needs_human")
    run_id, _started = _start_run(ip, intent="eval repeated blocker needs human")
    checkpoint = smoke_test.call(
        {
            "tool": "oag.run.checkpoint",
            "arguments": {
                "ip_dir": str(ip),
                "run_id": run_id,
                "stage": "sim",
                "intent": "eval repeated blocker needs human",
                "max_blocker_repeats": 1,
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
            },
        }
    )
    assert checkpoint["result"]["status"] == "needs_human", checkpoint
    rc, payload, stderr = _hook_json(ip, run_id)
    assert rc == 0, stderr
    assert payload is None, payload
    return {
        "ip": str(ip),
        "run_id": run_id,
        "checkpoint_status": checkpoint["result"]["status"],
        "hook_stdout": "",
        "allows_stop": True,
    }


def case_completion_requires_decision_receipt(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "decision_receipt")
    run_id, _started = _start_run(ip, intent="eval decision receipt gate")
    _close_run(ip, run_id, intent="eval decision receipt gate")
    undecided = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "claim_complete",
                "stage": "sim",
            },
        }
    )
    assert undecided["result"]["allowed"] is False, undecided
    assert undecided["result"]["reason"] == "decision_receipt_required", undecided
    decided = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "claim_complete",
                "stage": "sim",
                "record_decision": True,
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
            },
        }
    )
    assert decided["result"]["allowed"] is True, decided
    receipt = Path(decided["result"]["decision_receipt"]["path"])
    assert receipt.is_file(), receipt
    return {
        "ip": str(ip),
        "run_id": run_id,
        "without_receipt": undecided["result"]["reason"],
        "with_receipt_allowed": decided["result"]["allowed"],
        "receipt": str(receipt),
    }


def case_context_injection_before_work(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "context_injection")
    cache_path = smoke_test.ROOT / ".cache" / "context_inject.json"
    cache_path.unlink(missing_ok=True)
    rc, payload, stderr = _run_hook(
        "claude_context_inject.py",
        {
            "ip_dir": str(ip),
            "stage": "rtl",
            "prompt": f"Start rtl stage work for {ip.name}. Please inspect the OAG context first.",
        },
    )
    assert rc == 0, stderr
    context = _additional_context(payload)
    assert "OAG CONTEXT INJECTION" in context, payload
    assert ip.name in context, payload
    assert "IP KNOWLEDGE LEDGER" in context, payload
    rc_duplicate, duplicate_payload, duplicate_stderr = _run_hook(
        "claude_context_inject.py",
        {
            "ip_dir": str(ip),
            "stage": "rtl",
            "prompt": f"Start rtl stage work for {ip.name}. Please inspect the OAG context first.",
        },
    )
    assert rc_duplicate == 0, duplicate_stderr
    assert duplicate_payload is None, duplicate_payload
    rc_high_pressure, high_pressure_payload, high_pressure_stderr = _run_hook(
        "claude_context_inject.py",
        {
            "ip_dir": str(ip),
            "stage": "rtl",
            "context_pressure": "high",
            "prompt": f"Start rtl stage work for {ip.name}. Please inspect the OAG context first.",
        },
    )
    assert rc_high_pressure == 0, high_pressure_stderr
    assert high_pressure_payload is None, high_pressure_payload
    rc_post_compact, post_compact_payload, post_compact_stderr = _run_hook(
        "claude_context_inject.py",
        {
            "ip_dir": str(ip),
            "stage": "rtl",
            "hook_event_name": "PostCompact",
            "prompt": f"Start rtl stage work for {ip.name}. Please inspect the OAG context first.",
        },
    )
    assert rc_post_compact == 0, post_compact_stderr
    assert post_compact_payload is None, post_compact_payload
    rc_recovery, recovery_payload, recovery_stderr = _run_hook(
        "claude_context_inject.py",
        {
            "ip_dir": str(ip),
            "stage": "rtl",
            "prompt": f"Start rtl stage work for {ip.name}. Please inspect the OAG context first.",
        },
    )
    assert rc_recovery == 0, recovery_stderr
    recovery_context = _additional_context(recovery_payload)
    assert "OAG CONTEXT INJECTION" in recovery_context, recovery_payload
    assert recovery_payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit", recovery_payload
    return {
        "ip": str(ip),
        "hook": "claude_context_inject.py",
        "contains_context": "IP KNOWLEDGE LEDGER" in context,
        "duplicate_suppressed": duplicate_payload is None,
        "high_pressure_does_not_force": high_pressure_payload is None,
        "post_compact_marker_is_silent": post_compact_payload is None,
        "post_compact_recovers": "OAG CONTEXT INJECTION" in recovery_context,
        "stage_inferred": "rtl",
    }


def case_draft_on_pressure_injects_guard(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "draft_pressure")
    rc, payload, stderr = _run_hook(
        "claude_draft_pressure.py",
        {
            "ip_dir": str(ip),
            "prompt": f"Continue deep requirement interview for {ip.name}",
            "context_pressure": "high",
        },
    )
    assert rc == 0, stderr
    context = _additional_context(payload)
    assert "OAG DRAFT PRESSURE GUARD" in context, payload
    assert "oag.draft" in context, payload
    assert str(ip) in context, payload
    return {
        "ip": str(ip),
        "hook": "claude_draft_pressure.py",
        "pressure_guard": True,
        "requires_draft": "oag.draft" in context,
    }


def case_evidence_freshness_mutation_blocks(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "freshness_mutation")
    record = smoke_test.call(
        {
            "tool": "oag.record",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "claim": "evaluation fresh evidence baseline",
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
                "rocev": {
                    "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN"},
                    "contract": {"id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", "method": "scoreboard"},
                    "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                    "validation": {"status": "closed", "verdict": "pass", "rationale": "hash baseline"},
                },
            },
        }
    )
    assert record["result"]["status"] == "closed", record
    before_hash = record["result"]["record"]["evidence"]["file_hashes"][0]["sha256"]
    (ip / "sim" / "results.xml").write_text('<testsuite failures="1"/>\n', encoding="utf-8")
    check = smoke_test.call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})
    stale_issues = [issue for issue in check["result"]["issues"] if "evidence file stale: sim/results.xml" in issue]
    assert check["result"]["ok"] is False, check
    assert stale_issues, check
    return {
        "ip": str(ip),
        "record": record["result"]["id"],
        "baseline_hash": before_hash[:12],
        "mutated_file": "sim/results.xml",
        "stale_issue": stale_issues[0],
    }


def case_evidence_supersession_clears_stale_record(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "freshness_supersession")
    baseline = smoke_test.call(
        {
            "tool": "oag.record",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "claim": "evaluation stale evidence baseline",
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
                "rocev": {
                    "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN"},
                    "contract": {"id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", "method": "scoreboard"},
                    "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                    "validation": {"status": "closed", "verdict": "pass", "rationale": "hash baseline"},
                },
            },
        }
    )
    (ip / "sim" / "results.xml").write_text('<testsuite failures="1"/>\n', encoding="utf-8")
    stale_check = smoke_test.call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})
    assert any("evidence file stale: sim/results.xml" in issue for issue in stale_check["result"]["issues"]), stale_check
    superseder = smoke_test.call(
        {
            "tool": "oag.record",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "claim": "evaluation fresh evidence supersedes stale baseline",
                "supersedes": [baseline["result"]["id"]],
                "actor": {"kind": "ai", "id": "claude", "surface": "eval"},
                "rocev": {
                    "obligation": {"id": "OBL_DEMO_COUNTER_CX1_RESET_KNOWN"},
                    "contract": {"id": "CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD", "method": "scoreboard"},
                    "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
                    "validation": {"status": "closed", "verdict": "pass", "rationale": "fresh evidence"},
                },
            },
        }
    )
    fresh_check = smoke_test.call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})
    stale_issues = [issue for issue in fresh_check["result"]["issues"] if "evidence file stale: sim/results.xml" in issue]
    assert not stale_issues, fresh_check
    assert any("weak closure evidence: closed validation requires behavioral scoreboard or formal evidence" in issue for issue in fresh_check["result"]["issues"]), fresh_check
    return {
        "ip": str(ip),
        "baseline": baseline["result"]["id"],
        "superseder": superseder["result"]["id"],
        "stale_before": True,
        "stale_after": False,
        "remaining_closure_blocked": True,
    }


def case_no_vacuous_pass_blocks_empty_matrix(root: Path) -> dict[str, Any]:
    ip = root / "empty_vacuous"
    ip.mkdir(parents=True)
    compile_result = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    check = smoke_test.call({"tool": "oag.check", "arguments": {"ip_dir": str(ip)}})
    decision = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "claim_complete",
                "stage": "signoff",
            },
        }
    )
    assert compile_result["result"]["status"] == "fail", compile_result
    assert "no requirements in ontology/requirements.yaml" in compile_result["result"]["issues"], compile_result
    assert check["result"]["ok"] is False, check
    assert "closure matrix has no obligations" in check["result"]["issues"], check
    assert decision["result"]["allowed"] is False, decision
    assert decision["result"]["reason"] == "scope_lock_required", decision
    locked = smoke_test.call(
        {
            "tool": "oag.lock",
            "arguments": {
                "ip_dir": str(ip),
                "summary": "Evaluation locks empty scope to verify vacuous closure remains blocked after lock.",
                "confirmed_scope": ["empty matrix must not be accepted as closure"],
                "actor": {"kind": "human", "id": "eval-owner", "surface": "eval"},
            },
        }
    )
    assert locked["result"]["locked"] is True, locked
    locked_decision = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "claim_complete",
                "stage": "signoff",
            },
        }
    )
    assert locked_decision["result"]["allowed"] is False, locked_decision
    assert locked_decision["result"]["reason"] == "knowledge_check_failed", locked_decision
    return {
        "ip": str(ip),
        "compile_status": compile_result["result"]["status"],
        "check_ok": check["result"]["ok"],
        "decision_allowed": decision["result"]["allowed"],
        "decision_reason": decision["result"]["reason"],
        "locked_decision_reason": locked_decision["result"]["reason"],
        "matrix_issue": "closure matrix has no obligations",
    }


def case_module_per_file_boundary_blocks_greenfield(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "module_file_boundary")
    bad_decomposition = "\n".join(
        [
            "schema: oag_decomposition.v1",
            f"ip: {ip.name}",
            "profile:",
            "  mode: greenfield_modular",
            "  rationale: evaluation duplicate physical files must be justified",
            "modules:",
            f"  - id: {ip.name}_top",
            "    ownership: current_ip",
            f"    file: rtl/{ip.name}.sv",
            "    role: top",
            "    owned_obligations: [OBL_DEMO_COUNTER_CX1_RESET_KNOWN]",
            "    owned_contracts: [CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD]",
            f"  - id: {ip.name}_core",
            "    ownership: current_ip",
            f"    file: rtl/{ip.name}.sv",
            "    role: core",
            "    owned_obligations: []",
            "    owned_contracts: []",
            "",
        ]
    )
    decomp_path = oag_paths.ontology_path(ip, "decomposition.yaml")
    decomp_path.write_text(bad_decomposition, encoding="utf-8")
    _approve_eval_protected_update(ip, summary="Approve temporary duplicate-file decomposition fixture.")
    blocked = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    boundary_issues = [
        issue
        for issue in blocked["result"]["issues"]
        if "greenfield_modular module file boundary requires unique file per current_ip module" in issue
    ]
    assert blocked["result"]["status"] == "fail", blocked
    assert boundary_issues, blocked

    decomp_path.write_text(
        bad_decomposition.replace(
            "  rationale: evaluation duplicate physical files must be justified\n",
            "  rationale: evaluation duplicate physical files must be justified\n"
            "  shared_file_rationale: evaluation permits generated wrapper/core in one temporary file\n",
            1,
        ),
        encoding="utf-8",
    )
    _approve_eval_protected_update(ip, summary="Approve shared-file rationale fixture update.")
    allowed = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert not any(
        "greenfield_modular module file boundary requires unique file per current_ip module" in issue
        for issue in allowed["result"]["issues"]
    ), allowed
    assert allowed["result"]["status"] in {"ok", "pass"}, allowed
    return {
        "ip": str(ip),
        "blocked_status": blocked["result"]["status"],
        "boundary_issue": boundary_issues[0],
        "exception_status": allowed["result"]["status"],
        "exception": "profile.shared_file_rationale",
    }


def case_design_facts_graph_extraction_gate(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "design_facts_graph")
    (ip / "list" / "rtl.f").write_text("rtl/demo_counter_cx1.sv\nrtl/counter_leaf.sv\n", encoding="utf-8")
    oag_paths.ontology_path(ip, "decomposition.yaml").write_text(
        "\n".join(
            [
                "schema: oag_decomposition.v1",
                f"ip: {ip.name}",
                "profile:",
                "  mode: greenfield_modular",
                "  rationale: evaluation extracts implementation facts and checks module mapping",
                "modules:",
                "  - id: demo_counter_cx1",
                "    name: demo_counter_cx1",
                "    ownership: current_ip",
                "    file: rtl/demo_counter_cx1.sv",
                "    role: top",
                "    owned_obligations: [OBL_DEMO_COUNTER_CX1_RESET_KNOWN]",
                "    owned_contracts: [CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD]",
                "  - id: counter_leaf",
                "    name: counter_leaf",
                "    ownership: current_ip",
                "    file: rtl/counter_leaf.sv",
                "    role: datapath_leaf",
                "    owned_obligations: []",
                "    owned_contracts: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _approve_eval_protected_update(ip, summary="Approve design-facts decomposition fixture.")
    top = ip / "rtl" / "demo_counter_cx1.sv"
    leaf = ip / "rtl" / "counter_leaf.sv"
    top.write_text(
        "\n".join(
            [
                "module demo_counter_cx1(",
                "  input logic clk_i,",
                "  input logic rst_ni,",
                "  inout wire pad_io,",
                "  output logic [7:0] count_o",
                ");",
                "  parameter int DEPTH = 4;",
                "  logic [7:0] count_q;",
                "  logic [31:0] mem_q [0:3];",
                "  counter_leaf u_leaf(.clk_i(clk_i), .rst_ni(rst_ni), .count_o(count_o));",
                "  assign pad_io = 1'bz;",
                "  always_ff @(posedge clk_i or negedge rst_ni) begin",
                "    if (!rst_ni) count_q <= '0;",
                "    else count_q <= count_q + 8'd1;",
                "  end",
                "endmodule",
                "",
            ]
        ),
        encoding="utf-8",
    )
    leaf.write_text(
        "\n".join(
            [
                "module wrong_leaf(input logic clk_i, input logic rst_ni, output logic [7:0] count_o);",
                "  logic [7:0] leaf_q;",
                "  assign count_o = leaf_q;",
                "endmodule",
                "",
            ]
        ),
        encoding="utf-8",
    )
    blocked = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert blocked["result"]["status"] == "fail", blocked
    assert any("design_facts: counter_leaf not found in extracted RTL facts" in issue for issue in blocked["result"]["issues"]), blocked
    assert any("design_facts: extracted RTL module is not mapped" in issue for issue in blocked["result"]["issues"]), blocked

    leaf.write_text(leaf.read_text(encoding="utf-8").replace("module wrong_leaf", "module counter_leaf", 1), encoding="utf-8")
    allowed = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert allowed["result"]["status"] == "pass", allowed
    facts = json.loads(oag_paths.legacy_or_hidden(ip, "ontology/generated/design_facts_graph.json").read_text(encoding="utf-8"))
    modules = {module["name"]: module for module in facts["modules"]}
    assert {"demo_counter_cx1", "counter_leaf"} <= set(modules), facts
    top_facts = modules["demo_counter_cx1"]
    assert any(port["name"] == "pad_io" and port["direction"] == "inout" for port in top_facts["ports"]), facts
    assert any(memory["name"] == "mem_q" for memory in top_facts["memories"]), facts
    assert any(instance["name"] == "u_leaf" and instance["module"] == "counter_leaf" for instance in top_facts["instances"]), facts
    assert allowed["result"]["stats"]["design_facts_modules"] == 2, allowed
    return {
        "ip": str(ip),
        "blocked_issue": "decomposition module not found in extracted RTL facts",
        "after_fix_status": allowed["result"]["status"],
        "extractor": facts["extractor"]["backend"],
        "modules": sorted(modules),
        "ports": len(top_facts["ports"]),
        "instances": len(top_facts["instances"]),
    }


def case_interleaved_context_coverage_gate(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "interleaved_context")
    rules_path = oag_paths.legacy_or_hidden(ip, "ontology/design_rules.yaml")
    rules_text = rules_path.read_text(encoding="utf-8")
    rules_text = rules_text.replace(
        "instances:\n",
        "\n".join(
            [
                "  - id: RULE_INTERLEAVED_CONTEXT_COVERAGE",
                "    kind: interleaved_context_coverage",
                "    status: active",
                "instances:",
                "  - id: INST_CONTEXT_A_B_INTERLEAVED",
                "    rule: RULE_INTERLEAVED_CONTEXT_COVERAGE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    context_count: 2",
                "    interleaving_pattern: [A.SOM, B.SOM, A.EOM, B.EOM]",
                "    coverage_refs: [COV_INTERLEAVED_CTX]",
                "",
            ]
        ),
        1,
    )
    rules_path.write_text(rules_text, encoding="utf-8")
    blocked = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert blocked["result"]["status"] == "fail", blocked
    assert "INST_CONTEXT_A_B_INTERLEAVED: interleaved context coverage ref not observed: COV_INTERLEAVED_CTX" in blocked["result"]["issues"], blocked

    scoreboard_path = ip / "sim" / "scoreboard_events.jsonl"
    row = {
        "goal_id": "GOAL_INTERLEAVED_CTX",
        "scenario_id": "SC_A_B_INTERLEAVED",
        "cycle": 8,
        "stimulus": {"pattern": ["A.SOM", "B.SOM", "A.EOM", "B.EOM"]},
        "expected": {"contexts_closed": ["A", "B"]},
        "observed": {"contexts_closed": ["A", "B"]},
        "observed_source": {"kind": "monitor", "path": "ctx_monitor.closed_ids"},
        "passed": True,
        "mismatch": "",
        "coverage_refs": ["COV_INTERLEAVED_CTX"],
    }
    scoreboard_path.write_text(scoreboard_path.read_text(encoding="utf-8") + json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    allowed = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert allowed["result"]["status"] == "pass", allowed
    return {
        "ip": str(ip),
        "blocked_issue": "interleaved context coverage ref not observed",
        "coverage_ref": "COV_INTERLEAVED_CTX",
        "after_scoreboard_status": allowed["result"]["status"],
    }


def case_fault_model_coverage_gate(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "fault_model_coverage")
    rules_path = oag_paths.legacy_or_hidden(ip, "ontology/design_rules.yaml")
    rules_text = rules_path.read_text(encoding="utf-8")
    rules_text += "\n".join(
        [
            "",
            "  - id: INST_COUNTER_INC_FAULT_MODEL_COVERAGE",
            "    rule: RULE_FAULT_MODEL_COVERAGE",
            "    status: closed",
            "    requirement: REQ_DEMO_COUNTER_CX1_001",
            "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
            "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
            "    coverage_refs: [COV_INC]",
            "    fault_models: [FM_COUNTER_STUCK_AT_ZERO]",
            "    mutation_results: []",
            "",
        ]
    )
    rules_path.write_text(rules_text, encoding="utf-8")
    blocked = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert blocked["result"]["status"] == "fail", blocked
    assert (
        "INST_COUNTER_INC_FAULT_MODEL_COVERAGE: fault model has no mutation result: FM_COUNTER_STUCK_AT_ZERO"
        in blocked["result"]["issues"]
    ), blocked

    mutation_summary = ip / "mutation" / "relevant_tc" / "relevant_mutation_summary.json"
    mutation_summary.parent.mkdir(parents=True, exist_ok=True)
    mutation_summary.write_text(
        json.dumps(
            {
                "schema_version": "oag_relevant_mutation_summary.v1",
                "baseline_rows": 2,
                "mutants_run": 1,
                "mutants_killed": 1,
                "relevant_rows_total": 2,
                "relevant_rows_killed": 2,
                "uncovered_scenarios": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    rules_text = rules_path.read_text(encoding="utf-8").replace(
        "    mutation_results: []",
        "\n".join(
            [
                "    mutation_results:",
                "      - id: MUT_COUNTER_STUCK_AT_ZERO",
                "        fault_model: FM_COUNTER_STUCK_AT_ZERO",
                "        status: killed",
                "        evidence_ref: mutation/relevant_tc/relevant_mutation_summary.json",
            ]
        ),
        1,
    )
    rules_path.write_text(rules_text, encoding="utf-8")
    allowed = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert allowed["result"]["status"] == "pass", allowed
    graph = json.loads(oag_paths.legacy_or_hidden(ip, "ontology/generated/design_truth_graph.json").read_text(encoding="utf-8"))
    node_types = {node.get("type") for node in graph.get("nodes", []) if isinstance(node, dict)}
    assert "fault_model" in node_types, graph
    assert "mutation" in node_types, graph
    return {
        "ip": str(ip),
        "blocked_issue": "fault model has no mutation result",
        "mutation_evidence": "mutation/relevant_tc/relevant_mutation_summary.json",
        "after_mutation_status": allowed["result"]["status"],
        "graph_has_fault_model_nodes": "fault_model" in node_types,
    }


def case_verification_role_decomposition_gate(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "verification_role_decomposition")
    rules_path = oag_paths.legacy_or_hidden(ip, "ontology/design_rules.yaml")
    rules_text = rules_path.read_text(encoding="utf-8")
    rules_text += "\n".join(
        [
            "",
            "  - id: INST_COUNTER_VERIF_ARCH",
            "    rule: RULE_VERIFICATION_ROLE_DECOMPOSITION",
            "    status: closed",
            "    requirement: REQ_DEMO_COUNTER_CX1_001",
            "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
            "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
            "    style: uvm_concepts",
            "    framework: verilator_cpp",
            "    roles:",
            "      sequence: tb/sequence.cpp",
            "      driver: tb/driver.cpp",
            "      monitor: tb/monitor.cpp",
            "      reference_model: tb/reference_model.cpp",
            "      scoreboard: tb/scoreboard.cpp",
            "      coverage: tb/coverage.cpp",
            "      env: tb/env.cpp",
            "",
        ]
    )
    rules_path.write_text(rules_text, encoding="utf-8")
    blocked = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert blocked["result"]["status"] == "fail", blocked
    assert "INST_COUNTER_VERIF_ARCH: verification role missing artifact: test" in blocked["result"]["issues"], blocked
    assert "INST_COUNTER_VERIF_ARCH: verification role independence missing expected_source" in blocked["result"]["issues"], blocked

    for rel in [
        "tb/sequence.cpp",
        "tb/driver.cpp",
        "tb/monitor.cpp",
        "tb/reference_model.cpp",
        "tb/scoreboard.cpp",
        "tb/coverage.cpp",
        "tb/env.cpp",
        "tb/tests/test_counter.cpp",
    ]:
        path = ip / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"// {rel}\n", encoding="utf-8")
    rules_text = rules_path.read_text(encoding="utf-8")
    rules_text = rules_text.replace(
        "      env: tb/env.cpp\n",
        "\n".join(
            [
                "      env: tb/env.cpp",
                "      test: tb/tests/test_counter.cpp",
                "    independence:",
                "      expected_source: reference_model",
                "      observed_source: monitor",
                "      compare_source: scoreboard",
            ]
        )
        + "\n",
        1,
    )
    rules_path.write_text(rules_text, encoding="utf-8")
    allowed = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert allowed["result"]["status"] == "pass", allowed
    graph = json.loads(oag_paths.legacy_or_hidden(ip, "ontology/generated/design_truth_graph.json").read_text(encoding="utf-8"))
    role_nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict) and node.get("type") == "verification_role"]
    assert len(role_nodes) >= 8, graph
    return {
        "ip": str(ip),
        "blocked_issue": "verification role missing artifact",
        "style": "uvm_concepts",
        "framework": "verilator_cpp",
        "after_roles_status": allowed["result"]["status"],
        "verification_role_nodes": len(role_nodes),
    }


def case_signoff_domain_rule_gates(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "signoff_domain_rules")
    rules_path = oag_paths.legacy_or_hidden(ip, "ontology/design_rules.yaml")
    rules_path.write_text(
        rules_path.read_text(encoding="utf-8")
        + "\n".join(
            [
                "",
                "  - id: INST_AXI_APB_CDC",
                "    rule: RULE_CDC_CROSSING_COVERAGE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    clock_domains: [axi_aclk, pclk]",
                "    crossings: [apb_cfg_to_axi_shadow, axi_event_to_apb_status]",
                "    evidence_refs: [cdc/cdc_report.json]",
                "  - id: INST_AXI4_PROTOCOL",
                "    rule: RULE_PROTOCOL_COMPLIANCE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    protocol: AXI4",
                "    coverage_refs: [COV_AXI_PROTOCOL]",
                "    evidence_refs: [protocol/axi4_assertions.log]",
                "  - id: INST_STA_TIMING",
                "    rule: RULE_TIMING_CLOSURE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    sdc_refs: [sdc/top.sdc]",
                "    timing_reports: [sta/out/wns.json]",
                "    setup_wns_ns: 0.01",
                "    hold_wns_ns: 0.02",
                "    setup_wns_ns_min: 0.0",
                "    hold_wns_ns_min: 0.0",
                "    evidence_refs: [sta/out/wns.json]",
                "  - id: INST_FUNCTIONAL_COVERAGE",
                "    rule: RULE_FUNCTIONAL_COVERAGE_CLOSURE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    coverage_refs: [COV_FUNC_DONE]",
                "    coverage_goal: 100",
                "    coverage_actual: 95",
                "    evidence_refs: [cov/coverage_functional.json, cov/coverage_ssot.json]",
                "  - id: INST_RESET_XPROP",
                "    rule: RULE_RESET_XPROP_COVERAGE",
                "    status: closed",
                "    requirement: REQ_DEMO_COUNTER_CX1_001",
                "    obligation: OBL_DEMO_COUNTER_CX1_RESET_KNOWN",
                "    contract: CONTRACT_DEMO_COUNTER_CX1_SIM_SCOREBOARD",
                "    reset_scenarios: [async_assert_sync_deassert]",
                "    xprop_checks: [reset_release_no_unknown_outputs]",
                "    coverage_refs: [COV_RESET_XPROP]",
                "    evidence_refs: [sim/xprop_reset.log]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    blocked = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert blocked["result"]["status"] == "fail", blocked
    issues = blocked["result"]["issues"]
    assert "INST_AXI_APB_CDC: CDC crossing coverage evidence ref missing on disk: cdc/cdc_report.json" in issues, blocked
    assert "INST_AXI4_PROTOCOL: protocol compliance coverage ref not observed: COV_AXI_PROTOCOL" in issues, blocked
    assert "INST_STA_TIMING: timing closure missing target_clocks/target_frequency" in issues, blocked
    assert "INST_STA_TIMING: timing closure evidence ref missing on disk: sdc/top.sdc" in issues, blocked
    assert "INST_FUNCTIONAL_COVERAGE: functional coverage below goal: 95.0 < 100.0" in issues, blocked
    assert "INST_RESET_XPROP: reset/X-prop coverage coverage ref not observed: COV_RESET_XPROP" in issues, blocked

    files = {
        "cdc/cdc_report.json": {"status": "pass", "crossings": 2},
        "protocol/axi4_assertions.log": "AXI4 protocol assertions PASS\n",
        "sdc/top.sdc": "create_clock -name axi_aclk -period 10 [get_ports axi_aclk]\n",
        "sta/out/wns.json": {"status": "pass", "summary": {"all_setup_met": True, "all_hold_met": True}},
        "cov/coverage_functional.json": {"status": "pass", "score": 100},
        "cov/coverage_ssot.json": {"status": "pass", "covered": ["COV_FUNC_DONE"]},
        "sim/xprop_reset.log": "reset/X-prop checks PASS\n",
    }
    for rel, content in files.items():
        path = ip / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict):
            path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")
    (ip / "cov" / "coverage.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "coverage_points": [
                    {"id": "COV_AXI_PROTOCOL", "status": "hit"},
                    {"id": "COV_FUNC_DONE", "status": "hit"},
                    {"id": "COV_RESET_XPROP", "status": "hit"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    rules_text = rules_path.read_text(encoding="utf-8")
    rules_text = rules_text.replace(
        "    sdc_refs: [sdc/top.sdc]\n",
        "\n".join(
            [
                "    target_clocks:",
                "      - name: axi_aclk",
                "        frequency_mhz: 100",
                "        period_ns: 10.0",
                "      - name: pclk",
                "        frequency_mhz: 50",
                "        period_ns: 20.0",
                "    async_clock_groups:",
                "      - [axi_aclk, pclk]",
                "    input_delay_ratio: 0.5",
                "    output_delay_ratio: 0.5",
                "    sdc_refs: [sdc/top.sdc]",
            ]
        )
        + "\n",
        1,
    )
    rules_text = rules_text.replace("    coverage_actual: 95", "    coverage_actual: 100", 1)
    rules_path.write_text(rules_text, encoding="utf-8")
    allowed = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert allowed["result"]["status"] == "pass", allowed
    graph = json.loads(oag_paths.legacy_or_hidden(ip, "ontology/generated/design_truth_graph.json").read_text(encoding="utf-8"))
    node_types = {node.get("type") for node in graph.get("nodes", []) if isinstance(node, dict)}
    assert {"protocol", "clock_domain", "coverage_ref", "artifact"} <= node_types, graph
    return {
        "ip": str(ip),
        "blocked_checks": [
            "cdc evidence missing",
            "protocol coverage unobserved",
            "timing target frequency and SDC/report missing",
            "functional coverage below goal",
            "reset/X-prop coverage unobserved",
        ],
        "after_evidence_status": allowed["result"]["status"],
        "graph_node_types": sorted(node_types & {"protocol", "clock_domain", "coverage_ref", "artifact"}),
    }


def case_reviewer_separation_signoff_gate(root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / "reviewer_gate")
    _record_closed_validation(ip)
    _human_approve_signoff_profile(ip)
    compiled = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    assert compiled["result"]["status"] == "pass", compiled
    smoke_test.write_stage_receipt(ip, "sim")
    blocked = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "signoff",
                "stage": "signoff",
                "record_decision": True,
                "actor": {"kind": "human", "id": "eval-owner", "surface": "eval"},
            },
        }
    )
    assert blocked["result"]["allowed"] is False, blocked
    assert blocked["result"]["reason"] == "reviewer_receipt_required", blocked
    fake_review_path = oag_paths.ontology_path(ip, "validations/REV_SELF_ALLOWED.json")
    fake_review_path.parent.mkdir(parents=True, exist_ok=True)
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
                "actor": {"kind": "ai", "id": "producer", "surface": "eval"},
                "producer_actor": {"kind": "ai", "id": "producer", "surface": "eval"},
                "independent": False,
                "findings": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    still_blocked = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "signoff",
                "stage": "signoff",
                "record_decision": True,
                "actor": {"kind": "human", "id": "eval-owner", "surface": "eval"},
            },
        }
    )
    assert still_blocked["result"]["allowed"] is False, still_blocked
    assert still_blocked["result"]["reason"] == "reviewer_receipt_required", still_blocked
    review = smoke_test.call(
        {
            "tool": "oag.review",
            "arguments": {
                "ip_dir": str(ip),
                "action": "signoff",
                "stage": "signoff",
                "verdict": "pass",
                "actor": {"kind": "ai", "id": "signoff-reviewer", "surface": "eval"},
                "producer_actor": {"kind": "ai", "id": "producer", "surface": "eval"},
                "findings": [],
            },
        }
    )
    assert review["result"]["allowed"] is True, review
    assert Path(review["result"]["reviewer_receipt"]["path"]).is_file(), review
    allowed = smoke_test.call(
        {
            "tool": "oag.decide",
            "arguments": {
                "ip_dir": str(ip),
                "action": "signoff",
                "stage": "signoff",
                "record_decision": True,
                "actor": {"kind": "human", "id": "eval-owner", "surface": "eval"},
            },
        }
    )
    assert allowed["result"]["allowed"] is True, allowed
    return {
        "ip": str(ip),
        "blocked_reason": blocked["result"]["reason"],
        "non_independent_receipt_rejected": still_blocked["result"]["reason"] == "reviewer_receipt_required",
        "review_receipt": review["result"]["reviewer_receipt"]["id"],
        "signoff_allowed_after_review": allowed["result"]["allowed"],
    }


def case_claude_runtime_hook_configuration(root: Path) -> dict[str, Any]:
    hooks = json.loads((smoke_test.ROOT / "hooks.json").read_text(encoding="utf-8"))
    events = hooks.get("hooks") if isinstance(hooks.get("hooks"), dict) else {}
    user_commands = [
        hook.get("command")
        for group in events.get("UserPromptSubmit", [])
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    ]
    stop_commands = [
        hook.get("command")
        for group in events.get("Stop", [])
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    ]
    post_compact_commands = [
        hook.get("command")
        for group in events.get("PostCompact", [])
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    ]
    assert "python3 .claude/hooks/claude_context_inject.py" in user_commands, hooks
    assert "python3 .claude/hooks/claude_draft_pressure.py" in user_commands, hooks
    assert any("claude_stop_gate.py" in command for command in stop_commands), hooks
    assert "python3 .claude/hooks/claude_context_inject.py" in post_compact_commands, hooks
    return {
        "hooks_json": str(smoke_test.ROOT / "hooks.json"),
        "user_prompt_submit_hooks": len(user_commands),
        "stop_hooks": len(stop_commands),
        "post_compact_hooks": len(post_compact_commands),
        "runtime_note": "Claude Code must approve hooks at startup; this case verifies the committed hook contract.",
    }


CASES: list[tuple[str, CaseFn]] = [
    ("stop_gate_blocks_incomplete", case_stop_gate_blocks_incomplete),
    ("stop_gate_obeys_policy_limit", case_stop_gate_obeys_policy_limit),
    ("compile_skips_fresh_graph", case_compile_skips_fresh_graph),
    ("modeling_scaffold_seed", case_modeling_scaffold_seed),
    ("requirement_atom_scaffold_seed", case_requirement_atom_scaffold_seed),
    ("requirement_quality_scaffold_seed", case_requirement_quality_scaffold_seed),
    ("verification_plan_scaffold_seed", case_verification_plan_scaffold_seed),
    ("contract_strength_scaffold_seed", case_contract_strength_scaffold_seed),
    ("authoring_packet_scaffold_seed", case_authoring_packet_scaffold_seed),
    ("trace_graph_scaffold_seed", case_trace_graph_scaffold_seed),
    ("decision_matrix_generator_mctp_profile", case_decision_matrix_generator_mctp_profile),
    ("deep_semantic_intake_mctp_profile", case_deep_semantic_intake_mctp_profile),
    ("skill_router_split_contract", case_skill_router_split_contract),
    ("lock_readiness_scaffold_seed", case_lock_readiness_scaffold_seed),
    ("domain_intent_scaffold_seed", case_domain_intent_scaffold_seed),
    ("tb_methodology_scaffold_seed", case_tb_methodology_scaffold_seed),
    ("random_without_coverage_goals_fails", case_random_without_coverage_goals_fails),
    ("failed_scoreboard_row_with_coverage_ref_fails", case_failed_scoreboard_row_with_coverage_ref_fails),
    ("unresolved_scoreboard_coverage_ref_fails", case_unresolved_scoreboard_coverage_ref_fails),
    ("missing_results_xml_after_tb_closure_fails", case_missing_results_xml_after_tb_closure_fails),
    ("missing_domain_intent_blocks_cdc_closure", case_missing_domain_intent_blocks_cdc_closure),
    ("cdc_sim_only_closure_fails", case_cdc_sim_only_closure_fails),
    ("multibit_cdc_direct_sample_fails", case_multibit_cdc_direct_sample_fails),
    ("rdc_contract_requires_reset_relation", case_rdc_contract_requires_reset_relation),
    ("missing_behavior_model_blocks_behavioral_closure", case_missing_behavior_model_blocks_behavioral_closure),
    ("missing_cycle_rules_blocks_temporal_closure", case_missing_cycle_rules_blocks_temporal_closure),
    ("prose_only_contract_fails_closure_grade_check", case_prose_only_contract_fails_closure_grade_check),
    ("scoreboard_without_scenario_id_fails_check", case_scoreboard_without_scenario_id_fails_check),
    ("scoreboard_dut_derived_expected_source_fails_check", case_scoreboard_dut_derived_expected_source_fails_check),
    ("manual_spec_expected_source_blocks_closure", case_manual_spec_expected_source_blocks_closure),
    ("scenario_mapping_required_after_tb_closure", case_scenario_mapping_required_after_tb_closure),
    ("stop_gate_allows_complete", case_stop_gate_allows_complete),
    ("stop_gate_allows_needs_human", case_stop_gate_allows_needs_human),
    ("completion_requires_decision_receipt", case_completion_requires_decision_receipt),
    ("context_injection_before_work", case_context_injection_before_work),
    ("draft_on_pressure_injects_guard", case_draft_on_pressure_injects_guard),
    ("evidence_freshness_mutation_blocks", case_evidence_freshness_mutation_blocks),
    ("evidence_supersession_clears_stale_record", case_evidence_supersession_clears_stale_record),
    ("no_vacuous_pass_blocks_empty_matrix", case_no_vacuous_pass_blocks_empty_matrix),
    ("module_per_file_boundary_blocks_greenfield", case_module_per_file_boundary_blocks_greenfield),
    ("design_facts_graph_extraction_gate", case_design_facts_graph_extraction_gate),
    ("interleaved_context_coverage_gate", case_interleaved_context_coverage_gate),
    ("fault_model_coverage_gate", case_fault_model_coverage_gate),
    ("verification_role_decomposition_gate", case_verification_role_decomposition_gate),
    ("signoff_domain_rule_gates", case_signoff_domain_rule_gates),
    ("reviewer_separation_signoff_gate", case_reviewer_separation_signoff_gate),
    ("claude_runtime_hook_configuration", case_claude_runtime_hook_configuration),
]


def _run_case(name: str, fn: CaseFn, root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        observations = fn(root / name)
        return {
            "name": name,
            "ok": True,
            "duration_s": round(time.perf_counter() - started, 3),
            "observations": observations,
            "error": "",
        }
    except Exception as exc:  # pragma: no cover - failure path is for reports
        return {
            "name": name,
            "ok": False,
            "duration_s": round(time.perf_counter() - started, 3),
            "observations": {},
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=6),
        }


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        f"OAG evaluation: {report['passed']}/{report['total']} passed",
        f"temp_root: {report['temp_root']}",
    ]
    for case in report["cases"]:
        mark = "PASS" if case["ok"] else "FAIL"
        lines.append(f"- {mark} {case['name']} ({case['duration_s']}s)")
        if case["error"]:
            lines.append(f"  error: {case['error']}")
        else:
            for key, value in case["observations"].items():
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--keep-temp", action="store_true", help="keep the temporary evaluation IPs on disk")
    args = parser.parse_args(argv)

    if args.keep_temp:
        temp_dir = tempfile.mkdtemp(prefix="oag-eval-")
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="oag-eval-")
        temp_dir = cleanup.name

    root = Path(temp_dir)
    cases = [_run_case(name, fn, root) for name, fn in CASES]
    passed = sum(1 for case in cases if case["ok"])
    report = {
        "schema_version": "oag_evaluation_report.v1",
        "ok": passed == len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "total": len(cases),
        "temp_root": temp_dir,
        "cases": cases,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_text(report))

    if cleanup is not None:
        cleanup.cleanup()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
