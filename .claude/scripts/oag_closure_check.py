#!/usr/bin/env python3
"""Check that OAG final closure has validator and gate-review evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


CODEX_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODEX_ROOT.parent
DEFAULT_VALIDATION_REPORTS = (
    Path("knowledge/validations/oag_validation_report.json"),
    Path("ontology/validations/oag_validation_report.json"),
    Path("reports/oag_validation_report.json"),
)
DEFAULT_GATE_REPORTS = (
    Path("knowledge/gate_reviews/oag_gate_decision.json"),
    Path("ontology/decisions/oag_gate_decision.json"),
    Path("reports/oag_gate_decision.json"),
)
CUSTOM_RECEIPT_DIRS = (
    Path("knowledge/subagents"),
    Path(".claude/oag/subagent-receipts"),
)
PASS_STATUSES = {"pass", "passed", "ok"}
PASS_OR_WAIVED_STATUSES = PASS_STATUSES | {"waived", "waived_with_risk"}
DEVELOPMENT_CLOSURE_ARTIFACTS = (
    Path("rtl/rtl_compile.json"),
    Path("lint/dut_lint.json"),
    Path("sim/results.xml"),
    Path("sim/scoreboard_events.jsonl"),
    Path("cov/coverage.json"),
)
OPTIONAL_GATE_ARTIFACTS = (
    Path("ontology/generated/design_truth_graph.json"),
    Path("ontology/generated/design_facts_graph.json"),
    Path("signoff/truth_coverage.json"),
)
CUSTOM_FINAL_TEXT_PATTERNS = (
    re.compile(r"\bmay_claim_complete\s*[:=]\s*true\b", re.IGNORECASE),
    re.compile(r"\bfinal_decision_authority\s*[:=]\s*true\b", re.IGNORECASE),
    re.compile(r"\bcompletion_claim\s*[:=]\s*true\b", re.IGNORECASE),
    re.compile(r"\bclaim_complete\s*[:=]\s*true\b", re.IGNORECASE),
    re.compile(r"\bfinal closure\s*[:=]\s*(pass|approved|complete)\b", re.IGNORECASE),
)


def issue(code: str, message: str, path: str | None = None) -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def load_catalog_check() -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from oag_agent_catalog_check import check_catalog  # pylint: disable=import-outside-toplevel

    return check_catalog()


def resolve_ip_dir(raw: str, issues: list[dict[str, str]]) -> Path | None:
    try:
        ip_dir = Path(raw).expanduser().resolve()
    except Exception as exc:  # pragma: no cover - defensive path normalization
        issues.append(issue("IP_DIR_INVALID", f"Cannot resolve ip-dir: {exc}", raw))
        return None
    if not ip_dir.exists() or not ip_dir.is_dir():
        issues.append(issue("IP_DIR_MISSING", "ip-dir must exist and be a directory.", str(ip_dir)))
        return None
    return ip_dir


def display_path(ip_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(ip_dir.resolve()))
    except Exception:
        return str(path)


def resolve_inside_ip(ip_dir: Path, raw: str | Path, code: str, issues: list[dict[str, str]]) -> Path | None:
    raw_path = Path(raw).expanduser()
    candidate = raw_path if raw_path.is_absolute() else ip_dir / raw_path
    try:
        resolved = candidate.resolve(strict=False)
        ip_resolved = ip_dir.resolve()
    except Exception as exc:
        issues.append(issue(code, f"Cannot resolve path: {exc}", str(raw)))
        return None
    try:
        resolved.relative_to(ip_resolved)
    except ValueError:
        issues.append(issue(code, "Path must stay inside ip-dir after symlink resolution.", str(raw)))
        return None
    return resolved


def find_default_report(ip_dir: Path, candidates: tuple[Path, ...], code: str, issues: list[dict[str, str]]) -> Path | None:
    for candidate in candidates:
        path = resolve_inside_ip(ip_dir, candidate, code, issues)
        if path and path.is_file():
            return path
    return None


def read_json(path: Path, code: str, issues: list[dict[str, str]], ip_dir: Path) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append(issue(code, "Report file does not exist.", display_path(ip_dir, path)))
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(issue(code, f"Report is not valid JSON: {exc}", display_path(ip_dir, path)))
        return None
    if not isinstance(payload, dict):
        issues.append(issue(code, "Report JSON must be an object.", display_path(ip_dir, path)))
        return None
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_oag_tool(ip_dir: Path, tool: str) -> dict[str, Any] | None:
    proc = subprocess.run(
        [
            sys.executable,
            str(CODEX_ROOT / "scripts" / "oag_cli.py"),
            "call",
            "--json",
            json.dumps({"tool": tool, "arguments": {"ip_dir": str(ip_dir)}}),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "OAG_DISABLE_BACKEND": "1"},
    )
    if proc.returncode != 0:
        return {"_tool_error": proc.stderr or proc.stdout or f"{tool} failed"}
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        return {"_tool_error": f"{tool} returned invalid JSON: {exc}"}
    result = payload.get("result") if isinstance(payload, dict) else None
    return result if isinstance(result, dict) else {"_tool_error": f"{tool} returned no result object"}


def validate_oag_development_closure(ip_dir: Path, issues: list[dict[str, str]]) -> None:
    lock_status = run_oag_tool(ip_dir, "oag.lock_status")
    if not isinstance(lock_status, dict) or lock_status.get("_tool_error"):
        issues.append(issue("SCOPE_LOCK_UNAVAILABLE", str((lock_status or {}).get("_tool_error") or "oag.lock_status failed")))
    elif lock_status.get("locked") is not True:
        blockers = lock_status.get("blockers") if isinstance(lock_status.get("blockers"), list) else []
        detail = "; ".join(str(item) for item in blockers[:4]) or "scope is not locked"
        issues.append(issue("SCOPE_LOCK_REQUIRED", detail, "ontology/scope_lock.json"))

    check = run_oag_tool(ip_dir, "oag.check")
    if not isinstance(check, dict) or check.get("_tool_error"):
        issues.append(issue("OAG_CHECK_UNAVAILABLE", str((check or {}).get("_tool_error") or "oag.check failed")))
    elif check.get("ok") is not True:
        check_issues = check.get("issues") if isinstance(check.get("issues"), list) else []
        detail = "; ".join(str(item) for item in check_issues[:5]) or "oag.check did not pass"
        issues.append(issue("OAG_CHECK_FAILED", detail))

    inspect = run_oag_tool(ip_dir, "oag.inspect")
    if not isinstance(inspect, dict) or inspect.get("_tool_error"):
        issues.append(issue("OAG_INSPECT_UNAVAILABLE", str((inspect or {}).get("_tool_error") or "oag.inspect failed")))
    else:
        gaps = inspect.get("gaps") if isinstance(inspect.get("gaps"), list) else []
        if gaps:
            issues.append(issue("OAG_INSPECT_GAPS", "; ".join(str(item) for item in gaps[:8])))


def required_gate_artifacts(ip_dir: Path, validation_path: Path) -> list[str]:
    paths = [validation_path]
    paths.extend(ip_dir / rel for rel in DEVELOPMENT_CLOSURE_ARTIFACTS)
    paths.extend(ip_dir / rel for rel in OPTIONAL_GATE_ARTIFACTS if (ip_dir / rel).is_file())
    result: list[str] = []
    for path in paths:
        if path.is_file():
            rendered = display_path(ip_dir, path)
            if rendered:
                result.append(rendered)
    return sorted(set(result))


def normalized_status(value: Any) -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    return str(value or "").strip().lower()


def validate_common_report(report: dict[str, Any], schema_version: str, role_name: str, issues: list[dict[str, str]], path: Path, ip_dir: Path) -> None:
    if report.get("schema_version") != schema_version:
        issues.append(issue("REPORT_SCHEMA_VERSION", f"Expected schema_version {schema_version}.", display_path(ip_dir, path)))
    if report.get("product_name") != "IP Dev Agent":
        issues.append(issue("REPORT_PRODUCT_NAME", "Report product_name must be IP Dev Agent.", display_path(ip_dir, path)))
    if report.get("internal_gateway") != "Ontology Agent Gateway":
        issues.append(issue("REPORT_GATEWAY", "Report internal_gateway must be Ontology Agent Gateway.", display_path(ip_dir, path)))
    if report.get("role_name") != role_name:
        issues.append(issue("REPORT_ROLE", f"Report role_name must be {role_name}.", display_path(ip_dir, path)))


def nested_status(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return normalized_status(value.get("status") or value.get("decision") or value.get("verdict"))
    return normalized_status(value)


def validate_validation_report(report: dict[str, Any], path: Path, ip_dir: Path, issues: list[dict[str, str]]) -> None:
    validate_common_report(report, "oag_validation_report.v1", "oag-evidence-validator", issues, path, ip_dir)

    status = normalized_status(report.get("status") or report.get("decision") or report.get("verdict"))
    if status not in PASS_STATUSES:
        issues.append(issue("VALIDATION_STATUS", "Evidence validator report must pass.", display_path(ip_dir, path)))

    closure = report.get("closure_matrix")
    if not isinstance(closure, dict):
        issues.append(issue("VALIDATION_CLOSURE_MATRIX", "Validation report needs closure_matrix object.", display_path(ip_dir, path)))
    else:
        closure_status = normalized_status(closure.get("status") or closure.get("decision") or closure.get("verdict"))
        open_count = closure.get("open_count")
        if closure_status and closure_status not in PASS_STATUSES:
            issues.append(issue("VALIDATION_CLOSURE_MATRIX", "closure_matrix.status must pass.", display_path(ip_dir, path)))
        if open_count is not None and open_count != 0:
            issues.append(issue("VALIDATION_CLOSURE_MATRIX", "closure_matrix.open_count must be 0.", display_path(ip_dir, path)))
        if not closure_status and open_count is None:
            issues.append(issue("VALIDATION_CLOSURE_MATRIX", "closure_matrix needs status=pass or open_count=0.", display_path(ip_dir, path)))

    for key in ("evidence", "mutation_guard", "coverage"):
        if not isinstance(report.get(key), dict):
            issues.append(issue("VALIDATION_REQUIRED_SECTION", f"Validation report needs {key} object.", display_path(ip_dir, path)))
            continue
        allowed = PASS_STATUSES if key == "evidence" else PASS_OR_WAIVED_STATUSES
        status_value = nested_status(report, key)
        if status_value not in allowed:
            issues.append(issue("VALIDATION_REQUIRED_SECTION", f"{key}.status must be pass or waived as allowed.", display_path(ip_dir, path)))

    report_issues = report.get("issues")
    if not isinstance(report_issues, list):
        issues.append(issue("VALIDATION_ISSUES", "Validation report issues must be a list.", display_path(ip_dir, path)))
    elif report_issues:
        issues.append(issue("VALIDATION_ISSUES", "Validation report must have no open issues for closure.", display_path(ip_dir, path)))


def validate_gate_report(
    report: dict[str, Any],
    path: Path,
    validation_path: Path,
    ip_dir: Path,
    issues: list[dict[str, str]],
) -> None:
    validate_common_report(report, "oag_gate_decision.v1", "oag-gate-reviewer", issues, path, ip_dir)

    if report.get("decision") != "PASS":
        issues.append(issue("GATE_DECISION", "Gate reviewer decision must be PASS.", display_path(ip_dir, path)))

    blockers = report.get("blockers")
    if not isinstance(blockers, list):
        issues.append(issue("GATE_BLOCKERS", "Gate decision blockers must be a list.", display_path(ip_dir, path)))
    elif blockers:
        issues.append(issue("GATE_BLOCKERS", "Gate decision must have no blockers for closure.", display_path(ip_dir, path)))

    checked = report.get("checked_artifacts")
    if not isinstance(checked, list) or not checked:
        issues.append(issue("GATE_CHECKED_ARTIFACTS", "Gate decision must list checked_artifacts.", display_path(ip_dir, path)))
        checked = []

    checked_set = {str(item) for item in checked if isinstance(item, str)}
    required_artifacts = required_gate_artifacts(ip_dir, validation_path)
    for artifact in required_artifacts:
        if artifact not in checked_set:
            issues.append(issue("GATE_REQUIRED_ARTIFACT_MISSING", "Gate decision did not check a current closure artifact.", artifact))

    checked_hashes = report.get("checked_artifact_hashes")
    if not isinstance(checked_hashes, dict):
        issues.append(issue("GATE_HASHES_MISSING", "Gate decision must include checked_artifact_hashes.", display_path(ip_dir, path)))
        checked_hashes = {}
    for artifact in required_artifacts:
        artifact_path = resolve_inside_ip(ip_dir, artifact, "GATE_HASH_PATH", issues)
        if not artifact_path or not artifact_path.is_file():
            continue
        expected_hash = str(checked_hashes.get(artifact) or "")
        current_hash = sha256(artifact_path)
        if not expected_hash:
            issues.append(issue("GATE_ARTIFACT_HASH_MISSING", "Gate decision lacks a hash for a current closure artifact.", artifact))
        elif expected_hash != current_hash:
            issues.append(issue("GATE_ARTIFACT_STALE", "Gate decision hash is stale; re-run evidence validation and gate review.", artifact))

    validation_ref = report.get("validation_report")
    if not isinstance(validation_ref, str) or not validation_ref.strip():
        issues.append(issue("GATE_VALIDATION_REF", "Gate decision must reference validation_report.", display_path(ip_dir, path)))
        return
    resolved_ref = resolve_inside_ip(ip_dir, validation_ref, "GATE_VALIDATION_REF", issues)
    if resolved_ref and resolved_ref.resolve() != validation_path.resolve():
        issues.append(issue("GATE_VALIDATION_REF", "Gate decision must reference the validation report being checked.", display_path(ip_dir, path)))


def custom_json_claims_completion(payload: dict[str, Any]) -> bool:
    role = str(payload.get("role_name") or payload.get("agent_type") or "")
    custom_role = role.startswith("oag-custom-")
    return bool(
        custom_role
        and (
            payload.get("may_claim_complete") is True
            or payload.get("final_decision_authority") is True
            or payload.get("completion_claim") is True
            or payload.get("claim_complete") is True
        )
    )


def scan_custom_completion_claims(ip_dir: Path, issues: list[dict[str, str]]) -> None:
    for receipt_dir in CUSTOM_RECEIPT_DIRS:
        root = resolve_inside_ip(ip_dir, receipt_dir, "CUSTOM_RECEIPT_PATH", issues)
        if not root or not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            try:
                path.resolve().relative_to(ip_dir.resolve())
            except ValueError:
                issues.append(issue("CUSTOM_RECEIPT_PATH", "Subagent receipt escapes ip-dir.", display_path(ip_dir, path)))
                continue

            if path.suffix.lower() == ".json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    payload = None
                if isinstance(payload, dict) and custom_json_claims_completion(payload):
                    issues.append(issue("CUSTOM_COMPLETION_CLAIM", "Custom subagent receipt claims completion authority.", display_path(ip_dir, path)))
                    continue

            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if any(pattern.search(text) for pattern in CUSTOM_FINAL_TEXT_PATTERNS):
                issues.append(issue("CUSTOM_COMPLETION_CLAIM", "Custom subagent receipt contains final-closure claim text.", display_path(ip_dir, path)))


def build_result(
    ip_dir: Path | None,
    validation_path: Path | None,
    gate_path: Path | None,
    catalog_result: dict[str, Any] | None,
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": "oag_closure_check.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "status": "fail" if issues else "pass",
        "ip_dir": str(ip_dir) if ip_dir else None,
        "validation_report": display_path(ip_dir, validation_path) if ip_dir else None,
        "gate_report": display_path(ip_dir, gate_path) if ip_dir else None,
        "catalog": catalog_result or {},
        "issues": issues,
    }


def check_closure(ip_dir_arg: str, validation_arg: str | None, gate_arg: str | None) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    catalog_result = load_catalog_check()
    if catalog_result.get("status") != "pass":
        issues.append(issue("CATALOG_CHECK", "OAG agent catalog check must pass before closure.", str(CODEX_ROOT / "oag" / "agent-catalog.toml")))
    if catalog_result.get("completion_authority") != ["oag-gate-reviewer"]:
        issues.append(issue("CATALOG_COMPLETION_AUTHORITY", "Only oag-gate-reviewer may claim completion.", str(CODEX_ROOT / "oag" / "agent-catalog.toml")))
    if catalog_result.get("final_decision_authority") != ["oag-gate-reviewer"]:
        issues.append(issue("CATALOG_FINAL_DECISION_AUTHORITY", "Only oag-gate-reviewer may have final decision authority.", str(CODEX_ROOT / "oag" / "agent-catalog.toml")))

    ip_dir = resolve_ip_dir(ip_dir_arg, issues)
    if ip_dir is None:
        return build_result(None, None, None, catalog_result, issues)

    validation_path = (
        resolve_inside_ip(ip_dir, validation_arg, "VALIDATION_REPORT_PATH", issues)
        if validation_arg
        else find_default_report(ip_dir, DEFAULT_VALIDATION_REPORTS, "VALIDATION_REPORT_PATH", issues)
    )
    if validation_path is None:
        issues.append(issue("VALIDATION_REPORT_MISSING", "Missing OAG validation report.", str(DEFAULT_VALIDATION_REPORTS[0])))

    gate_path = (
        resolve_inside_ip(ip_dir, gate_arg, "GATE_REPORT_PATH", issues)
        if gate_arg
        else find_default_report(ip_dir, DEFAULT_GATE_REPORTS, "GATE_REPORT_PATH", issues)
    )
    if gate_path is None:
        issues.append(issue("GATE_REPORT_MISSING", "Missing OAG gate-review decision.", str(DEFAULT_GATE_REPORTS[0])))

    validation_report = read_json(validation_path, "VALIDATION_REPORT_JSON", issues, ip_dir) if validation_path else None
    gate_report = read_json(gate_path, "GATE_REPORT_JSON", issues, ip_dir) if gate_path else None

    if validation_report and validation_path:
        validate_validation_report(validation_report, validation_path, ip_dir, issues)
    if gate_report and gate_path and validation_path:
        validate_gate_report(gate_report, gate_path, validation_path, ip_dir, issues)

    validate_oag_development_closure(ip_dir, issues)
    scan_custom_completion_claims(ip_dir, issues)
    return build_result(ip_dir, validation_path, gate_path, catalog_result, issues)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate OAG closure gate evidence.")
    parser.add_argument("--ip-dir", required=True, help="IP directory to check.")
    parser.add_argument("--validation-report", help="Validation report path, relative to ip-dir unless absolute.")
    parser.add_argument("--gate-report", help="Gate-review decision path, relative to ip-dir unless absolute.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_closure(args.ip_dir, args.validation_report, args.gate_report)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag closure check")
    else:
        print("FAIL oag closure check", file=sys.stderr)
        for item in result["issues"]:
            suffix = f" ({item['path']})" if "path" in item else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
