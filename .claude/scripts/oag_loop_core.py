#!/usr/bin/env python3
"""Bounded OAG loop policy and batch projection helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import oag_paths


SCHEMA_POLICY = "oag_loop_policy.v1"
SCHEMA_PLAN = "oag_bounded_plan.v1"
SCHEMA_DECISION = "oag_loop_decision.v1"

BOUNDARY_ORDER = {
    "decompose": 10,
    "contract": 20,
    "target_lock": 30,
    "rtl": 40,
    "evidence": 50,
    "record": 60,
    "gate": 70,
    "all": 999,
}

BOUNDARY_ALIASES = {
    "": "",
    "all": "all",
    "full": "all",
    "decompose": "decompose",
    "decomposition": "decompose",
    "req": "decompose",
    "requirement": "decompose",
    "requirements": "decompose",
    "contract": "contract",
    "contracts": "contract",
    "target": "target_lock",
    "targetlock": "target_lock",
    "target_lock": "target_lock",
    "lock": "target_lock",
    "rtl": "rtl",
    "tb": "evidence",
    "testbench": "evidence",
    "evidence": "evidence",
    "sim": "evidence",
    "simulation": "evidence",
    "coverage": "evidence",
    "cov": "evidence",
    "formal": "evidence",
    "record": "record",
    "rocev": "record",
    "validation": "record",
    "gate": "gate",
    "review": "gate",
    "signoff": "gate",
}

JOB_BOUNDARY = {
    "WRITE_CONTRACT_JOB": "contract",
    "TARGET_LOCK_JOB": "target_lock",
    "RTL_IMPLEMENT_JOB": "rtl",
    "TB_SCOREBOARD_COVERAGE_JOB": "evidence",
    "FORMAL_ASSERTION_JOB": "evidence",
    "SIM_RUN_JOB": "evidence",
    "STALE_REFRESH_JOB": "evidence",
    "VALIDATION_RECORD_JOB": "record",
    "GATE_REVIEW_JOB": "gate",
}

JOB_DEFAULT_MODE = {
    "WRITE_CONTRACT_JOB": "plan_only",
    "TARGET_LOCK_JOB": "plan_only",
    "RTL_IMPLEMENT_JOB": "dispatch",
    "TB_SCOREBOARD_COVERAGE_JOB": "dispatch",
    "FORMAL_ASSERTION_JOB": "dispatch",
    "SIM_RUN_JOB": "dispatch",
    "STALE_REFRESH_JOB": "dispatch",
    "VALIDATION_RECORD_JOB": "execute",
    "GATE_REVIEW_JOB": "plan_only",
}

POLICY_ENV = {
    "until": "OAG_LOOP_UNTIL",
    "requirements": "OAG_LOOP_REQUIREMENT",
    "obligations": "OAG_LOOP_OBLIGATION",
    "owner_modules": "OAG_LOOP_OWNER",
    "job_types": "OAG_LOOP_JOB_TYPE",
    "limit": "OAG_LOOP_LIMIT",
    "max_iterations": "OAG_LOOP_MAX_ITERATIONS",
    "mode": "OAG_LOOP_MODE",
}


def _read_yaml_file(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _read_json_file(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _str_items(value: Any) -> list[str]:
    items: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str):
            parts = re.split(r"[,:\n]+", item)
            items.extend(part.strip() for part in parts if part.strip())
        else:
            text = str(item).strip()
            if text:
                items.append(text)
    return sorted(dict.fromkeys(items))


def _safe_filename(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return text or "unnamed"


def _hash_value(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def normalize_until(value: Any, *, default: str = "all") -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    raw = re.sub(r"\s+", "", raw)
    if not raw:
        return default
    normalized = BOUNDARY_ALIASES.get(raw, raw)
    if normalized not in BOUNDARY_ORDER:
        raise ValueError(f"invalid OAG loop boundary: {value!r}")
    return normalized


def _normalize_mode(value: Any, *, default: str = "plan_only") -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    if not raw:
        return default
    if raw not in {"plan_only", "dispatch", "execute"}:
        raise ValueError(f"invalid OAG loop mode: {value!r}")
    return raw


def _int_or_default(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        result = int(value)
    except Exception:
        return default
    return max(result, minimum)


def _policy_doc(ip: Path) -> dict[str, Any]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, "ontology/policies.yaml"))
    return data if isinstance(data, dict) else {}


def stored_loop_policy(ip: Path) -> dict[str, Any]:
    execution = _policy_doc(ip).get("execution_policy")
    if not isinstance(execution, dict):
        return {}
    policy = execution.get("loop_policy")
    return policy if isinstance(policy, dict) else {}


def _first_present(arguments: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in arguments and arguments[key] is not None:
            return arguments[key]
    return None


def _raw_policy_from_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    nested = arguments.get("loop_policy")
    if isinstance(nested, dict):
        raw.update(nested)
    key_map = {
        "until": ("loop_until", "until", "boundary", "loop_boundary"),
        "requirements": ("loop_requirements", "loop_requirement", "requirements", "requirement"),
        "obligations": ("loop_obligations", "loop_obligation", "obligations", "obligation"),
        "owner_modules": ("loop_owner_modules", "loop_owner_module", "owner_modules", "owner_module", "owner"),
        "job_types": ("loop_job_types", "loop_job_type", "job_types", "job_type"),
        "limit": ("loop_limit", "limit"),
        "max_iterations": ("loop_max_iterations", "max_iterations"),
        "mode": ("loop_mode", "mode"),
    }
    for target, aliases in key_map.items():
        value = _first_present(arguments, *aliases)
        if value is not None:
            raw[target] = value
    return raw


def _raw_policy_from_env(env: dict[str, str] | None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    raw: dict[str, Any] = {}
    for target, name in POLICY_ENV.items():
        value = source.get(name)
        if value is not None and str(value).strip():
            raw[target] = value
    return raw


def resolve_loop_policy(
    ip: Path,
    arguments: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
    force_active: bool = False,
) -> dict[str, Any]:
    arguments = arguments or {}
    stored = stored_loop_policy(ip)
    raw_args = _raw_policy_from_arguments(arguments)
    raw_env = _raw_policy_from_env(env)
    active = force_active or bool(stored) or bool(raw_args) or bool(raw_env)
    merged = {**stored, **raw_env, **raw_args}
    policy = {
        "schema_version": SCHEMA_POLICY,
        "active": active,
        "until": normalize_until(merged.get("until"), default="all"),
        "requirements": _str_items(merged.get("requirements")),
        "obligations": _str_items(merged.get("obligations")),
        "owner_modules": _str_items(merged.get("owner_modules")),
        "job_types": [item.upper() for item in _str_items(merged.get("job_types"))],
        "limit": _int_or_default(merged.get("limit"), 1, minimum=1),
        "max_iterations": _int_or_default(merged.get("max_iterations"), 8, minimum=1),
        "mode": _normalize_mode(merged.get("mode"), default="plan_only"),
    }
    return policy


def loop_policy_storage(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_POLICY,
        "until": str(policy.get("until") or "all"),
        "requirements": _str_items(policy.get("requirements")),
        "obligations": _str_items(policy.get("obligations")),
        "owner_modules": _str_items(policy.get("owner_modules")),
        "job_types": _str_items(policy.get("job_types")),
        "limit": _int_or_default(policy.get("limit"), 1, minimum=1),
        "max_iterations": _int_or_default(policy.get("max_iterations"), 8, minimum=1),
        "mode": _normalize_mode(policy.get("mode"), default="plan_only"),
    }


def _yaml_items(ip: Path, rel: str, key: str) -> list[dict[str, Any]]:
    data = _read_yaml_file(oag_paths.legacy_or_hidden(ip, rel))
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return [item for item in data[key] if isinstance(item, dict)]
    return []


def _obligation_requirements(ip: Path) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for obligation in _yaml_items(ip, "ontology/obligations.yaml", "obligations"):
        oid = str(obligation.get("id") or "").strip()
        if not oid:
            continue
        refs: list[str] = []
        for key in (
            "requirement",
            "requirements",
            "requirement_ref",
            "requirement_refs",
            "source_requirement",
            "source_requirements",
            "derived_from",
            "parent_requirement",
        ):
            refs.extend(_str_items(obligation.get(key)))
        mapping[oid] = sorted(dict.fromkeys(refs))
    return mapping


def _task_owner_module(task: dict[str, Any]) -> str:
    owner = task.get("owner") if isinstance(task.get("owner"), dict) else {}
    for value in (
        task.get("owner_module"),
        owner.get("module"),
        task.get("module"),
        owner.get("file"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _job_type_for_task(task: dict[str, Any]) -> str:
    values = " ".join(
        [
            str(task.get("next_action_kind") or ""),
            str(task.get("kind") or ""),
            str(task.get("phase") or ""),
            str(task.get("agent_type") or ""),
            str(task.get("summary") or ""),
            " ".join(_str_items(task.get("required_evidence"))),
            " ".join(_str_items(task.get("allowed_write_paths"))),
        ]
    ).lower()
    evidence_family = str(task.get("evidence_family") or "").lower()
    if "record_parent_closure" in values or str(task.get("kind") or "") == "closure":
        return "VALIDATION_RECORD_JOB"
    if "checkpoint" in values or "gate" in values or "signoff" in values:
        return "GATE_REVIEW_JOB"
    if "target_lock" in values or "scope_lock" in values:
        return "TARGET_LOCK_JOB"
    if "rtl" in values:
        return "RTL_IMPLEMENT_JOB"
    if evidence_family == "formal" or "formal" in values or "assertion" in values or "proof" in values:
        return "FORMAL_ASSERTION_JOB"
    if evidence_family in {"sim", "cov"} or "scoreboard" in values or "coverage" in values or "sim/" in values:
        return "TB_SCOREBOARD_COVERAGE_JOB"
    if "produce_evidence" in values or "triage" in values or "merge_evidence" in values:
        return "STALE_REFRESH_JOB"
    if "author_obligations" in values or "planning" in values or "contract" in values:
        return "WRITE_CONTRACT_JOB"
    return "STALE_REFRESH_JOB"


def _task_to_candidate(ip: Path, task: dict[str, Any], requirement_map: dict[str, list[str]]) -> dict[str, Any]:
    obligation = str(task.get("obligation") or "").strip()
    requirements = _str_items(task.get("requirements")) or requirement_map.get(obligation, [])
    job_type = _job_type_for_task(task)
    boundary = JOB_BOUNDARY.get(job_type, "evidence")
    return {
        "task_id": str(task.get("task_id") or _safe_filename(str(task.get("summary") or job_type))),
        "job_type": job_type,
        "boundary_stage": boundary,
        "requirements": requirements,
        "obligations": [obligation] if obligation else _str_items(task.get("obligations")),
        "owner_module": _task_owner_module(task),
        "contracts": _str_items(task.get("contracts")),
        "required_evidence": _str_items(task.get("required_evidence")),
        "dispatch_profile": _dispatch_profile(job_type),
        "can_execute": JOB_DEFAULT_MODE.get(job_type) == "execute",
        "task": task,
    }


def _pseudo_task_from_next_action(action: dict[str, Any]) -> dict[str, Any]:
    next_action = action.get("next_action") if isinstance(action.get("next_action"), dict) else {}
    return {
        "task_id": str(next_action.get("kind") or action.get("status") or "next_action"),
        "kind": str(next_action.get("kind") or ""),
        "phase": str(action.get("stage") or ""),
        "next_action_kind": str(next_action.get("kind") or ""),
        "summary": str(next_action.get("summary") or ""),
        "obligation": str(action.get("active_obligation") or ""),
        "contracts": _str_items(action.get("active_contracts")),
        "required_evidence": _str_items(next_action.get("required_evidence")),
        "owner": action.get("owner") if isinstance(action.get("owner"), dict) else {},
    }


def _ready_candidates(ip: Path, action: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = [task for task in action.get("ready_tasks", []) if isinstance(task, dict)]
    if not tasks:
        next_action = action.get("next_action") if isinstance(action.get("next_action"), dict) else {}
        if str(next_action.get("kind") or "").strip():
            tasks = [_pseudo_task_from_next_action(action)]
    requirement_map = _obligation_requirements(ip)
    return [_task_to_candidate(ip, task, requirement_map) for task in tasks]


def _dispatch_profile(job_type: str) -> str:
    if job_type == "RTL_IMPLEMENT_JOB":
        return "rtl"
    if job_type in {"TB_SCOREBOARD_COVERAGE_JOB", "SIM_RUN_JOB"}:
        return "tb"
    if job_type == "FORMAL_ASSERTION_JOB":
        return "formal"
    if job_type == "VALIDATION_RECORD_JOB":
        return "record"
    if job_type == "GATE_REVIEW_JOB":
        return "gate"
    return "planning"


def _matches_policy(candidate: dict[str, Any], policy: dict[str, Any]) -> bool:
    if policy.get("requirements"):
        if not set(_str_items(candidate.get("requirements"))) & set(_str_items(policy.get("requirements"))):
            return False
    if policy.get("obligations"):
        if not set(_str_items(candidate.get("obligations"))) & set(_str_items(policy.get("obligations"))):
            return False
    if policy.get("owner_modules"):
        owner = str(candidate.get("owner_module") or "")
        if owner not in set(_str_items(policy.get("owner_modules"))):
            return False
    if policy.get("job_types"):
        if str(candidate.get("job_type") or "").upper() not in set(_str_items(policy.get("job_types"))):
            return False
    return True


def build_bounded_plan(ip: Path, action: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    candidates = _ready_candidates(ip, action)
    until = str(policy.get("until") or "all")
    until_order = BOUNDARY_ORDER.get(until, BOUNDARY_ORDER["all"])
    in_boundary = [
        item
        for item in candidates
        if BOUNDARY_ORDER.get(str(item.get("boundary_stage") or "evidence"), 0) <= until_order
    ]
    filtered = [item for item in in_boundary if _matches_policy(item, policy)]
    limit = _int_or_default(policy.get("limit"), 1, minimum=1)
    selected = filtered[:limit]
    stop_reason = ""
    if not candidates:
        stop_reason = "no_runnable_batch"
    elif not in_boundary:
        stop_reason = "boundary_reached"
    elif not filtered:
        stop_reason = "no_runnable_batch"

    batch = _batch_from_candidates(selected, policy) if selected else None
    return {
        "schema_version": SCHEMA_PLAN,
        "status": "pass",
        "policy": loop_policy_storage(policy),
        "recommended_batch": batch,
        "filtered_counts": {
            "total_ready": len(candidates),
            "within_boundary": len(in_boundary),
            "after_scope_filter": len(filtered),
            "selected": len(selected),
            "outside_boundary": max(len(candidates) - len(in_boundary), 0),
        },
        "stop_reason": stop_reason,
    }


def _batch_from_candidates(candidates: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    first = candidates[0]
    tasks = [
        {
            "task_id": item["task_id"],
            "job_type": item["job_type"],
            "boundary_stage": item["boundary_stage"],
            "requirements": item["requirements"],
            "obligations": item["obligations"],
            "owner_module": item["owner_module"],
            "contracts": item["contracts"],
            "required_evidence": item["required_evidence"],
            "dispatch_profile": item["dispatch_profile"],
            "can_execute": item["can_execute"],
        }
        for item in candidates
    ]
    requirements = sorted({req for item in tasks for req in _str_items(item.get("requirements"))})
    obligations = sorted({obl for item in tasks for obl in _str_items(item.get("obligations"))})
    contracts = sorted({contract for item in tasks for contract in _str_items(item.get("contracts"))})
    evidence = sorted({ref for item in tasks for ref in _str_items(item.get("required_evidence"))})
    batch_seed = {
        "policy": loop_policy_storage(policy),
        "tasks": [task["task_id"] for task in tasks],
    }
    job_type = str(first.get("job_type") or "")
    return {
        "schema_version": "oag_recommended_batch.v1",
        "batch_id": f"batch.{_hash_value(batch_seed)[:16]}",
        "job_type": job_type,
        "boundary_stage": str(first.get("boundary_stage") or ""),
        "requirements": requirements,
        "obligations": obligations,
        "owner_module": str(first.get("owner_module") or ""),
        "contracts": contracts,
        "required_evidence": evidence,
        "dispatch_profile": str(first.get("dispatch_profile") or ""),
        "can_execute": all(bool(item.get("can_execute")) for item in tasks) and JOB_DEFAULT_MODE.get(job_type) == "execute",
        "default_mode": JOB_DEFAULT_MODE.get(job_type, "dispatch"),
        "stop_after_batch": len(tasks) >= _int_or_default(policy.get("limit"), 1, minimum=1),
        "tasks": tasks,
    }


def loop_decision_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    batch = plan.get("recommended_batch") if isinstance(plan.get("recommended_batch"), dict) else None
    return {
        "schema_version": "oag_loop_hook_decision.v1",
        "decision": "continue" if batch else "stop",
        "reason": "batch_available" if batch else str(plan.get("stop_reason") or "no_runnable_batch"),
        "loop_policy": plan.get("policy") if isinstance(plan.get("policy"), dict) else {},
        "recommended_batch": batch,
        "plan": plan,
    }


def loop_decision_path(ip: Path, run_id: str) -> Path:
    runs_dir = oag_paths.legacy_or_hidden(ip, "ontology/runs")
    return runs_dir / _safe_filename(run_id) / "loop_decision.json"


def write_loop_decision(ip: Path, run_id: str, payload: dict[str, Any]) -> Path:
    path = loop_decision_path(ip, run_id)
    body = {
        "schema_version": SCHEMA_DECISION,
        "run_id": run_id,
        "payload": payload,
    }
    _write_json_file(path, body)
    return path


def active_loop_fields(arguments: dict[str, Any]) -> bool:
    return bool(_raw_policy_from_arguments(arguments))
