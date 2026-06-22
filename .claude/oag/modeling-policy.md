# OAG Modeling Policy

## Principle

Full FL/CL files are optional by IP profile.

Oracle responsibility is required for closure. A skipped model file must not
become skipped expected behavior.

Micro-oracles are not only TB inputs. They are also RTL generation inputs. RTL
agents implement behavior/cycle rules, while TB agents independently predict
from those same rules.

Do not escalate because a template says so. Escalate because the oracle cannot
otherwise predict behavior, timing, ordering, or priority without ambiguity.

## Canonical Location

Use this split unless a decision receipt explicitly approves an equivalent:

```text
ontology/policies.yaml
  modeling_policy        # profile and required proof depth

ontology/modeling.yaml
  behavior_model         # micro-FL behavior rules or refs
  cycle_rules            # micro-CL timing/protocol/sync/priority rules
  approved_equivalent_oracles

ontology/contracts.yaml
  behavior_refs
  cycle_rule_refs
  scenario_refs
  scoreboard_row_refs

req/evidence_plan.yaml
  planned_scenarios

sim/scenario_mapping.json
  actual executed scenarios after TB/sim
```

`approved_equivalent_oracles` must include `decision_receipt_id`, `approver`,
`scope`, `substitute_artifact`, `reason_full_model_not_required`, and
`obligations_covered`.

## Profiles

### `simple_leaf_apb_peripheral`

Examples:

- GPIO;
- timer;
- simple interrupt controller;
- small APB register bank;
- simple control/status peripheral.

Required for closing relevant obligations:

- `behavior_model` or approved equivalent behavior oracle;
- `cycle_rules` or approved equivalent cycle contract;
- planned scenarios before implementation closure;
- scoreboard `expected_source`;
- actual scenario mapping after TB/sim output;
- traceability to contracts and validations.

Not required by default:

- full `fl_model.py`;
- full `cl_model.py`;
- separate C++ or Python executable model.

Minimum micro-oracle shape:

```yaml
behavior_model:
  registers:
    DATA_OUT:
      reset: 0
      write: stored_value := PWDATA[GPIO_WIDTH-1:0]
      read: PRDATA := stored_value
    DATA_IN:
      write: no_effect
      read: PRDATA := gpio_in_sync2
cycle_rules:
  apb:
    write_sample: PSEL && PENABLE && PWRITE
    read_sample: PSEL && PENABLE && !PWRITE
    pready: always_1
    prdata_valid: enable_phase
```

### `moderate_stateful_peripheral`

Examples:

- UART;
- SPI;
- I2C;
- PWM with nontrivial modes;
- FIFO-like control peripheral;
- timer with capture/compare interactions.

Required:

- behavior oracle;
- cycle contract;
- executable oracle preferred;
- coverage goals;
- scenario matrix;
- scoreboard expected-source mapping.

Full FL/CL:

- recommended;
- required if behavior cannot be captured safely as simple rules.

### `complex_stateful_ip`

Examples:

- DMA;
- bus bridge;
- packet parser;
- cache;
- accelerator;
- reorder buffer;
- protocol converter;
- stream processor with backpressure or reorder.

Required:

- full FL model;
- full or partial CL model;
- equivalence goals;
- coverage closure;
- independent validation;
- freshness and gate-review evidence.

## Severity Policy

Use stage-aware severity so early exploration stays flexible and closure stays
strict.

```yaml
severity_policy:
  draft:
    missing_modeling_policy: warn
    missing_behavior_model: info
    missing_cycle_rules: info
    missing_scenario_mapping: ignore
  lock_proposal:
    missing_modeling_policy: block
    missing_behavior_model_for_behavioral_obligation: warn
    missing_cycle_rules_for_temporal_obligation: warn
  implementation:
    missing_behavior_model_for_touched_obligation: block
    missing_cycle_rules_for_touched_temporal_obligation: block
    missing_scenario_mapping: warn
  tb:
    missing_scenario_mapping: block
    scoreboard_expected_manual_only: warn
    scoreboard_expected_dut_derived: block
  development_closure:
    missing_behavior_oracle_for_closed_obligation: block
    missing_cycle_oracle_for_closed_temporal_obligation: block
    missing_validation_record: block
    stale_gate: block
  release:
    any_unresolved_traceability_gap: block
```

## Enforcement Unit

Enforce the complete proof chain per closing obligation, not as a whole-IP
all-or-nothing gate.

Reset may close while IRQ remains open if the reset chain is complete:

```text
REQ_RESET
  -> OBL_RESET
  -> CONTRACT_RESET
  -> behavior_model.reset_defaults
  -> SCN_RESET_DEFAULTS
  -> EVT_RESET_DEFAULTS
  -> validation record
```

The incomplete IRQ chain should stay open with a precise blocker.
