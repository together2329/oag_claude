#!/usr/bin/env python3
"""Check OAG assume/guarantee contract strength."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CLOSURE_STATUSES = {"closed", "pass", "passed", "validated", "locked", "complete", "done", "signoff"}
BEHAVIORAL_TYPES = {
    "behavioral",
    "behavioral_temporal",
    "csr_semantics",
    "architectural_state",
    "interrupt_event",
    "error_negative",
    "reset",
}
TEMPORAL_TYPES = {
    "temporal",
    "behavioral_temporal",
    "protocol",
    "interface_protocol",
    "ordering",
    "backpressure",
    "interrupt_event",
    "reset",
}
STORAGE_TYPES = {"storage", "storage_commit", "commit", "sram", "descriptor", "ordering"}
ERROR_TYPES = {"error_negative", "malformed", "drop", "overflow", "underflow", "timeout"}


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


def item_id(item: dict[str, Any], index: int) -> str:
    return text(item.get("id") or item.get("contract_id")) or f"contracts[{index}]"


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def is_locked(ip_dir: Path) -> bool:
    scope = read_json(ip_dir / "ontology" / "scope_lock.json")
    return scope.get("state") == "locked"


def contract_status(contract: dict[str, Any]) -> str:
    return text(contract.get("status") or contract.get("validation_status") or contract.get("decision_status")).lower()


def contract_type(contract: dict[str, Any]) -> str:
    return text(contract.get("contract_type") or contract.get("type") or contract.get("kind")).lower()


def needs_strong_check(contract: dict[str, Any], *, hard_gate: bool) -> bool:
    if hard_gate:
        return True
    if contract_status(contract) in CLOSURE_STATUSES:
        return True
    return bool(contract.get("closure_rule") or contract.get("validation_refs") or contract.get("gate_refs"))


def oracle_dict(contract: dict[str, Any]) -> dict[str, Any]:
    oracle = contract.get("oracle")
    return oracle if isinstance(oracle, dict) else {}


def projection_dict(contract: dict[str, Any]) -> dict[str, Any]:
    projection = contract.get("verification_projection")
    return projection if isinstance(projection, dict) else {}


def combined_refs(contract: dict[str, Any], key: str) -> list[str]:
    oracle = oracle_dict(contract)
    projection = projection_dict(contract)
    return [
        *str_items(contract.get(key)),
        *str_items(oracle.get(key)),
        *str_items(projection.get(key)),
    ]


def has_behavior_oracle(contract: dict[str, Any]) -> bool:
    return bool(
        combined_refs(contract, "behavior_refs")
        or combined_refs(contract, "approved_equivalent_oracle_refs")
        or combined_refs(contract, "fl_model_refs")
        or combined_refs(contract, "cl_model_refs")
    )


def has_temporal_or_protocol_oracle(contract: dict[str, Any]) -> bool:
    return bool(
        combined_refs(contract, "cycle_rule_refs")
        or combined_refs(contract, "protocol_refs")
        or combined_refs(contract, "property_refs")
        or combined_refs(contract, "approved_equivalent_oracle_refs")
    )


def has_proof_projection(contract: dict[str, Any]) -> bool:
    return bool(
        combined_refs(contract, "scenario_refs")
        or combined_refs(contract, "scenarios")
        or combined_refs(contract, "scoreboard_row_refs")
        or combined_refs(contract, "scoreboard_rows")
        or combined_refs(contract, "assertion_refs")
        or combined_refs(contract, "assertion_props")
        or combined_refs(contract, "formal_goals")
        or combined_refs(contract, "property_refs")
    )


def guarantee_mentions_ordering(contract: dict[str, Any]) -> bool:
    guarantee = contract.get("guarantee")
    if not isinstance(guarantee, dict):
        return False
    blob = json.dumps(guarantee, ensure_ascii=False).lower()
    return any(term in blob for term in ("before", "after", "last", "ordering", "visible", "commit", "valid"))


def check_contract(ip_dir: Path, contract: dict[str, Any], index: int, *, hard_gate: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    cid = item_id(contract, index)
    base = f"contracts[{index}]"
    ctype = contract_type(contract)

    if not text(contract.get("id") or contract.get("contract_id")):
        issues.append(issue("CONTRACT_ID_MISSING", f"{cid} missing id.", base))
    if not (text(contract.get("obligation") or contract.get("obligation_id")) or str_items(contract.get("obligation_refs"))):
        issues.append(issue("CONTRACT_OBLIGATION_REF_MISSING", f"{cid} missing obligation ref.", base))
    if not ctype:
        issues.append(issue("CONTRACT_TYPE_MISSING", f"{cid} missing contract_type.", base))

    if not needs_strong_check(contract, hard_gate=hard_gate):
        return issues

    variables = contract.get("variables") if isinstance(contract.get("variables"), dict) else {}
    assume = contract.get("assume") if isinstance(contract.get("assume"), dict) else {}
    guarantee = contract.get("guarantee") if isinstance(contract.get("guarantee"), dict) else {}
    oracle = oracle_dict(contract)

    if not variables:
        issues.append(issue("CONTRACT_VARIABLES_MISSING", f"{cid} needs variables for implementation-ready contract strength.", base))
    if not assume:
        issues.append(issue("CONTRACT_ASSUME_MISSING", f"{cid} needs explicit assume section.", base))
    if not guarantee:
        issues.append(issue("CONTRACT_GUARANTEE_MISSING", f"{cid} needs explicit guarantee section.", base))
    if not oracle and not (
        str_items(contract.get("behavior_refs"))
        or str_items(contract.get("cycle_rule_refs"))
        or str_items(contract.get("approved_equivalent_oracle_refs"))
    ):
        issues.append(issue("CONTRACT_ORACLE_MISSING", f"{cid} needs oracle refs or approved equivalent oracle.", base))

    if ctype in BEHAVIORAL_TYPES and not has_behavior_oracle(contract):
        issues.append(issue("CONTRACT_BEHAVIOR_ORACLE_MISSING", f"{cid} behavioral contract needs behavior refs or approved equivalent oracle.", base))
    if ctype in TEMPORAL_TYPES and not has_temporal_or_protocol_oracle(contract):
        issues.append(issue("CONTRACT_CYCLE_OR_PROTOCOL_ORACLE_MISSING", f"{cid} temporal/protocol contract needs cycle/protocol refs or approved equivalent oracle.", base))

    if not has_proof_projection(contract):
        issues.append(issue("CONTRACT_PROOF_PROJECTION_MISSING", f"{cid} needs scenario, scoreboard, assertion, formal, or property proof projection.", base))

    if ctype in STORAGE_TYPES and not guarantee_mentions_ordering(contract):
        issues.append(issue("CONTRACT_STORAGE_ORDERING_GUARANTEE", f"{cid} storage/commit contract needs explicit ordering/visibility guarantee.", base))

    if ctype in ERROR_TYPES:
        negative_refs = str_items(contract.get("negative_scenario_refs")) or str_items(projection_dict(contract).get("negative_scenarios"))
        if not negative_refs and not text(contract.get("negative_rationale")):
            issues.append(issue("CONTRACT_NEGATIVE_SCENARIOS_MISSING", f"{cid} error/drop contract needs negative scenarios or negative_rationale.", base))

    pass_condition = text(contract.get("pass_condition")).lower()
    if pass_condition and "simulation" in pass_condition and "pass" in pass_condition:
        if not assume or not guarantee or not has_behavior_oracle(contract) and not has_temporal_or_protocol_oracle(contract):
            issues.append(issue("CONTRACT_SIM_PASS_WEAK", f"{cid} uses simulation-pass prose without closure-grade contract shape.", base))

    return issues


def check(ip_dir: Path, *, require_locked: bool = False) -> dict[str, Any]:
    hard_gate = require_locked or is_locked(ip_dir)
    path = ip_dir / "ontology" / "contracts.yaml"
    doc = read_yaml(path)
    issues: list[dict[str, str]] = []
    if "__load_error__" in doc:
        issues.append(issue("CONTRACT_FILE_INVALID", f"Cannot read contracts.yaml: {doc['__load_error__']}", str(path)))
        doc = {}
    if not doc:
        if hard_gate:
            issues.append(issue("CONTRACT_FILE_MISSING", "Locked scope needs ontology/contracts.yaml.", str(path)))
        contracts: list[dict[str, Any]] = []
    else:
        contracts = [item for item in as_list(doc.get("contracts")) if isinstance(item, dict)]
    if hard_gate and not contracts:
        issues.append(issue("CONTRACT_REQUIRED", "Locked scope needs at least one contract.", "contracts"))

    for index, contract in enumerate(contracts):
        issues.extend(check_contract(ip_dir, contract, index, hard_gate=hard_gate))

    next_actions: list[str] = []
    if issues:
        next_actions.append("Strengthen contracts with assume/guarantee, variables, oracle refs, and proof projection.")
    elif not hard_gate:
        next_actions.append("Draft contract strength is advisory until lock or --require-locked.")
    else:
        next_actions.append("Contracts are strong enough for implementation-readiness screening.")

    return {
        "schema_version": "oag_contract_strength_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "scope_locked": is_locked(ip_dir),
        "require_locked": require_locked,
        "hard_gate": hard_gate,
        "counts": {"contracts": len(contracts), "issues": len(issues)},
        "issues": issues,
        "next_actions": next_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--require-locked", action="store_true", help="Apply hard gates even if scope is still draft.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check(Path(args.ip_dir), require_locked=args.require_locked)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag contract strength check")
    else:
        print("FAIL oag contract strength check")
        for item in result["issues"]:
            path = f" {item['path']}" if item.get("path") else ""
            print(f"- {item['code']}:{path} {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
