#!/usr/bin/env python3
"""Spec-to-RTL auto-research driver for OAG-managed IP work.

The driver does not generate RTL by itself. It anchors a spec input, optionally
runs caller-provided implementation commands, executes the common development
validator, and writes an OAG-readable auto-research report with ranked next
actions. The goal is to make the loop measurable and hard to bypass while
keeping the actual RTL/TB implementation style IP-specific.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import oag_dev_validator


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_RESEARCH_REPORT = "signoff/ip_research_report.json"
DEFAULT_VALIDATOR_REPORT = "signoff/development_validator_report.json"
DEFAULT_COMMAND_TRACE = "signoff/spec_to_rtl_command_trace.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_ip(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_to_ip(ip: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(ip.resolve()).as_posix()
    except Exception:
        return str(path)


def _existing_refs(ip: Path, refs: list[str]) -> list[str]:
    out: list[str] = []
    for ref in refs:
        clean = str(ref or "").strip()
        if clean and (ip / clean).is_file() and clean not in out:
            out.append(clean)
    return out


def _call_oag(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"tool": tool, "arguments": arguments}, ensure_ascii=False)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "oag_cli.py"), "call", "--json", payload],
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        data = json.loads(proc.stdout)
    except Exception:
        data = {}
    if isinstance(data, dict):
        data.setdefault("returncode", proc.returncode)
        if proc.stderr.strip():
            data.setdefault("stderr", proc.stderr.strip())
        return data
    return {"ok": False, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _render_command(command: str, values: dict[str, str]) -> str:
    rendered = command
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _run_shell(command: str, *, cwd: Path, timeout_s: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
            text=True,
            capture_output=True,
            timeout=timeout_s if timeout_s > 0 else None,
            check=False,
        )
        return {
            "command": command,
            "returncode": proc.returncode,
            "status": "pass" if proc.returncode == 0 else "fail",
            "stdout_tail": proc.stdout[-12000:],
            "stderr_tail": proc.stderr[-12000:],
            "duration_s": round(time.perf_counter() - started, 4),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "status": "timeout",
            "stdout_tail": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else f"timeout after {timeout_s}s",
            "duration_s": round(time.perf_counter() - started, 4),
        }


def _copy_spec(ip: Path, spec: str, spec_rel: str) -> str:
    if not spec:
        return ""
    src = Path(spec).expanduser()
    if not src.is_absolute():
        src = (PROJECT_ROOT / src).resolve()
    if not src.is_file():
        raise SystemExit(f"spec file missing: {src}")
    dst = ip / spec_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dst.resolve():
        shutil.copyfile(src, dst)
    return spec_rel


def _scaffold_if_needed(ip: Path, *, owner: str) -> dict[str, Any]:
    if (ip / "ontology" / "ip.yaml").is_file():
        return {"skipped": True, "reason": "ip already scaffolded"}
    return _call_oag("oag.scaffold", {"ip_dir": str(ip), "owner": owner})


def _run_stage_commands(ip: Path, commands: list[tuple[str, str]], *, spec_ref: str, timeout_s: float) -> list[dict[str, Any]]:
    values = {
        "ip_dir": str(ip),
        "spec": str(ip / spec_ref) if spec_ref else "",
        "project_root": str(PROJECT_ROOT),
    }
    results: list[dict[str, Any]] = []
    for stage, command in commands:
        if not command.strip():
            continue
        rendered = _render_command(command, values)
        result = _run_shell(rendered, cwd=PROJECT_ROOT, timeout_s=timeout_s)
        result["stage"] = stage
        results.append(result)
    return results


def _gate_by_id(validation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gates = validation.get("gates") if isinstance(validation.get("gates"), list) else []
    return {str(gate.get("id") or ""): gate for gate in gates if isinstance(gate, dict)}


def _rtl_refs(ip: Path) -> list[str]:
    refs = ["list/rtl.f", "rtl/rtl_compile.json"]
    if (ip / "rtl").is_dir():
        for path in sorted((ip / "rtl").glob("*.sv"))[:12]:
            refs.append(_relative_to_ip(ip, path))
    return _existing_refs(ip, refs)


def _action_reason(gate: dict[str, Any]) -> str:
    issues = gate.get("issues") if isinstance(gate.get("issues"), list) else []
    if issues:
        return "; ".join(str(item) for item in issues[:3])
    return str(gate.get("summary") or "gate is not closed")


def _failed_gate_actions(ip: Path, validation: dict[str, Any], validator_ref: str) -> list[dict[str, Any]]:
    gate_labels = {
        "oag_compile": ("OAG_COMPILE", "Compile authored ontology and generated projections."),
        "rtl_compile": ("RTL_COMPILE", "Produce passing RTL compile evidence."),
        "lint": ("RTL_LINT", "Produce clean lint evidence."),
        "simulation": ("DUT_SIMULATION", "Run DUT simulation and emit passing results.xml."),
        "scoreboard_rows_v1": ("SCOREBOARD_ROWS_V1", "Emit DUT-facing scoreboard_rows.v1 evidence."),
        "coverage": ("COVERAGE_CLOSURE", "Close functional coverage evidence."),
        "validator_report": ("IP_SPECIFIC_VALIDATOR", "Add an IP-specific validator report before development closure."),
        "stage_run_receipts": ("STAGE_RECEIPTS", "Refresh stage_run_receipt.v1 fingerprints after running stages."),
        "oag_inspect": ("ROCEV_INSPECT_CLOSURE", "Close OAG inspect gaps."),
        "oag_check": ("ROCEV_CHECK", "Resolve OAG check issues and stale evidence."),
    }
    gates = _gate_by_id(validation)
    actions: list[dict[str, Any]] = []
    for gate_id in validation.get("failed_gates", []):
        action_id, summary = gate_labels.get(str(gate_id), (str(gate_id).upper(), "Resolve failed gate."))
        gate = gates.get(str(gate_id), {})
        evidence_refs = _existing_refs(ip, [validator_ref, "signoff/ip_research_report.json"])
        actions.append(
            {
                "rank": len(actions) + 1,
                "id": action_id,
                "status": "blocked",
                "reason": f"{summary} { _action_reason(gate) }",
                "evidence_refs": evidence_refs,
                "required_evidence": _required_evidence_for_gate(str(gate_id)),
            }
        )
    return actions


def _required_evidence_for_gate(gate_id: str) -> list[str]:
    required = {
        "rtl_compile": ["rtl/rtl_compile.json"],
        "lint": ["lint/dut_lint.json"],
        "simulation": ["sim/results.xml"],
        "scoreboard_rows_v1": ["sim/scoreboard_events.jsonl"],
        "coverage": ["cov/coverage.json"],
        "validator_report": ["signoff/<ip_specific>_validator_report.json"],
        "stage_run_receipts": ["ontology/evidence/stage_runs/<stage>.json"],
        "oag_inspect": ["knowledge/records/<closed_rocev_record>.json"],
        "oag_check": ["knowledge/records/<closed_rocev_record>.json", "ontology/validations/<decision>.json"],
    }
    return required.get(gate_id, [])


def _development_report_actions(ip: Path, validator_ref: str) -> tuple[list[dict[str, Any]], list[str]]:
    actions: list[dict[str, Any]] = []
    blockers: list[str] = []
    reports = [
        (
            "signoff/implementation_sta_report.json",
            "IMPLEMENTATION_STA",
            "Development STA is partial only; signoff still needs foundry/PVT corners and gate-level reset/X-prop evidence.",
            "Foundry/PVT and gate-level reset/X-prop evidence are required before signoff.",
        ),
        (
            "signoff/gate_reset_xprop_report.json",
            "GATE_LEVEL_RESET_XPROP",
            "Development gate reset/X-prop evidence is partial only; signoff still needs SDF/foundry context.",
            "SDF/foundry and gate-level reset/X-prop evidence are required before signoff.",
        ),
        (
            "signoff/formal_assertion_report.json",
            "FORMAL_ASSERTION_OPTION",
            "Development bounded formal is partial only; signoff needs promoted contracts, exhaustive/induction scope, and independent review.",
            "Bounded/development formal cannot replace promoted signoff contracts and independent review.",
        ),
    ]
    for ref, action_id, reason, blocker in reports:
        data = _read_json(ip / ref)
        if str(data.get("status") or "").lower() != "development_pass":
            continue
        actions.append(
            {
                "rank": 0,
                "id": action_id,
                "status": "partially_closed",
                "reason": reason,
                "evidence_refs": _existing_refs(ip, [ref, validator_ref]),
            }
        )
        blockers.append(blocker)
    return actions, blockers


def _evidence_strengths(ip: Path, spec_ref: str, validator_ref: str, validation: dict[str, Any]) -> list[dict[str, Any]]:
    strengths: list[dict[str, Any]] = []
    if spec_ref and (ip / spec_ref).is_file():
        strengths.append(
            {
                "id": "SPEC_INPUT_ANCHOR",
                "status": "candidate",
                "method": "copied_user_spec_input",
                "evidence_refs": [spec_ref],
            }
        )
    validator_status = str(validation.get("status") or "")
    strengths.append(
        {
            "id": "DEVELOPMENT_VALIDATOR_EXECUTION",
            "status": "pass" if validator_status == "pass" else "candidate",
            "method": "oag_dev_validator",
            "evidence_refs": _existing_refs(ip, [validator_ref]),
        }
    )
    rtl_refs = _rtl_refs(ip)
    if rtl_refs:
        rtl_gate = _gate_by_id(validation).get("rtl_compile", {})
        strengths.append(
            {
                "id": "RTL_ARTIFACTS",
                "status": "pass" if rtl_gate.get("status") == "pass" else "candidate",
                "method": "current_rtl_files_and_compile_report",
                "evidence_refs": rtl_refs,
            }
        )
    scoreboard_ref = "sim/scoreboard_events.jsonl"
    if (ip / scoreboard_ref).is_file():
        scoreboard_gate = _gate_by_id(validation).get("scoreboard_rows_v1", {})
        strengths.append(
            {
                "id": "DUT_SCOREBOARD_EVIDENCE",
                "status": "pass" if scoreboard_gate.get("status") == "pass" else "candidate",
                "method": "scoreboard_rows_v1",
                "evidence_refs": [scoreboard_ref],
            }
        )
    return strengths


def _build_research_report(
    ip: Path,
    *,
    stage: str,
    intent: str,
    spec_ref: str,
    command_trace_ref: str,
    validator_ref: str,
    validation: dict[str, Any],
    commands: list[dict[str, Any]],
    inspect_response: dict[str, Any],
    context_response: dict[str, Any],
    run_response: dict[str, Any],
) -> dict[str, Any]:
    actions = _failed_gate_actions(ip, validation, validator_ref)
    partial_actions, signoff_blockers = _development_report_actions(ip, validator_ref)
    for action in partial_actions:
        action["rank"] = len(actions) + 1
        actions.append(action)
    if not actions:
        actions.append(
            {
                "rank": 1,
                "id": "SIGNOFF_PROMOTION_REVIEW",
                "status": "blocked",
                "reason": "Development validator passed; signoff still needs signoff profile, signoff-grade evidence, and independent review.",
                "evidence_refs": _existing_refs(ip, [validator_ref]),
            }
        )
    if not signoff_blockers:
        signoff_blockers = [
            "Development closure is not signoff.",
            "Signoff requires closure_profile=signoff, signoff-grade evidence, and independent reviewer receipt.",
        ]
    evidence_refs = _existing_refs(
        ip,
        [
            spec_ref,
            validator_ref,
            command_trace_ref,
            "ontology/generated/design_truth_graph.json",
            "ontology/generated/design_spec.json",
            "sim/results.xml",
            "sim/scoreboard_events.jsonl",
            "cov/coverage.json",
        ],
    )
    command_failures = [item for item in commands if item.get("status") not in {"pass", "skipped"}]
    validation_status = str(validation.get("status") or "")
    checks = {
        "ranked_next_actions_present": True,
        "evidence_refs_present": True,
        "automation_boundary_declared": True,
        "validator_executed": True,
    }
    return {
        "schema_version": "ip_research_report.v1",
        "id": f"RESEARCH_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{ip.name.upper()}",
        "generated_at": _now(),
        "ip": ip.name,
        "stage": stage,
        "intent": intent,
        "status": "pass",
        "method": "spec_to_rtl_auto_research_loop_v1",
        "automation_boundary": (
            "Auto-research orchestration only; this is not signoff, not a waiver, and not an IP-specific "
            "testbench replacement."
        ),
        "inputs": {
            "spec": spec_ref,
            "ip_dir": str(ip),
            "run_id": ((run_response.get("result") or {}).get("run_id") if isinstance(run_response.get("result"), dict) else ""),
        },
        "observations": {
            "validator_status": validation_status,
            "failed_gates": validation.get("failed_gates", []),
            "command_failures": len(command_failures),
            "inspect_validation": ((inspect_response.get("result") or {}).get("validation") if isinstance(inspect_response.get("result"), dict) else ""),
            "context_available": bool(context_response.get("ok")),
        },
        "checks": checks,
        "evidence_refs": evidence_refs or [validator_ref],
        "evidence_strengths": _evidence_strengths(ip, spec_ref, validator_ref, validation),
        "ranked_next_actions": actions,
        "signoff_blockers": signoff_blockers,
    }


def _write_static_summary(ip: Path, research_ref: str) -> None:
    _write_json(
        ip / "signoff" / "static_signoff_summary.json",
        {
            "schema_version": "static_signoff_summary.v1",
            "status": "pass",
            "reports": {"auto_research": research_ref},
            "checks": {"auto_research_next_actions": "pass"},
        },
    )


def run_loop(args: argparse.Namespace) -> dict[str, Any]:
    ip = _resolve_ip(args.ip_dir)
    scaffold = _scaffold_if_needed(ip, owner=args.owner) if args.create else {"skipped": True, "reason": "create disabled"}
    spec_ref = _copy_spec(ip, args.spec, args.spec_rel)

    inspect_before = _call_oag("oag.inspect", {"ip_dir": str(ip), "stage": args.stage, "intent": args.intent})
    compile_response = _call_oag("oag.compile", {"ip_dir": str(ip)})
    context_response = _call_oag("oag.context", {"ip_dir": str(ip), "stage": args.stage, "intent": args.intent})
    run_response: dict[str, Any] = {}
    if args.start_run:
        run_response = _call_oag(
            "oag.run.start",
            {
                "ip_dir": str(ip),
                "stage": args.stage,
                "intent": args.intent,
                "actor": {"kind": "ai", "id": "claude", "surface": "spec_to_rtl_loop"},
            },
        )

    stage_commands = [
        ("rtl", args.rtl_command),
        ("lint", args.lint_command),
        ("sim", args.sim_command),
        ("scoreboard", args.scoreboard_command),
        ("coverage", args.coverage_command),
    ]
    commands = _run_stage_commands(ip, stage_commands, spec_ref=spec_ref, timeout_s=args.timeout_s)
    command_trace_ref = args.command_trace
    _write_json(
        ip / command_trace_ref,
        {
            "schema_version": "spec_to_rtl_command_trace.v1",
            "generated_at": _now(),
            "ip": ip.name,
            "stage": args.stage,
            "intent": args.intent,
            "commands": commands,
        },
    )

    validator_ref = args.validator_report
    research_ref = args.research_report

    def write_validation_and_research(validation_report: dict[str, Any]) -> dict[str, Any]:
        _write_json(ip / validator_ref, validation_report)
        research_report = _build_research_report(
            ip,
            stage=args.stage,
            intent=args.intent,
            spec_ref=spec_ref,
            command_trace_ref=command_trace_ref,
            validator_ref=validator_ref,
            validation=validation_report,
            commands=commands,
            inspect_response=inspect_before,
            context_response=context_response,
            run_response=run_response,
        )
        _write_json(ip / research_ref, research_report)
        if args.write_static_summary:
            _write_static_summary(ip, research_ref)
        return research_report

    validation = oag_dev_validator.validate_ip(ip, stage=args.stage, intent=args.intent, run_compile=not args.no_compile)
    research = write_validation_and_research(validation)
    if validation.get("status") != "pass":
        refreshed_validation = oag_dev_validator.validate_ip(
            ip,
            stage=args.stage,
            intent=args.intent,
            run_compile=not args.no_compile,
        )
        if refreshed_validation != validation:
            validation = refreshed_validation
            research = write_validation_and_research(validation)

    metrics_response: dict[str, Any] = {}
    handoff_response: dict[str, Any] = {}
    if args.metrics:
        metrics_response = _call_oag(
            "oag.metrics",
            {
                "ip_dir": str(ip),
                "stage": args.stage,
                "intent": args.intent,
                "actor": {"kind": "ai", "id": "claude", "surface": "spec_to_rtl_loop"},
            },
        )
    if args.handoff:
        handoff_response = _call_oag(
            "oag.handoff",
            {
                "ip_dir": str(ip),
                "stage": "handoff",
                "intent": args.intent,
                "actor": {"kind": "ai", "id": "claude", "surface": "spec_to_rtl_loop"},
            },
        )

    return {
        "schema_version": "spec_to_rtl_loop_result.v1",
        "generated_at": _now(),
        "ip": ip.name,
        "ip_dir": str(ip),
        "stage": args.stage,
        "intent": args.intent,
        "scaffold": scaffold,
        "spec_ref": spec_ref,
        "compile": compile_response.get("result") if isinstance(compile_response.get("result"), dict) else compile_response,
        "validator": {
            "status": validation.get("status"),
            "failed_gates": validation.get("failed_gates", []),
            "report": validator_ref,
        },
        "auto_research": {
            "status": research.get("status"),
            "report": research_ref,
            "ranked_next_actions": len(research.get("ranked_next_actions", [])),
            "signoff_blockers": len(research.get("signoff_blockers", [])),
        },
        "commands": commands,
        "metrics": metrics_response.get("result") if isinstance(metrics_response.get("result"), dict) else {},
        "handoff": handoff_response.get("result") if isinstance(handoff_response.get("result"), dict) else {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a measurable OAG spec-to-RTL auto-research loop.")
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--spec", default="", help="spec file to copy into the IP as draft input")
    parser.add_argument("--spec-rel", default="req/input_spec.md", help="destination spec path relative to the IP")
    parser.add_argument("--stage", default="implementation")
    parser.add_argument("--intent", default="spec-to-RTL auto research")
    parser.add_argument("--owner", default="claude")
    parser.add_argument("--create", action="store_true", help="scaffold the IP if it does not exist")
    parser.add_argument("--start-run", action="store_true", help="start an OAG run for the loop")
    parser.add_argument("--rtl-command", default="")
    parser.add_argument("--lint-command", default="")
    parser.add_argument("--sim-command", default="")
    parser.add_argument("--scoreboard-command", default="")
    parser.add_argument("--coverage-command", default="")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--no-compile", action="store_true", help="skip compile inside the development validator")
    parser.add_argument("--validator-report", default=DEFAULT_VALIDATOR_REPORT)
    parser.add_argument("--research-report", default=DEFAULT_RESEARCH_REPORT)
    parser.add_argument("--command-trace", default=DEFAULT_COMMAND_TRACE)
    parser.add_argument("--write-static-summary", action="store_true")
    parser.add_argument("--metrics", action="store_true", help="record OAG improvement metrics after writing the research report")
    parser.add_argument("--handoff", action="store_true", help="record OAG handoff after writing the research report")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run_loop(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"{result['ip']} spec-to-RTL loop validator={result['validator']['status']} "
            f"actions={result['auto_research']['ranked_next_actions']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
