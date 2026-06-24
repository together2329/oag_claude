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
    ("ALWAYS_LATCH", r"\balways_latch\b"),
    ("TYPEDEF", r"\btypedef\b"),
    ("ENUM", r"\benum\b"),
    ("STRUCT", r"\bstruct\b"),
    ("INTERFACE", r"\binterface\b"),
    ("MODPORT", r"\bmodport\b"),
    ("PACKAGE", r"\bpackage\b"),
    ("IMPORT", r"\bimport\b"),
    ("FUNCTION", r"\bfunction\b"),
    ("TASK", r"\btask\b"),
    ("CLASS", r"\bclass\b"),
    ("PROGRAM", r"\bprogram\b"),
    ("CLOCKING", r"\bclocking\b"),
    ("BIND", r"\bbind\b"),
    ("RANDOMIZE", r"\brandomize\s*\("),
    ("CONSTRAINT", r"\bconstraint\b"),
    ("DPI", r"\bimport\s+[\"']DPI"),
    ("UNIQUE_PRIORITY", r"\b(unique|priority)\s+(case|if)\b"),
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


def strip_sv_comments(text: str) -> str:
    def replace_block(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    text = re.sub(r"/\*.*?\*/", replace_block, text, flags=re.DOTALL)
    return re.sub(r"//.*", "", text)


def outside_generate_blocks(text: str) -> str:
    clean = strip_sv_comments(text)
    spans: list[tuple[int, int]] = []
    depth = 0
    start: int | None = None
    for match in re.finditer(r"\b(generate|endgenerate)\b", clean):
        token = match.group(1)
        if token == "generate":
            if depth == 0:
                start = match.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, match.end()))
                start = None
    if depth and start is not None:
        spans.append((start, len(clean)))
    if not spans:
        return clean
    pieces: list[str] = []
    cursor = 0
    for begin, end in spans:
        pieces.append(clean[cursor:begin])
        pieces.append("\n" * clean[begin:end].count("\n"))
        cursor = end
    pieces.append(clean[cursor:])
    return "".join(pieces)


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_file(path: Path, *, comb_warn_threshold: int) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    clean_text = strip_sv_comments(text)
    outside_generate = outside_generate_blocks(text)
    lines = clean_text.splitlines()
    issues: list[dict[str, Any]] = []

    case_stack: list[dict[str, Any]] = []
    comb_start: int | None = None
    comb_depth = 0

    for code, pattern in FORBIDDEN_PATTERNS:
        for match in re.finditer(pattern, clean_text):
            issues.append(issue(path, line_for_offset(clean_text, match.start()), "fail", code, "Construct is outside the default OAG SV-lite RTL dialect."))

    for match in re.finditer(r"\b(for|while|repeat|forever)\s*(\(|\b)", outside_generate):
        issues.append(issue(path, line_for_offset(outside_generate, match.start()), "fail", "PROCEDURAL_LOOP", "Procedural loops outside generate are forbidden by default."))

    for index, line in enumerate(lines, start=1):
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


def rel_to(base: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        return str(path)


def resolve_filelist_entry(entry: str, *, ip_dir: Path, cwd: Path) -> Path | None:
    raw = entry.strip()
    if not raw or raw.startswith("#") or raw.startswith("//"):
        return None
    raw = raw.split("//", 1)[0].strip()
    if not raw or raw.startswith(("+", "-")):
        return None
    path = Path(raw)
    candidates = [path] if path.is_absolute() else [ip_dir / path, cwd / path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def paths_from_ip_dir(ip_dir: Path, *, cwd: Path) -> list[Path]:
    paths: list[Path] = []
    filelist = ip_dir / "list" / "rtl.f"
    if filelist.is_file():
        for line in filelist.read_text(encoding="utf-8", errors="ignore").splitlines():
            resolved = resolve_filelist_entry(line, ip_dir=ip_dir, cwd=cwd)
            if resolved and resolved.suffix in {".v", ".sv", ".vh", ".svh"}:
                paths.append(resolved)
    rtl_dir = ip_dir / "rtl"
    if rtl_dir.is_dir():
        paths.extend(sorted(path.resolve() for path in rtl_dir.glob("*.v")))
        paths.extend(sorted(path.resolve() for path in rtl_dir.glob("*.sv")))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


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
    parser.add_argument("paths", nargs="*", help="RTL files to scan.")
    parser.add_argument("--ip-dir", help="IP directory; scans list/rtl.f and rtl/*.sv/*.v.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--comb-warn-threshold", type=int, default=80, help="Warn on combinational blocks longer than this many lines.")
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    paths = [Path(item) for item in args.paths]
    if args.ip_dir:
        ip_dir = Path(args.ip_dir).resolve()
        paths.extend(paths_from_ip_dir(ip_dir, cwd=cwd))
    if not paths:
        parser.error("provide RTL paths or --ip-dir")

    result = build_result(paths, comb_warn_threshold=args.comb_warn_threshold, strict=args.strict)
    if args.ip_dir:
        ip_dir = Path(args.ip_dir).resolve()
        result["ip_dir"] = str(ip_dir)
        result["scanned_files"] = [rel_to(ip_dir, Path(item)) for item in result["scanned_files"]]
        for item in result["issues"]:
            item["path"] = rel_to(ip_dir, Path(str(item["path"])))
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
