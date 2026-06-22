#!/usr/bin/env python3
"""Lightweight CDC/RDC intent and RTL screening for OAG IP work."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def item_id(item: dict[str, Any], *fallback: str) -> str:
    for key in ("id", "name", *fallback):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def rtl_clock_reset_inventory(paths: list[Path]) -> dict[str, Any]:
    edge_re = re.compile(r"@\s*\(([^)]*)\)")
    clockish: set[str] = set()
    resetish: set[str] = set()
    async_blocks = 0
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in edge_re.finditer(text):
            event = match.group(1)
            if "," in event or " or " in event:
                async_blocks += 1
            for edge, signal in re.findall(r"\b(posedge|negedge)\s+([A-Za-z_][A-Za-z0-9_$]*)", event):
                lower = signal.lower()
                if "rst" in lower or "reset" in lower:
                    resetish.add(signal)
                else:
                    clockish.add(signal)
    return {
        "clock_like_signals": sorted(clockish),
        "reset_like_signals": sorted(resetish),
        "async_event_blocks": async_blocks,
    }


def domain_intent_issues(intent: dict[str, Any], *, require_domain_intent: bool) -> list[str]:
    issues: list[str] = []
    if not intent:
        if require_domain_intent:
            issues.append("CHECK_DOMAIN_INTENT_PRESENT: missing ontology/domain_intent.yaml")
        return issues
    if intent.get("schema_version") != "oag_domain_intent.v1":
        issues.append("ontology/domain_intent.yaml: schema_version must be oag_domain_intent.v1")
    for clock in as_list(intent.get("clock_domains")):
        if isinstance(clock, dict) and (not item_id(clock, "clock") or not str(clock.get("clock") or "").strip()):
            issues.append("clock domain entries require id and clock")
    for reset in as_list(intent.get("reset_domains")):
        if not isinstance(reset, dict):
            continue
        rid = item_id(reset, "reset") or "<reset_domain>"
        for field in ("reset", "polarity", "assertion", "deassertion"):
            if not str(reset.get(field) or "").strip():
                issues.append(f"{rid}: reset domain missing {field}")
    for entry in as_list(intent.get("async_inputs")):
        if not isinstance(entry, dict):
            continue
        signal = str(entry.get("signal") or item_id(entry) or "<async_input>")
        if not str(entry.get("classification") or "").strip():
            issues.append(f"{signal}: async input missing classification")
        if not str(entry.get("required_mitigation") or entry.get("allowed_pattern") or entry.get("stable_assumption") or "").strip():
            issues.append(f"{signal}: async input missing required mitigation or stable assumption")
    for crossing in as_list(intent.get("cdc_crossings")):
        if not isinstance(crossing, dict):
            continue
        cid = item_id(crossing, "source") or "<cdc_crossing>"
        ctype = str(crossing.get("crossing_type") or crossing.get("classification") or "").lower()
        pattern = str(crossing.get("allowed_pattern") or crossing.get("mitigation") or "").lower()
        if not ctype:
            issues.append(f"{cid}: CDC crossing missing crossing_type")
        if pattern in {"direct", "none", "no_sync", "unsynchronized"}:
            issues.append(f"{cid}: CDC crossing uses unsafe direct/no-sync pattern")
        if "multi_bit" in ctype and not any(token in (ctype + " " + pattern) for token in ("gray", "fifo", "handshake", "mcp", "stable", "sample", "approved")):
            issues.append(f"{cid}: multi-bit CDC needs Gray/FIFO/handshake/MCP/stable/sample/approved classification")
    for crossing in as_list(intent.get("rdc_crossings")):
        if not isinstance(crossing, dict):
            continue
        rid = item_id(crossing, "classification") or "<rdc_crossing>"
        classification = str(crossing.get("classification") or "").lower()
        if classification in {"no_known_rdc", "none", "not_applicable"}:
            if not (as_list(crossing.get("basis")) or str(crossing.get("rationale") or "").strip()):
                issues.append(f"{rid}: no-known-RDC classification needs basis")
            continue
        if not str(crossing.get("mitigation") or crossing.get("reset_sequence") or crossing.get("isolation") or crossing.get("synchronizer") or crossing.get("qualifier") or "").strip():
            issues.append(f"{rid}: RDC crossing needs sequencing, isolation, synchronizer, or qualifier")
    return issues


def check(ip_dir: Path, rtl_files: list[Path], *, require_domain_intent: bool) -> dict[str, Any]:
    intent_path = ip_dir / "ontology" / "domain_intent.yaml"
    intent = read_yaml(intent_path)
    issues = domain_intent_issues(intent, require_domain_intent=require_domain_intent)
    inventory = rtl_clock_reset_inventory(rtl_files)
    if not intent and (len(inventory["clock_like_signals"]) > 1 or len(inventory["reset_like_signals"]) > 1):
        issues.append("CHECK_DOMAIN_INTENT_PRESENT: multi-clock or multi-reset RTL requires ontology/domain_intent.yaml")
    status = "fail" if issues else "pass"
    return {
        "schema_version": "oag_domain_crossing_check.v1",
        "status": status,
        "ip": ip_dir.name,
        "domain_intent": str(intent_path),
        "rtl_files": [str(path) for path in rtl_files],
        "inventory": inventory,
        "counts": {"issues": len(issues), "rtl_files": len(rtl_files)},
        "issues": issues,
        "limitations": [
            "lightweight structural screen only",
            "does not replace static CDC/RDC, formal, or signoff tools",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--rtl-file", action="append", default=[])
    parser.add_argument("--require-domain-intent", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    ip_dir = Path(args.ip_dir)
    rtl_files = [Path(item) for item in args.rtl_file]
    result = check(ip_dir, rtl_files, require_domain_intent=args.require_domain_intent)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag domain crossing check")
    else:
        print("FAIL oag domain crossing check")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
