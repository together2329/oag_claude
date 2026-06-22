#!/usr/bin/env python3
"""Check generated OAG role-specific authoring packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PACKET_DIR = Path("ontology/generated/authoring_packets")
DUT_DERIVED_TOKENS = {"dut_output", "rtl_expression", "post_hoc_simulation", "observed dut behavior", "observed_dut_output"}


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


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def is_locked(ip_dir: Path) -> bool:
    scope = read_json(ip_dir / "ontology" / "scope_lock.json")
    return scope.get("state") == "locked"


def check_rtl_packet(path: Path, data: dict[str, Any], *, hard_gate: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    rel = str(path)
    if data.get("__load_error__"):
        return [issue("PACKET_INVALID_JSON", f"Cannot read packet: {data['__load_error__']}", rel)]
    if data.get("schema_version") != "oag_rtl_authoring_packet.v1":
        issues.append(issue("RTL_PACKET_SCHEMA", "RTL packet must use schema_version oag_rtl_authoring_packet.v1.", rel))
    if data.get("packet_type") != "rtl_authoring_packet":
        issues.append(issue("RTL_PACKET_TYPE", "RTL packet must use packet_type rtl_authoring_packet.", rel))
    if not str_items(data.get("allowed_truth_sources")):
        issues.append(issue("RTL_PACKET_TRUTH_SOURCES", "RTL packet needs allowed_truth_sources.", rel))
    forbidden = {item.lower() for item in str_items(data.get("forbidden_sources"))}
    if hard_gate and not any("tb" in item or "sim" in item or "dut" in item for item in forbidden):
        issues.append(issue("RTL_PACKET_FORBIDDEN_SOURCES", "RTL packet must forbid TB/simulation/DUT-observed truth sources.", rel))
    if hard_gate and not str_items(data.get("contract_refs_to_implement")):
        issues.append(issue("RTL_PACKET_CONTRACT_REFS", "RTL packet needs contract_refs_to_implement.", rel))
    if hard_gate and not (
        str_items(data.get("behavior_refs_implemented_target"))
        or str_items(data.get("cycle_rule_refs_implemented_target"))
        or str_items(data.get("domain_intent_refs"))
    ):
        issues.append(issue("RTL_PACKET_ORACLE_TARGETS", "RTL packet needs behavior/cycle/domain implementation targets.", rel))
    if hard_gate and data.get("ppa_notes_required") is not True:
        issues.append(issue("RTL_PACKET_PPA_NOTES", "RTL packet should require PPA notes.", rel))
    if hard_gate and data.get("cdc_rdc_notes_required") is not True:
        issues.append(issue("RTL_PACKET_CDC_RDC_NOTES", "RTL packet should require CDC/RDC notes.", rel))
    return issues


def check_tb_packet(path: Path, data: dict[str, Any], *, hard_gate: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    rel = str(path)
    if data.get("__load_error__"):
        return [issue("PACKET_INVALID_JSON", f"Cannot read packet: {data['__load_error__']}", rel)]
    if data.get("schema_version") != "oag_tb_authoring_packet.v1":
        issues.append(issue("TB_PACKET_SCHEMA", "TB packet must use schema_version oag_tb_authoring_packet.v1.", rel))
    if data.get("packet_type") != "tb_authoring_packet":
        issues.append(issue("TB_PACKET_TYPE", "TB packet must use packet_type tb_authoring_packet.", rel))
    if data.get("expected_source_policy") != "contract_oracle_only":
        issues.append(issue("TB_PACKET_EXPECTED_SOURCE_POLICY", "TB packet must require contract_oracle_only expected sources.", rel))
    forbidden = {item.lower() for item in str_items(data.get("forbidden_expected_sources"))}
    if hard_gate and not (forbidden & DUT_DERIVED_TOKENS or any("dut" in item or "rtl" in item for item in forbidden)):
        issues.append(issue("TB_PACKET_FORBIDDEN_EXPECTED", "TB packet must forbid DUT/RTL/post-hoc expected sources.", rel))
    if hard_gate and not str_items(data.get("contract_refs")):
        issues.append(issue("TB_PACKET_CONTRACT_REFS", "TB packet needs contract_refs.", rel))
    if hard_gate and not str_items(data.get("scenario_refs")):
        issues.append(issue("TB_PACKET_SCENARIOS", "TB packet needs scenario_refs.", rel))
    if hard_gate and not str_items(data.get("scoreboard_row_refs")):
        issues.append(issue("TB_PACKET_SCOREBOARD_ROWS", "TB packet needs scoreboard_row_refs.", rel))
    return issues


def check(ip_dir: Path, *, require_locked: bool = False, require_packets: bool = False) -> dict[str, Any]:
    hard_gate = require_locked or require_packets or is_locked(ip_dir)
    packets_dir = ip_dir / PACKET_DIR
    rtl_packets = sorted(packets_dir.glob("rtl__*.json")) if packets_dir.is_dir() else []
    tb_packets = sorted(packets_dir.glob("tb__*.json")) if packets_dir.is_dir() else []
    issues: list[dict[str, str]] = []

    if hard_gate and not rtl_packets:
        issues.append(issue("RTL_PACKET_MISSING", "RTL implementation dispatch needs generated rtl__*.json authoring packet.", str(packets_dir)))
    if hard_gate and not tb_packets:
        issues.append(issue("TB_PACKET_MISSING", "TB implementation dispatch needs generated tb__*.json authoring packet.", str(packets_dir)))

    for path in rtl_packets:
        issues.extend(check_rtl_packet(path, read_json(path), hard_gate=hard_gate))
    for path in tb_packets:
        issues.extend(check_tb_packet(path, read_json(path), hard_gate=hard_gate))

    next_actions: list[str] = []
    if issues:
        next_actions.append("Run oag.compile and repair generated role-specific packet inputs by fixing authored ontology.")
    elif not hard_gate:
        next_actions.append("Draft packet check is advisory; use --require-packets before RTL/TB dispatch.")
    else:
        next_actions.append("Role-specific authoring packets are ready for bounded subagent dispatch.")

    return {
        "schema_version": "oag_authoring_packet_check.v1",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "scope_locked": is_locked(ip_dir),
        "require_locked": require_locked,
        "require_packets": require_packets,
        "hard_gate": hard_gate,
        "counts": {"rtl_packets": len(rtl_packets), "tb_packets": len(tb_packets), "issues": len(issues)},
        "issues": issues,
        "next_actions": next_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--require-locked", action="store_true")
    parser.add_argument("--require-packets", action="store_true", help="Require RTL and TB role packets even if scope is draft.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check(Path(args.ip_dir), require_locked=args.require_locked, require_packets=args.require_packets)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag authoring packet check")
    else:
        print("FAIL oag authoring packet check")
        for item in result["issues"]:
            path = f" {item['path']}" if item.get("path") else ""
            print(f"- {item['code']}:{path} {item['message']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
