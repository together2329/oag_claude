#!/usr/bin/env python3
"""Verify an OAG baseline manifest and optional git tag anchoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from oag_baseline_check import check_manifest, read_document  # pylint: disable=wrong-import-position


MANIFEST_SHA_RE = re.compile(r"manifest_sha256:\s*(sha256:[0-9a-fA-F]{64})")


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def git_root(path: Path) -> tuple[Path | None, list[dict[str, str]]]:
    probe = run_git(path, ["rev-parse", "--show-toplevel"])
    if probe.returncode != 0:
        return None, [issue("BASELINE_VERIFY_GIT_ROOT", "Manifest is not inside a git repository.", probe.stderr.strip())]
    return Path(probe.stdout.strip()), []


def manifest_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_git_tag(manifest_path: Path, payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    root, root_issues = git_root(manifest_path.parent)
    issues.extend(root_issues)
    if root is None:
        return issues

    git_info = payload.get("git") if isinstance(payload.get("git"), dict) else {}
    tag = str(git_info.get("tag") or "").strip()
    if not tag:
        return [issue("BASELINE_VERIFY_TAG_MISSING", "Manifest git.tag is required for --verify-git-tag.")]

    tag_type = run_git(root, ["cat-file", "-t", tag])
    if tag_type.returncode != 0:
        issues.append(issue("BASELINE_VERIFY_TAG_MISSING", f"Git tag does not exist: {tag}", tag_type.stderr.strip()))
        return issues
    if tag_type.stdout.strip() != "tag":
        issues.append(issue("BASELINE_VERIFY_TAG_ANNOTATED", "Git tag must be annotated, not lightweight.", tag))

    commit = run_git(root, ["rev-list", "-n", "1", tag])
    if commit.returncode != 0 or not commit.stdout.strip():
        issues.append(issue("BASELINE_VERIFY_TAG_COMMIT", f"Cannot resolve tag commit for {tag}.", commit.stderr.strip()))
        return issues

    try:
        rel = manifest_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        issues.append(issue("BASELINE_VERIFY_MANIFEST_PATH", "Manifest path is not under the git repository.", str(manifest_path)))
        return issues

    show = run_git(root, ["show", f"{commit.stdout.strip()}:{rel}"])
    if show.returncode != 0:
        issues.append(issue("BASELINE_VERIFY_MANIFEST_AT_TAG", "Manifest file is not present in the tag commit tree.", rel))
    else:
        tree_bytes = show.stdout.encode("utf-8")
        current_bytes = manifest_path.read_bytes()
        if tree_bytes != current_bytes:
            issues.append(issue("BASELINE_VERIFY_MANIFEST_TREE_MISMATCH", "Current manifest bytes differ from the manifest stored in the tag commit.", rel))

    tag_contents = run_git(root, ["tag", "-l", tag, "--format=%(contents)"])
    if tag_contents.returncode == 0:
        match = MANIFEST_SHA_RE.search(tag_contents.stdout)
        if match:
            expected = match.group(1).lower()
            actual = manifest_sha(manifest_path).lower()
            if expected != actual:
                issues.append(issue("BASELINE_VERIFY_TAG_MANIFEST_HASH", "Annotated tag manifest_sha256 does not match current manifest bytes.", tag))
    return issues


def verify(manifest_path: Path, *, ip_dir: Path | None = None, verify_git: bool = False) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    baseline = check_manifest(manifest_path, ip_dir=ip_dir)
    issues = list(baseline.get("issues", []))
    payload, load_issues = read_document(manifest_path)
    issues.extend(load_issues)
    if payload is None:
        payload = {}
    if verify_git and payload:
        issues.extend(verify_git_tag(manifest_path, payload))
    return {
        "schema_version": "oag_baseline_verify.v1",
        "status": "fail" if issues else "pass",
        "manifest": str(manifest_path),
        "ip_dir": baseline.get("ip_dir") or (str(ip_dir) if ip_dir else ""),
        "baseline_id": baseline.get("baseline_id") or payload.get("baseline_id"),
        "verify_git_tag": verify_git,
        "counts": {"issues": len(issues)},
        "issues": issues,
        "next_actions": ["Repair baseline manifest/tag anchoring before publishing baseline."] if issues else ["Baseline manifest verification passed."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--ip-dir")
    parser.add_argument("--verify-git-tag", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = verify(Path(args.manifest), ip_dir=Path(args.ip_dir) if args.ip_dir else None, verify_git=args.verify_git_tag)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS OAG baseline verify")
    else:
        print("FAIL OAG baseline verify", file=sys.stderr)
        for item in result["issues"]:
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
