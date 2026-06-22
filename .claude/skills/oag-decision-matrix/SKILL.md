---
name: oag-decision-matrix
description: Use when OAG hardware IP work needs lock-blocking product or design choices captured, seeded from a profile, audited, or kept separate from locked truth before requirements, RTL, TB, or closure.
---

# OAG Decision Matrix

Use this skill after deep semantic intake and before requirement lock when an
IP has unresolved architecture, interface, protocol, storage, IRQ, error/drop,
or verification choices.

## Rules

- Treat recommendations as draft guidance, not locked truth.
- Keep undecided rows as `status: unresolved` or `proposed`.
- Use `status: decided` only for explicit user/spec confirmation.
- Use `status: waived` only with `waiver_reason` and risk.
- Mark implementation-affecting rows as `lock_required: true`.
- Do not use the decision matrix to silently choose RTL/TB behavior.

## Commands

Seed profile decisions:

```bash
python3 .claude/scripts/oag_decision_matrix_generate.py --ip-dir <ip> --profile <profile> --write --json
```

For protocol packet IPs, start with `--profile protocol-packet-ip`.
For MCTP RX, use `--profile mctp-rx`.

Audit lock readiness:

```bash
python3 .claude/scripts/oag_lock_readiness_check.py --ip-dir <ip> --json
```

## Output

Maintain `ontology/decision_matrix.yaml`. Every lock-blocking row should name
its question, status, owner, recommended answer if any, affected requirements
or contracts, and verification implications.
