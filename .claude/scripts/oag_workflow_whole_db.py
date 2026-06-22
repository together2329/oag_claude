#!/usr/bin/env python3
"""Build a single Markdown review bundle for the .claude workflow pack."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODEX_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODEX_ROOT.parent
DEFAULT_OUT = PROJECT_ROOT / "oag_workflow_whole_db.md"

TRANSIENT_PARTS = {
    ".cache",
    ".tmp",
    "tmp",
    "runs",
    "sessions",
    "shell_snapshots",
    "__pycache__",
}

LANG_BY_SUFFIX = {
    ".base": "yaml",
    ".cfg": "ini",
    ".json": "json",
    ".jsonl": "json",
    ".md": "markdown",
    ".py": "python",
    ".sh": "bash",
    ".sv": "systemverilog",
    ".toml": "toml",
    ".txt": "text",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def safe_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def should_skip(path: Path, source: Path, output: Path, *, exclude_transient: bool) -> bool:
    if not path.is_file():
        return True
    try:
        if path.resolve() == output.resolve():
            return True
    except FileNotFoundError:
        pass
    rel_parts = path.relative_to(source).parts
    if exclude_transient and any(part in TRANSIENT_PARTS for part in rel_parts):
        return True
    if path.name.endswith((".pyc", ".pyo")):
        return True
    return False


def discover_files(source: Path, output: Path, *, exclude_transient: bool) -> list[Path]:
    return sorted(
        (
            path
            for path in source.rglob("*")
            if not should_skip(path, source, output, exclude_transient=exclude_transient)
        ),
        key=lambda item: item.relative_to(source).as_posix(),
    )


def longest_backtick_run(text: str) -> int:
    longest = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def fence_for(text: str) -> str:
    return "`" * max(3, longest_backtick_run(text) + 1)


def decode_payload(data: bytes) -> tuple[str, bool]:
    if b"\x00" in data:
        return base64.b64encode(data).decode("ascii"), True
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        return base64.b64encode(data).decode("ascii"), True


def language_for(path: Path, binary: bool) -> str:
    if binary:
        return "text"
    return LANG_BY_SUFFIX.get(path.suffix.lower(), "text")


def file_record(path: Path, source: Path) -> dict[str, Any]:
    data = path.read_bytes()
    text, binary = decode_payload(data)
    rel = safe_rel(path, source)
    return {
        "path": rel,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "line_count": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        "binary_encoded": binary,
        "language": language_for(path, binary),
        "content": text,
    }


def write_bundle(
    output: Path,
    source: Path,
    records: list[dict[str, Any]],
    *,
    exclude_transient: bool,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = sum(int(item["bytes"]) for item in records)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "schema_version": "oag_workflow_whole_db.v1",
        "generated_at": generated_at,
        "git_head": git_head(PROJECT_ROOT),
        "source": safe_rel(source, PROJECT_ROOT),
        "output": safe_rel(output, PROJECT_ROOT),
        "file_count": len(records),
        "total_bytes": total_bytes,
        "exclude_transient": exclude_transient,
    }
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# OAG Workflow Whole DB\n\n")
        handle.write("Generated review bundle for the `.claude` workflow pack.\n\n")
        handle.write("```json\n")
        handle.write(json.dumps(manifest, indent=2, sort_keys=True))
        handle.write("\n```\n\n")
        handle.write("## File Index\n\n")
        handle.write("| # | Path | Bytes | Lines | SHA-256 |\n")
        handle.write("|---:|---|---:|---:|---|\n")
        for index, record in enumerate(records, start=1):
            handle.write(
                f"| {index} | `{record['path']}` | {record['bytes']} | "
                f"{record['line_count']} | `{record['sha256']}` |\n"
            )
        handle.write("\n")
        for index, record in enumerate(records, start=1):
            content = str(record["content"])
            fence = fence_for(content)
            handle.write(f"## {index}. `{record['path']}`\n\n")
            handle.write(f"- bytes: `{record['bytes']}`\n")
            handle.write(f"- lines: `{record['line_count']}`\n")
            handle.write(f"- sha256: `{record['sha256']}`\n")
            handle.write(f"- binary_encoded: `{str(record['binary_encoded']).lower()}`\n\n")
            if record["binary_encoded"]:
                handle.write("Content is base64 encoded because the source was not UTF-8 text.\n\n")
            handle.write(f"{fence}{record['language']}\n")
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
            handle.write(f"{fence}\n\n")


def build_summary(output: Path, source: Path, records: list[dict[str, Any]], exclude_transient: bool) -> dict[str, Any]:
    return {
        "schema_version": "oag_workflow_whole_db_result.v1",
        "status": "pass",
        "source": safe_rel(source, PROJECT_ROOT),
        "output": safe_rel(output, PROJECT_ROOT),
        "file_count": len(records),
        "total_bytes": sum(int(item["bytes"]) for item in records),
        "exclude_transient": exclude_transient,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bundle .claude files into one Markdown review file.")
    parser.add_argument("--source", default=str(CODEX_ROOT), help="Source directory to bundle. Defaults to .claude.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output Markdown path. Defaults to oag_workflow_whole_db.md.")
    parser.add_argument(
        "--exclude-transient",
        action="store_true",
        help="Exclude transient cache/run/session directories. Default includes all .claude regular files.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if not source.is_dir():
        print(f"source directory not found: {source}", file=sys.stderr)
        return 2
    records = [file_record(path, source) for path in discover_files(source, output, exclude_transient=args.exclude_transient)]
    write_bundle(output, source, records, exclude_transient=args.exclude_transient)
    summary = build_summary(output, source, records, args.exclude_transient)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"wrote {summary['output']} ({summary['file_count']} files, {summary['total_bytes']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
