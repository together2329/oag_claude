#!/usr/bin/env python3
"""Create an OAG baseline manifest with raw-byte hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import oag_paths  # noqa: E402


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def rel_path(raw: str, ip_dir: Path) -> Path | None:
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        return None
    return ip_dir / raw


def file_hash(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {
        "content_sha256": f"sha256:{digest.hexdigest()}",
        "hash_mode": "raw_bytes",
        "size_bytes": size,
    }


def parse_tracked(entries: list[str]) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    tracked: dict[str, list[str]] = {}
    issues: list[dict[str, str]] = []
    for raw in entries:
        if ":" not in raw:
            issues.append(issue("BASELINE_CUT_TRACKED_ARTIFACT", "Use --tracked-artifact group:relative/path.", raw))
            continue
        group, rel = raw.split(":", 1)
        group = group.strip()
        rel = rel.strip()
        if not group or not rel:
            issues.append(issue("BASELINE_CUT_TRACKED_ARTIFACT", "Tracked artifact group and path are required.", raw))
            continue
        tracked.setdefault(group, []).append(rel)
    return tracked, issues


def git_dirty(ip_dir: Path) -> tuple[bool, str]:
    probe = subprocess.run(
        ["git", "-C", str(ip_dir), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return False, ""
    root = Path(probe.stdout.strip())
    try:
        rel = ip_dir.resolve().relative_to(root.resolve())
    except ValueError:
        rel = ip_dir.resolve()
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--", str(rel)],
        text=True,
        capture_output=True,
        check=False,
    )
    dirty = status.stdout.strip()
    return bool(dirty), dirty


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix in {".yaml", ".yml"}:
        import yaml  # type: ignore

        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_manifest(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = Path(args.ip_dir).resolve()
    issues: list[dict[str, str]] = []

    if not args.allow_dirty:
        dirty, status = git_dirty(ip_dir)
        if dirty:
            issues.append(issue("BASELINE_CUT_DIRTY_TREE", "Refusing to cut baseline from a dirty IP tree; use --allow-dirty for draft generation.", status))

    tracked, tracked_issues = parse_tracked(args.tracked_artifact or [])
    issues.extend(tracked_issues)
    if not tracked:
        issues.append(issue("BASELINE_CUT_TRACKED_ARTIFACTS", "At least one --tracked-artifact group:path entry is required."))

    hashes: dict[str, dict[str, Any]] = {}
    for rels in tracked.values():
        for rel in rels:
            path = rel_path(rel, ip_dir)
            if path is None:
                issues.append(issue("BASELINE_CUT_TRACKED_PATH", "Tracked artifact path must be relative and stay under the IP directory.", rel))
                continue
            if not path.is_file():
                issues.append(issue("BASELINE_CUT_TRACKED_MISSING", "Tracked artifact file is missing.", rel))
                continue
            hashes[rel] = file_hash(path)

    tag = args.tag or ""
    payload = {
        "schema_version": "oag_baseline_manifest.v1",
        "baseline_id": args.baseline_id,
        "ip": args.ip or ip_dir.name,
        "baseline": {
            "class": args.baseline_class,
            "version": args.version,
            "state": args.baseline_state,
            "supersedes": args.supersedes,
        },
        "approval": {
            "state": args.approval_state,
            "approval_ref": args.approval_ref,
        },
        "git": {
            "tag": tag,
            "commit": "resolved_by_tag" if tag else "",
            "tag_type": "annotated" if tag else "",
        },
        "tracked_artifacts": tracked,
        "external_artifacts": [],
        "hashes": hashes,
        "environment": {
            "commands": {
                "baseline_check": "python3 .claude/scripts/oag_baseline_check.py --manifest <manifest> --json",
            }
        },
        "gate": {
            "gate_ref": args.gate_ref,
            "validation_ref": args.validation_ref,
            "decision": args.gate_decision,
        },
    }

    output = Path(args.output).resolve() if args.output else oag_paths.ontology_path(ip_dir, Path("baselines") / f"{args.baseline_id}.yaml")
    if issues:
        return {
            "schema_version": "oag_baseline_cut.v1",
            "status": "fail",
            "ip_dir": str(ip_dir),
            "manifest": str(output),
            "counts": {"tracked_artifacts": sum(len(v) for v in tracked.values()), "issues": len(issues)},
            "issues": issues,
            "next_actions": ["Clean the IP tree, provide tracked artifacts, and rerun baseline cut."],
        }

    write_manifest(output, payload)
    return {
        "schema_version": "oag_baseline_cut.v1",
        "status": "pass",
        "ip_dir": str(ip_dir),
        "manifest": str(output),
        "baseline_id": args.baseline_id,
        "counts": {"tracked_artifacts": sum(len(v) for v in tracked.values()), "issues": 0},
        "issues": [],
        "next_actions": [
            f"Run python3 .claude/scripts/oag_baseline_check.py --manifest {output} --json.",
            "Create an annotated git tag only after the manifest is committed and verified.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--ip", default="")
    parser.add_argument("--version", required=True)
    parser.add_argument("--baseline-class", default="candidate", choices=["candidate", "golden", "release", "archived"])
    parser.add_argument("--baseline-state", default="draft", choices=["draft", "active", "superseded", "revoked"])
    parser.add_argument("--supersedes")
    parser.add_argument("--approval-state", default="reviewed", choices=["none", "reviewed", "approved", "rejected"])
    parser.add_argument("--approval-ref", required=True)
    parser.add_argument("--gate-ref", required=True)
    parser.add_argument("--validation-ref", required=True)
    parser.add_argument("--gate-decision", default="pass", choices=["pass", "fail", "blocked", "waived"])
    parser.add_argument("--tag", default="")
    parser.add_argument("--tracked-artifact", action="append", default=[], help="Tracked artifact as group:relative/path.")
    parser.add_argument("--output")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow draft manifest generation from a dirty git tree.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = create_manifest(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print(f"PASS OAG baseline cut: {result['manifest']}")
    else:
        print("FAIL OAG baseline cut", file=sys.stderr)
        for item in result["issues"]:
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
