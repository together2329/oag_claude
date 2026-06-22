#!/usr/bin/env python3
"""Development-closure validator for OAG-managed IP directories.

This command is intentionally a thin layer over OAG's canonical gates. It does
not replace an IP-specific simulator or scoreboard. It checks that those tools
have emitted the artifacts OAG can judge consistently across IPs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import oag_cli


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_REPORT = "signoff/development_validator_report.json"


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


def _gate(gate_id: str, passed: bool, summary: str, *, issues: list[str] | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": "pass" if passed else "fail",
        "summary": summary,
        "issues": issues or [],
        "details": details or {},
    }


def _status_gate(gate_id: str, path: Path, *, expected: str = "pass") -> dict[str, Any]:
    present, status = oag_cli._status_from_json(path)
    rel = str(path)
    passed = present and status == expected
    issues: list[str] = []
    if not present:
        issues.append(f"missing {rel}")
    elif status != expected:
        issues.append(f"{rel} status is {status}, expected {expected}")
    return _gate(gate_id, passed, f"{rel}: {status}", issues=issues, details={"path": rel, "present": present, "status": status})


def _simulation_gate(ip: Path) -> dict[str, Any]:
    path = ip / "sim" / "results.xml"
    present, status = oag_cli._simulation_status(path)
    issues: list[str] = []
    if not present:
        issues.append("missing sim/results.xml")
    elif status != "pass":
        issues.append(f"sim/results.xml status is {status}, expected pass")
    return _gate(
        "simulation",
        present and status == "pass",
        f"sim/results.xml: {status}",
        issues=issues,
        details={"path": "sim/results.xml", "present": present, "status": status},
    )


def _scoreboard_gate(ip: Path) -> dict[str, Any]:
    scoreboard = oag_cli._scoreboard_summary(ip / "sim" / "scoreboard_events.jsonl")
    summary = scoreboard.get("summary") if isinstance(scoreboard.get("summary"), dict) else {}
    total = int(summary.get("total") or 0)
    failed = int(summary.get("failed") or 0)
    unreadable = int(summary.get("unreadable") or 0)
    schema_failed = int(summary.get("schema_failed") or 0)
    passed = bool(scoreboard.get("present")) and total > 0 and failed == 0 and unreadable == 0 and schema_failed == 0
    issues = [str(item) for item in scoreboard.get("issues", [])] if isinstance(scoreboard.get("issues"), list) else []
    if not scoreboard.get("present"):
        issues.append("missing sim/scoreboard_events.jsonl")
    if total <= 0:
        issues.append("scoreboard has no rows")
    if failed:
        issues.append(f"scoreboard has {failed} failed row(s)")
    if unreadable:
        issues.append(f"scoreboard has {unreadable} unreadable row(s)")
    if schema_failed:
        issues.append(f"scoreboard has {schema_failed} schema-invalid row(s)")
    return _gate(
        "scoreboard_rows_v1",
        passed,
        f"rows={total} failed={failed} schema_failed={schema_failed}",
        issues=issues,
        details={"path": "sim/scoreboard_events.jsonl", "summary": summary},
    )


def _coverage_gate(ip: Path) -> dict[str, Any]:
    present, status = oag_cli._coverage_status(ip)
    issues: list[str] = []
    if not present:
        issues.append("missing coverage evidence")
    elif status != "pass":
        issues.append(f"coverage status is {status}, expected pass")
    details: dict[str, Any] = {"present": present, "status": status}
    coverage_path = ip / "cov" / "coverage.json"
    if coverage_path.is_file():
        details["path"] = "cov/coverage.json"
        details["coverage"] = _read_json(coverage_path)
    return _gate("coverage", present and status == "pass", f"coverage: {status}", issues=issues, details=details)


def _validator_report_gate(ip: Path) -> dict[str, Any]:
    reports = sorted((ip / "signoff").glob("*validator*.json")) if (ip / "signoff").is_dir() else []
    reports = [path for path in reports if path.name != Path(DEFAULT_REPORT).name]
    pass_reports: list[str] = []
    failed_reports: list[str] = []
    for path in reports:
        present, status = oag_cli._status_from_json(path)
        rel = str(path.relative_to(ip))
        if present and status == "pass":
            pass_reports.append(rel)
        else:
            failed_reports.append(f"{rel}: {status}")
    issues: list[str] = []
    if not reports:
        issues.append("missing signoff/*validator*.json")
    issues.extend(failed_reports)
    return _gate(
        "validator_report",
        bool(pass_reports) and not failed_reports,
        f"passing_reports={len(pass_reports)} total={len(reports)}",
        issues=issues,
        details={"passing_reports": pass_reports, "failed_reports": failed_reports},
    )


def _stage_receipt_gate(ip: Path) -> dict[str, Any]:
    issues = oag_cli._stage_receipt_issues(ip, require_any=True)
    receipts = sorted((ip / "ontology" / "evidence" / "stage_runs").glob("*.json")) if (ip / "ontology" / "evidence" / "stage_runs").is_dir() else []
    return _gate(
        "stage_run_receipts",
        not issues,
        f"receipts={len(receipts)} issues={len(issues)}",
        issues=issues,
        details={"receipts": [str(path.relative_to(ip)) for path in receipts]},
    )


def _oag_gate(gate_id: str, response: dict[str, Any], *, expected: str) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    issues = [str(item) for item in result.get("issues", [])] if isinstance(result.get("issues"), list) else []
    passed = False
    summary = ""
    details: dict[str, Any] = {}
    if gate_id == "oag_compile":
        status = str(result.get("status") or "")
        passed = bool(response.get("ok")) and status == expected
        summary = f"compile status={status or '<missing>'}"
        details = {"status": status, "stats": result.get("stats") if isinstance(result.get("stats"), dict) else {}}
    elif gate_id == "oag_inspect":
        validation = str(result.get("validation") or "")
        passed = bool(response.get("ok")) and validation == expected
        summary = f"inspect validation={validation or '<missing>'}"
        details = {
            "validation": validation,
            "gaps": result.get("gaps") if isinstance(result.get("gaps"), list) else [],
        }
        issues.extend([str(item) for item in details["gaps"]])
    elif gate_id == "oag_check":
        ok = result.get("ok") is True
        passed = bool(response.get("ok")) and ok
        summary = f"check ok={ok}"
        details = {
            "ok": ok,
            "closure_matrix": result.get("closure_matrix") if isinstance(result.get("closure_matrix"), dict) else {},
            "improvement_metrics": result.get("improvement_metrics") if isinstance(result.get("improvement_metrics"), dict) else {},
        }
    if not response.get("ok"):
        issues.append(str(response.get("stderr") or response.get("errors") or "oag call failed"))
    return _gate(gate_id, passed, summary, issues=issues, details=details)


def validate_ip(ip: Path, *, stage: str, intent: str, run_compile: bool) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    compile_response: dict[str, Any] = {}
    if run_compile:
        compile_response = _call_oag("oag.compile", {"ip_dir": str(ip)})
        gates.append(_oag_gate("oag_compile", compile_response, expected="pass"))

    gates.extend(
        [
            _status_gate("rtl_compile", ip / "rtl" / "rtl_compile.json"),
            _status_gate("lint", ip / "lint" / "dut_lint.json"),
            _simulation_gate(ip),
            _scoreboard_gate(ip),
            _coverage_gate(ip),
            _validator_report_gate(ip),
            _stage_receipt_gate(ip),
        ]
    )

    inspect_response = _call_oag("oag.inspect", {"ip_dir": str(ip), "stage": stage, "intent": intent})
    check_response = _call_oag("oag.check", {"ip_dir": str(ip)})
    gates.append(_oag_gate("oag_inspect", inspect_response, expected="closed"))
    gates.append(_oag_gate("oag_check", check_response, expected="pass"))

    failed = [gate for gate in gates if gate.get("status") != "pass"]
    check_result = check_response.get("result") if isinstance(check_response.get("result"), dict) else {}
    inspect_result = inspect_response.get("result") if isinstance(inspect_response.get("result"), dict) else {}
    metrics = check_result.get("improvement_metrics") if isinstance(check_result.get("improvement_metrics"), dict) else {}
    return {
        "schema_version": "oag_development_validator_report.v1",
        "generated_at": _now(),
        "ip": ip.name,
        "ip_dir": str(ip),
        "stage": stage,
        "intent": intent,
        "status": "pass" if not failed else "fail",
        "gates": gates,
        "failed_gates": [str(gate.get("id")) for gate in failed],
        "inspect": {
            "validation": inspect_result.get("validation"),
            "gaps": inspect_result.get("gaps") if isinstance(inspect_result.get("gaps"), list) else [],
        },
        "check": {
            "ok": check_result.get("ok") is True,
            "issues": check_result.get("issues") if isinstance(check_result.get("issues"), list) else [],
        },
        "metrics": metrics,
        "not_signoff": [
            "development validator pass is not signoff",
            "signoff requires signoff profile, independent review, and signoff-grade domain evidence",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OAG development-closure evidence for an IP.")
    parser.add_argument("--ip-dir", required=True, help="IP directory to validate")
    parser.add_argument("--stage", default="implementation")
    parser.add_argument("--intent", default="development closure validation")
    parser.add_argument("--no-compile", action="store_true", help="skip oag.compile before validation")
    parser.add_argument("--write-report", action="store_true", help=f"write report to {DEFAULT_REPORT} unless --report is set")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="report path relative to the IP directory")
    parser.add_argument("--json", action="store_true", help="emit full JSON report")
    args = parser.parse_args()

    ip = _resolve_ip(args.ip_dir)
    report = validate_ip(ip, stage=args.stage, intent=args.intent, run_compile=not args.no_compile)

    if args.write_report:
        report_path = ip / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["report_path"] = str(report_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{ip.name} development validator {report['status']}")
        if report["failed_gates"]:
            print("failed_gates=" + ",".join(report["failed_gates"]))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
