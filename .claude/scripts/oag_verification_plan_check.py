#!/usr/bin/env python3
"""Check OAG verification strategy plan readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VALID_STATUSES = {"draft", "planned", "ready", "blocked", "closed", "waived"}
LOCK_READY_STATUSES = {"planned", "ready", "closed", "waived"}
VALID_RISK_STATUSES = {"open", "accepted", "mitigated", "waived", "closed"}
STRONG_PROOF_METHODS = {
    "assertion",
    "assertion_sim",
    "formal",
    "bounded_formal",
    "protocol_checker",
    "static_cdc_rdc",
    "tool_cdc_rdc",
}
TEMPORAL_HINTS = (
    "temporal",
    "protocol",
    "priority",
    "ordering",
    "latency",
    "handshake",
    "sequence",
    "interleav",
    "descriptor_valid",
    "commit",
)
NEGATIVE_HINTS = (
    "error",
    "drop",
    "malformed",
    "overflow",
    "timeout",
    "illegal",
    "unsupported",
    "unexpected",
    "sequence",
)


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


def str_items(value: Any) -> list[str]:
    return [str(item).strip() for item in as_list(value) if str(item).strip()]


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


def refs_from_yaml(path: Path, keys: tuple[str, ...]) -> set[str]:
    doc = read_yaml(path)
    refs: set[str] = set()
    for key in keys:
        for item in as_list(doc.get(key)):
            if isinstance(item, dict):
                ident = text(item.get("id"))
                if ident:
                    refs.add(ident)
    return refs


def objective_needs_negative(objective: dict[str, Any]) -> bool:
    blob = " ".join(
        [
            text(objective.get("id")),
            text(objective.get("intent")),
            " ".join(str_items(objective.get("proof_methods"))),
            " ".join(str_items(objective.get("scenarios"))),
        ]
    ).lower()
    return any(hint in blob for hint in NEGATIVE_HINTS)


def objective_needs_strong_proof(objective: dict[str, Any]) -> bool:
    blob = " ".join(
        [
            text(objective.get("id")),
            text(objective.get("intent")),
            " ".join(str_items(objective.get("proof_methods"))),
            " ".join(str_items(objective.get("scenarios"))),
        ]
    ).lower()
    return any(hint in blob for hint in TEMPORAL_HINTS)


def check(ip_dir: Path, *, require_locked: bool = False) -> dict[str, Any]:
    locked = is_locked(ip_dir)
    hard_gate = require_locked or locked
    path = ip_dir / "ontology" / "verification_plan.yaml"
    doc = read_yaml(path)
    issues: list[dict[str, str]] = []

    if "__load_error__" in doc:
        issues.append(issue("VPLAN_INVALID", f"Cannot read verification_plan.yaml: {doc['__load_error__']}", str(path)))
        doc = {}
    if not doc:
        if hard_gate:
            issues.append(issue("VPLAN_MISSING", "Locked or required verification work needs ontology/verification_plan.yaml.", str(path)))
        return {
            "schema_version": "oag_verification_plan_check.v1",
            "status": "fail" if issues else "pass",
            "ip": ip_dir.name,
            "scope_locked": locked,
            "require_locked": require_locked,
            "hard_gate": hard_gate,
            "counts": {"objectives": 0, "issues": len(issues), "open_strategy_blockers": 0},
            "issues": issues,
            "next_actions": ["Create ontology/verification_plan.yaml before TB implementation."] if issues else ["Draft has no verification plan yet."],
        }

    if doc.get("schema_version") != "oag_verification_plan.v1":
        issues.append(issue("VPLAN_SCHEMA_VERSION", "verification_plan.yaml must use schema_version oag_verification_plan.v1.", str(path)))

    objectives = [item for item in as_list(doc.get("verification_objectives")) if isinstance(item, dict)]
    if hard_gate and not objectives:
        issues.append(issue("VPLAN_OBJECTIVE_REQUIRED", "Locked or required verification work needs at least one verification objective.", "verification_objectives"))

    requirement_ids = refs_from_yaml(ip_dir / "ontology" / "requirements.yaml", ("requirements",))
    obligation_ids = refs_from_yaml(ip_dir / "ontology" / "obligations.yaml", ("obligations",))
    contract_ids = refs_from_yaml(ip_dir / "ontology" / "contracts.yaml", ("contracts",))

    seen: set[str] = set()
    open_strategy_blockers = str_items(doc.get("open_strategy_blockers"))
    if hard_gate and open_strategy_blockers:
        issues.append(issue("VPLAN_OPEN_BLOCKERS", "Verification plan has open_strategy_blockers after lock.", "open_strategy_blockers"))

    for index, objective in enumerate(objectives):
        base = f"verification_objectives[{index}]"
        oid = text(objective.get("id"))
        status = text(objective.get("status")).lower()
        requirement = text(objective.get("requirement"))
        obligation = text(objective.get("obligation"))
        contract = text(objective.get("contract"))
        proof_methods = str_items(objective.get("proof_methods"))
        scenarios = str_items(objective.get("scenarios"))
        coverage_goals = str_items(objective.get("coverage_goals"))
        negative_scenarios = str_items(objective.get("negative_scenarios"))
        assertion_candidates = str_items(objective.get("assertion_candidates"))
        formal_candidates = str_items(objective.get("formal_candidates"))
        residual_risks = [item for item in as_list(objective.get("residual_risks")) if isinstance(item, dict)]

        if not oid:
            issues.append(issue("VOBJ_ID", "Verification objective missing id.", base))
        elif oid in seen:
            issues.append(issue("VOBJ_DUPLICATE_ID", f"Duplicate verification objective id {oid}.", base))
        seen.add(oid)

        if status not in VALID_STATUSES:
            issues.append(issue("VOBJ_STATUS", f"{oid or base} has invalid status {status or '<missing>'}.", base))
        elif hard_gate and status not in LOCK_READY_STATUSES:
            issues.append(issue("VOBJ_NOT_READY", f"{oid or base} status {status} is not ready for post-lock TB work.", base))

        if not text(objective.get("intent")):
            issues.append(issue("VOBJ_INTENT", f"{oid or base} missing intent.", base))
        if not requirement:
            issues.append(issue("VOBJ_REQUIREMENT", f"{oid or base} missing requirement ref.", base))
        elif requirement_ids and requirement not in requirement_ids:
            issues.append(issue("VOBJ_REQUIREMENT_UNKNOWN", f"{oid or base} references unknown requirement {requirement}.", base))
        if not obligation:
            issues.append(issue("VOBJ_OBLIGATION", f"{oid or base} missing obligation ref.", base))
        elif obligation_ids and obligation not in obligation_ids:
            issues.append(issue("VOBJ_OBLIGATION_UNKNOWN", f"{oid or base} references unknown obligation {obligation}.", base))
        if not contract:
            issues.append(issue("VOBJ_CONTRACT", f"{oid or base} missing contract ref.", base))
        elif contract_ids and contract not in contract_ids:
            issues.append(issue("VOBJ_CONTRACT_UNKNOWN", f"{oid or base} references unknown contract {contract}.", base))

        if not proof_methods:
            issues.append(issue("VOBJ_PROOF_METHODS", f"{oid or base} missing proof_methods.", base))
        if not scenarios:
            issues.append(issue("VOBJ_SCENARIOS", f"{oid or base} missing scenarios.", base))
        if hard_gate and not coverage_goals:
            issues.append(issue("VOBJ_COVERAGE_GOALS", f"{oid or base} missing coverage_goals.", base))
        if objective_needs_negative(objective) and not negative_scenarios and not text(objective.get("negative_rationale")):
            issues.append(issue("VOBJ_NEGATIVE_SCENARIOS", f"{oid or base} needs negative_scenarios or negative_rationale.", base))
        if objective_needs_strong_proof(objective):
            methods = {item.lower() for item in proof_methods}
            has_strong = bool(methods & STRONG_PROOF_METHODS or assertion_candidates or formal_candidates)
            if hard_gate and not has_strong and not text(objective.get("strong_proof_rationale")):
                issues.append(issue("VOBJ_STRONG_PROOF_PATH", f"{oid or base} needs assertion/formal/protocol checker path or rationale.", base))

        if hard_gate and not residual_risks:
            issues.append(issue("VOBJ_RESIDUAL_RISK", f"{oid or base} needs residual_risks, even if the residual risk is none.", base))
        for risk_index, risk in enumerate(residual_risks):
            risk_base = f"{base}.residual_risks[{risk_index}]"
            if not text(risk.get("id")):
                issues.append(issue("VOBJ_RISK_ID", f"{oid or base} residual risk missing id.", risk_base))
            if not text(risk.get("risk")):
                issues.append(issue("VOBJ_RISK_TEXT", f"{oid or base} residual risk missing text.", risk_base))
            risk_status = text(risk.get("status")).lower()
            if risk_status not in VALID_RISK_STATUSES:
                issues.append(issue("VOBJ_RISK_STATUS", f"{oid or base} residual risk has invalid status {risk_status or '<missing>'}.", risk_base))
            elif hard_gate and risk_status == "open":
                issues.append(issue("VOBJ_OPEN_RISK", f"{oid or base} residual risk remains open after lock.", risk_base))

    next_actions: list[str] = []
    if issues:
        next_actions.append("Resolve verification plan objective, proof method, scenario, coverage, or residual risk issues.")
    elif not hard_gate:
        next_actions.append("Draft verification strategy is advisory until user lock and hard gate re-check.")
    else:
        next_actions.append("Verification strategy is ready for TB implementation handoff.")

    return {
        "schema_version": "oag_verification_plan_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "scope_locked": locked,
        "require_locked": require_locked,
        "hard_gate": hard_gate,
        "counts": {
            "objectives": len(objectives),
            "issues": len(issues),
            "open_strategy_blockers": len(open_strategy_blockers),
        },
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
        print("PASS oag verification plan check")
    else:
        print("FAIL oag verification plan check")
        for item in result["issues"]:
            path = f" {item['path']}" if item.get("path") else ""
            print(f"- {item['code']}:{path} {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
