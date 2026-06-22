#!/usr/bin/env python3
"""Dependency-aware wavefront planner for OAG parallel work."""

from __future__ import annotations

import argparse
import json
import os
import re
import hashlib
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
CODEX_ROOT = SCRIPTS_DIR.parent
PROJECT_ROOT = Path(os.environ.get("OAG_PROJECT_ROOT") or CODEX_ROOT.parent).expanduser().resolve()
SCHEMAS_DIR = CODEX_ROOT / "schemas"

sys.path.insert(0, str(SCRIPTS_DIR))
from oag_validate_json import validate_document  # pylint: disable=wrong-import-position


TASK_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
DONE_STATUSES = {"handoff_pass", "closed", "waived"}
ACTIVE_STATUSES = {"claimed"}
VALID_STATUSES = {"pending", "claimed", "handoff_pass", "blocked", "failed", "inconclusive", "waived", "closed"}
VALID_KINDS = {"read_only", "write", "integration", "closure"}
VALID_OWNERSHIP = {"none", "exclusive_file", "integration_owner"}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def issue(code: str, message: str, path: str | None = None) -> dict[str, str]:
    payload = {"code": code, "message": message}
    if path:
        payload["path"] = path
    return payload


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


def graph_paths(ip_dir: Path, run_id: str) -> dict[str, Path]:
    run_dir = ip_dir / "ontology" / "runs" / run_id
    return {
        "run_dir": run_dir,
        "graph": run_dir / "wavefront_task_graph.json",
        "locks": run_dir / "ownership_locks.json",
        "barriers": run_dir / "barriers.json",
        "claims": run_dir / "claims",
        "events": ip_dir / "knowledge" / "wavefront" / run_id / "events.jsonl",
    }


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


def load_schema(name: str) -> dict[str, Any]:
    return load_json(SCHEMAS_DIR / name)


def validate_named_schema(name: str, payload: Any) -> list[dict[str, str]]:
    return validate_document(load_schema(name), payload)


def append_event(ip_dir: Path, run_id: str, event: str, *, task_id: str = "", status: str = "", details: dict[str, Any] | None = None) -> None:
    path = graph_paths(ip_dir, run_id)["events"]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "oag_wavefront_event.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run_id,
        "event": event,
        "created_at": utc_now(),
    }
    if task_id:
        payload["task_id"] = task_id
    if status:
        payload["status"] = status
    if details is not None:
        payload["details"] = details
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"[]", "null", "None"}:
        return [] if value == "[]" else None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return value.strip('"').strip("'")


