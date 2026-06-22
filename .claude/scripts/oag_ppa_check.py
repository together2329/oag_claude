#!/usr/bin/env python3
"""Lightweight heuristic PPA/dialect checker for OAG-generated RTL."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ALWAYS_FF", r"\balways_ff\b"),
    ("ALWAYS_COMB", r"\balways_comb\b"),
    ("TYPEDEF", r"\btypedef\b"),
    ("ENUM", r"\benum\b"),
    ("STRUCT", r"\bstruct\b"),
    ("INTERFACE", r"\binterface\b"),
    ("PACKAGE", r"\bpackage\b"),
    ("CLASS", r"\bclass\b"),
    ("ASSERTION", r"\b(assert|assume|cover)\s+property\b"),
    ("COVERGROUP", r"\bcovergroup\b"),
)


def issue(path: Path, line: int, severity: str, code: str, message: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "line": line,
        "severity": severity,
        "code": code,
        "message": message,
    }


def strip_line_comment(line: str) -> str:
    return line.split("//", 1)[0]


def scan_file(path: Path, *, comb_warn_threshold: int) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    issues: list[dict[str, Any]] = []

    generate_depth = 0
    case_stack: list[dict[str, Any]] = []
    comb_start: int | None = None
    comb_depth = 0

    for index, raw in enumerate(lines, start=1):
        line = strip_line_comment(raw)

        for code, pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                issues.append(issue(path, index, "fail", code, "Construct is outside the default OAG SV-lite RTL dialect."))

        if re.search(r"\bgenerate\b", line):
            generate_depth += 1
        if re.search(r"\bendgenerate\b", line) and generate_depth > 0:
            generate_depth -= 1

        if generate_depth == 0 and re.search(r"\b(for|while|repeat|forever)\s*(\(|\b)", line):
            issues.append(issue(path, index, "fail", "PROCEDURAL_LOOP", "Procedural loops outside generate are forbidden by default."))

        if re.search(r"\bassign\s+\w*clk\w*\s*=", line, re.IGNORECASE) and re.search(r"\&|\||\?", line):
            issues.append(issue(path, index, "warn", "MANUAL_CLOCK_GATING", "Possible manual clock gating; prefer enables unless policy allows gates."))
        if re.search(r"@(posedge|negedge)\s*\([^)]*[&|?]", line):
            issues.append(issue(path, index, "warn", "GATED_CLOCK_EVENT", "Possible gated clock in event control."))

        width_match = re.search(r"\[(\d+)\s*:\s*0\]", line)
        if width_match and int(width_match.group(1)) + 1 > 1024:
            issues.append(issue(path, index, "warn", "VERY_WIDE_VECTOR", "Very wide vector; confirm memory/datapath sizing is intentional."))

        if re.search(r"\bcase[zx]?\s*\(", line):
            case_stack.append({"line": index, "has_default": False})
        if case_stack and re.search(r"\bdefault\s*:", line):
            case_stack[-1]["has_default"] = True
        if re.search(r"\bendcase\b", line) and case_stack:
            item = case_stack.pop()
            if not item["has_default"]:
                issues.append(issue(path, int(item["line"]), "warn", "CASE_WITHOUT_DEFAULT", "Case statement has no default behavior."))

        if re.search(r"\balways\s*@\s*\(\s*(\*|all)\s*\)", line):
            comb_start = index
            comb_depth = 0
        if comb_start is not None:
            comb_depth += line.count("begin") - line.count("end")
            if comb_depth <= 0 and index > comb_start:
                length = index - comb_start + 1
                if length > comb_warn_threshold:
                    issues.append(issue(path, comb_start, "warn", "LARGE_COMB_BLOCK", f"Combinational block is {length} lines; check critical path and latch risk."))
                comb_start = None

        if "PREADY" in line and re.search(r"\bassign\s+PREADY\s*=.*\bPREADY\b", line):
            issues.append(issue(path, index, "warn", "PREADY_SELF_REFERENCE", "PREADY assignment appears self-referential."))

    for item in case_stack:
        issues.append(issue(path, int(item["line"]), "warn", "UNCLOSED_CASE", "Case statement did not close before end of file."))

    return issues


def build_result(paths: list[Path], *, comb_warn_threshold: int, strict: bool) -> dict[str, Any]:
    all_issues: list[dict[str, Any]] = []
    scanned: list[str] = []
    for path in paths:
        if not path.exists():
            all_issues.append(issue(path, 0, "fail", "FILE_MISSING", "RTL file does not exist."))
            continue
        scanned.append(str(path))
        all_issues.extend(scan_file(path, comb_warn_threshold=comb_warn_threshold))

    has_fail = any(item["severity"] == "fail" for item in all_issues)
    has_warn = any(item["severity"] == "warn" for item in all_issues)
    status = "fail" if has_fail or (strict and has_warn) else "warn" if has_warn else "pass"
    return {
        "schema_version": "oag_ppa_check.v1",
        "status": status,
        "dialect": "oag_sv_lite_v1",
        "scanned_files": scanned,
        "counts": {
            "issues": len(all_issues),
            "fail": sum(1 for item in all_issues if item["severity"] == "fail"),
            "warn": sum(1 for item in all_issues if item["severity"] == "warn"),
        },
        "issues": all_issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight OAG PPA/dialect checks on RTL files.")
    parser.add_argument("paths", nargs="+", help="RTL files to scan.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--comb-warn-threshold", type=int, default=80, help="Warn on combinational blocks longer than this many lines.")
    args = parser.parse_args(argv)

    result = build_result([Path(item) for item in args.paths], comb_warn_threshold=args.comb_warn_threshold, strict=args.strict)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS oag ppa check")
    else:
        print(f"{result['status'].upper()} oag ppa check", file=sys.stderr)
        for item in result["issues"]:
            print(f"- {item['severity']} {item['code']} {item['path']}:{item['line']}: {item['message']}", file=sys.stderr)
    return 0 if result["status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
