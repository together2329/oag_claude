#!/usr/bin/env python3
"""IP-local path resolver for legacy and .oag layouts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HIDDEN_DIR = ".oag"
OAG_TOP_LEVEL_DIRS = frozenset({"knowledge", "ontology", "evidence", "cache", "manifests"})


def ip_root(ip_dir: str | Path) -> Path:
    return Path(ip_dir).expanduser().resolve()


def oag_root(ip_dir: str | Path) -> Path:
    return ip_root(ip_dir) / HIDDEN_DIR


def _clean_rel(rel: str | Path) -> Path:
    path = Path(rel)
    if path.is_absolute():
        raise ValueError(f"OAG relative path must not be absolute: {rel}")
    parts = path.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"OAG relative path must be normalized: {rel}")
    if parts[0] == HIDDEN_DIR:
        return Path(*parts[1:]) if len(parts) > 1 else Path()
    return path


def _state_rel(rel: str | Path) -> Path:
    clean = _clean_rel(rel)
    if not clean.parts:
        raise ValueError("OAG relative path must name a file or directory under .oag")
    return clean


def _write_base(ip_dir: str | Path) -> Path:
    ip = ip_root(ip_dir)
    hidden = oag_root(ip)
    return hidden if hidden.exists() else ip


def state_path(ip_dir: str | Path, rel: str | Path) -> Path:
    clean = _state_rel(rel)
    return _write_base(ip_dir) / clean


def legacy_or_hidden(ip_dir: str | Path, rel: str | Path) -> Path:
    ip = ip_root(ip_dir)
    clean = _state_rel(rel)
    hidden = ip / HIDDEN_DIR / clean
    legacy = ip / clean
    if hidden.exists():
        return hidden
    if legacy.exists():
        return legacy
    return state_path(ip, clean)


def ontology_path(ip_dir: str | Path, rel: str | Path) -> Path:
    clean = _clean_rel(rel)
    if clean.parts and clean.parts[0] == "ontology":
        clean = Path(*clean.parts[1:])
    return state_path(ip_dir, Path("ontology") / clean)


def generated_path(ip_dir: str | Path, rel: str | Path) -> Path:
    clean = _clean_rel(rel)
    if clean.parts[:2] == ("ontology", "generated"):
        clean = Path(*clean.parts[2:])
    elif clean.parts and clean.parts[0] == "generated":
        clean = Path(*clean.parts[1:])
    return state_path(ip_dir, Path("ontology") / "generated" / clean)


def evidence_path(ip_dir: str | Path, rel: str | Path) -> Path:
    clean = _clean_rel(rel)
    if clean.parts and clean.parts[0] == "evidence":
        clean = Path(*clean.parts[1:])
    return state_path(ip_dir, Path("evidence") / clean)


def layout_status(ip_dir: str | Path) -> dict[str, Any]:
    ip = ip_root(ip_dir)
    hidden = ip / HIDDEN_DIR
    legacy_state = sorted(name for name in OAG_TOP_LEVEL_DIRS if (ip / name).exists())
    hidden_state = sorted(name for name in OAG_TOP_LEVEL_DIRS if (hidden / name).exists())
    layout = "dot_oag" if hidden.exists() else "legacy"
    warnings: list[str] = []
    if hidden.exists() and legacy_state:
        warnings.append("mixed_layout: .oag exists with legacy top-level OAG state")
    return {
        "schema_version": "oag_paths.v1",
        "ip_dir": str(ip),
        "layout": layout,
        "oag_root": str(hidden),
        "write_base": str(_write_base(ip)),
        "legacy_state": legacy_state,
        "hidden_state": hidden_state,
        "warnings": warnings,
        "samples": {
            "ledger": str(state_path(ip, "knowledge/ledger.jsonl")),
            "scope_lock": str(ontology_path(ip, "scope_lock.json")),
            "authoring_packets": str(generated_path(ip, "authoring_packets")),
            "sim_results": str(evidence_path(ip, "sim/results.xml")),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve OAG IP-local paths for legacy and .oag layouts.")
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = layout_status(args.ip_dir)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
