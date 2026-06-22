#!/usr/bin/env python3
"""Shared helpers for OAG Claude Code hook adapters."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]  # .claude/
PROJECT = ROOT.parent
INACTIVE_RUN_STATUSES = {"complete", "parked"}

STAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "req": ("req", "requirement", "requirements", "interview", "locked truth"),
    "rtl": ("rtl", "verilog", "systemverilog", "module", "implementation"),
    "tb": ("tb", "testbench", "scoreboard", "stimulus"),
    "sim": ("sim", "simulation", "verilator", "cocotb"),
    "lint": ("lint",),
    "formal": ("formal", "assertion", "sva"),
    "coverage": ("coverage", "coverpoint", "cov"),
    "signoff": ("signoff", "closure", "complete", "claim_complete"),
}

OAG_TRIGGER_KEYWORDS = (
    "oag",
)

APPROVAL_ONLY_RE = re.compile(
    r"^\s*(승인|승인합니다|approve|approved|approval|ok|okay|yes|y|확인|동의|허가)\s*[.!?。]*\s*$",
    re.IGNORECASE,
)
RUN_LIMIT_COMMAND_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?"
    r"(?P<stage>requirements?|req|요구사항|rtl|lint|tb|testbench|formal|sim|simulation|시뮬|시뮬레이션|coverage|cov|signoff|사인오프)"
    r"\s*(?:까지만|까지|만)\s*[.!?。]*\s*$",
    re.IGNORECASE,
)
RUN_LIMIT_ALL_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?(?:끝까지|쭉쭉\s*다|전부|전체|all|full)\s*[.!?。]*\s*$",
    re.IGNORECASE,
)
RUN_LIMIT_NONE_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?(?:자동\s*진행\s*(?:꺼|끄기|중지|off)|auto\s*continue\s*off|none)\s*[.!?。]*\s*$",
    re.IGNORECASE,
)
RUN_LIMIT_ALIASES = {
    "req": "requirements",
    "requirement": "requirements",
    "requirements": "requirements",
    "요구사항": "requirements",
    "rtl": "rtl",
    "lint": "lint",
    "tb": "tb",
    "testbench": "tb",
    "formal": "formal",
    "sim": "sim",
    "simulation": "sim",
    "시뮬": "sim",
    "시뮬레이션": "sim",
    "coverage": "coverage",
    "cov": "coverage",
    "signoff": "signoff",
    "사인오프": "signoff",
}


def read_payload() -> dict[str, Any]:
    try:
        raw = os.read(0, 1_000_000).decode("utf-8")
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def first_text(payload: Any, keys: tuple[str, ...]) -> str:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for value in payload.values():
            found = first_text(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = first_text(value, keys)
            if found:
                return found
    return ""


def prompt_text(payload: dict[str, Any]) -> str:
    return first_text(payload, ("prompt", "user_prompt", "userPrompt", "message", "content", "input"))


def project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT / path
    return path.resolve()


def is_ip_dir(path: Path) -> bool:
    return (path / "ontology").is_dir() and (
        (path / "ontology" / "requirements.yaml").is_file()
        or (path / "ontology" / "ip.yaml").is_file()
        or (path / "req" / "locked_truth.md").is_file()
    )


def scan_ip_dirs() -> list[Path]:
    ips: list[Path] = []
    for child in sorted(PROJECT.iterdir()):
        if child.is_dir() and is_ip_dir(child):
            ips.append(child.resolve())
    return ips


def active_run_ips() -> list[Path]:
    ips: list[Path] = []
    for active in PROJECT.glob("*/ontology/runs/active_run.json"):
        try:
            data = json.loads(active.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        status = str(data.get("status") or "") if isinstance(data, dict) else ""
        run_id = str(data.get("run_id") or "") if isinstance(data, dict) else ""
        if not status and run_id:
            state_path = active.parents[2] / "ontology" / "runs" / run_id / "run_state.json"
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                state = {}
            status = str(state.get("status") or "") if isinstance(state, dict) else ""
        if status in INACTIVE_RUN_STATUSES:
            continue
        ips.append(active.parents[2].resolve())
    return ips


def infer_stage(text: str, fallback: str = "") -> str:
    lower = text.lower()
    for stage, words in STAGE_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(word)}\b", lower) for word in words):
            return stage
    return fallback


def has_oag_work_signal(text: str) -> bool:
    lower = text.lower()
    return any(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(needle)}(?![A-Za-z0-9_-])", lower) for needle in OAG_TRIGGER_KEYWORDS)


def _is_approval_only(text: str) -> bool:
    return bool(APPROVAL_ONLY_RE.match(text or ""))


def parse_run_limit_command(text: str) -> str:
    prompt = text or ""
    if RUN_LIMIT_NONE_RE.match(prompt):
        return "none"
    if RUN_LIMIT_ALL_RE.match(prompt):
        return "all"
    match = RUN_LIMIT_COMMAND_RE.match(prompt)
    if not match:
        return ""
    return RUN_LIMIT_ALIASES.get(match.group("stage").lower(), "")


def _ip_name_in_prompt(ip_name: str, prompt: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_.-]){re.escape(ip_name.lower())}(?![A-Za-z0-9_.-])"
    return re.search(pattern, prompt.lower()) is not None


def target_ip_dirs(payload: dict[str, Any], *, require_signal: bool = True) -> list[Path]:
    prompt = prompt_text(payload)
    explicit = str(payload.get("ip_dir") or os.environ.get("OAG_IP_DIR") or "").strip()
    if explicit:
        path = project_path(explicit)
        return [path] if path.exists() else []

    matches = [ip for ip in scan_ip_dirs() if _ip_name_in_prompt(ip.name, prompt)]
    if matches:
        return matches if len(matches) == 1 else []

    if _is_approval_only(prompt):
        return []

    active = active_run_ips()
    if len(active) == 1 and (not require_signal or has_oag_work_signal(prompt)):
        return active
    return []


def hook_additional_context(text: str, hook_event: str = "UserPromptSubmit") -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": text,
        }
    }
