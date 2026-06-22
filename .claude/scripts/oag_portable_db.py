#!/usr/bin/env python3
"""Export, inspect, and import portable OAG DB snapshots.

The package format is intentionally platform-neutral. Claude Code, Cursor, CI, or a
future OAG UI should all be able to carry the same durable OAG state forward by
moving this package between workspaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = "oag_portable_db.v1"
MANIFEST_NAME = "OAG_MANIFEST.json"

DEFAULT_IP_DIRS = [
    "req",
    "ontology",
    "knowledge",
    "handoff",
    "signoff",
    "doc",
]

ARTIFACT_DIRS = [
    "cov",
    "formal",
    "lint",
    "regress",
]

ARTIFACT_FILES = [
    "rtl/rtl_compile.json",
    "sim/results.xml",
    "sim/scoreboard_events.jsonl",
    "sim/protocol_monitor_results.json",
    "sim/run.log",
    "sim/verilator_build.log",
]

SOURCE_DIRS = [
    "rtl",
    "tb",
    "list",
    "sdc",
    "scripts",
]

COMMON_PATHS = [
    ".claude/AGENTS.md",
    ".claude/agents",
    ".claude/rules",
    ".claude/skills/oag-ip-workflow",
    ".cursor/README.md",
    ".cursor/mcp.json",
    ".cursor/rules",
    ".cursor/scripts",
]

SKIP_NAMES = {
    ".DS_Store",
    ".pytest_cache",
    "__pycache__",
    "obj_dir",
}

SKIP_SUFFIXES = {
    ".pyc",
    ".vcd",
    ".fst",
    ".o",
    ".a",
    ".so",
    ".dylib",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _git_info(root: Path) -> dict[str, Any]:
    status = _git(root, "status", "--porcelain=v1")
    return {
        "root": _git(root, "rev-parse", "--show-toplevel") or str(root),
        "head": _git(root, "rev-parse", "HEAD"),
        "branch": _git(root, "branch", "--show-current"),
        "dirty": bool(status),
        "status_porcelain": status.splitlines(),
    }


def _safe_rel(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    rel_posix = rel.as_posix()
    parts = PurePosixPath(rel_posix).parts
    if not rel_posix or rel_posix.startswith("/") or ".." in parts:
        raise ValueError(f"unsafe relative path: {rel_posix}")
    return rel_posix


def _is_skipped(path: Path) -> bool:
    if any(part in SKIP_NAMES for part in path.parts):
        return True
    return path.suffix in SKIP_SUFFIXES


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file() and not _is_skipped(path):
        yield path
        return
    if not path.is_dir():
        return
    for child in sorted(path.rglob("*")):
        if child.is_file() and not _is_skipped(child):
            yield child


def _discover_ips(root: Path) -> list[str]:
    ips: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "ontology" / "ip.yaml").is_file() or (child / "knowledge" / "_index.json").is_file():
            ips.append(child.name)
    return ips


def _collect_paths(
    root: Path,
    *,
    ips: list[str],
    include_common: bool,
    include_source: bool,
    include_artifacts: bool,
) -> list[Path]:
    paths: list[Path] = []
    for ip in ips:
        ip_root = root / ip
        if not ip_root.is_dir():
            raise FileNotFoundError(f"IP directory not found: {ip}")
        for rel in DEFAULT_IP_DIRS:
            paths.extend(_iter_files(ip_root / rel))
        if include_artifacts:
            for rel in ARTIFACT_DIRS:
                paths.extend(_iter_files(ip_root / rel))
            for rel in ARTIFACT_FILES:
                paths.extend(_iter_files(ip_root / rel))
            mutation = ip_root / "mutation"
            if mutation.is_dir():
                for child in sorted(mutation.rglob("*")):
                    if child.is_file() and child.suffix in {".json", ".jsonl", ".csv"} and not _is_skipped(child):
                        paths.append(child)
        if include_source:
            for rel in SOURCE_DIRS:
                paths.extend(_iter_files(ip_root / rel))
    if include_common:
        for rel in COMMON_PATHS:
            paths.extend(_iter_files(root / rel))
    unique: dict[str, Path] = {}
    for path in paths:
        unique[_safe_rel(path, root)] = path
    return [unique[key] for key in sorted(unique)]


def _manifest(
    root: Path,
    *,
    ips: list[str],
    files: list[Path],
    include_common: bool,
    include_source: bool,
    include_artifacts: bool,
) -> dict[str, Any]:
    entries = []
    for path in files:
        entries.append(
            {
                "path": _safe_rel(path, root),
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "project": {
            "root": str(root),
            "git": _git_info(root),
        },
        "selection": {
            "ips": ips,
            "include_common": include_common,
            "include_source": include_source,
            "include_artifacts": include_artifacts,
        },
        "files": entries,
        "file_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
    }


def cmd_export(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ips = args.ip or _discover_ips(root)
    if not ips:
        raise SystemExit("no IP directories found; pass --ip <name>")
    files = _collect_paths(
        root,
        ips=ips,
        include_common=args.include_common,
        include_source=args.include_source,
        include_artifacts=not args.no_artifacts,
    )
    manifest = _manifest(
        root,
        ips=ips,
        files=files,
        include_common=args.include_common,
        include_source=args.include_source,
        include_artifacts=not args.no_artifacts,
    )
    out = Path(args.out).resolve() if args.out else root / ".oag" / "exports" / f"oag_portable_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=out.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with tarfile.open(tmp_path, "w:gz") as tar:
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            info = tarfile.TarInfo(MANIFEST_NAME)
            info.size = len(manifest_bytes)
            info.mtime = int(datetime.now(timezone.utc).timestamp())
            with tempfile.NamedTemporaryFile(delete=False) as mf:
                mf.write(manifest_bytes)
                mf_path = Path(mf.name)
            try:
                tar.add(mf_path, arcname=MANIFEST_NAME, recursive=False)
            finally:
                mf_path.unlink(missing_ok=True)
            for path in files:
                rel = _safe_rel(path, root)
                tar.add(path, arcname=f"files/{rel}", recursive=False)
        tmp_path.replace(out)
    finally:
        tmp_path.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "status": "pass",
                "archive": str(out),
                "ips": ips,
                "file_count": manifest["file_count"],
                "total_bytes": manifest["total_bytes"],
                "git_head": manifest["project"]["git"]["head"],
                "git_dirty": manifest["project"]["git"]["dirty"],
            },
            indent=2,
        )
    )
    return 0


def _read_manifest(archive: Path) -> dict[str, Any]:
    with tarfile.open(archive, "r:gz") as tar:
        member = tar.getmember(MANIFEST_NAME)
        fh = tar.extractfile(member)
        if fh is None:
            raise ValueError(f"{MANIFEST_NAME} has no content")
        manifest = json.loads(fh.read().decode("utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {manifest.get('schema_version')}")
    return manifest


def cmd_inspect(args: argparse.Namespace) -> int:
    manifest = _read_manifest(Path(args.archive))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def _safe_out_path(dest: Path, rel: str) -> Path:
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe package path: {rel}")
    out = (dest / Path(*pure.parts)).resolve()
    out.relative_to(dest.resolve())
    return out


def cmd_import(args: argparse.Namespace) -> int:
    archive = Path(args.archive).resolve()
    dest = Path(args.dest).resolve()
    manifest = _read_manifest(archive)
    selected_ips = set(args.ip or manifest["selection"]["ips"])
    changed = 0
    skipped = 0
    conflicts: list[str] = []
    imported_paths: list[str] = []
    with tarfile.open(archive, "r:gz") as tar:
        for entry in manifest["files"]:
            rel = str(entry["path"])
            first = PurePosixPath(rel).parts[0] if PurePosixPath(rel).parts else ""
            if first and first not in selected_ips and not rel.startswith(".claude/") and not rel.startswith(".cursor/"):
                continue
            out = _safe_out_path(dest, rel)
            member_name = f"files/{rel}"
            member = tar.getmember(member_name)
            fh = tar.extractfile(member)
            if fh is None:
                raise ValueError(f"missing package member content: {member_name}")
            data = fh.read()
            actual_hash = hashlib.sha256(data).hexdigest()
            if actual_hash != entry["sha256"]:
                raise ValueError(f"package hash mismatch: {rel}")
            if out.exists():
                existing_hash = _sha256(out)
                if existing_hash == entry["sha256"]:
                    skipped += 1
                    continue
                if not args.force:
                    conflicts.append(rel)
                    continue
            if args.dry_run:
                changed += 1
                imported_paths.append(rel)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            changed += 1
            imported_paths.append(rel)
    if conflicts:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "conflicting_existing_files",
                    "conflicts": conflicts,
                    "changed": changed,
                    "skipped": skipped,
                },
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "pass",
                "archive": str(archive),
                "dest": str(dest),
                "dry_run": args.dry_run,
                "selected_ips": sorted(selected_ips),
                "changed": changed,
                "skipped": skipped,
                "imported_paths": imported_paths[:50],
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="write a portable OAG DB archive")
    export.add_argument("--root", default=".", help="project root")
    export.add_argument("--ip", action="append", help="IP directory to export; repeatable")
    export.add_argument("--out", help="output .tar.gz path")
    export.add_argument("--include-common", action="store_true", help="include common OAG rules/adapters")
    export.add_argument("--include-source", action="store_true", help="include RTL/TB/list/SDC/scripts source directories")
    export.add_argument("--no-artifacts", action="store_true", help="exclude compact stage/evidence artifacts")
    export.set_defaults(func=cmd_export)

    inspect = sub.add_parser("inspect", help="print the portable DB manifest")
    inspect.add_argument("archive")
    inspect.set_defaults(func=cmd_inspect)

    import_p = sub.add_parser("import", help="import a portable OAG DB archive")
    import_p.add_argument("archive")
    import_p.add_argument("--dest", default=".", help="destination project root")
    import_p.add_argument("--ip", action="append", help="IP directory to import; repeatable")
    import_p.add_argument("--force", action="store_true", help="overwrite conflicting existing files")
    import_p.add_argument("--dry-run", action="store_true", help="report changes without writing files")
    import_p.set_defaults(func=cmd_import)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
