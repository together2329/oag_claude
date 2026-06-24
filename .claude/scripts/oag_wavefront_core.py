#!/usr/bin/env python3
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Final, Iterator

import oag_paths
from oag_validate_json import validate_document


SCRIPTS_DIR: Final = Path(__file__).resolve().parent
CODEX_ROOT: Final = SCRIPTS_DIR.parent
PROJECT_ROOT: Final = Path(os.environ.get("OAG_PROJECT_ROOT") or CODEX_ROOT.parent).expanduser().resolve()
SCHEMAS_DIR: Final = CODEX_ROOT / "schemas"
RUN_LOCK_TIMEOUT_SECONDS: Final = 10.0
RUN_LOCK_STALE_SECONDS: Final = 120.0


JsonObject = dict[str, Any]
Issue = dict[str, str]


@dataclass(frozen=True)
class WavefrontRun:
    ip_dir: Path
    run_id: str


@dataclass(frozen=True)
class WavefrontEvent:
    run: WavefrontRun
    event: str
    task_id: str = ""
    status: str = ""
    details: JsonObject | None = None


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def issue(code: str, message: str, path: str | None = None) -> Issue:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


def result(status: str, schema_version: str, **extra: Any) -> JsonObject:
    return {"schema_version": schema_version, "status": status, **extra}


def resolve_project_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"path must stay under project root: {raw}") from exc
    return resolved


def resolve_read_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def project_rel(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {path}") from exc


def display_path(path: Path) -> str:
    try:
        return project_rel(path)
    except ValueError:
        return str(path.expanduser().resolve())


def ip_rel_path(raw: str, ip_dir: Path) -> str:
    if not raw:
        return raw
    path = Path(raw).expanduser()
    if path.is_absolute():
        resolved = path.resolve()
        try:
            return resolved.relative_to(ip_dir.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"task path must stay under ip_dir: {raw}") from exc
    normalized = Path(raw)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"relative task path must not escape ip_dir: {raw}")
    return normalized.as_posix().strip("/")


def graph_paths(run: WavefrontRun) -> dict[str, Path]:
    ip_dir = run.ip_dir
    run_id = run.run_id
    return {
        "run_dir": oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}"),
        "graph": oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}/wavefront_task_graph.json"),
        "locks": oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}/ownership_locks.json"),
        "barriers": oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}/barriers.json"),
        "claims": oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}/claims"),
        "run_lock": oag_paths.legacy_or_hidden(ip_dir, f"ontology/runs/{run_id}/claims/.run-state.lock"),
        "events": oag_paths.legacy_or_hidden(ip_dir, f"knowledge/wavefront/{run_id}/events.jsonl"),
    }


@contextmanager
def run_state_lock(run: WavefrontRun) -> Iterator[None]:
    path = graph_paths(run)["run_lock"]
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + RUN_LOCK_TIMEOUT_SECONDS
    payload = json.dumps({"pid": os.getpid(), "created_at": utc_now()}, sort_keys=True) + "\n"
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError as exc:
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > RUN_LOCK_STALE_SECONDS:
                try:
                    path.unlink()
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for wavefront run lock: {path}") from exc
            time.sleep(0.05)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def path_fingerprint(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_dir():
        return "dir"
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def load_schema(name: str) -> JsonObject:
    return load_json(SCHEMAS_DIR / name)


def validate_named_schema(name: str, payload: Any) -> list[Issue]:
    return validate_document(load_schema(name), payload)


def append_event(event: WavefrontEvent) -> None:
    path = graph_paths(event.run)["events"]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: JsonObject = {
        "schema_version": "oag_wavefront_event.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": event.run.run_id,
        "event": event.event,
        "created_at": utc_now(),
    }
    if event.task_id:
        payload["task_id"] = event.task_id
    if event.status:
        payload["status"] = event.status
    if event.details is not None:
        payload["details"] = event.details
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")
