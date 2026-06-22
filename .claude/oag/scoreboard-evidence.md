# OAG Scoreboard Evidence

The scoreboard must compare independent expected behavior against observed DUT
behavior.

## Expected Sources

Expected behavior may come from:

- `behavior_model`;
- `cycle_rules`;
- approved FL/CL model;
- formal property;
- approved equivalent oracle with `decision_receipt_id`.

Expected behavior must not come from:

- observed DUT output;
- copied RTL expression;
- post-hoc simulation result;
- untraceable prose;
- a child-agent summary without durable refs.

Manual expected values are allowed as provisional smoke/debug evidence only.
They must not be promoted to obligation closure unless linked to a decision
receipt or replaced by model/cycle/formal refs.

An `approved_equivalent_oracle` expected source must include:

- `decision_receipt_id`;
- `approver`;
- `scope`;
- `substitute_artifact`;
- `reason_full_model_not_required`;
- `obligations_covered`.

## Observed Sources

Observed behavior must be DUT-facing:

- `dut_signal`;
- `monitor`;
- `waveform`;
- `transaction`;
- `assertion`.

Observed behavior must not be a model output or an expected-source projection.

## Scoreboard Row Shape

Use `scoreboard_rows.v1` semantics independent of TB language:

```json
{
  "goal_id": "CONTRACT_APB_DATA_OUT_RW",
  "scenario_id": "SCN_APB_DATA_OUT_RW",
  "obligation_id": "OBL_APB_DATA_OUT",
  "contract_id": "CONTRACT_APB_DATA_OUT_RW",
  "expected_source": {
    "kind": "behavior_model",
    "refs": ["behavior_model.registers.DATA_OUT.read"]
  },
  "observed_source": {
    "kind": "dut_signal",
    "refs": ["PRDATA"]
  },
  "compare": {
    "method": "case_equality",
    "width": 32
  },
  "passed": true,
  "coverage_refs": ["FCOV_DATA_OUT_RW"]
}
```

Provisional smoke/debug example:

```json
{
  "goal_id": "CONTRACT_RESET_DEFAULTS",
  "scenario_id": "SCN_RESET_DEFAULTS",
  "obligation_id": "OBL_RESET",
  "contract_id": "CONTRACT_RESET_DEFAULTS",
  "expected_source": {
    "kind": "manual_spec",
    "status": "provisional",
    "source_refs": ["REQ_RESET"]
  },
  "observed_source": {
    "kind": "dut_signal",
    "refs": ["DATA_OUT", "DIR", "IRQ_STATUS"]
  },
  "passed": true
}
```

## Stage Policy

```text
Smoke evidence may be provisional.
Closure evidence must be traceable.
Release evidence must be independently validated.
```

Detailed policy:

```text
manual_spec expected_source:
  smoke/dev debug: allowed as provisional evidence
  obligation closure: block unless approved by decision receipt or replaced by model/cycle/formal refs
  release signoff: block unless explicitly approved

dut-derived expected_source:
  any closure stage: block
```

## Validator Questions

Evidence validation should ask:

- Is the expected source independent?
- Is the observed source DUT-facing?
- Does the scenario resolve to a contract and obligation?
- Do behavior/cycle/model refs resolve?
- Does the row actually judge the closing obligation?
- Are coverage refs present when coverage is load-bearing?
- Are validation and gate artifacts fresh?

It should not ask for a specific simulator, TB framework, or model language.
