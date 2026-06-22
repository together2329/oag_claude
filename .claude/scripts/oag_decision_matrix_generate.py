#!/usr/bin/env python3
"""Generate draft OAG decision matrix rows from profile seeds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CODEX_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = CODEX_ROOT / "oag" / "profiles"


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"__load_error__": str(exc)}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml  # type: ignore

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def text(value: Any) -> str:
    return str(value or "").strip()


def load_profile(profile_id: str) -> dict[str, Any]:
    path = PROFILE_DIR / f"{profile_id}.yaml"
    profile = read_yaml(path)
    if profile.get("__load_error__"):
        raise ValueError(f"cannot read profile {profile_id}: {profile['__load_error__']}")
    if not profile:
        raise ValueError(f"profile not found: {profile_id}")
    merged: dict[str, Any] = {}
    parent = text(profile.get("extends"))
    if parent:
        merged = load_profile(parent)
    result = {**merged, **profile}
    result["required_decisions"] = [
        *[item for item in as_list(merged.get("required_decisions")) if isinstance(item, dict)],
        *[item for item in as_list(profile.get("required_decisions")) if isinstance(item, dict)],
    ]
    return result


def existing_matrix(ip_dir: Path) -> dict[str, Any]:
    matrix = read_yaml(ip_dir / "ontology" / "decision_matrix.yaml")
    if not matrix or matrix.get("__load_error__"):
        return {"schema_version": "oag_decision_matrix.v1", "ip": ip_dir.name, "decisions": []}
    if not isinstance(matrix.get("decisions"), list):
        matrix["decisions"] = []
    return matrix


def build_rows(profile: dict[str, Any], *, owner: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in as_list(profile.get("required_decisions")):
        if not isinstance(item, dict):
            continue
        did = text(item.get("id"))
        if not did:
            continue
        rows.append(
            {
                "id": did,
                "question": text(item.get("question")),
                "status": "unresolved",
                "lock_required": bool(item.get("lock_required", True)),
                "owner": owner,
                "recommended": item.get("recommended"),
                "decision": None,
                "rationale": "Profile seed; recommendation is not locked truth until user decision.",
                "affects": [str(value) for value in as_list(item.get("affects")) if str(value).strip()],
                "refs": [f".claude/oag/profiles/{profile.get('profile_id')}.yaml"],
            }
        )
    return rows


def generate(ip_dir: Path, *, profile_id: str, owner: str, write: bool = False) -> dict[str, Any]:
    profile = load_profile(profile_id)
    rows = build_rows(profile, owner=owner)
    matrix = existing_matrix(ip_dir)
    existing_ids = {text(item.get("id")) for item in as_list(matrix.get("decisions")) if isinstance(item, dict)}
    added = [row for row in rows if row["id"] not in existing_ids]
    if write:
        matrix["schema_version"] = "oag_decision_matrix.v1"
        matrix["ip"] = matrix.get("ip") or ip_dir.name
        matrix.setdefault("policy", {"status": "draft", "purpose": "Profile-seeded lock decisions."})
        matrix["decisions"] = [*as_list(matrix.get("decisions")), *added]
        write_yaml(ip_dir / "ontology" / "decision_matrix.yaml", matrix)
    return {
        "schema_version": "oag_decision_matrix_generate.v1",
        "status": "pass",
        "ip": ip_dir.name,
        "profile": profile_id,
        "write": write,
        "rows": rows,
        "added": added,
        "counts": {"profile_rows": len(rows), "added": len(added), "existing": len(rows) - len(added)},
    }


def list_profiles() -> dict[str, Any]:
    profiles = sorted(path.stem for path in PROFILE_DIR.glob("*.yaml"))
    return {"schema_version": "oag_profile_list.v1", "profiles": profiles}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir")
    parser.add_argument("--profile", default="protocol-packet-ip")
    parser.add_argument("--owner", default="unassigned")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = list_profiles() if args.list_profiles else generate(Path(args.ip_dir or "."), profile_id=args.profile, owner=args.owner, write=args.write)
    except Exception as exc:
        result = {"schema_version": "oag_decision_matrix_generate.v1", "status": "fail", "errors": [str(exc)]}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("status") == "fail":
        for error in result.get("errors", []):
            print(f"ERROR {error}")
    elif args.list_profiles:
        print("\n".join(result["profiles"]))
    else:
        print(f"PASS generated {result['counts']['profile_rows']} decision rows ({result['counts']['added']} new)")
    return 0 if result.get("status", "pass") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
