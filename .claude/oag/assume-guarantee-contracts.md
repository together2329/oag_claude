# OAG Assume-Guarantee Contracts

OAG contracts are not pass-condition prose. Closure-grade contracts separate
environment responsibility from DUT responsibility.

```text
assume    = what the environment is allowed/required to do
guarantee = what the DUT must guarantee under those assumptions
```

This prevents two common failures:

- RTL invents missing semantics from convention.
- TB computes expected behavior from RTL or observed DUT output.

## Contract Shape

```yaml
contracts:
  - id: CONTRACT_DATA_OUT_WRITE
    obligation: OBL_DATA_OUT_WRITE_CAPTURE
    contract_type: behavioral_temporal
    variables:
      inputs: [PSEL, PENABLE, PWRITE, PADDR, PWDATA, PRESETn]
      outputs: [PRDATA]
      architectural_state: [DATA_OUT_Q]
      controlled: [DATA_OUT_Q]
      observed: [PRDATA]
    assume:
      legal_stimulus:
        - APB transfer uses setup followed by enable phase.
      protocol_preconditions:
        - PADDR, PWRITE, and PWDATA are stable during enable phase.
      reset_preconditions:
        - PRESETn == 1
    guarantee:
      state_relation:
        - DATA_OUT_Q_next == PWDATA[GPIO_WIDTH-1:0]
      temporal_relation:
        - update occurs on next rising PCLK edge
      forbidden_relation:
        - unmapped writes do not mutate DATA_OUT_Q
    oracle:
      behavior_refs:
        - behavior_model.registers.DATA_OUT.write
      cycle_rule_refs:
        - cycle_rules.apb.write_sample_enable_phase
    verification_projection:
      scenarios: [SCN_DATA_OUT_WRITE]
      scoreboard_rows: [EVT_DATA_OUT_WRITE_MATCH]
```

## How Agents Use This

RTL implementation agents implement `guarantee`.

TB implementation agents use `assume` to build legal and negative stimulus and
use `oracle` to compute independent expected behavior.

Evidence validators check that RTL implementation traces and TB expected
sources resolve to the same contract oracle.

Gate reviewers reject prose-only contracts for closure-grade claims.

## Minimum Closure Rules

- Behavioral contracts require a guarantee and behavior oracle or approved
  equivalent oracle.
- Temporal/protocol contracts require a guarantee and cycle/protocol oracle or
  approved equivalent oracle.
- Contracts with `pass_condition: simulation passes` but no assumption,
  guarantee, variables, and oracle are smoke evidence only.
- If an assumption is missing, the agent must not silently move it into the DUT
  guarantee or vice versa.
