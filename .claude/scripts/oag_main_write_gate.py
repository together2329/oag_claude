#!/usr/bin/env python3
"""Block locked-stage implementation writes that bypass native OAG subagents."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


CODEX_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get("OAG_PROJECT_ROOT") or CODEX_ROOT.parent).expanduser().resolve()

IMPLEMENTATION_PATTERNS = (
    "rtl/*.sv",
    "rtl/**/*.sv",
    "rtl/*.v",
    "rtl/**/*.v",
    "rtl/*.svh",
    "rtl/**/*.svh",
    "list/*.f",
    "list/**/*.f",
    "list/*.vf",
    "list/**/*.vf",
    "tb/*",
    "tb/**/*",
    "scripts/run_sim.sh",
    "scripts/*sim*",
    "scripts/**/*sim*",
    "sim/*",
    "sim/**/*",
    "lint/*",
    "lint/**/*",
    "cov/*",
    "cov/**/*",
    "coverage/*",
    "coverage/**/*",
    "formal/*",
    "formal/**/*",
    "sdc/*",
    "sdc/**/*",
    "signoff/*",
    "signoff/**/*",
)
IGNORED_PATH_PATTERNS = (
    "**/.gitkeep",
    "knowledge/dispatches/**/*",
    "knowledge/subagents/**/*",
    "ontology/generated/**/*",
)
SUBAGENT_ROLE_FRAGMENTS = (
    "rtl-implementation-agent",
    "tb-implementation-agent",
    "rtl-lint-static-agent",
    "sim-execution-agent",
    "coverage-agent",
    "mutation-guard-agent",
    "evidence-validator",
    "gate-reviewer",
    "custom-worker",
)
SAFE_RECEIPT_STATUSES = {"HANDOFF_PASS", "STATIC_HANDOFF_PASS", "RTL_HANDOFF_PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"}
WAIVER_ACTIONS = {"main_agent_subagent_waiver", "subagent_waiver", "main_agent_implementation_waiver"}


def issue(code: str, message: str, path: str | None = None) -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def project_rel(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_project_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def normalize_candidate(raw: str, ip_dir: Path) -> str:
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if path.is_absolute():
        return project_rel(path)
    ip_rel = project_rel(ip_dir)
    normalized = raw.strip().replace("\\", "/").strip("/")
    if normalized == ip_rel or normalized.startswith(ip_rel + "/"):
        return normalized
    return f"{ip_rel}/{normalized}" if ip_rel else normalized


def ip_relative(path: str, ip_dir: Path) -> str:
    ip_rel = project_rel(ip_dir)
    return path[len(ip_rel) + 1:] if path.startswith(ip_rel + "/") else path


def path_matches(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    normalized = path.strip("/")
    for pattern in patterns:
        pat = str(pattern).strip("/")
        if not pat:
            continue
        if fnmatch.fnmatch(normalized, pat) or fnmatch.fnmatch(normalized, pat.rstrip("/") + "/*"):
            return True
        if normalized == pat or normalized.startswith(pat + "/"):
            return True
    return False


def scope_locked(ip_dir: Path) -> bool:
    try:
        payload = load_json(ip_dir / "ontology" / "scope_lock.json")
    except Exception:
        return False
    return isinstance(payload, dict) and str(payload.get("state") or "").strip().lower() == "locked"


def git_status_paths(ip_dir: Path) -> list[str]:
    ip_rel = project_rel(ip_dir)
    proc = subprocess.run(
        ["git", "status", "--short", "-uall", "--", ip_rel],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1].strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        if raw:
            paths.append(raw)
    return sorted(set(paths))


def implementation_changes(ip_dir: Path) -> list[str]:
    candidates: list[str] = []
    for path in git_status_paths(ip_dir):
        rel = ip_relative(path, ip_dir)
        if path_matches(rel, IGNORED_PATH_PATTERNS):
            continue
        if path_matches(rel, IMPLEMENTATION_PATTERNS):
            candidates.append(path)
    return sorted(set(candidates))


def human_waiver(ip_dir: Path) -> dict[str, Any] | None:
    validations = ip_dir / "ontology" / "validations"
    for path in sorted(validations.glob("DEC_*.json"), reverse=True):
        try:
            receipt = load_json(path)
        except Exception:
            continue
        if not isinstance(receipt, dict):
            continue
        action = str(receipt.get("action") or "").strip()
        actor = receipt.get("actor") if isinstance(receipt.get("actor"), dict) else {}
        if action in WAIVER_ACTIONS and receipt.get("allowed") is True and str(actor.get("kind") or "").lower() == "human":
            return {"path": project_rel(path), "receipt": receipt}
    return None


def receipt_covered_paths(ip_dir: Path) -> tuple[set[str], list[dict[str, Any]]]:
    covered: set[str] = set()
    receipts: list[dict[str, Any]] = []
    for path in sorted((ip_dir / "knowledge" / "subagents").glob("*.json")):
        try:
            receipt = load_json(path)
        except Exception:
            continue
        if not isinstance(receipt, dict):
            continue
        role = str(receipt.get("role_name") or "")
        if not role.startswith("oag-") or not any(fragment in role for fragment in SUBAGENT_ROLE_FRAGMENTS):
            continue
        if receipt.get("schema_version") != "oag_subagent_receipt.v1":
            continue
        if receipt.get("may_claim_complete") is not False or receipt.get("status") not in SAFE_RECEIPT_STATUSES:
            continue
        dispatch_path = normalize_candidate(str(receipt.get("dispatch_path") or ""), ip_dir)
        if not dispatch_path or not (PROJECT_ROOT / dispatch_path).is_file():
            continue
        paths: list[str] = []
        for field in ("changed_paths", "generated_side_effects", "evidence_outputs"):
            value = receipt.get(field)
            if isinstance(value, list):
                paths.extend(str(item) for item in value if isinstance(item, str))
        normalized = {normalize_candidate(item, ip_dir) for item in paths}
        covered.update(item for item in normalized if item)
        receipts.append(
            {
                "path": project_rel(path),
                "role_name": role,
                "dispatch_id": str(receipt.get("dispatch_id") or ""),
                "status": str(receipt.get("status") or ""),
                "covered_paths": sorted(normalized),
            }
        )
    return covered, receipts


def check_ip(ip_dir: Path) -> dict[str, Any]:
    ip_dir = ip_dir.expanduser().resolve()
    issues: list[dict[str, str]] = []
    if not ip_dir.exists():
        issues.append(issue("IP_DIR_MISSING", "IP directory does not exist.", str(ip_dir)))
        return build_result(ip_dir, locked=False, changes=[], receipts=[], waiver=None, issues=issues)

    locked = scope_locked(ip_dir)
    changes = implementation_changes(ip_dir)
    if not locked or not changes:
        return build_result(ip_dir, locked=locked, changes=changes, receipts=[], waiver=None, issues=issues)

    waiver = human_waiver(ip_dir)
    if waiver:
        return build_result(ip_dir, locked=locked, changes=changes, receipts=[], waiver=waiver, issues=issues)

    covered, receipts = receipt_covered_paths(ip_dir)
    uncovered = []
    for path in changes:
        if path in covered:
            continue
        rel = ip_relative(path, ip_dir)
        if any(path_matches(rel, [ip_relative(candidate, ip_dir)]) for candidate in covered):
            continue
        uncovered.append(path)
    for path in uncovered:
        issues.append(
            issue(
                "MAIN_AGENT_WRITE_WITHOUT_SUBAGENT",
                "Locked implementation/verification artifact changed without a covering native OAG subagent receipt.",
                path,
            )
        )
    return build_result(ip_dir, locked=locked, changes=changes, receipts=receipts, waiver=waiver, issues=issues)


def build_result(
    ip_dir: Path,
    *,
    locked: bool,
    changes: list[str],
    receipts: list[dict[str, Any]],
    waiver: dict[str, Any] | None,
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": "oag_main_write_gate.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "status": "fail" if issues else "pass",
        "ip": ip_dir.name,
        "ip_dir": project_rel(ip_dir),
        "scope_locked": locked,
        "implementation_changes": changes,
        "subagent_receipts": receipts,
        "waiver": waiver,
        "issues": issues,
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    issues = [item for result in results for item in result.get("issues", [])]
    return {
        "schema_version": "oag_main_write_gate_report.v1",
        "status": "fail" if issues else "pass",
        "results": results,
        "issues": issues,
    }


def print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag main write gate")
    else:
        print("FAIL oag main write gate", file=sys.stderr)
        for item in result.get("issues", []):
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Require native OAG subagent receipts for locked implementation writes.")
    parser.add_argument("--ip-dir", action="append", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = aggregate([check_ip(resolve_project_path(raw)) for raw in args.ip_dir])
    print_result(result, args.json)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
