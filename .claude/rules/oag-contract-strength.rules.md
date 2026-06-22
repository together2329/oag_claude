# OAG Contract Strength Rules

These rules are enforced by `oag_contract_strength_check.py`.

## Hard Gates

- Closure-grade contracts must separate `assume` and `guarantee`.
- Closure-grade contracts must name `variables`.
- Behavioral contracts must resolve to behavior refs or an approved equivalent
  oracle.
- Temporal, protocol, ordering, backpressure, interrupt, and reset contracts
  must resolve to cycle/protocol refs or an approved equivalent oracle.
- Verification-bearing contracts must name scenarios and at least one proof
  row/property/formal goal.
- Storage/commit contracts must name ordering guarantees and observable proof
  projection.
- Error/drop contracts must name negative scenarios or an explicit rationale.
- `pass_condition: simulation passes` without oracle/proof projection is smoke
  evidence only.

## Draft Behavior

Draft scopes may keep weak contracts as interview placeholders. The checker is
advisory unless `--require-locked` is used or `ontology/scope_lock.json` is
locked.
