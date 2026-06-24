#!/usr/bin/env python3
"""Validate OAG artifact lifecycle metadata and consumer eligibility."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
CODEX_ROOT = SCRIPTS_DIR.parent
SCHEMAS_DIR = CODEX_ROOT / "schemas"

sys.path.insert(0, str(SCRIPTS_DIR))
import oag_paths  # noqa: E402
from oag_validate_json import validate_document  # pylint: disable=wrong-import-position


LIFECYCLE_PATH = Path("ontology/artifact_lifecycle.json")
DESIGN_TRUTH_STAGES = {"canonical", "curated", "serving"}
AUTHORING_PACKET_CONSUMERS = {"rtl_authoring_packet", "tb_authoring_packet"}


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def read_json(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [issue("LIFECYCLE_INVALID_JSON", f"Cannot read lifecycle JSON: {exc}", str(path))]
    if not isinstance(payload, dict):
        return None, [issue("LIFECYCLE_SHAPE", "Lifecycle document must be a JSON object.", str(path))]
    return payload, []


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def str_items(value: Any) -> list[str]:
    return [str(item).strip() for item in as_list(value) if str(item).strip()]


def load_schema() -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / "oag_artifact_lifecycle.schema.json").read_text(encoding="utf-8"))


def schema_issues(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        issue("LIFECYCLE_SCHEMA", f"{item.get('code')}: {item.get('message')}", str(item.get("path") or ""))
        for item in validate_document(load_schema(), payload)
    ]


def check_artifact(item: dict[str, Any], *, consumer: str = "", selected: bool = False) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    artifact_id = str(item.get("id") or item.get("path") or "<unknown>")
    stage = str(item.get("processing_stage") or "")
    approval = str(item.get("approval_state") or "")
    validity = str(item.get("validity_state") or "")
    allowed = str_items(item.get("allowed_consumers"))
    derived_from = str_items(item.get("derived_from"))

    if not allowed:
        issues.append(issue("LIFECYCLE_ALLOWED_CONSUMERS", "Artifact must list allowed_consumers.", artifact_id))
    if item.get("granularity") == "object" and not str(item.get("object_id") or "").strip():
        issues.append(issue("LIFECYCLE_OBJECT_ID", "Object-level lifecycle entries require object_id.", artifact_id))
    if stage in DESIGN_TRUTH_STAGES and not derived_from:
        issues.append(issue("LIFECYCLE_DERIVED_FROM", f"{stage} artifact must list derived_from.", artifact_id))
    if approval == "approved" and not str(item.get("approval_ref") or "").strip():
        issues.append(issue("LIFECYCLE_APPROVAL_REF", "Approved artifact must list approval_ref.", artifact_id))

    if selected and consumer:
        if consumer not in allowed:
            issues.append(issue("LIFECYCLE_CONSUMER_FORBIDDEN", f"{consumer} is not listed in allowed_consumers.", artifact_id))
        if consumer in AUTHORING_PACKET_CONSUMERS:
            if stage not in DESIGN_TRUTH_STAGES:
                issues.append(issue("LIFECYCLE_PROCESSING_STAGE", f"{consumer} requires canonical, curated, or serving input.", artifact_id))
            if approval != "approved":
                issues.append(issue("LIFECYCLE_APPROVAL_STATE", f"{consumer} requires approval_state=approved.", artifact_id))
            if validity != "current":
                issues.append(issue("LIFECYCLE_VALIDITY_STATE", f"{consumer} requires validity_state=current.", artifact_id))
    return issues


def check(ip_dir: Path, *, require: bool = False, artifact_id: str = "", consumer: str = "") -> dict[str, Any]:
    path = oag_paths.legacy_or_hidden(ip_dir, str(LIFECYCLE_PATH))
    issues: list[dict[str, str]] = []
    if not path.is_file():
        if require:
            issues.append(issue("LIFECYCLE_MISSING", "Required ontology/artifact_lifecycle.json is missing.", str(path)))
        return {
            "schema_version": "oag_lifecycle_check.v1",
            "status": "fail" if issues else "pass",
            "ip": ip_dir.name,
            "lifecycle_path": str(path),
            "counts": {"artifacts": 0, "selected": 0, "issues": len(issues)},
            "issues": issues,
            "next_actions": ["Create ontology/artifact_lifecycle.json before implementation packet filtering."] if issues else [],
        }

    payload, load_issues = read_json(path)
    if load_issues:
        issues.extend(load_issues)
        payload = {}
    if payload:
        issues.extend(schema_issues(payload))

    artifacts = payload.get("artifacts") if isinstance(payload, dict) else []
    if not isinstance(artifacts, list):
        artifacts = []

    selected_count = 0
    for item in artifacts:
        if not isinstance(item, dict):
            issues.append(issue("LIFECYCLE_ARTIFACT_SHAPE", "Each artifact lifecycle entry must be an object."))
            continue
        matches_artifact = not artifact_id or item.get("id") == artifact_id
        listed_for_consumer = bool(consumer and consumer in str_items(item.get("allowed_consumers")))
        selected = matches_artifact and (bool(artifact_id) or not consumer or listed_for_consumer)
        if selected:
            selected_count += 1
        issues.extend(check_artifact(item, consumer=consumer, selected=selected))

    if artifact_id and selected_count == 0:
        issues.append(issue("LIFECYCLE_ARTIFACT_NOT_FOUND", f"Artifact id not found: {artifact_id}", artifact_id))
    if consumer and not artifact_id and selected_count == 0:
        issues.append(issue("LIFECYCLE_CONSUMER_NO_INPUTS", f"No lifecycle entries are allowed for consumer {consumer}.", consumer))

    return {
        "schema_version": "oag_lifecycle_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "lifecycle_path": str(path),
        "consumer": consumer,
        "artifact_id": artifact_id,
        "counts": {"artifacts": len(artifacts), "selected": selected_count, "issues": len(issues)},
        "issues": issues,
        "next_actions": ["Repair lifecycle metadata before using affected artifacts."] if issues else ["Lifecycle metadata is eligible for requested consumer."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--require", action="store_true", help="Fail when ontology/artifact_lifecycle.json is missing.")
    parser.add_argument("--artifact-id", default="")
    parser.add_argument("--consumer", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check(Path(args.ip_dir), require=args.require, artifact_id=args.artifact_id, consumer=args.consumer)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS OAG lifecycle check")
    else:
        print("FAIL OAG lifecycle check", file=sys.stderr)
        for item in result["issues"]:
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
