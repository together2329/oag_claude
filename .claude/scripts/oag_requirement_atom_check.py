#!/usr/bin/env python3
"""Check OAG V2 requirement atoms and assume/guarantee contract strength."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CLOSURE_CONTRACT_TYPES = {
    "behavioral",
    "behavioral_temporal",
    "temporal",
    "protocol",
    "interface_protocol",
    "csr_semantics",
    "interrupt_event",
    "ordering",
    "backpressure",
    "error_negative",
    "reset",
}

SHALLOW_WORDS = {"correct", "works", "work", "proper", "properly", "valid", "handle", "handles"}


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


def item_id(item: Any) -> str:
    return text(item.get("id")) if isinstance(item, dict) else ""


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def is_locked(ip_dir: Path) -> bool:
    scope = read_json(ip_dir / "ontology" / "scope_lock.json")
    return scope.get("state") == "locked"


def ambiguity_values(atom: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    ambiguity = atom.get("ambiguity") if isinstance(atom.get("ambiguity"), dict) else {}
    return as_list(ambiguity.get("missing_terms")), as_list(ambiguity.get("open_questions"))


def atom_has_observable_phenomena(atom: dict[str, Any]) -> bool:
    phenomena = atom.get("phenomena") if isinstance(atom.get("phenomena"), dict) else {}
    observable_keys = (
        "controlled_state",
        "controlled_variables",
        "observable_outputs",
        "dut_outputs",
    )
    return any(as_list(phenomena.get(key)) for key in observable_keys)


def check_atoms(ip_dir: Path, *, require_locked: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    path = ip_dir / "ontology" / "requirement_atoms.yaml"
    atoms_doc = read_yaml(path)
    req_doc = read_yaml(ip_dir / "ontology" / "requirements.yaml")
    req_ids = {item_id(item) for item in as_list(req_doc.get("requirements")) if isinstance(item, dict)}
    locked = require_locked or is_locked(ip_dir)

    if "__load_error__" in atoms_doc:
        return [issue("ATOM_FILE_INVALID", f"Cannot read requirement_atoms.yaml: {atoms_doc['__load_error__']}", str(path))]
    if not atoms_doc:
        if locked:
            return [issue("ATOM_FILE_MISSING", "Locked scope requires ontology/requirement_atoms.yaml.", str(path))]
        return []
    if atoms_doc.get("schema_version") != "oag_requirement_atoms.v1":
        issues.append(issue("ATOM_SCHEMA_VERSION", "requirement_atoms.yaml must use schema_version oag_requirement_atoms.v1.", str(path)))
    atoms = [item for item in as_list(atoms_doc.get("requirement_atoms")) if isinstance(item, dict)]
    if locked and not atoms:
        issues.append(issue("ATOM_REQUIRED", "Locked scope requires at least one requirement atom.", str(path)))

    seen: set[str] = set()
    for index, atom in enumerate(atoms):
        base = f"requirement_atoms[{index}]"
        aid = item_id(atom)
        if not aid:
            issues.append(issue("ATOM_ID", "Requirement atom missing id.", base))
        elif aid in seen:
            issues.append(issue("ATOM_DUPLICATE_ID", f"Duplicate requirement atom id {aid}.", base))
        seen.add(aid)

        source = text(atom.get("source_requirement_id"))
        if not source:
            issues.append(issue("ATOM_SOURCE_REQUIREMENT", f"{aid or base} missing source_requirement_id.", base))
        elif req_ids and source not in req_ids:
            issues.append(issue("ATOM_SOURCE_UNKNOWN", f"{aid or base} references unknown requirement {source}.", base))
        if not text(atom.get("normalized_text")):
            issues.append(issue("ATOM_NORMALIZED_TEXT", f"{aid or base} missing normalized_text.", base))

        pattern = atom.get("pattern") if isinstance(atom.get("pattern"), dict) else {}
        if not text(pattern.get("trigger")):
            issues.append(issue("ATOM_TRIGGER", f"{aid or base} missing pattern.trigger.", base))
        if not text(pattern.get("response")):
            issues.append(issue("ATOM_RESPONSE", f"{aid or base} missing pattern.response.", base))
        if locked and not (text(pattern.get("timing")) or text(pattern.get("latency")) or text(pattern.get("valid_cycle"))):
            issues.append(issue("ATOM_TIMING", f"{aid or base} locked atom needs timing, latency, or valid_cycle.", base))

        boundary = atom.get("boundary") if isinstance(atom.get("boundary"), dict) else {}
        if not text(boundary.get("responsible_agent")):
            issues.append(issue("ATOM_BOUNDARY", f"{aid or base} missing boundary.responsible_agent.", base))
        if not atom_has_observable_phenomena(atom):
            issues.append(issue("ATOM_PHENOMENA", f"{aid or base} needs controlled/observable phenomena.", base))

        missing_terms, open_questions = ambiguity_values(atom)
        if locked and (missing_terms or open_questions) and text(atom.get("status")) != "blocked":
            issues.append(issue("ATOM_AMBIGUITY", f"{aid or base} has unresolved ambiguity after lock.", base))

    return issues


def obligation_is_shallow(obligation: dict[str, Any]) -> bool:
    semantic_keys = (
        "trigger",
        "preconditions",
        "environment_assumptions",
        "dut_responsibility",
        "controlled_state",
        "controlled_variable",
        "controlled_variables",
        "observable",
        "observables",
        "forbidden_behavior",
        "latency",
        "latency_bound",
        "priority_relation",
        "reset_exception",
        "oracle_projection",
        "guarantee",
    )
    if any(key in obligation and as_list(obligation.get(key)) != [] for key in semantic_keys):
        return False
    words = set(text(obligation.get("text")).lower().replace(".", "").split())
    return bool(words & SHALLOW_WORDS) or len(words) < 8


def check_obligations(ip_dir: Path, *, require_locked: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not (require_locked or is_locked(ip_dir)):
        return issues
    path = ip_dir / "ontology" / "obligations.yaml"
    doc = read_yaml(path)
    if "__load_error__" in doc:
        return [issue("OBLIGATION_FILE_INVALID", f"Cannot read obligations.yaml: {doc['__load_error__']}", str(path))]
    for index, obligation in enumerate(as_list(doc.get("obligations"))):
        if not isinstance(obligation, dict):
            continue
        status = text(obligation.get("status")).lower()
        if status in {"draft", "template"}:
            continue
        if obligation_is_shallow(obligation):
            issues.append(
                issue(
                    "OBLIGATION_SHALLOW",
                    f"{item_id(obligation) or f'obligations[{index}]'} is prose-only; add trigger/preconditions/guarantee/observable/oracle_projection.",
                    f"obligations[{index}]",
                )
            )
    return issues


def contract_needs_assume_guarantee(contract: dict[str, Any], *, require_locked: bool) -> bool:
    if require_locked:
        return True
    status = text(contract.get("status")).lower()
    if status in {"closed", "pass", "passed", "validated", "locked"}:
        return True
    ctype = text(contract.get("contract_type")).lower()
    return ctype in CLOSURE_CONTRACT_TYPES and bool(contract.get("closure_rule"))


def check_contracts(ip_dir: Path, *, require_locked: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    locked = require_locked or is_locked(ip_dir)
    path = ip_dir / "ontology" / "contracts.yaml"
    doc = read_yaml(path)
    if "__load_error__" in doc:
        return [issue("CONTRACT_FILE_INVALID", f"Cannot read contracts.yaml: {doc['__load_error__']}", str(path))]
    for index, contract in enumerate(as_list(doc.get("contracts"))):
        if not isinstance(contract, dict):
            continue
        cid = item_id(contract) or f"contracts[{index}]"
        if not contract_needs_assume_guarantee(contract, require_locked=locked):
            continue
        assume = contract.get("assume") if isinstance(contract.get("assume"), dict) else {}
        guarantee = contract.get("guarantee") if isinstance(contract.get("guarantee"), dict) else {}
        if not assume:
            issues.append(issue("CONTRACT_ASSUME_MISSING", f"{cid} needs explicit assume section.", f"contracts[{index}]"))
        if not guarantee:
            issues.append(issue("CONTRACT_GUARANTEE_MISSING", f"{cid} needs explicit guarantee section.", f"contracts[{index}]"))
        oracle = contract.get("oracle") if isinstance(contract.get("oracle"), dict) else {}
        has_oracle = bool(
            as_list(oracle.get("behavior_refs"))
            or as_list(oracle.get("cycle_rule_refs"))
            or as_list(contract.get("behavior_refs"))
            or as_list(contract.get("cycle_rule_refs"))
            or as_list(oracle.get("approved_equivalent_oracle_refs"))
            or as_list(contract.get("approved_equivalent_oracle_refs"))
        )
        if not has_oracle:
            issues.append(issue("CONTRACT_ORACLE_MISSING", f"{cid} needs behavior/cycle/protocol oracle refs or approved equivalent oracle.", f"contracts[{index}]"))
    return issues


def check(ip_dir: Path, *, require_locked: bool = False) -> dict[str, Any]:
    atom_issues = check_atoms(ip_dir, require_locked=require_locked)
    obligation_issues = check_obligations(ip_dir, require_locked=require_locked)
    contract_issues = check_contracts(ip_dir, require_locked=require_locked)
    issues = atom_issues + obligation_issues + contract_issues
    return {
        "schema_version": "oag_requirement_atom_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "scope_locked": is_locked(ip_dir),
        "require_locked": require_locked,
        "counts": {
            "atom_issues": len(atom_issues),
            "obligation_issues": len(obligation_issues),
            "contract_issues": len(contract_issues),
            "issues": len(issues),
        },
        "issues": issues,
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
        print("PASS oag requirement atom check")
    else:
        print("FAIL oag requirement atom check")
        for item in result["issues"]:
            path = f" {item['path']}" if item.get("path") else ""
            print(f"- {item['code']}:{path} {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
