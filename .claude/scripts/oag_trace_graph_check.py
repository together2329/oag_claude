#!/usr/bin/env python3
"""Check OAG source-to-evidence trace graph ID integrity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"__load_error__": str(exc)}


def read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def str_items(value: Any) -> list[str]:
    return [str(item).strip() for item in as_list(value) if str(item).strip()]


def text(value: Any) -> str:
    return str(value or "").strip()


def item_id(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return text(item.get("id") or item.get("contract_id") or item.get("obligation_id") or item.get("scenario_id") or item.get("event_id"))


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def is_locked(ip_dir: Path) -> bool:
    scope = read_json(ip_dir / "ontology" / "scope_lock.json")
    return isinstance(scope, dict) and scope.get("state") == "locked"


def collect_ids(items: list[Any]) -> set[str]:
    return {item_id(item) for item in items if item_id(item)}


def yaml_items(ip_dir: Path, rel: str, key: str) -> list[dict[str, Any]]:
    doc = read_yaml(ip_dir / rel)
    if not isinstance(doc, dict):
        return []
    return [item for item in as_list(doc.get(key)) if isinstance(item, dict)]


def planned_scenario_and_rows(ip_dir: Path) -> tuple[set[str], set[str]]:
    doc = read_yaml(ip_dir / "req" / "evidence_plan.yaml")
    scenario_ids: set[str] = set()
    row_ids: set[str] = set()
    for scenario in as_list(doc.get("planned_scenarios")):
        if not isinstance(scenario, dict):
            continue
        sid = text(scenario.get("id") or scenario.get("scenario_id"))
        if sid:
            scenario_ids.add(sid)
        row_ids.update(str_items(scenario.get("expected_scoreboard_rows")))
    for contract in as_list(doc.get("contracts")):
        if not isinstance(contract, dict):
            continue
        scenario_ids.update(str_items(contract.get("scenario_refs")))
        row_ids.update(str_items(contract.get("scoreboard_row_refs")))
        row_ids.update(str_items(contract.get("expected_scoreboard_rows")))
    return scenario_ids, row_ids


def scoreboard_ids(ip_dir: Path) -> tuple[set[str], list[dict[str, Any]], list[dict[str, str]]]:
    path = ip_dir / "sim" / "scoreboard_events.jsonl"
    ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    if not path.is_file():
        return ids, rows, issues
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            issues.append(issue("SCOREBOARD_JSONL_INVALID", f"Invalid scoreboard JSONL line {lineno}: {exc}", str(path)))
            continue
        if isinstance(row, dict):
            rid = text(row.get("event_id") or row.get("id"))
            if rid:
                ids.add(rid)
            rows.append(row)
    return ids, rows, issues


def contract_refs(contract: dict[str, Any], *keys: str) -> list[str]:
    refs: list[str] = []
    oracle = contract.get("oracle") if isinstance(contract.get("oracle"), dict) else {}
    projection = contract.get("verification_projection") if isinstance(contract.get("verification_projection"), dict) else {}
    for key in keys:
        refs.extend(str_items(contract.get(key)))
        refs.extend(str_items(oracle.get(key)))
        refs.extend(str_items(projection.get(key)))
    return refs


def check(ip_dir: Path, *, require_locked: bool = False) -> dict[str, Any]:
    hard_gate = require_locked or is_locked(ip_dir)
    issues: list[dict[str, str]] = []

    claims = yaml_items(ip_dir, "req/source_claims.yaml", "claims")
    requirements = yaml_items(ip_dir, "ontology/requirements.yaml", "requirements")
    atoms = yaml_items(ip_dir, "ontology/requirement_atoms.yaml", "requirement_atoms")
    obligations = yaml_items(ip_dir, "ontology/obligations.yaml", "obligations")
    contracts = yaml_items(ip_dir, "ontology/contracts.yaml", "contracts")
    vobjs = yaml_items(ip_dir, "ontology/verification_plan.yaml", "verification_objectives")
    coverage_goals = yaml_items(ip_dir, "ontology/tb_methodology.yaml", "coverage_goals")
    planned_scenarios, planned_rows = planned_scenario_and_rows(ip_dir)
    scoreboard_row_ids, scoreboard_rows, scoreboard_issues = scoreboard_ids(ip_dir)
    issues.extend(scoreboard_issues)

    claim_ids = collect_ids(claims)
    req_ids = collect_ids(requirements)
    atom_ids = collect_ids(atoms)
    obligation_ids = collect_ids(obligations)
    contract_ids = collect_ids(contracts)
    scenario_ids = set(planned_scenarios)
    row_ids = set(planned_rows) | scoreboard_row_ids

    for contract in contracts:
        scenario_ids.update(contract_refs(contract, "scenario_refs", "scenarios"))
        row_ids.update(contract_refs(contract, "scoreboard_row_refs", "scoreboard_rows"))
    for objective in vobjs:
        scenario_ids.update(str_items(objective.get("scenarios")))
        scenario_ids.update(str_items(objective.get("negative_scenarios")))

    for index, req in enumerate(requirements):
        rid = item_id(req) or f"requirements[{index}]"
        refs = str_items(req.get("source_claim_refs"))
        if hard_gate and not refs:
            issues.append(issue("TRACE_REQ_SOURCE_CLAIM_MISSING", f"{rid} missing source_claim_refs.", f"requirements[{index}]"))
        for ref in refs:
            if claim_ids and ref not in claim_ids:
                issues.append(issue("TRACE_REQ_SOURCE_CLAIM_UNKNOWN", f"{rid} references unknown source claim {ref}.", f"requirements[{index}]"))

    for index, atom in enumerate(atoms):
        aid = item_id(atom) or f"requirement_atoms[{index}]"
        ref = text(atom.get("source_requirement_id"))
        if hard_gate and not ref:
            issues.append(issue("TRACE_ATOM_REQUIREMENT_MISSING", f"{aid} missing source_requirement_id.", f"requirement_atoms[{index}]"))
        elif req_ids and ref and ref not in req_ids:
            issues.append(issue("TRACE_ATOM_REQUIREMENT_UNKNOWN", f"{aid} references unknown requirement {ref}.", f"requirement_atoms[{index}]"))

    for index, obligation in enumerate(obligations):
        oid = item_id(obligation) or f"obligations[{index}]"
        refs = str_items(obligation.get("requirement_refs")) or str_items(obligation.get("requirements")) or [text(obligation.get("requirement"))]
        refs = [ref for ref in refs if ref]
        if hard_gate and not refs:
            issues.append(issue("TRACE_OBLIGATION_REQUIREMENT_MISSING", f"{oid} missing requirement ref.", f"obligations[{index}]"))
        for ref in refs:
            if req_ids and ref not in req_ids:
                issues.append(issue("TRACE_OBLIGATION_REQUIREMENT_UNKNOWN", f"{oid} references unknown requirement {ref}.", f"obligations[{index}]"))

    for index, contract in enumerate(contracts):
        cid = item_id(contract) or f"contracts[{index}]"
        refs = str_items(contract.get("obligation_refs")) or [text(contract.get("obligation") or contract.get("obligation_id"))]
        refs = [ref for ref in refs if ref]
        if hard_gate and not refs:
            issues.append(issue("TRACE_CONTRACT_OBLIGATION_MISSING", f"{cid} missing obligation ref.", f"contracts[{index}]"))
        for ref in refs:
            if obligation_ids and ref not in obligation_ids:
                issues.append(issue("TRACE_CONTRACT_OBLIGATION_UNKNOWN", f"{cid} references unknown obligation {ref}.", f"contracts[{index}]"))
        for ref in contract_refs(contract, "scenario_refs", "scenarios"):
            if scenario_ids and ref not in scenario_ids:
                issues.append(issue("TRACE_CONTRACT_SCENARIO_UNKNOWN", f"{cid} references unknown scenario {ref}.", f"contracts[{index}]"))
        for ref in contract_refs(contract, "scoreboard_row_refs", "scoreboard_rows"):
            if row_ids and ref not in row_ids:
                issues.append(issue("TRACE_CONTRACT_SCOREBOARD_ROW_UNKNOWN", f"{cid} references unknown scoreboard row {ref}.", f"contracts[{index}]"))

    for index, objective in enumerate(vobjs):
        oid = item_id(objective) or f"verification_objectives[{index}]"
        for label, ref, known in (
            ("requirement", text(objective.get("requirement")), req_ids),
            ("obligation", text(objective.get("obligation")), obligation_ids),
            ("contract", text(objective.get("contract")), contract_ids),
        ):
            if hard_gate and not ref:
                issues.append(issue("TRACE_VOBJ_REF_MISSING", f"{oid} missing {label} ref.", f"verification_objectives[{index}]"))
            elif known and ref and ref not in known:
                issues.append(issue("TRACE_VOBJ_REF_UNKNOWN", f"{oid} references unknown {label} {ref}.", f"verification_objectives[{index}]"))

    for index, row in enumerate(scoreboard_rows):
        rid = text(row.get("event_id") or row.get("id")) or f"scoreboard[{index}]"
        if not text(row.get("scenario_id")):
            issues.append(issue("TRACE_SCOREBOARD_SCENARIO_MISSING", f"{rid} missing scenario_id.", f"scoreboard_events[{index}]"))
        refs = str_items(row.get("contract_refs")) or str_items(row.get("contracts")) or [text(row.get("contract_id"))]
        refs = [ref for ref in refs if ref]
        if not refs:
            issues.append(issue("TRACE_SCOREBOARD_CONTRACTS_MISSING", f"{rid} missing contract refs.", f"scoreboard_events[{index}]"))
        if not row.get("expected_source"):
            issues.append(issue("TRACE_SCOREBOARD_EXPECTED_SOURCE_MISSING", f"{rid} missing expected_source.", f"scoreboard_events[{index}]"))

    for index, goal in enumerate(coverage_goals):
        gid = item_id(goal) or f"coverage_goals[{index}]"
        refs = [text(goal.get("requirement")), text(goal.get("obligation")), text(goal.get("contract"))]
        if hard_gate and not any(refs):
            issues.append(issue("TRACE_COVERAGE_GOAL_UNMAPPED", f"{gid} must map to requirement, obligation, or contract.", f"coverage_goals[{index}]"))

    next_actions = ["Resolve orphan refs or missing source-to-contract-to-evidence links."] if issues else ["Trace graph IDs are consistent for the checked scope."]
    if not hard_gate and not issues:
        next_actions = ["Draft trace graph is advisory until lock or --require-locked."]
    return {
        "schema_version": "oag_trace_graph_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "scope_locked": is_locked(ip_dir),
        "require_locked": require_locked,
        "hard_gate": hard_gate,
        "counts": {
            "source_claims": len(claims),
            "requirements": len(requirements),
            "requirement_atoms": len(atoms),
            "obligations": len(obligations),
            "contracts": len(contracts),
            "verification_objectives": len(vobjs),
            "scenarios": len(scenario_ids),
            "scoreboard_rows": len(row_ids),
            "issues": len(issues),
        },
        "issues": issues,
        "next_actions": next_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--require-locked", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check(Path(args.ip_dir), require_locked=args.require_locked)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag trace graph check")
    else:
        print("FAIL oag trace graph check")
        for item in result["issues"]:
            path = f" {item['path']}" if item.get("path") else ""
            print(f"- {item['code']}:{path} {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
