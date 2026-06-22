---
name: oag-evidence-closure
description: Use when OAG simulation, scoreboard, coverage, assertion, formal, validation, gate, or completion evidence must be audited for freshness, traceability, proof strength, and closure readiness.
---

# OAG Evidence Closure

Use this skill after implementation or verification artifacts exist. It checks
whether evidence can support closure; it does not treat passing tests as
closure by itself.

## Rules

- Evidence must trace through Requirement -> Obligation -> Contract ->
  Evidence -> Validation -> Decision.
- Scoreboard rows need scenario IDs, contract refs, independent
  `expected_source`, DUT-facing `observed_source`, and explicit pass/fail.
- Coverage contributes only when tied to passing checks and known contracts.
- Evidence added after gate PASS makes the gate stale.
- Gate review and completion decisions must use current artifact hashes.

## Commands

Run the closure audit set:

```bash
python3 .claude/scripts/oag_trace_graph_check.py --ip-dir <ip> --require-locked --json
python3 .claude/scripts/oag_verification_plan_check.py --ip-dir <ip> --require-locked --json
python3 .claude/scripts/oag_closure_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.check","arguments":{"ip_dir":"<ip>"}}'
```

Before claiming completion:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.decide","arguments":{"ip_dir":"<ip>","action":"claim_complete","record_decision":true}}'
```

If any command blocks, report the blocker instead of claiming closure.
