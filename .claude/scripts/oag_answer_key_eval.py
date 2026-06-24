#!/usr/bin/env python3
"""Answer-key evaluator for OAG control-loop behavior.

This runner complements oag_eval.py. Instead of encoding every expectation as
Python assertions, it reads JSON cases with input prompts and expected observed
fields, then runs the real OAG hooks/CLI against fresh temporary IP fixtures.
The report includes correctness, duration, and simple loop-efficiency metrics.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import oag_paths  # noqa: E402
import smoke_test  # noqa: E402


DEFAULT_SUITE = SCRIPT_DIR.parent / "evals" / "oag_control_cases.json"


def _load_suite(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError(f"invalid answer-key suite: {path}")
    return data


def _hook_blocked(stdout: str) -> bool:
    if not stdout.strip():
        return False
    try:
        payload = json.loads(stdout)
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("decision") == "block"


def _context_configured(stdout: str) -> bool:
    return "OAG RUN LIMIT CONFIGURED" in smoke_test.hook_context(
        type("HookProc", (), {"stdout": stdout})()  # small duck-typed adapter
    )


def _run_limit_case(case: dict[str, Any], root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / str(case["id"]))
    started = smoke_test.call(
        {
            "tool": "oag.run.start",
            "arguments": {
                "ip_dir": str(ip),
                "stage": "sim",
                "intent": f"answer-key {case['id']}",
                "actor": {"kind": "ai", "id": "claude", "surface": "answer-key-eval"},
            },
        }
    )
    run_id = str(started["result"]["run_id"])
    prompt = str((case.get("input") or {}).get("prompt") or "")
    context_proc = smoke_test.context_hook({"ip_dir": str(ip), "prompt": prompt})
    stop = smoke_test.call({"tool": "oag.stop_check", "arguments": {"ip_dir": str(ip), "run_id": run_id}})
    stop_proc = smoke_test.stop_gate({"ip_dir": str(ip), "run_id": run_id})
    policy = stop["result"].get("policy") if isinstance(stop["result"].get("policy"), dict) else {}
    return {
        "ip": str(ip),
        "run_id": run_id,
        "configured_limit": policy.get("hook_auto_continue_until"),
        "context_configured": _context_configured(context_proc.stdout),
        "context_returncode": context_proc.returncode,
        "stop_should_continue": stop["result"].get("should_continue"),
        "stop_reason": stop["result"].get("reason"),
        "next_action_stage": policy.get("next_action_stage"),
        "stop_hook_blocked": _hook_blocked(stop_proc.stdout),
        "stop_hook_returncode": stop_proc.returncode,
        "stop_hook_stdout_bytes": len(stop_proc.stdout.encode("utf-8")),
    }


def _compile_fresh_skip_case(case: dict[str, Any], root: Path) -> dict[str, Any]:
    ip = smoke_test.make_ip(root / str(case["id"]))
    first = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    second = smoke_test.call({"tool": "oag.compile", "arguments": {"ip_dir": str(ip)}})
    manifest = oag_paths.legacy_or_hidden(ip, "ontology/generated/compile_manifest.json")
    return {
        "ip": str(ip),
        "first_status": first["result"].get("status"),
        "first_skipped": first["result"].get("skipped"),
        "second_status": second["result"].get("status"),
        "second_skipped": second["result"].get("skipped"),
        "manifest_written": manifest.is_file(),
        "manifest": str(manifest),
    }


def _score_case(
    case: dict[str, Any],
    observed: dict[str, Any],
    duration_s: float,
    *,
    speed_scale: float = 1.0,
) -> tuple[float, list[str]]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    mismatches: list[str] = []
    correct = 0
    total = 0
    for key, expected_value in expected.items():
        total += 1
        actual = observed.get(key)
        if actual == expected_value:
            correct += 1
        else:
            mismatches.append(f"{key}: expected {expected_value!r}, observed {actual!r}")
    speed = case.get("speed") if isinstance(case.get("speed"), dict) else {}
    max_duration = speed.get("max_duration_s")
    if max_duration is not None:
        total += 1
        try:
            effective_max_duration = float(max_duration) * speed_scale
            if duration_s <= effective_max_duration:
                correct += 1
            else:
                mismatches.append(
                    f"duration_s: expected <= {effective_max_duration:.3f}, observed {duration_s:.3f}"
                )
        except Exception:
            mismatches.append(f"duration_s: invalid max_duration_s {max_duration!r}")
    return (correct / total if total else 1.0), mismatches


def _run_case(case: dict[str, Any], root: Path, *, speed_scale: float = 1.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        kind = str(case.get("kind") or "")
        if kind == "run_limit_prompt":
            observed = _run_limit_case(case, root)
        elif kind == "compile_fresh_skip":
            observed = _compile_fresh_skip_case(case, root)
        else:
            raise ValueError(f"unknown case kind: {kind}")
        duration_s = round(time.perf_counter() - started, 4)
        score, mismatches = _score_case(case, observed, duration_s, speed_scale=speed_scale)
        return {
            "id": str(case.get("id") or ""),
            "kind": kind,
            "ok": not mismatches,
            "score": round(score, 4),
            "duration_s": duration_s,
            "observed": observed,
            "expected": case.get("expected") or {},
            "mismatches": mismatches,
        }
    except Exception as exc:
        duration_s = round(time.perf_counter() - started, 4)
        return {
            "id": str(case.get("id") or ""),
            "kind": str(case.get("kind") or ""),
            "ok": False,
            "score": 0.0,
            "duration_s": duration_s,
            "observed": {},
            "expected": case.get("expected") or {},
            "mismatches": [f"{type(exc).__name__}: {exc}"],
        }


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        f"OAG answer-key evaluation: {report['passed']}/{report['total']} passed, score={report['score']:.3f}",
        f"temp_root: {report['temp_root']}",
    ]
    for case in report["cases"]:
        mark = "PASS" if case["ok"] else "FAIL"
        lines.append(f"- {mark} {case['id']} score={case['score']:.3f} duration={case['duration_s']}s")
        for mismatch in case["mismatches"]:
            lines.append(f"  mismatch: {mismatch}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=str(DEFAULT_SUITE), help="answer-key suite JSON path")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--keep-temp", action="store_true", help="keep temporary IP fixtures")
    parser.add_argument(
        "--speed-scale",
        type=float,
        default=1.0,
        help="multiply per-case max_duration_s thresholds; useful for full smoke runs on loaded hosts",
    )
    args = parser.parse_args(argv)

    suite = _load_suite(Path(args.suite))
    if args.keep_temp:
        temp_dir = tempfile.mkdtemp(prefix="oag-answer-key-")
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="oag-answer-key-")
        temp_dir = cleanup.name

    root = Path(temp_dir)
    cases = [_run_case(case, root, speed_scale=max(0.0, args.speed_scale)) for case in suite["cases"]]
    passed = sum(1 for case in cases if case["ok"])
    score = sum(float(case["score"]) for case in cases) / len(cases) if cases else 1.0
    report = {
        "schema_version": "oag_answer_key_report.v1",
        "suite": suite.get("name") or str(args.suite),
        "ok": passed == len(cases),
        "score": round(score, 4),
        "passed": passed,
        "failed": len(cases) - passed,
        "total": len(cases),
        "temp_root": temp_dir,
        "cases": cases,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_text(report))

    if cleanup is not None:
        cleanup.cleanup()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
