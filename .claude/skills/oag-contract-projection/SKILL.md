---
name: oag-contract-projection
description: Use when OAG requirements or requirement atoms must be projected into independently checkable obligations and assume/guarantee contracts with behavior, cycle, scenario, scoreboard, assertion, or coverage proof refs.
---

# OAG Contract Projection

Use this skill after source claims, ambiguity, decision rows, and requirement
atoms exist. Projection turns intent into obligations and closure-grade
contracts.

## Rules

- Do not project prose-only requirements into closure-grade contracts.
- Keep environment responsibility in `assume`; keep DUT responsibility in
  `guarantee`.
- Behavioral contracts need behavior refs or an approved equivalent oracle.
- Temporal contracts need cycle-rule refs or an approved equivalent oracle.
- Interface/protocol contracts need variables, legal stimulus assumptions, and
  observable response guarantees.
- Verification projection must name scenarios and scoreboard/assertion/formal
  proof refs before closure.

## Checks

Run:

```bash
python3 .claude/scripts/oag_requirement_atom_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_contract_strength_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_trace_graph_check.py --ip-dir <ip> --json
```

Use `--require-locked` for hard pre-implementation or closure audits.

## Output

Update authored truth only:

- `ontology/obligations.yaml`
- `ontology/contracts.yaml`
- `ontology/modeling.yaml`
- `req/evidence_plan.yaml`
- `ontology/verification_plan.yaml`

After edits, run `oag.compile`; do not hand-edit generated projections.
