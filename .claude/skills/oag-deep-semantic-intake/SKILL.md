---
name: oag-deep-semantic-intake
description: Use when a compressed hardware IP request or spec note must be decomposed into source claims, hidden implications, ambiguity rows, and lock-blocking decision candidates before requirements, RTL, or TB work.
---

# OAG Deep Semantic Intake

Use this skill before requirement lock when user input is compressed, such as
"I need mctp rx ip" or "AXI WDATA has the full PCIe TLP".

## Rules

- Preserve the original phrase as a source claim.
- Extract hidden implications instead of turning them into locked truth.
- Emit ambiguity rows for missing interface, protocol, storage, IRQ, error, and
  verification decisions.
- Emit decision candidates with `status: unresolved` or `proposed`, never
  `decided`, unless the user explicitly confirms them.
- Do not edit `req/locked_truth.md`, canonical ontology, RTL, TB, or evidence
  as part of intake.

## Tool

Use:

```bash
python3 .claude/scripts/oag_deep_semantic_intake.py --ip-dir <ip> --topic "<topic>" --prompt "<user/source text>" --profile <profile> --json
```

For MCTP RX style requests, use `--profile mctp-rx`.
