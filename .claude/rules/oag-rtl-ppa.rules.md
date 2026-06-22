# OAG RTL PPA Rules

Use these rules for generated RTL implementation and static review.

```text
Before RTL code:
  read locked behavior/cycle contracts
  read RTL dialect policy
  read PPA intent or classify a provisional PPA intent
  read domain intent when clocks, resets, async inputs, or crossings are in scope
  identify likely critical paths
  identify high-toggle state/datapath
  identify area-risk structures
  do not invent behavior

During RTL code:
  preserve locked contract behavior
  use OAG SV-lite by default: Verilog-2001 plus logic and static generate
  prefer simple decode for simple peripherals
  use explicit register write enables where applicable
  avoid unnecessary pipelines for simple leaf peripherals
  avoid manual clock gating unless policy explicitly allows it
  avoid accidental priority muxes and latches
  keep reset limited to architecturally required state unless policy requires more

After RTL code:
  run or assign oag_ppa_check.py for lightweight heuristic review
  record rtl_dialect in the receipt
  record ppa_notes for nontrivial RTL
  record domain_crossing_notes for crossing-sensitive RTL
  record implemented_contracts, behavior_refs_implemented, and cycle_rule_refs_implemented
  record may_claim_complete=false

Validator:
  check RTL dialect pass
  check parse/lint pass where available
  check implemented contract refs
  check PPA notes present for nontrivial RTL
  check CDC/RDC claims through domain intent, not PPA notes
  check no PPA optimization changed contract behavior
```
