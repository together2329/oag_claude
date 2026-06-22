---
name: oag-authoring-packet
description: Use before locked OAG RTL, TB, or evidence implementation dispatch when role-specific generated authoring packets must be compiled, audited, or passed to native subagents instead of raw user prose.
---

# OAG Authoring Packet

Use this skill after lock readiness passes and before spawning RTL, TB, or
evidence-producing subagents.

## Rules

- RTL/TB agents consume authoring packets, not original natural-language prose.
- `rtl__*.json` packets carry implementation contract refs, behavior refs,
  cycle refs, interface refs, and PPA/CDC note requirements.
- `tb__*.json` packets carry scenarios, expected-source policy, scoreboard
  rows, coverage refs, and assertion/formal candidates.
- Do not edit files under `ontology/generated/authoring_packets/` by hand.
- If a packet is wrong, fix authored ontology and compile again.

## Commands

Generate packets:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.compile","arguments":{"ip_dir":"<ip>"}}'
```

Validate packets:

```bash
python3 .claude/scripts/oag_authoring_packet_check.py --ip-dir <ip> --require-packets --json
```

## Dispatch Use

When spawning a native OAG subagent, include the relevant packet path and keep
the dispatch allowed paths narrow. RTL dispatch should reference `rtl__*.json`.
TB dispatch should reference `tb__*.json`.
