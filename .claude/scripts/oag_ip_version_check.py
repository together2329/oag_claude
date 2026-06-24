#!/usr/bin/env python3
"""Validate OAG IP-local functional version and baseline ledger state."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
CODEX_ROOT = SCRIPTS_DIR.parent
SCHEMAS_DIR = CODEX_ROOT / "schemas"
VERSION_LEDGER = Path("ontology/ip_version.yaml")

sys.path.insert(0, str(SCRIPTS_DIR))
from oag_validate_json import validate_document  # pylint: disable=wrong-import-position
import oag_paths  # noqa: E402


SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
GOLDEN_CLASSES = {"golden", "release"}


def issue(code: str, message: str, path: str = "") -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def read_document(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    try:
        if path.suffix in {".yaml", ".yml"}:
            import yaml  # type: ignore

            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exercised through smoke failure output
        return None, [issue("IP_VERSION_LOAD_ERROR", f"Cannot read IP version ledger: {exc}", str(path))]
    if not isinstance(payload, dict):
        return None, [issue("IP_VERSION_SHAPE", "IP version ledger must be an object.", str(path))]
    return payload, []


def load_schema() -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / "oag_ip_version.schema.json").read_text(encoding="utf-8"))


def schema_issues(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        issue("IP_VERSION_SCHEMA", f"{item.get('code')}: {item.get('message')}", str(item.get("path") or ""))
        for item in validate_document(load_schema(), payload)
    ]


def parse_semver(raw: Any) -> tuple[int, int, int] | None:
    match = SEMVER_RE.match(str(raw or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def rel_path(raw: str, ip_dir: Path) -> Path | None:
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        return None
    return ip_dir / raw


def git_dir_exists(ip_dir: Path) -> bool:
    git_path = ip_dir / ".git"
    return git_path.exists()


def git_tag_type(ip_dir: Path, tag: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(ip_dir), "cat-file", "-t", tag],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def check_version_sequence(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    previous: tuple[int, int, int] | None = None
    for index, entry in enumerate(entries):
        version = str(entry.get("version") or "")
        parsed = parse_semver(version)
        if parsed is None:
            issues.append(issue("IP_VERSION_SEMVER", "Version must use MAJOR.MINOR.PATCH numeric semver.", version))
            previous = None
            continue
        if previous is None:
            previous = parsed
            continue
        change_class = str(entry.get("change_class") or "")
        major, minor, patch = parsed
        prev_major, prev_minor, prev_patch = previous
        if change_class == "patch":
            if not (major == prev_major and minor == prev_minor and patch > prev_patch):
                issues.append(issue("IP_VERSION_PATCH_SEQUENCE", "Patch bump must keep major/minor and increase patch.", version))
        elif change_class == "minor":
            if not (major == prev_major and minor > prev_minor):
                issues.append(issue("IP_VERSION_MINOR_SEQUENCE", "Minor bump must keep major and increase minor.", version))
        elif change_class == "major":
            if not major > prev_major:
                issues.append(issue("IP_VERSION_MAJOR_SEQUENCE", "Major bump must increase major.", version))
        elif change_class != "initial":
            issues.append(issue("IP_VERSION_CHANGE_CLASS", "Unknown change_class.", version))
        previous = parsed
    return issues


def check_active_entry(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    versions = payload.get("versions") if isinstance(payload.get("versions"), list) else []
    active = [entry for entry in versions if isinstance(entry, dict) and entry.get("state") == "active"]
    if len(active) != 1:
        issues.append(issue("IP_VERSION_ACTIVE_COUNT", "IP version ledger must have exactly one active version."))
        return issues
    current = str(payload.get("current_version") or "")
    active_version = str(active[0].get("version") or "")
    if current != active_version:
        issues.append(issue("IP_VERSION_CURRENT_ACTIVE", "current_version must match the active version.", active_version))
    return issues


def check_entry_refs(entry: dict[str, Any], ip_dir: Path, *, active: bool, verify_git_tag: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    version = str(entry.get("version") or "<unknown>")
    baseline_class = str(entry.get("baseline_class") or "")
    if baseline_class in GOLDEN_CLASSES:
        for field, code in (
            ("baseline_manifest", "IP_VERSION_BASELINE_MANIFEST"),
            ("git_tag", "IP_VERSION_GIT_TAG"),
            ("approval_ref", "IP_VERSION_APPROVAL_REF"),
        ):
            if not str(entry.get(field) or "").strip():
                issues.append(issue(code, f"{baseline_class} version requires {field}.", version))
    if entry.get("change_class") == "patch" and entry.get("functional_truth_changed") is True:
        issues.append(issue("IP_VERSION_PATCH_TRUTH_CHANGE", "Patch version cannot mark functional_truth_changed=true.", version))

    tag_prefix = ""
    # Filled by caller through entry shadow property when useful.
    if isinstance(entry.get("_tag_prefix"), str):
        tag_prefix = str(entry["_tag_prefix"])
    tag = str(entry.get("git_tag") or "")
    if tag_prefix and tag and not tag.startswith(tag_prefix):
        issues.append(issue("IP_VERSION_TAG_PREFIX", "git_tag must start with version_policy.tag_prefix.", version))

    if active and baseline_class in GOLDEN_CLASSES:
        for field, code in (("baseline_manifest", "IP_VERSION_BASELINE_MANIFEST_MISSING"), ("approval_ref", "IP_VERSION_APPROVAL_REF_MISSING")):
            raw = str(entry.get(field) or "")
            path = rel_path(raw, ip_dir)
            if path is None:
                issues.append(issue(code, f"{field} must be a relative path under the IP directory.", version))
            elif not path.is_file():
                issues.append(issue(code, f"{field} does not exist for active version.", raw))

    if verify_git_tag and active and baseline_class in GOLDEN_CLASSES:
        if not tag:
            issues.append(issue("IP_VERSION_GIT_TAG", "Active golden/release version requires git_tag.", version))
        else:
            tag_type = git_tag_type(ip_dir, tag)
            if tag_type is None:
                issues.append(issue("IP_VERSION_GIT_TAG_MISSING", "git_tag does not exist in the IP-local repo.", tag))
            elif tag_type != "tag":
                issues.append(issue("IP_VERSION_GIT_TAG_NOT_ANNOTATED", "git_tag must be an annotated tag.", tag))
    return issues


def check_ip_version(ip_dir: Path, *, require_ip_git: bool = False, verify_git_tag: bool = False) -> dict[str, Any]:
    ip_root = ip_dir.resolve()
    path = oag_paths.legacy_or_hidden(ip_root, "ontology/ip_version.yaml")
    issues: list[dict[str, str]] = []
    if not path.is_file():
        issues.append(issue("IP_VERSION_LEDGER_MISSING", "Missing ontology/ip_version.yaml.", str(path)))
        return {
            "schema_version": "oag_ip_version_check.v1",
            "status": "fail",
            "ip_dir": str(ip_root),
            "version_path": str(path),
            "counts": {"versions": 0, "issues": len(issues)},
            "issues": issues,
        }

    payload, load_issues = read_document(path)
    if payload is None:
        payload = {}
    issues.extend(load_issues)
    if payload:
        issues.extend(schema_issues(payload))

    if require_ip_git and not git_dir_exists(ip_root):
        issues.append(issue("IP_VERSION_LOCAL_GIT_MISSING", "IP version stewardship requires an IP-local .git directory.", str(ip_root / ".git")))
    if verify_git_tag and not git_dir_exists(ip_root):
        issues.append(issue("IP_VERSION_LOCAL_GIT_MISSING", "Cannot verify git tags without an IP-local .git directory.", str(ip_root / ".git")))

    versions = [entry for entry in payload.get("versions", []) if isinstance(entry, dict)] if isinstance(payload.get("versions"), list) else []
    issues.extend(check_active_entry(payload))
    issues.extend(check_version_sequence(versions))
    policy = payload.get("version_policy") if isinstance(payload.get("version_policy"), dict) else {}
    tag_prefix = str(policy.get("tag_prefix") or "")
    if policy.get("git_scope") != "ip_local_repo":
        issues.append(issue("IP_VERSION_GIT_SCOPE", "version_policy.git_scope must be ip_local_repo."))

    for entry in versions:
        entry_with_policy = dict(entry)
        entry_with_policy["_tag_prefix"] = tag_prefix
        issues.extend(
            check_entry_refs(
                entry_with_policy,
                ip_root,
                active=entry.get("state") == "active",
                verify_git_tag=verify_git_tag,
            )
        )

    return {
        "schema_version": "oag_ip_version_check.v1",
        "status": "fail" if issues else "pass",
        "ip": payload.get("ip", ip_root.name) if isinstance(payload, dict) else ip_root.name,
        "current_version": payload.get("current_version", "") if isinstance(payload, dict) else "",
        "ip_dir": str(ip_root),
        "version_path": str(path),
        "git_scope": policy.get("git_scope") if isinstance(policy, dict) else "",
        "counts": {"versions": len(versions), "issues": len(issues)},
        "issues": issues,
        "next_actions": ["Repair ontology/ip_version.yaml before cutting or promoting a baseline."] if issues else ["IP version ledger is eligible for the requested checks."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--require-ip-git", action="store_true", help="Require an IP-local .git directory.")
    parser.add_argument("--verify-git-tag", action="store_true", help="Verify the active golden/release tag exists and is annotated.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_ip_version(Path(args.ip_dir), require_ip_git=args.require_ip_git, verify_git_tag=args.verify_git_tag)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS OAG IP version check")
    else:
        print("FAIL OAG IP version check", file=sys.stderr)
        for item in result["issues"]:
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
