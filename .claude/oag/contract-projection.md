# OAG Contract Projection

Common-style SSOT projection becomes OAG ROCEV projection.

Closure-grade contracts must project into evidence:

```text
Requirement
  -> Obligation
    -> Contract
      -> behavior_model or cycle_rules or approved oracle with decision_receipt_id
        -> RTL implementation trace
        -> planned scenario
          -> actual scenario mapping
            -> scoreboard row or formal assertion
              -> validation record
                -> gate decision
```

RTL and TB both consume the same contract oracle:

```text
RTL implementation: implements behavior/cycle rules.
TB expected oracle: predicts expected behavior from behavior/cycle rules.
Validator: checks that both traces resolve to the same contracts.
```

## Contract Type Requirements

Not every contract needs every ref. Required refs depend on contract type.

```yaml
contract_type_requirements:
  structural:
    requires:
      - structure_refs
  behavioral:
    requires:
      - behavior_refs
  temporal:
    requires:
      - cycle_rule_refs
  cdc:
    requires:
      - clock_domain_refs
      - crossing_refs
      - mitigation_refs
      - cdc_evidence_refs
  rdc:
    requires:
      - reset_domain_refs
      - rdc_crossing_refs
      - reset_sequence_or_isolation_or_sync_refs
      - rdc_evidence_refs
  verification:
    requires:
      - scenario_refs
      - scoreboard_row_refs
      - coverage_refs_or_assertion_refs_when_load_bearing
  assertion:
    requires:
      - property_refs
      - cycle_rule_refs
      - assertion_evidence_refs
  formal:
    requires:
      - property_refs
      - proof_scope
      - formal_evidence_refs
  signoff:
    requires:
      - validation_refs
      - gate_refs
```

Examples:

- a filelist or module ownership contract needs structure refs;
- APB timing, synchronizer visibility, and IRQ priority need cycle-rule refs;
- CDC contracts need clock-domain refs, crossing refs, mitigation refs, and
  CDC evidence refs;
- RDC contracts need reset-domain refs, crossing refs, reset sequence or
  isolation/sync refs, and RDC evidence refs;
- register read/write behavior needs behavior refs;
- TB proof contracts need scenario refs and scoreboard-row refs.
- assertion contracts need property refs and assertion evidence refs;
- formal contracts need property refs, proof scope, and formal evidence refs;
- coverage refs are load-bearing only when they resolve to contracts and
  passing checks.

## Strong Contract Example

```yaml
contract_id: CONTRACT_APB_DATA_OUT_RW
obligation_id: OBL_APB_DATA_OUT
contract_type: behavioral
method: scoreboard
behavior_refs:
  - behavior_model.registers.DATA_OUT.write
  - behavior_model.registers.DATA_OUT.read
cycle_rule_refs:
  - cycle_rules.apb.write_sample_enable_phase
  - cycle_rules.apb.read_response_enable_phase
scenario_refs:
  - SCN_APB_DATA_OUT_RW
scoreboard_row_refs:
  - EVT_DATA_OUT_WRITE_MATCH
  - EVT_DATA_OUT_READ_MATCH
rtl_trace_refs:
  - rtl.apb_gpio.DATA_OUT.write_block
closure_rule:
  required:
    - rtl_trace_present
    - scenario_mapping_present
    - scoreboard_rows_pass
    - expected_source_independent
    - validation_record_present
```

This is closure-grade because it identifies the obligation, the rule, the
scenario, the expected source, the evidence row, and the validation need.

## Domain-Safety Contract Example

```yaml
contract_id: CONTRACT_GPIO_I_SYNC
obligation_id: OBL_APB_GPIO_DATA_IN_SYNC
contract_type: cdc
clock_domain_refs:
  - clock_domains.pclk_domain
crossing_refs:
  - cdc_crossings.CDC_GPIO_I_TO_PCLK
mitigation_refs:
  - sync_structures.gpio_i_two_stage_sync
cycle_rule_refs:
  - cycle_rules.sync.gpio_i_two_stage
cdc_evidence_refs:
  - cdc/oag_domain_crossing_check.json
closure_rule:
  development:
    required:
      - domain_intent_present
      - synchronizer_structure_detected
      - functional_scenario_passed
  release:
    required:
      - static_cdc_report_pass_or_approved_equivalent
      - validation_record_present
      - gate_review_fresh
```

Simulation may support this claim, but simulation alone does not close CDC/RDC
signoff.

## Weak Contract Example

```yaml
contract_id: CONTRACT_APB_DATA_OUT_RW
pass_condition: simulation passes
```

This is not closure-grade because it does not identify the rule, scenario,
expected source, or scoreboard evidence.

## Projection Rules

Use these rules when deriving contracts:

- behavioral contracts identify state/output truth;
- temporal contracts identify sampling, valid cycles, latency, synchronization,
  and priority;
- verification contracts identify scenarios, evidence artifacts, and compare
  rows;
- assertion contracts identify local temporal or protocol properties;
- formal contracts identify proof targets, bounds, assumptions, and proof
  reports;
- signoff contracts identify validation reports, gate decisions, and freshness
  hashes.

If a required ref cannot be created yet, emit an explicit TODO with owner,
reason, and severity. Do not silently weaken the contract.

An approved equivalent oracle is not a free-form note. It must resolve to a
decision receipt and name the approver, scope, substitute artifact, why full
FL/CL is not required, and the obligations covered.

## Planned Vs Actual Scenario Mapping

Requirement and planning stages may use planned scenarios:

```yaml
planned_scenarios:
  - id: SCN_APB_DATA_OUT_RW
    obligations:
      - OBL_APB_DATA_OUT
    contracts:
      - CONTRACT_APB_DATA_OUT_RW
    expected_scoreboard_rows:
      - EVT_DATA_OUT_WRITE_MATCH
      - EVT_DATA_OUT_READ_MATCH
```

After TB/sim execution, actual evidence must map the executed scenario:

```json
{
  "scenario_id": "SCN_APB_DATA_OUT_RW",
  "contracts": ["CONTRACT_APB_DATA_OUT_RW"],
  "behavior_refs": ["behavior_model.registers.DATA_OUT.read"],
  "cycle_rule_refs": ["cycle_rules.apb.read_response_enable_phase"],
  "scoreboard_rows": ["EVT_DATA_OUT_READ_MATCH"],
  "coverage_refs": ["FCOV_DATA_OUT_RW"]
}
```

Do not require `sim/scenario_mapping.json` before a simulator has produced
simulation evidence. Do require it for TB/sim closure.

Coverage in the actual mapping is closure-grade only when the covered scenario
passed and the coverage ref resolves to a contract-linked goal.
