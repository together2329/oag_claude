#!/usr/bin/env python3
"""Check OAG source claims, ambiguity register, and requirement quality."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LOCK_READY_AMBIGUITY_STATUSES = {"resolved", "waived"}
VALID_AMBIGUITY_STATUSES = {"open", "unresolved", "proposed", "resolved", "waived", "blocked"}
LOCK_READY_REQUIREMENT_AMBIGUITY = {"clear", "waived"}


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


def item_id(item: Any) -> str:
    return text(item.get("id")) if isinstance(item, dict) else ""


def check_source_claims(ip_dir: Path, *, hard_gate: bool) -> tuple[list[dict[str, str]], set[str], dict[str, int]]:
    path = ip_dir / "req" / "source_claims.yaml"
    doc = read_yaml(path)
    issues: list[dict[str, str]] = []
    claim_ids: set[str] = set()
    counts = {"source_claims": 0}

    if "__load_error__" in doc:
        return [issue("SOURCE_CLAIMS_INVALID", f"Cannot read source_claims.yaml: {doc['__load_error__']}", str(path))], claim_ids, counts
    if not doc:
        if hard_gate:
            issues.append(issue("SOURCE_CLAIMS_MISSING", "Locked or required scope needs req/source_claims.yaml.", str(path)))
        return issues, claim_ids, counts
    if doc.get("schema_version") != "oag_source_claims.v1":
        issues.append(issue("SOURCE_CLAIMS_SCHEMA_VERSION", "source_claims.yaml must use schema_version oag_source_claims.v1.", str(path)))

    for index, claim in enumerate(as_list(doc.get("claims"))):
        if not isinstance(claim, dict):
            continue
        counts["source_claims"] += 1
        base = f"claims[{index}]"
        cid = item_id(claim)
        if not cid:
            issues.append(issue("SOURCE_CLAIM_ID", "Source claim missing id.", base))
        elif cid in claim_ids:
            issues.append(issue("SOURCE_CLAIM_DUPLICATE_ID", f"Duplicate source claim id {cid}.", base))
        claim_ids.add(cid)
        if not text(claim.get("source")):
            issues.append(issue("SOURCE_CLAIM_SOURCE", f"{cid or base} missing source.", base))
        if hard_gate and not (text(claim.get("quote")) or text(claim.get("summary"))):
            issues.append(issue("SOURCE_CLAIM_TEXT", f"{cid or base} needs quote or summary.", base))
        if hard_gate and not text(claim.get("normalized_meaning")):
            issues.append(issue("SOURCE_CLAIM_NORMALIZED_MEANING", f"{cid or base} needs normalized_meaning.", base))

    if hard_gate and not claim_ids:
        issues.append(issue("SOURCE_CLAIMS_REQUIRED", "Locked or required scope needs at least one source claim.", "claims"))
    return issues, claim_ids, counts


def check_ambiguities(ip_dir: Path, *, hard_gate: bool) -> tuple[list[dict[str, str]], set[str], dict[str, int], list[str]]:
    path = ip_dir / "req" / "ambiguity_register.yaml"
    doc = read_yaml(path)
    issues: list[dict[str, str]] = []
    ambiguity_ids: set[str] = set()
    blockers: list[str] = []
    counts = {"ambiguities": 0, "lock_required_ambiguities": 0, "unresolved_lock_ambiguities": 0}

    if "__load_error__" in doc:
        return [issue("AMBIGUITY_REGISTER_INVALID", f"Cannot read ambiguity_register.yaml: {doc['__load_error__']}", str(path))], ambiguity_ids, counts, blockers
    if not doc:
        if hard_gate:
            issues.append(issue("AMBIGUITY_REGISTER_MISSING", "Locked or required scope needs req/ambiguity_register.yaml.", str(path)))
        return issues, ambiguity_ids, counts, blockers
    if doc.get("schema_version") != "oag_ambiguity_register.v1":
        issues.append(issue("AMBIGUITY_SCHEMA_VERSION", "ambiguity_register.yaml must use schema_version oag_ambiguity_register.v1.", str(path)))

    for index, ambiguity in enumerate(as_list(doc.get("ambiguities"))):
        if not isinstance(ambiguity, dict):
            continue
        counts["ambiguities"] += 1
        base = f"ambiguities[{index}]"
        aid = item_id(ambiguity)
        status = text(ambiguity.get("status")).lower()
        lock_required = ambiguity.get("lock_required")
        if not aid:
            issues.append(issue("AMBIGUITY_ID", "Ambiguity row missing id.", base))
        elif aid in ambiguity_ids:
            issues.append(issue("AMBIGUITY_DUPLICATE_ID", f"Duplicate ambiguity id {aid}.", base))
        ambiguity_ids.add(aid)
        if not text(ambiguity.get("question")):
            issues.append(issue("AMBIGUITY_QUESTION", f"{aid or base} missing question.", base))
        if status not in VALID_AMBIGUITY_STATUSES:
            issues.append(issue("AMBIGUITY_STATUS", f"{aid or base} has invalid status {status or '<missing>'}.", base))
        if not isinstance(lock_required, bool):
            issues.append(issue("AMBIGUITY_LOCK_REQUIRED", f"{aid or base} lock_required must be boolean.", base))
            lock_required = False
        if not text(ambiguity.get("owner")):
            issues.append(issue("AMBIGUITY_OWNER", f"{aid or base} missing owner.", base))
        if lock_required:
            counts["lock_required_ambiguities"] += 1
            if status not in LOCK_READY_AMBIGUITY_STATUSES:
                counts["unresolved_lock_ambiguities"] += 1
                blockers.append(aid or base)
                if hard_gate:
                    issues.append(issue("AMBIGUITY_LOCK_BLOCKER", f"{aid or base} is lock-required but status is {status or '<missing>'}.", base))
        if status == "resolved" and not has_value(ambiguity.get("resolution")):
            issues.append(issue("AMBIGUITY_RESOLUTION_MISSING", f"{aid or base} is resolved but has no resolution.", base))
        if status == "waived" and not text(ambiguity.get("waiver_reason")):
            issues.append(issue("AMBIGUITY_WAIVER_REASON", f"{aid or base} is waived but has no waiver_reason.", base))

    return issues, ambiguity_ids, counts, blockers


def check_requirements(ip_dir: Path, *, hard_gate: bool, claim_ids: set[str]) -> tuple[list[dict[str, str]], dict[str, int]]:
    path = ip_dir / "ontology" / "requirements.yaml"
    doc = read_yaml(path)
    issues: list[dict[str, str]] = []
    counts = {"requirements": 0}
    if "__load_error__" in doc:
        return [issue("REQ_FILE_INVALID", f"Cannot read requirements.yaml: {doc['__load_error__']}", str(path))], counts
    reqs = [item for item in as_list(doc.get("requirements")) if isinstance(item, dict)]
    counts["requirements"] = len(reqs)
    if hard_gate and not reqs:
        issues.append(issue("REQ_REQUIRED", "Locked or required scope needs at least one requirement.", "requirements"))

    seen: set[str] = set()
    for index, req in enumerate(reqs):
        base = f"requirements[{index}]"
        rid = item_id(req)
        if not rid:
            issues.append(issue("REQ_ID", "Requirement missing id.", base))
        elif rid in seen:
            issues.append(issue("REQ_DUPLICATE_ID", f"Duplicate requirement id {rid}.", base))
        seen.add(rid)
        if not text(req.get("text")):
            issues.append(issue("REQ_TEXT", f"{rid or base} missing text.", base))
        if not hard_gate:
            continue
        if text(req.get("status")).lower() in {"draft", "template", "todo"}:
            issues.append(issue("REQ_STATUS_DRAFT", f"{rid or base} is still draft after lock.", base))
        if not (text(req.get("requirement_type")) or text(req.get("type"))):
            issues.append(issue("REQ_TYPE_MISSING", f"{rid or base} missing requirement_type or type.", base))
        if not (text(req.get("source")) or as_list(req.get("source_refs"))):
            issues.append(issue("REQ_SOURCE_MISSING", f"{rid or base} missing source or source_refs.", base))
        source_claim_refs = [text(item) for item in as_list(req.get("source_claim_refs")) if text(item)]
        if not source_claim_refs:
            issues.append(issue("REQ_SOURCE_CLAIM_REFS", f"{rid or base} missing source_claim_refs.", base))
        elif claim_ids:
            for ref in source_claim_refs:
                if ref not in claim_ids:
                    issues.append(issue("REQ_SOURCE_CLAIM_UNKNOWN", f"{rid or base} references unknown source claim {ref}.", base))
        if not as_list(req.get("verification_method")):
            issues.append(issue("REQ_VERIFICATION_METHOD", f"{rid or base} missing verification_method.", base))
        ambiguity_status = text(req.get("ambiguity_status")).lower()
        if ambiguity_status not in LOCK_READY_REQUIREMENT_AMBIGUITY:
            issues.append(issue("REQ_AMBIGUITY_STATUS", f"{rid or base} ambiguity_status must be clear or waived for lock readiness.", base))

    return issues, counts


def check(ip_dir: Path, *, require_locked: bool = False) -> dict[str, Any]:
    locked = is_locked(ip_dir)
    hard_gate = require_locked or locked
    source_issues, claim_ids, source_counts = check_source_claims(ip_dir, hard_gate=hard_gate)
    ambiguity_issues, _ambiguity_ids, ambiguity_counts, blockers = check_ambiguities(ip_dir, hard_gate=hard_gate)
    req_issues, req_counts = check_requirements(ip_dir, hard_gate=hard_gate, claim_ids=claim_ids)
    issues = source_issues + ambiguity_issues + req_issues
    next_actions: list[str] = []
    if ambiguity_counts["unresolved_lock_ambiguities"]:
        next_actions.append("Resolve or waive lock-required ambiguities in req/ambiguity_register.yaml.")
    if req_issues:
        next_actions.append("Upgrade requirements with source refs, type, verification method, and clear ambiguity status.")
    if not issues and not hard_gate:
        next_actions.append("Draft requirement quality is advisory until user lock and hard gate re-check.")
    return {
        "schema_version": "oag_req_quality_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "scope_locked": locked,
        "require_locked": require_locked,
        "hard_gate": hard_gate,
        "counts": {
            **source_counts,
            **ambiguity_counts,
            **req_counts,
            "source_issues": len(source_issues),
            "ambiguity_issues": len(ambiguity_issues),
            "requirement_issues": len(req_issues),
            "issues": len(issues),
        },
        "unresolved_lock_ambiguities": blockers,
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
        print("PASS oag requirement quality check")
    else:
        print("FAIL oag requirement quality check")
        for item in result["issues"]:
            path = f" {item['path']}" if item.get("path") else ""
            print(f"- {item['code']}:{path} {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
