#!/usr/bin/env python3
"""Run OAG auto-research through resumable Claude Code exec sessions.

This wrapper keeps the durable OAG record in files instead of relying on chat
memory. It starts a fresh `claude exec` session or resumes an exact session with
`claude exec resume`, captures JSONL events, and records a manifest that proves
whether native `spawn_agent` collaboration was observed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_RUN_ROOT = PROJECT_ROOT / ".claude" / "runs" / "auto_research"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return clean[:80] or "auto-research"


def _resolve_ip(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except Exception:
        return str(path)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _claude_version() -> str:
    proc = subprocess.run(["claude", "--version"], text=True, capture_output=True, check=False)
    return (proc.stdout or proc.stderr).strip()


def _build_prompt(args: argparse.Namespace, ip: Path) -> str:
    ip_rel = _rel(ip)
    objective = args.objective.strip() or f"Run OAG auto research for {ip_rel}."
    if args.allow_ip_writes:
        subagent_policy = (
            "For write-producing research, create an OAG dispatch record before spawning an OAG custom researcher, "
            "then include dispatch_id, dispatch_path, allowed write paths, allowed tool side effects, and receipt path in the child assignment."
        )
        write_policy = "Research may write only bounded OAG research/report artifacts that are explicitly named in the final summary."
    else:
        subagent_policy = (
            "For read-only discovery, prefer a built-in explorer-style native subagent, not an OAG custom/write-capable role that requires dispatch metadata."
        )
        write_policy = "Read and analyze only; do not edit the IP directory or product files. Put results in the final response for the wrapper manifest."
    return "\n".join(
        [
            "Read-only subagent capability probe for exec-mode auto research.",
            "Use a native Claude Code subagent. Spawn one built-in explorer subagent.",
            f"Child task: from product root `{PROJECT_ROOT}`, run the two preflight checks below, inspect only `{ip_rel}` top-level files, and reply with `FINAL_AUTO_RESEARCH_SUMMARY`.",
            "Wait for the child result, then synthesize the parent `FINAL_AUTO_RESEARCH_SUMMARY`.",
            "Do not edit files. Do not run parent-side shell commands before the native spawn attempt.",
            "",
            f"Product root: {PROJECT_ROOT}",
            f"IP directory: {ip_rel}",
            f"Objective: {objective}",
            "",
            "Execution mode:",
            "- This is a resumable Claude Code exec run. Treat repository artifacts, locked files, manifests, receipts, hashes, and checked files as the source of truth.",
            "- Do not rely on compacted conversation memory as source truth.",
            "- Keep the work bounded to auto research and evidence discovery unless the objective explicitly asks for implementation.",
            "",
            "Native subagent requirement:",
            "- Use native Claude Code subagents only for research sharding.",
            f"- {subagent_policy}",
            "- Spawn at least one native subagent for bounded discovery.",
            "- The native operation may appear as `multi_agent_v1.spawn_agent` or as a Claude Code CLI/App `spawn_agent` collaboration event.",
            "- Do not decide native-spawn availability from the visible callable tool namespace alone.",
            "- Do not run `omo run --agent`, Python worker role-play, shell wrappers, or manual child-role impersonation as a substitute.",
            "- Only if an actual native spawn attempt fails or the runtime returns a spawn-unavailable error, report the observed native-spawn blocker and stop.",
            "",
            "Preflight:",
            "- `python3 .claude/scripts/oag_agent_catalog_check.py` from the product root, not from inside the IP directory.",
            "- `python3 .claude/scripts/oag_claude_config_doctor.py --include-omo-plugin-features` from the product root, not from inside the IP directory.",
            "- Keep checks small; do not run full smoke/eval unless required by the objective.",
            "",
            "Research policy:",
            f"- {write_policy}",
            "- Do not create or substantially edit RTL, TB, sim, lint, coverage, formal, SDC, signoff, or implementation filelist artifacts.",
            "- If the IP is locked, protected implementation/verification/report writes require native OAG subagent dispatch and receipt.",
            "- Keep external reference repositories read-only if referenced.",
            "",
            "Final response format:",
            "FINAL_AUTO_RESEARCH_SUMMARY",
            "status: PASS | BLOCKED | INCONCLUSIVE",
            "session_continuation_notes: <what a future exec resume should use>",
            "native_spawn: <observed spawn_agent/wait result or blocker>",
            "changed_paths: <paths or none>",
            "evidence_paths: <paths or none>",
            "ranked_next_actions: <ordered next actions>",
            "blockers: <blockers or none>",
        ]
    )


def _command(args: argparse.Namespace, prompt: str) -> list[str]:
    if args.session_id and args.last:
        raise SystemExit("--session-id and --last are mutually exclusive")

    cmd = ["claude", "exec"]
    if args.session_id or args.last:
        cmd.append("resume")

    cmd.extend(["--json"])
    if args.model:
        cmd.extend(["-m", args.model])
    if args.reasoning_effort:
        cmd.extend(["-c", f"model_reasoning_effort={json.dumps(args.reasoning_effort)}"])
    cmd.extend(["-c", f"agents.max_depth={int(args.max_depth)}"])
    cmd.extend(["-c", f"agents.max_threads={int(args.max_threads)}"])
    if args.yolo:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    if args.bypass_hook_trust:
        cmd.append("--dangerously-bypass-hook-trust")

    if args.session_id or args.last:
        if args.last:
            cmd.append("--last")
        else:
            cmd.append(args.session_id)
    else:
        cmd.extend(["-C", str(PROJECT_ROOT)])

    cmd.append(prompt)
    return cmd


def _parse_events(stdout: str) -> dict[str, Any]:
    thread_id = ""
    agent_messages: list[str] = []
    spawn_started = 0
    spawn_completed = 0
    wait_completed = 0
    child_messages: list[str] = []
    parse_errors = 0
    event_count = 0

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except Exception:
            parse_errors += 1
            continue
        if not isinstance(event, dict):
            continue
        event_count += 1
        if event.get("type") == "thread.started":
            thread_id = str(event.get("thread_id") or thread_id)
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") == "agent_message":
            text = str(item.get("text") or "")
            if text:
                agent_messages.append(text)
        if item.get("type") == "collab_tool_call":
            tool = str(item.get("tool") or "")
            status = str(item.get("status") or "")
            if tool == "spawn_agent":
                if status == "in_progress":
                    spawn_started += 1
                if status == "completed":
                    spawn_completed += 1
            if tool == "wait" and status == "completed":
                wait_completed += 1
            states = item.get("agents_states")
            if isinstance(states, dict):
                for state in states.values():
                    if isinstance(state, dict) and state.get("message"):
                        child_messages.append(str(state["message"]))

    final_message = agent_messages[-1] if agent_messages else ""
    blocker_text = "\n".join([final_message, *child_messages]).lower()
    blocker = any(token in blocker_text for token in ("blocked", "unavailable", "cannot spawn", "spawn attempt fails"))
    return {
        "thread_id": thread_id,
        "event_count": event_count,
        "parse_errors": parse_errors,
        "agent_messages": agent_messages[-8:],
        "final_message": final_message,
        "spawn_agent_started": spawn_started,
        "spawn_agent_completed": spawn_completed,
        "wait_completed": wait_completed,
        "child_messages": child_messages[-8:],
        "native_spawn_observed": spawn_started > 0 or spawn_completed > 0,
        "blocker_detected": blocker,
    }


def _status(returncode: int, summary: dict[str, Any]) -> str:
    if returncode != 0:
        return "fail"
    if summary.get("blocker_detected"):
        return "blocked"
    if not summary.get("native_spawn_observed"):
        return "blocked_no_native_spawn_observed"
    return "pass"


def run(args: argparse.Namespace) -> dict[str, Any]:
    ip = _resolve_ip(args.ip_dir)
    run_root = Path(args.run_root).expanduser().resolve() if args.run_root else DEFAULT_RUN_ROOT
    run_id = f"{_now_label()}_{_slug(ip.name)}"
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(args, ip)
    command = _command(args, prompt)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    manifest: dict[str, Any] = {
        "schema_version": "oag_exec_auto_research_manifest.v1",
        "created_at": _now(),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "project_root": str(PROJECT_ROOT),
        "ip_dir": str(ip),
        "ip_dir_relative": _rel(ip),
        "resume": {
            "session_id": args.session_id,
            "last": bool(args.last),
        },
        "claude_version": _claude_version(),
        "prompt_path": str(prompt_path),
        "prompt_sha256": _sha256_text(prompt),
        "dry_run": bool(args.dry_run),
        "allow_ip_writes": bool(args.allow_ip_writes),
        "command_preview": command[:-1] + ["<prompt>"],
    }

    if args.dry_run:
        manifest.update(
            {
                "status": "dry_run",
                "returncode": None,
                "event_summary": {},
            }
        )
        (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest

    started = _now()
    try:
        proc = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env={**os.environ},
            text=True,
            capture_output=True,
            timeout=args.timeout_s if args.timeout_s > 0 else None,
            check=False,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        returncode = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else f"timeout after {args.timeout_s}s"
        returncode = 124
        timed_out = True

    (run_dir / "events.jsonl").write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    summary = _parse_events(stdout)
    manifest.update(
        {
            "started_at": started,
            "finished_at": _now(),
            "returncode": returncode,
            "timed_out": timed_out,
            "status": "timeout" if timed_out else _status(returncode, summary),
            "events_path": str(run_dir / "events.jsonl"),
            "stderr_path": str(run_dir / "stderr.txt"),
            "event_summary": summary,
        }
    )
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run resumable Claude Code exec-mode OAG auto research.")
    parser.add_argument("--ip-dir", required=True, help="IP directory to research, relative to the product root unless absolute")
    parser.add_argument("--objective", default="", help="Bounded research objective")
    parser.add_argument("--session-id", default="", help="Exact Claude Code session/thread id to resume with `claude exec resume`")
    parser.add_argument("--last", action="store_true", help="Resume the most recent recorded session; exact --session-id is safer")
    parser.add_argument("--run-root", default="", help="Directory for run manifests and JSONL traces")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-threads", type=int, default=4)
    parser.add_argument("--timeout-s", type=float, default=1800.0)
    parser.add_argument("--allow-ip-writes", action="store_true", help="Allow Claude Code to write bounded research/report artifacts")
    parser.add_argument("--yolo", action="store_true", help="Pass --dangerously-bypass-approvals-and-sandbox to claude exec")
    parser.add_argument("--bypass-hook-trust", action="store_true", help="Pass --dangerously-bypass-hook-trust to claude exec")
    parser.add_argument("--dry-run", action="store_true", help="Write prompt and manifest without invoking Claude Code")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['status']} {result['run_dir']}")
    return 0 if result.get("status") in {"pass", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