def load_simple_yaml_template(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    root: dict[str, Any] = {}
    tasks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and line == "tasks:":
            root["tasks"] = tasks
            current = None
            list_key = None
            continue
        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            root[key.strip()] = parse_scalar(value)
            continue
        if indent == 2 and line.startswith("- "):
            current = {}
            tasks.append(current)
            item = line[2:].strip()
            if item and ":" in item:
                key, value = item.split(":", 1)
                current[key.strip()] = parse_scalar(value)
            list_key = None
            continue
        if current is None:
            continue
        if indent == 4 and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            parsed = parse_scalar(value)
            if value.strip() == "":
                parsed = []
                list_key = key
            else:
                list_key = None
            current[key] = parsed
            continue
        if indent == 6 and line.startswith("- ") and list_key:
            current.setdefault(list_key, []).append(parse_scalar(line[2:]))
    if tasks:
        root["tasks"] = tasks
    return root


def load_template(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        data = load_json(path)
    else:
        data = load_simple_yaml_template(path)
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError(f"template must contain a tasks list: {path}")
    return data


def normalize_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if isinstance(raw, str) and raw:
        return [raw]
    return []


def normalize_task(raw: dict[str, Any], ip_dir: Path) -> dict[str, Any]:
    task_id = str(raw.get("task_id") or "").strip()
    if not TASK_ID_RE.match(task_id):
        raise ValueError(f"invalid task_id: {task_id}")
    kind = str(raw.get("kind") or "read_only").strip()
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid task kind for {task_id}: {kind}")
    ownership_mode = str(raw.get("ownership_mode") or ("none" if kind == "read_only" else "exclusive_file")).strip()
    if ownership_mode not in VALID_OWNERSHIP:
        raise ValueError(f"invalid ownership_mode for {task_id}: {ownership_mode}")
    allowed_write_paths = [ip_rel_path(item, ip_dir) for item in normalize_list(raw.get("allowed_write_paths"))]
    shared_artifacts = [ip_rel_path(item, ip_dir) for item in normalize_list(raw.get("shared_artifacts"))]
    stale_if_paths_changed = [ip_rel_path(item, ip_dir) for item in normalize_list(raw.get("stale_if_paths_changed"))]
    return {
        **raw,
        "task_id": task_id,
        "kind": kind,
        "phase": str(raw.get("phase") or kind),
        "agent_type": str(raw.get("agent_type") or ""),
        "depends_on": normalize_list(raw.get("depends_on")),
        "barrier_inputs": normalize_list(raw.get("barrier_inputs")),
        "barrier_outputs": normalize_list(raw.get("barrier_outputs")),
        "allowed_write_paths": sorted(set(allowed_write_paths)),
        "shared_artifacts": sorted(set(shared_artifacts)),
        "stale_if_paths_changed": sorted(set(stale_if_paths_changed)),
        "ownership_mode": ownership_mode,
        "status": str(raw.get("status") or "pending"),
        "may_claim_complete": False,
    }


def load_graph(ip_dir: Path, run_id: str) -> dict[str, Any]:
    path = graph_paths(ip_dir, run_id)["graph"]
    if not path.is_file():
        raise ValueError(f"wavefront graph is missing: {path}")
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"wavefront graph is not an object: {path}")
    return data


def write_graph(ip_dir: Path, run_id: str, graph: dict[str, Any]) -> None:
    graph["updated_at"] = utc_now()
    write_json(graph_paths(ip_dir, run_id)["graph"], graph)


def load_locks(ip_dir: Path, run_id: str) -> dict[str, Any]:
    path = graph_paths(ip_dir, run_id)["locks"]
    if path.is_file():
        data = load_json(path)
        if isinstance(data, dict):
            return data
    return {
        "schema_version": "oag_ownership_locks.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run_id,
        "ip_id": ip_dir.name,
        "locks": [],
        "updated_at": utc_now(),
    }


def write_locks(ip_dir: Path, run_id: str, locks: dict[str, Any]) -> None:
    locks["updated_at"] = utc_now()
    write_json(graph_paths(ip_dir, run_id)["locks"], locks)


def load_barriers(ip_dir: Path, run_id: str) -> dict[str, Any]:
    path = graph_paths(ip_dir, run_id)["barriers"]
    if path.is_file():
        data = load_json(path)
        if isinstance(data, dict):
            return data
    return {
        "schema_version": "oag_wavefront_barriers.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run_id,
        "ip_id": ip_dir.name,
        "tokens": [],
        "updated_at": utc_now(),
    }


def write_barriers(ip_dir: Path, run_id: str, barriers: dict[str, Any]) -> None:
    barriers["updated_at"] = utc_now()
    write_json(graph_paths(ip_dir, run_id)["barriers"], barriers)


def task_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(task.get("task_id")): task for task in graph.get("tasks", []) if isinstance(task, dict)}


