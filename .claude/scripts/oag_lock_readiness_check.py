#!/usr/bin/env python3
"""Check OAG decision matrix and post-lock requirement readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import oag_requirement_atom_check  # noqa: E402
import oag_req_quality_check  # noqa: E402
import oag_verification_plan_check  # noqa: E402
import oag_contract_strength_check  # noqa: E402
import oag_trace_graph_check  # noqa: E402


LOCK_READY_STATUSES = {"decided", "waived"}
VALID_STATUSES = {"unresolved", "proposed", "decided", "waived", "blocked"}


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"__load_error__": str(exc)}


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"__load_error__": str(exc)}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def text(value: Any) -> str:
    return str(value or "").strip()


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def is_locked(ip_dir: Path) -> bool:
    scope = read_json(ip_dir / "ontology" / "scope_lock.json")
    return scope.get("state") == "locked"


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def check_decisions(ip_dir: Path, *, hard_gate: bool) -> tuple[list[dict[str, str]], dict[str, int], list[str]]:
    path = ip_dir / "ontology" / "decision_matrix.yaml"
    doc = read_yaml(path)
    issues: list[dict[str, str]] = []
    blockers: list[str] = []

    if "__load_error__" in doc:
        return [issue("DECISION_MATRIX_INVALID", f"Cannot read decision_matrix.yaml: {doc['__load_error__']}", str(path))], {
            "decisions": 0,
            "lock_required": 0,
            "unresolved_lock_blockers": 0,
        }, blockers

    if not doc:
        if hard_gate:
            issues.append(issue("DECISION_MATRIX_MISSING", "Locked or required scope needs ontology/decision_matrix.yaml.", str(path)))
        return issues, {"decisions": 0, "lock_required": 0, "unresolved_lock_blockers": 0}, blockers

    if doc.get("schema_version") != "oag_decision_matrix.v1":
        issues.append(issue("DECISION_MATRIX_SCHEMA_VERSION", "decision_matrix.yaml must use schema_version oag_decision_matrix.v1.", str(path)))

    decisions = [item for item in as_list(doc.get("decisions")) if isinstance(item, dict)]
    counts = {"decisions": len(decisions), "lock_required": 0, "unresolved_lock_blockers": 0}
    if hard_gate and not decisions:
        issues.append(issue("DECISION_REQUIRED", "Locked or required scope needs at least one decision row.", "decisions"))

    seen: set[str] = set()
    for index, decision in enumerate(decisions):
        base = f"decisions[{index}]"
        did = text(decision.get("id"))
        status = text(decision.get("status")).lower()
        lock_required = decision.get("lock_required")

        if not did:
            issues.append(issue("DECISION_ID", "Decision row missing id.", base))
        elif did in seen:
            issues.append(issue("DECISION_DUPLICATE_ID", f"Duplicate decision id {did}.", base))
        seen.add(did)

        if not text(decision.get("question")):
            issues.append(issue("DECISION_QUESTION", f"{did or base} missing question.", base))
        if status not in VALID_STATUSES:
            issues.append(issue("DECISION_STATUS", f"{did or base} has invalid status {status or '<missing>'}.", base))
        if not isinstance(lock_required, bool):
            issues.append(issue("DECISION_LOCK_REQUIRED", f"{did or base} lock_required must be boolean.", base))
            lock_required = False
        if not text(decision.get("owner")):
            issues.append(issue("DECISION_OWNER", f"{did or base} missing owner.", base))

        if lock_required:
            counts["lock_required"] += 1
            if status not in LOCK_READY_STATUSES:
                counts["unresolved_lock_blockers"] += 1
                blockers.append(did or base)
                if hard_gate:
                    issues.append(issue("DECISION_LOCK_BLOCKER", f"{did or base} is lock-required but status is {status or '<missing>'}.", base))

        if status == "decided" and not has_value(decision.get("decision")):
            issues.append(issue("DECISION_VALUE_MISSING", f"{did or base} is decided but has no decision value.", base))
        if status == "waived" and not text(decision.get("waiver_reason")):
            issues.append(issue("DECISION_WAIVER_REASON", f"{did or base} is waived but has no waiver_reason.", base))

    return issues, counts, blockers


def check(ip_dir: Path, *, require_locked: bool = False) -> dict[str, Any]:
    locked = is_locked(ip_dir)
    hard_gate = require_locked or locked
    decision_issues, decision_counts, blockers = check_decisions(ip_dir, hard_gate=hard_gate)
    req_quality_result = oag_req_quality_check.check(ip_dir, require_locked=hard_gate)
    req_quality_issues = req_quality_result.get("issues", []) if isinstance(req_quality_result, dict) else []
    atom_result = oag_requirement_atom_check.check(ip_dir, require_locked=hard_gate)
    atom_issues = atom_result.get("issues", []) if isinstance(atom_result, dict) else []
    contract_strength_result = oag_contract_strength_check.check(ip_dir, require_locked=hard_gate)
    contract_strength_issues = contract_strength_result.get("issues", []) if isinstance(contract_strength_result, dict) else []
    vplan_result = oag_verification_plan_check.check(ip_dir, require_locked=hard_gate)
    vplan_issues = vplan_result.get("issues", []) if isinstance(vplan_result, dict) else []
    trace_result = oag_trace_graph_check.check(ip_dir, require_locked=hard_gate)
    trace_issues = trace_result.get("issues", []) if isinstance(trace_result, dict) else []
    issues = decision_issues + req_quality_issues + atom_issues + contract_strength_issues + vplan_issues + trace_issues

    next_actions: list[str] = []
    if decision_counts["unresolved_lock_blockers"]:
        next_actions.append("Resolve or waive lock-required decisions in ontology/decision_matrix.yaml.")
    if req_quality_issues:
        next_actions.append("Resolve source claims, ambiguity register, or requirement quality issues.")
    if atom_issues:
        next_actions.append("Resolve requirement atom, shallow obligation, or assume/guarantee contract issues.")
    if contract_strength_issues:
        next_actions.append("Resolve closure-grade contract strength issues before implementation or validation.")
    if vplan_issues:
        next_actions.append("Resolve verification strategy plan issues before TB implementation or closure.")
    if trace_issues:
        next_actions.append("Resolve source-to-contract-to-evidence trace graph issues.")
    if not issues and not hard_gate:
        next_actions.append("Draft is lock-ready only after user lock and hard gate re-check.")

    return {
        "schema_version": "oag_lock_readiness_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "scope_locked": locked,
        "require_locked": require_locked,
        "hard_gate": hard_gate,
        "counts": {
            **decision_counts,
            "decision_issues": len(decision_issues),
            "requirement_quality_issues": len(req_quality_issues),
            "atom_issues": len(atom_issues),
            "contract_strength_issues": len(contract_strength_issues),
            "verification_plan_issues": len(vplan_issues),
            "trace_issues": len(trace_issues),
            "issues": len(issues),
        },
        "unresolved_lock_blockers": blockers,
        "issues": issues,
        "next_actions": next_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--require-locked", action="store_true", help="Apply post-lock hard gates even if scope_lock is still draft.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check(Path(args.ip_dir), require_locked=args.require_locked)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag lock readiness check")
    else:
        print("FAIL oag lock readiness check")
        for item in result["issues"]:
            path = f" {item['path']}" if item.get("path") else ""
            print(f"- {item['code']}:{path} {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
