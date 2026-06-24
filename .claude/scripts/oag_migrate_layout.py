#!/usr/bin/env python3
"""Migrate an OAG IP between the legacy top-level layout and the .oag hidden-state
layout. Only the ontology/ and knowledge/ subtrees move (the same subtrees the
oag_paths resolver routes); human-facing surfaces stay top-level.

Dry-run by default: prints a move manifest and changes nothing. --apply performs
the moves, preserves file hashes, and writes a migration receipt under
<ip>/.oag/manifests/. --rollback <receipt> reverses a prior migration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import oag_paths  # noqa: E402

MIGRATING_SUBTREES = ("ontology", "knowledge")
RECEIPT_SCHEMA = "oag_layout_migration.v1"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    """sha256 of every file under root, keyed by path relative to root."""
    out: dict[str, str] = {}
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out[p.relative_to(root).as_posix()] = _sha256(p)
    return out


def plan(ip_dir: Path, *, direction: str) -> list[dict[str, Any]]:
    ip = oag_paths.ip_root(ip_dir)
    hidden = ip / oag_paths.HIDDEN_DIR
    moves: list[dict[str, Any]] = []
    for sub in MIGRATING_SUBTREES:
        legacy = ip / sub
        hiddensub = hidden / sub
        if direction == "to_dot_oag":
            src, dst = legacy, hiddensub
        else:
            src, dst = hiddensub, legacy
        moves.append(
            {
                "subtree": sub,
                "from": str(src.relative_to(ip)),
                "to": str(dst.relative_to(ip)),
                "src_exists": src.is_dir(),
                "dst_exists": dst.is_dir(),
                "file_count": len(_hash_tree(src)) if src.is_dir() else 0,
            }
        )
    return moves


def _apply_one(ip: Path, src: Path, dst: Path, *, resolve: bool) -> dict[str, Any]:
    if not src.is_dir():
        return {"from": str(src.relative_to(ip)), "to": str(dst.relative_to(ip)), "status": "skipped_no_source"}
    pre = _hash_tree(src)
    if dst.exists():
        if not resolve:
            raise SystemExit(f"refusing to overwrite existing {dst.relative_to(ip)} (use --resolve if hashes match)")
        if _hash_tree(dst) != pre:
            raise SystemExit(f"--resolve given but {dst.relative_to(ip)} differs from source; aborting")
        # Idempotent: destination already holds identical content.
        shutil.rmtree(src)
        return {"from": str(src.relative_to(ip)), "to": str(dst.relative_to(ip)), "status": "resolved_identical", "file_count": len(pre), "sha256": pre}
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    post = _hash_tree(dst)
    if post != pre:
        raise SystemExit(f"hash mismatch after moving {src.relative_to(ip)} -> {dst.relative_to(ip)}")
    return {"from": str(src.relative_to(ip)), "to": str(dst.relative_to(ip)), "status": "moved", "file_count": len(pre), "sha256": pre}


def migrate(ip_dir: Path, *, direction: str, apply: bool, resolve: bool) -> dict[str, Any]:
    ip = oag_paths.ip_root(ip_dir)
    moves = plan(ip, direction=direction)
    result: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "ip": ip.name,
        "ip_dir": str(ip),
        "direction": direction,
        "applied": False,
        "created_at": _now(),
        "moves": moves,
    }
    if not apply:
        result["mode"] = "dry_run"
        return result

    applied_moves: list[dict[str, Any]] = []
    for sub in MIGRATING_SUBTREES:
        legacy = ip / sub
        hiddensub = ip / oag_paths.HIDDEN_DIR / sub
        src, dst = (legacy, hiddensub) if direction == "to_dot_oag" else (hiddensub, legacy)
        applied_moves.append(_apply_one(ip, src, dst, resolve=resolve))

    result["applied"] = True
    result["mode"] = "apply"
    result["applied_moves"] = applied_moves

    receipt_dir = ip / oag_paths.HIDDEN_DIR / "manifests"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"migration_{_stamp()}_{direction}.json"
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["receipt"] = str(receipt_path.relative_to(ip))
    return result


def rollback(receipt_path: Path) -> dict[str, Any]:
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise SystemExit(f"not an {RECEIPT_SCHEMA} receipt: {receipt_path}")
    ip = oag_paths.ip_root(receipt["ip_dir"])
    reverse = "rollback" if receipt.get("direction") == "to_dot_oag" else "to_dot_oag"
    reversed_moves: list[dict[str, Any]] = []
    for move in receipt.get("applied_moves", []):
        # original move was from -> to; reverse it (to -> from)
        cur = ip / move["to"]
        back = ip / move["from"]
        if move.get("status") in ("moved", "resolved_identical") and cur.is_dir():
            expected = move.get("sha256", {})
            if _hash_tree(cur) != expected:
                raise SystemExit(f"rollback aborted: {move['to']} changed since migration")
            back.parent.mkdir(parents=True, exist_ok=True)
            if back.exists():
                raise SystemExit(f"rollback aborted: {move['from']} already exists")
            shutil.move(str(cur), str(back))
            if _hash_tree(back) != expected:
                raise SystemExit(f"rollback hash mismatch restoring {move['from']}")
            reversed_moves.append({"from": move["to"], "to": move["from"], "status": "restored", "file_count": move.get("file_count", 0)})
    return {
        "schema_version": RECEIPT_SCHEMA,
        "ip": ip.name,
        "ip_dir": str(ip),
        "direction": reverse,
        "applied": True,
        "mode": "rollback",
        "created_at": _now(),
        "source_receipt": str(receipt_path),
        "applied_moves": reversed_moves,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", help="IP directory to migrate")
    parser.add_argument("--to-dot-oag", action="store_true", help="move ontology/ and knowledge/ under <ip>/.oag/ (default direction)")
    parser.add_argument("--from-dot-oag", action="store_true", help="move ontology/ and knowledge/ back to the top level")
    parser.add_argument("--apply", action="store_true", help="perform the moves (default is dry-run)")
    parser.add_argument("--resolve", action="store_true", help="if the destination already holds identical content, drop the source instead of failing")
    parser.add_argument("--rollback", help="reverse a prior migration from its receipt JSON")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.rollback:
        result = rollback(Path(args.rollback))
    else:
        if not args.ip_dir:
            parser.error("--ip-dir is required unless --rollback is given")
        direction = "rollback" if args.from_dot_oag else "to_dot_oag"
        result = migrate(Path(args.ip_dir), direction=direction, apply=args.apply, resolve=args.resolve)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        mode = result.get("mode", "")
        print(f"{result['direction']} [{mode}] {result['ip']}")
        for move in result.get("applied_moves", result.get("moves", [])):
            print(f"  {move.get('from')} -> {move.get('to')} ({move.get('status', 'planned')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
