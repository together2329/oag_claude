#!/usr/bin/env python3
"""Create a draft deep semantic intake report for compressed IP intent."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_").lower()
    return text or "intake"


def run_decision_generator(ip_dir: Path, *, profile: str, owner: str) -> dict[str, Any]:
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "oag_decision_matrix_generate.py"),
            "--ip-dir",
            str(ip_dir),
            "--profile",
            profile,
            "--owner",
            owner,
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"status": "fail", "errors": [proc.stderr or proc.stdout]}
    return json.loads(proc.stdout)


def hidden_implications(prompt: str, *, profile: str) -> list[str]:
    lower = prompt.lower()
    implications: list[str] = []
    if "axi" in lower:
        implications.extend(
            [
                "AXI profile, channel subset, data/address width, burst policy, and outstanding behavior must be explicit.",
                "AXI byte-lane and WSTRB policy must be explicit before parser or storage RTL.",
            ]
        )
    if "tlp" in lower or "pcie" in lower:
        implications.extend(
            [
                "TLP boundary, byte ordering, length matching, and malformed ingress policy must be explicit.",
                "PCIe transport binding support profile must be separated from unsupported/out-of-v0 features.",
            ]
        )
    if "mctp" in lower or profile == "mctp-rx":
        implications.extend(
            [
                "MCTP header version, EID acceptance, Source EID/TO/MsgTag context key, sequence policy, and interleaving policy must be explicit.",
                "Single-packet and multi-packet assembly support must be separately locked.",
            ]
        )
    if "sram" in lower:
        implications.extend(
            [
                "SRAM descriptor/payload layout, descriptor valid ordering, and FW ownership must be explicit.",
                "Partial or dropped messages must not be exposed as completed descriptors.",
            ]
        )
    if "irq" in lower or "interrupt" in lower:
        implications.append("IRQ level/pulse, mask, status, and clear semantics must be explicit.")
    if not implications:
        implications.append("Boundary, interface, reset, error policy, and verification scenarios must be explicit before lock.")
    return implications


def ambiguity_questions(prompt: str, *, profile: str) -> list[str]:
    if profile == "mctp-rx" or "mctp" in prompt.lower():
        return [
            "Which AXI profile, data width, address width, and ingress region are in scope?",
            "Does one AXI write burst represent exactly one PCIe TLP, and does WLAST mark TLP end?",
            "Which DSP0238 support subset is in v0 scope?",
            "Is assembly context key Source EID + TO + Msg Tag after destination acceptance?",
            "What is the 16th-context overflow policy?",
            "What SRAM descriptor/payload layout and FW ownership model is locked?",
            "What IRQ/status/error/drop matrix is locked?",
        ]
    return [
        "What is the exact interface boundary?",
        "What is the supported feature profile?",
        "What are the reset/default semantics?",
        "What error/drop/status policies are required?",
        "Which verification scenarios prove the locked behavior?",
    ]


def build_markdown(ip_dir: Path, *, topic: str, prompt: str, profile: str, decision_result: dict[str, Any]) -> str:
    decisions = decision_result.get("rows") if isinstance(decision_result.get("rows"), list) else []
    lines = [
        f"# Deep Semantic Intake: {topic}",
        "",
        f"- ip: `{ip_dir.name}`",
        f"- profile: `{profile}`",
        f"- status: draft",
        "",
        "## Source Claim",
        "",
        "```text",
        prompt.strip(),
        "```",
        "",
        "## Hidden Implications",
        "",
    ]
    lines.extend(f"- {item}" for item in hidden_implications(prompt, profile=profile))
    lines.extend(["", "## Ambiguity Questions", ""])
    lines.extend(f"- {item}" for item in ambiguity_questions(prompt, profile=profile))
    lines.extend(["", "## Candidate Lock Decisions", ""])
    for row in decisions:
        if not isinstance(row, dict):
            continue
        lines.append(f"- `{row.get('id')}`: {row.get('question')} Recommended draft: {row.get('recommended')}")
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "This report is draft intake. It is not locked truth and does not authorize RTL, TB, validation, gate review, or closure.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def create_intake(ip_dir: Path, *, topic: str, prompt: str, profile: str, owner: str) -> dict[str, Any]:
    decision_result = run_decision_generator(ip_dir, profile=profile, owner=owner)
    out_dir = ip_dir / "req" / "deep_semantic_intake"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{now_stamp()}_{slug(topic)}.md"
    path.write_text(build_markdown(ip_dir, topic=topic, prompt=prompt, profile=profile, decision_result=decision_result), encoding="utf-8")
    return {
        "schema_version": "oag_deep_semantic_intake.v1",
        "status": "pass",
        "ip": ip_dir.name,
        "profile": profile,
        "topic": topic,
        "path": str(path),
        "decision_seed": decision_result,
        "hidden_implications": hidden_implications(prompt, profile=profile),
        "ambiguity_questions": ambiguity_questions(prompt, profile=profile),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip-dir", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--profile", default="protocol-packet-ip")
    parser.add_argument("--owner", default="unassigned")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = create_intake(Path(args.ip_dir), topic=args.topic, prompt=args.prompt, profile=args.profile, owner=args.owner)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"PASS wrote {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