def dependency_ready(task: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    for dep in normalize_list(task.get("depends_on")):
        dep_task = tasks.get(dep)
        if not dep_task:
            blockers.append(f"missing dependency {dep}")
            continue
        if str(dep_task.get("status") or "") not in DONE_STATUSES:
            blockers.append(f"dependency {dep} status={dep_task.get('status')}")
    return not blockers, blockers


def barrier_ready(task: dict[str, Any], barriers: dict[str, Any]) -> tuple[bool, list[str]]:
    tokens = {str(item) for item in barriers.get("tokens", [])}
    blockers = [item for item in normalize_list(task.get("barrier_inputs")) if item not in tokens]
    return not blockers, blockers


def active_lock_paths(locks: dict[str, Any], *, exclude_task: str = "") -> dict[str, str]:
    paths: dict[str, str] = {}
    for lock in locks.get("locks", []):
        if not isinstance(lock, dict):
            continue
        task_id = str(lock.get("task_id") or "")
        if exclude_task and task_id == exclude_task:
            continue
        path = str(lock.get("path") or "")
        if path:
            paths[path] = task_id
    return paths


def task_write_paths(task: dict[str, Any]) -> list[str]:
    return sorted(set(normalize_list(task.get("allowed_write_paths")) + normalize_list(task.get("shared_artifacts"))))


def seed_pre_edit_hashes(task: dict[str, Any], ip_dir: Path) -> None:
    hashes = {
        path: path_fingerprint(ip_dir / path)
        for path in normalize_list(task.get("stale_if_paths_changed"))
    }
    if hashes:
        task["pre_edit_hashes"] = hashes


def stale_path_issues(task: dict[str, Any], ip_dir: Path) -> list[dict[str, str]]:
    hashes = task.get("pre_edit_hashes") if isinstance(task.get("pre_edit_hashes"), dict) else {}
    issues: list[dict[str, str]] = []
    for path in normalize_list(task.get("stale_if_paths_changed")):
        expected = str(hashes.get(path) or "")
        observed = path_fingerprint(ip_dir / path)
        if expected and observed != expected:
            issues.append(issue("STALE_PATH_CHANGED", f"path changed since wavefront plan: {path}", path))
    return issues


def ready_tasks(graph: dict[str, Any], barriers: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = task_map(graph)
    ready: list[dict[str, Any]] = []
    for task in graph.get("tasks", []):
        if not isinstance(task, dict) or task.get("status") != "pending":
            continue
        deps_ok, _ = dependency_ready(task, tasks)
        barriers_ok, _ = barrier_ready(task, barriers)
        if deps_ok and barriers_ok:
            ready.append(task)
    return ready


def verify_invariants(graph: dict[str, Any], locks: dict[str, Any], barriers: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in validate_named_schema("oag_wavefront_task_graph.schema.json", graph):
        issues.append(issue(f"GRAPH_SCHEMA_{item['code']}", item["message"], item["path"]))
    for item in validate_named_schema("oag_ownership_locks.schema.json", locks):
        issues.append(issue(f"LOCKS_SCHEMA_{item['code']}", item["message"], item["path"]))

    tasks = task_map(graph)
    if len(tasks) != len(graph.get("tasks", [])):
        issues.append(issue("DUPLICATE_TASK_ID", "task_id values must be unique"))
    for task in graph.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or "")
        status = str(task.get("status") or "")
        kind = str(task.get("kind") or "")
        ownership = str(task.get("ownership_mode") or "")
        if status not in VALID_STATUSES:
            issues.append(issue("TASK_STATUS", f"invalid task status: {status}", task_id))
        if kind not in VALID_KINDS:
            issues.append(issue("TASK_KIND", f"invalid task kind: {kind}", task_id))
        if ownership not in VALID_OWNERSHIP:
            issues.append(issue("OWNERSHIP_MODE", f"invalid ownership mode: {ownership}", task_id))
        if task.get("may_claim_complete") is not False:
            issues.append(issue("TASK_COMPLETION_CLAIM", "task must keep may_claim_complete=false", task_id))
        for dep in normalize_list(task.get("depends_on")):
            if dep not in tasks:
                issues.append(issue("MISSING_DEPENDENCY", f"task dependency does not exist: {dep}", task_id))
        if kind == "write" and ownership != "exclusive_file":
            issues.append(issue("WRITE_OWNERSHIP", "write tasks require exclusive_file ownership", task_id))
        if kind == "integration" and ownership != "integration_owner":
            issues.append(issue("INTEGRATION_OWNERSHIP", "integration tasks require integration_owner ownership", task_id))
        if normalize_list(task.get("shared_artifacts")) and ownership != "integration_owner":
            issues.append(issue("SHARED_ARTIFACT_OWNERSHIP", "shared artifacts require integration_owner ownership", task_id))
        if kind in {"write", "integration"} and not task_write_paths(task):
            issues.append(issue("MISSING_WRITE_SCOPE", "write/integration task has no write paths", task_id))
        if kind == "read_only" and task_write_paths(task):
            issues.append(issue("READ_ONLY_WRITE_SCOPE", "read_only task must not own write paths", task_id))

    seen_paths: dict[str, str] = {}
    for lock in locks.get("locks", []):
        if not isinstance(lock, dict):
            continue
        task_id = str(lock.get("task_id") or "")
        path = str(lock.get("path") or "")
        if task_id not in tasks:
            issues.append(issue("LOCK_TASK_MISSING", "ownership lock refers to unknown task", path))
        if path in seen_paths and seen_paths[path] != task_id:
            issues.append(issue("DOUBLE_WRITER_LOCK", f"path locked by {seen_paths[path]} and {task_id}", path))
        seen_paths[path] = task_id

    # Keep the barriers object intentionally lightweight but check token shape.
    if not isinstance(barriers.get("tokens", []), list):
        issues.append(issue("BARRIER_TOKENS", "barriers.tokens must be a list"))
    return issues


def result(status: str, schema_version: str, **extra: Any) -> dict[str, Any]:
    return {"schema_version": schema_version, "status": status, **extra}


def cmd_plan(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    run_id = args.run_id
    template = load_template(resolve_read_path(args.template))
    tasks = [normalize_task(task, ip_dir) for task in template["tasks"] if isinstance(task, dict)]
    for task in tasks:
        seed_pre_edit_hashes(task, ip_dir)
    if not tasks:
        raise ValueError("wavefront template produced no tasks")
    now = utc_now()
    graph = {
        "schema_version": "oag_wavefront_task_graph.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run_id,
        "ip_id": ip_dir.name,
        "ip_dir": project_rel(ip_dir),
        "template": str(args.template),
        "tasks": tasks,
        "created_at": now,
        "updated_at": now,
    }
    locks = {
        "schema_version": "oag_ownership_locks.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run_id,
        "ip_id": ip_dir.name,
        "locks": [],
        "updated_at": now,
    }
    barriers = {
        "schema_version": "oag_wavefront_barriers.v1",
        "product_name": "IP Dev Agent",
        "internal_gateway": "Ontology Agent Gateway",
        "run_id": run_id,
        "ip_id": ip_dir.name,
        "tokens": normalize_list(args.barrier),
        "updated_at": now,
    }
    paths = graph_paths(ip_dir, run_id)
    paths["run_dir"].mkdir(parents=True, exist_ok=True)
    paths["claims"].mkdir(parents=True, exist_ok=True)
    write_json(paths["graph"], graph)
    write_json(paths["locks"], locks)
    write_json(paths["barriers"], barriers)
    append_event(ip_dir, run_id, "planned", details={"template": str(args.template), "tasks": [task["task_id"] for task in tasks]})
    issues = verify_invariants(graph, locks, barriers)
    return result(
        "fail" if issues else "pass",
        "oag_wavefront_plan_result.v1",
        graph_path=project_rel(paths["graph"]),
        locks_path=project_rel(paths["locks"]),
        barriers_path=project_rel(paths["barriers"]),
        events_path=project_rel(paths["events"]),
        ready_tasks=[task["task_id"] for task in ready_tasks(graph, barriers)],
        issues=issues,
    )


def cmd_ready(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    graph = load_graph(ip_dir, args.run_id)
    barriers = load_barriers(ip_dir, args.run_id)
    ready = ready_tasks(graph, barriers)
    append_event(ip_dir, args.run_id, "ready", details={"ready_tasks": [task["task_id"] for task in ready]})
    return result("pass", "oag_wavefront_ready_result.v1", ready_tasks=ready)


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    graph = load_graph(ip_dir, args.run_id)
    locks = load_locks(ip_dir, args.run_id)
    barriers = load_barriers(ip_dir, args.run_id)
    counts: dict[str, int] = {}
    for task in graph.get("tasks", []):
        status = str(task.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return result(
        "pass",
        "oag_wavefront_status_result.v1",
        counts=counts,
        ready_task_ids=[task["task_id"] for task in ready_tasks(graph, barriers)],
        active_locks=locks.get("locks", []),
        barrier_tokens=barriers.get("tokens", []),
    )


def cmd_claim(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    graph = load_graph(ip_dir, args.run_id)
    locks = load_locks(ip_dir, args.run_id)
    barriers = load_barriers(ip_dir, args.run_id)
    tasks = task_map(graph)
    task = tasks.get(args.task_id)
    issues: list[dict[str, str]] = []
    if not task:
        issues.append(issue("TASK_NOT_FOUND", f"task not found: {args.task_id}"))
        return result("fail", "oag_wavefront_claim_result.v1", issues=issues)
    if task.get("status") != "pending":
        issues.append(issue("TASK_NOT_PENDING", f"task status is {task.get('status')}", args.task_id))
    deps_ok, dep_blockers = dependency_ready(task, tasks)
    if not deps_ok:
        issues.extend(issue("DEPENDENCY_UNMET", blocker, args.task_id) for blocker in dep_blockers)
    barriers_ok, barrier_blockers = barrier_ready(task, barriers)
    if not barriers_ok:
        issues.extend(issue("BARRIER_UNMET", f"missing barrier token: {token}", args.task_id) for token in barrier_blockers)
    issues.extend(stale_path_issues(task, ip_dir))

    write_paths = task_write_paths(task)
    active = active_lock_paths(locks)
    for path in write_paths:
        if path in active:
            issues.append(issue("OWNERSHIP_CONFLICT", f"path already locked by {active[path]}", path))
    if issues:
        append_event(ip_dir, args.run_id, "blocked", task_id=args.task_id, status="blocked", details={"issues": issues})
        return result("fail", "oag_wavefront_claim_result.v1", issues=issues)

    claim_file = graph_paths(ip_dir, args.run_id)["claims"] / f"{args.task_id}.lock"
    claim_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with claim_file.open("x", encoding="utf-8") as fh:
            fh.write(json.dumps({"task_id": args.task_id, "claimed_by": args.claimed_by or "", "claimed_at": utc_now()}) + "\n")
    except FileExistsError:
        return result("fail", "oag_wavefront_claim_result.v1", issues=[issue("TASK_ALREADY_CLAIMED", "task claim lock already exists", args.task_id)])

    task["status"] = "claimed"
    task["claimed_by"] = args.claimed_by or ""
    task["claimed_at"] = utc_now()
    for lock_path in write_paths:
        locks.setdefault("locks", []).append(
            {
                "task_id": args.task_id,
                "path": lock_path,
                "mode": task.get("ownership_mode"),
                "dispatch_id": args.dispatch_id or "",
                "claimed_at": task["claimed_at"],
            }
        )
    write_graph(ip_dir, args.run_id, graph)
    write_locks(ip_dir, args.run_id, locks)
    append_event(ip_dir, args.run_id, "claimed", task_id=args.task_id, status="claimed", details={"write_paths": write_paths})
    return result(
        "pass",
        "oag_wavefront_claim_result.v1",
        task=task,
        active_locks=locks.get("locks", []),
        issues=[],
    )


def cmd_record(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    graph = load_graph(ip_dir, args.run_id)
    locks = load_locks(ip_dir, args.run_id)
    barriers = load_barriers(ip_dir, args.run_id)
    tasks = task_map(graph)
    task = tasks.get(args.task_id)
    if not task:
        return result("fail", "oag_wavefront_record_result.v1", issues=[issue("TASK_NOT_FOUND", f"task not found: {args.task_id}")])
    status = args.status
    if status not in VALID_STATUSES:
        return result("fail", "oag_wavefront_record_result.v1", issues=[issue("TASK_STATUS", f"invalid status: {status}")])
    requested_outputs = normalize_list(args.barrier_output)
    declared_outputs = set(normalize_list(task.get("barrier_outputs")))
    undeclared_outputs = [token for token in requested_outputs if token not in declared_outputs]
    if undeclared_outputs:
        return result(
            "fail",
            "oag_wavefront_record_result.v1",
            issues=[
                issue("BARRIER_OUTPUT_UNDECLARED", f"task did not declare barrier output: {token}", args.task_id)
                for token in undeclared_outputs
            ],
        )
    task["status"] = status
    task["recorded_at"] = utc_now()
    if args.receipt:
        task["receipt_path"] = ip_rel_path(args.receipt, ip_dir)
    if status not in ACTIVE_STATUSES:
        locks["locks"] = [lock for lock in locks.get("locks", []) if not isinstance(lock, dict) or lock.get("task_id") != args.task_id]
        claim_file = graph_paths(ip_dir, args.run_id)["claims"] / f"{args.task_id}.lock"
        if claim_file.is_file():
            claim_file.unlink()
    tokens = set(str(item) for item in barriers.get("tokens", []))
    tokens.update(requested_outputs)
    barriers["tokens"] = sorted(tokens)
    write_graph(ip_dir, args.run_id, graph)
    write_locks(ip_dir, args.run_id, locks)
    write_barriers(ip_dir, args.run_id, barriers)
    append_event(
        ip_dir,
        args.run_id,
        "recorded",
        task_id=args.task_id,
        status=status,
        details={"barrier_outputs": requested_outputs, "receipt": args.receipt or ""},
    )
    return result(
        "pass",
        "oag_wavefront_record_result.v1",
        task=task,
        barrier_tokens=barriers.get("tokens", []),
        active_locks=locks.get("locks", []),
    )


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    graph = load_graph(ip_dir, args.run_id)
    locks = load_locks(ip_dir, args.run_id)
    barriers = load_barriers(ip_dir, args.run_id)
    issues = verify_invariants(graph, locks, barriers)
    append_event(ip_dir, args.run_id, "verified", status="fail" if issues else "pass", details={"issues": issues})
    return result("fail" if issues else "pass", "oag_wavefront_verify_result.v1", issues=issues)


def cmd_close(args: argparse.Namespace) -> dict[str, Any]:
    ip_dir = resolve_project_path(args.ip_dir)
    graph = load_graph(ip_dir, args.run_id)
    locks = load_locks(ip_dir, args.run_id)
    active = [lock for lock in locks.get("locks", []) if isinstance(lock, dict)]
    open_tasks = [
        task for task in graph.get("tasks", [])
        if isinstance(task, dict) and str(task.get("status") or "") not in DONE_STATUSES
    ]
    issues: list[dict[str, str]] = []
    if active:
        issues.append(issue("ACTIVE_LOCKS", "cannot close wavefront with active ownership locks"))
    if open_tasks and not args.allow_open:
        issues.append(issue("OPEN_TASKS", "cannot close wavefront with open tasks"))
    if issues:
        return result("fail", "oag_wavefront_close_result.v1", issues=issues, open_tasks=open_tasks, active_locks=active)
    graph["closed_at"] = utc_now()
    write_graph(ip_dir, args.run_id, graph)
    append_event(ip_dir, args.run_id, "closed", status="pass", details={"open_tasks": [task.get("task_id") for task in open_tasks]})
    return result("pass", "oag_wavefront_close_result.v1", open_tasks=open_tasks, active_locks=active)


def print_result(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload.get("status") == "pass":
        print(f"PASS {payload.get('schema_version')}")
    else:
        print(f"FAIL {payload.get('schema_version')}", file=sys.stderr)
        for item in payload.get("issues", []):
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan and gate OAG dependency-aware wavefront work.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Create a wavefront task graph from a template.")
    plan.add_argument("--ip-dir", required=True)
    plan.add_argument("--run-id", required=True)
    plan.add_argument("--template", required=True)
    plan.add_argument("--barrier", action="append")
    plan.add_argument("--json", action="store_true")

    ready = sub.add_parser("ready", help="List dependency-satisfied tasks.")
    ready.add_argument("--ip-dir", required=True)
    ready.add_argument("--run-id", required=True)
    ready.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Summarize a wavefront run.")
    status.add_argument("--ip-dir", required=True)
    status.add_argument("--run-id", required=True)
    status.add_argument("--json", action="store_true")

    claim = sub.add_parser("claim", help="Claim a ready task and create ownership locks.")
    claim.add_argument("--ip-dir", required=True)
    claim.add_argument("--run-id", required=True)
    claim.add_argument("--task-id", required=True)
    claim.add_argument("--claimed-by", default="")
    claim.add_argument("--dispatch-id", default="")
    claim.add_argument("--json", action="store_true")

    record = sub.add_parser("record", help="Record bounded worker status and barrier outputs.")
    record.add_argument("--ip-dir", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--task-id", required=True)
    record.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    record.add_argument("--barrier-output", action="append")
    record.add_argument("--receipt", default="")
    record.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify", help="Verify graph, lock, and barrier invariants.")
    verify.add_argument("--ip-dir", required=True)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--json", action="store_true")

    close = sub.add_parser("close", help="Close a wavefront run after all active ownership is released.")
    close.add_argument("--ip-dir", required=True)
    close.add_argument("--run-id", required=True)
    close.add_argument("--allow-open", action="store_true")
    close.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            payload = cmd_plan(args)
        elif args.command == "ready":
            payload = cmd_ready(args)
        elif args.command == "status":
            payload = cmd_status(args)
        elif args.command == "claim":
            payload = cmd_claim(args)
        elif args.command == "record":
            payload = cmd_record(args)
        elif args.command == "verify":
            payload = cmd_verify(args)
        else:
            payload = cmd_close(args)
    except Exception as exc:
        payload = result("fail", "oag_wavefront_error.v1", issues=[issue("EXCEPTION", str(exc))])
    print_result(payload, bool(getattr(args, "json", False)))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
