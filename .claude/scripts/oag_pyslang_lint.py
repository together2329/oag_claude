#!/usr/bin/env python3
"""Run optional pyslang syntax lint and write OAG lint evidence."""

from __future__ import annotations

import argparse
import glob
import json
import shlex
import sys
from pathlib import Path
from typing import Any


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def resolve_filelist_ref(ip: Path, base: Path, token: str) -> Path:
    candidate = Path(token)
    if candidate.is_absolute():
        return candidate
    base_candidate = base / candidate
    if base_candidate.exists():
        return base_candidate
    return ip / candidate


def parse_filelist(ip: Path, filelist: Path, seen: set[Path] | None = None) -> tuple[list[Path], list[str], list[str]]:
    seen = seen or set()
    filelist = filelist if filelist.is_absolute() else ip / filelist
    filelist = filelist.resolve()
    if filelist in seen:
        return [], [], []
    seen.add(filelist)
    files: list[Path] = []
    incdirs: list[str] = []
    warnings: list[str] = []
    if not filelist.is_file():
        return [], [], [f"missing filelist: {rel(filelist, ip)}"]
    base = filelist.parent
    for raw in filelist.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.split("//", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            tokens = line.split()
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token == "-f" and index + 1 < len(tokens):
                nested = resolve_filelist_ref(ip, base, tokens[index + 1])
                nested_files, nested_incdirs, nested_warnings = parse_filelist(ip, nested, seen)
                files.extend(nested_files)
                incdirs.extend(nested_incdirs)
                warnings.extend(nested_warnings)
                index += 2
                continue
            if token.startswith("-f") and len(token) > 2:
                nested = resolve_filelist_ref(ip, base, token[2:])
                nested_files, nested_incdirs, nested_warnings = parse_filelist(ip, nested, seen)
                files.extend(nested_files)
                incdirs.extend(nested_incdirs)
                warnings.extend(nested_warnings)
            elif token.startswith("+incdir+"):
                incdirs.extend(part for part in token[len("+incdir+") :].split("+") if part)
            elif token.startswith("-") or token.startswith("+"):
                pass
            else:
                pattern = Path(token)
                if not pattern.is_absolute():
                    pattern = base / pattern
                    if not glob.glob(str(pattern)):
                        pattern = ip / token
                matches = [Path(item).resolve() for item in glob.glob(str(pattern))]
                if matches:
                    files.extend(matches)
                else:
                    warnings.append(f"unmatched filelist entry: {token}")
            index += 1
    unique: list[Path] = []
    seen_files: set[Path] = set()
    for path in files:
        if path not in seen_files:
            unique.append(path)
            seen_files.add(path)
    return unique, sorted(set(incdirs)), warnings


def build_result(ip: Path, filelist: Path, *, allow_missing: bool) -> dict[str, Any]:
    files, incdirs, warnings = parse_filelist(ip, filelist)
    try:
        import pyslang  # type: ignore
    except Exception as exc:
        status = "skipped" if allow_missing else "fail"
        return {
            "schema_version": "oag_pyslang_lint.v1",
            "status": status,
            "tool": "pyslang",
            "available": False,
            "reason": f"pyslang unavailable: {exc}",
            "files": [rel(path, ip) for path in files],
            "include_dirs": incdirs,
            "warnings": warnings,
            "diagnostics": [],
            "counts": {"files": len(files), "diagnostics": 0},
        }

    diagnostics: list[dict[str, str]] = []
    for path in files:
        if not path.is_file():
            diagnostics.append({"path": rel(path, ip), "message": "RTL file missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = pyslang.SyntaxTree.fromText(text)
            for item in getattr(tree, "diagnostics", []):
                diagnostics.append({"path": rel(path, ip), "message": str(item)})
        except Exception as exc:
            diagnostics.append({"path": rel(path, ip), "message": f"pyslang parse failed: {exc}"})
    status = "fail" if diagnostics else "pass"
    return {
        "schema_version": "oag_pyslang_lint.v1",
        "status": status,
        "tool": "pyslang",
        "available": True,
        "files": [rel(path, ip) for path in files],
        "include_dirs": incdirs,
        "warnings": warnings,
        "diagnostics": diagnostics,
        "counts": {"files": len(files), "diagnostics": len(diagnostics)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", type=Path, default=Path.cwd())
    parser.add_argument("--filelist", type=Path, default=Path("list/lint.f"))
    parser.add_argument("--out", type=Path, default=Path("lint/dut_lint.json"))
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ip = args.ip_dir.resolve()
    result = build_result(ip, args.filelist, allow_missing=args.allow_missing)
    out = args.out if args.out.is_absolute() else ip / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} pyslang lint -> {rel(out, ip)}")
    return 0 if result["status"] in {"pass", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
