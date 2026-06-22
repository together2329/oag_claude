# OAG V2 Discussion Summary

This document summarizes the working direction discussed for IP Dev Agent/OAG.
It is a review summary, not canonical product truth by itself.

## One-Line Definition

OAG is not a system for quickly producing RTL.

OAG is an IP design operating system that preserves design truth while deriving
RTL, TB, verification evidence, validation, and decisions from that truth.

Short version:

```text
Do not translate requirements directly into code.
First turn requirements into verifiable meaning units, then build RTL/TB/evidence.
```

## Core Philosophy

RTL is not truth.

RTL is an implementation of truth. The durable truth lives in locked
requirements, obligations, contracts, oracles, validation records, gate
decisions, and decision history.

TB is not just stimulus.

TB is a contract proof instrument. Expected behavior must come from an
independent oracle such as `behavior_model`, `cycle_rules`, an approved FL/CL
artifact, a formal property, a golden vector, or an approved equivalent oracle.
Expected values must not be derived from RTL or observed DUT output.

Evidence is not closure.

Compile pass, lint pass, simulation pass, coverage hit, and subagent summary are
evidence candidates. Closure requires traceability, validation, freshness, and
the required gate decision.

## Current OAG V1 State

Current OAG already has a strong V1 foundation:

- Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision.
- Draft/lock separation.
- Before lock: main agent owns intake, interview, draft, and clarification.
- After lock: main agent orchestrates; native OAG subagents implement and verify.
- Dispatch and receipt tracking for subagent work.
- `behavior_model` and `cycle_rules` as micro-oracle anchors.
- TB expected-source independence.
- CDC/RDC domain intent and simulation-only closure blocking.
- OAG SV-lite RTL dialect and PPA-lite reasoning.
- Coverage tied to passing checks and contract-linked intent.
- Evidence freshness, stale gate, decision receipt, and closure checks.
- Regression tests and pack release checks that enforce many of these rules.

This means OAG is already more than a prompt pack. It is an operating layer for
LLM-assisted IP development.

## What Is Still Missing

The missing part is not the philosophy. The missing part is deeper mechanical
enforcement of meaning decomposition.

Current flow is roughly:

```text
Requirement -> Obligation -> Contract
```

OAG V2 should make it:

```text
Stakeholder Need
  -> Goal / Intent
    -> Requirement Statement
      -> Requirement Atom
        -> Phenomena / Boundary / Assumption
          -> Atomic Obligation
            -> Assume-Guarantee Contract
              -> Behavior / Cycle / Domain / Proof Oracle
                -> RTL Implementation Trace
                -> TB Prediction + Observation
                -> Assertion / Formal / Coverage / Mutation Evidence
                  -> Validation
                    -> Gate Decision
```

The goal is to prevent an agent from treating vague prose as implementation
authority.

## Why Requirement Atoms Matter

Short requests such as:

```text
I need mctp rx ip
```

must not authorize architecture, RTL, TB, or closure.

Before implementation, OAG should force the agent to identify:

- trigger;
- condition;
- response;
- interface;
- boundary;
- environment assumptions;
- DUT guarantees;
- observables;
- timing;
- exception and error policy;
- open questions.

If those fields are unknown, the correct state is `draft` or `blocked`, not
implementation.

This prevents the agent from inventing scope such as transport binding,
buffering, backpressure, packet reassembly, filtering, or error policy.

## Why Decision Matrix Matters

Requirement atoms explain the meaning of a requirement. The decision matrix
records choices that are not yet safe to treat as truth.

For a complex IP, the agent should not turn an unanswered question into RTL.
Instead it should create rows such as:

```yaml
decisions:
  - id: DEC_MCTP_RX_CONTEXT_KEY
    question: What fields form the MCTP assembly context key?
    status: unresolved
    lock_required: true
    recommended: Source EID + TO + Msg Tag
    decision: null
    rationale: Context key changes ordering, buffering, scoreboard, and RTL.
    affects: [requirements, obligations, contracts, modeling, verification]
```

`status=proposed` is still draft. Only `decided` or `waived` rows can clear a
lock-required decision. This makes the workflow explicit:

```text
draft request
  -> requirement atoms
  -> decision matrix
  -> user/spec decides lock blockers
  -> lock readiness check
  -> native subagent implementation
```

The important rule is:

```text
No unresolved lock-required decision, no RTL/TB dispatch.
```

## Requirement Atom Shape

A requirement atom is a normalized, verifiable slice of a requirement.

Example shape:

```yaml
requirement_atom:
  id: ATOM_DATA_OUT_WRITE
  source_requirement_id: REQ_DATA_OUT_APB_ACCESS
  normalized_text: >
    When an APB write transfer to DATA_OUT completes while reset is inactive,
    the IP shall update DATA_OUT_Q from PWDATA on the next rising PCLK edge.
  pattern:
    trigger: PSEL && PENABLE && PWRITE && PADDR == DATA_OUT_ADDR
    condition: PRESETn == 1
    response: DATA_OUT_Q_next == PWDATA[GPIO_WIDTH-1:0]
    timing: next rising PCLK edge
    exception: reset dominates write
  boundary:
    responsible_agent: dut
    environment_agents: [apb_master]
  phenomena:
    dut_inputs: [PSEL, PENABLE, PWRITE, PADDR, PWDATA, PRESETn]
    controlled_state: [DATA_OUT_Q]
    observable_outputs: [PRDATA, gpio_o]
  ambiguity:
    missing_terms: []
    open_questions: []
```

## Atomic Obligations

An obligation should answer one independent judgment question:

```text
Under this trigger and precondition, does the DUT guarantee this observable
behavior within this timing and priority rule?
```

Weak obligation:

```yaml
id: OBL_APB_WORKS
text: APB register behavior is correct.
```

Strong obligation:

```yaml
id: OBL_DATA_OUT_WRITE_CAPTURE
parent_requirement: REQ_DATA_OUT_APB_ACCESS
kind: behavioral_temporal
trigger: PSEL && PENABLE && PWRITE && PADDR == DATA_OUT_ADDR
preconditions:
  - PRESETn == 1
environment_assumptions:
  - APB transfer follows setup/enable phase protocol.
controlled_state:
  - DATA_OUT_Q
guarantee:
  - DATA_OUT_Q_next == PWDATA[GPIO_WIDTH-1:0]
latency:
  - next rising PCLK edge
observable:
  - subsequent DATA_OUT readback
forbidden_behavior:
  - unmapped write changes DATA_OUT_Q
  - reset cycle captures write
oracle_projection:
  behavior_refs:
    - behavior_model.registers.DATA_OUT.write
  cycle_rule_refs:
    - cycle_rules.apb.write_sample_enable_phase
```

## Assume / Guarantee

Assume/guarantee separates environment responsibility from DUT responsibility.

Assume:

```text
The environment obeys these rules.
```

Guarantee:

```text
Under those assumptions, the DUT must provide these behaviors.
```

Example:

```yaml
contract:
  id: CONTRACT_DATA_OUT_WRITE
  obligation_id: OBL_DATA_OUT_WRITE_CAPTURE
  assume:
    legal_stimulus:
      - APB master follows setup -> enable phase.
      - PADDR, PWRITE, and PWDATA are stable during enable phase.
    reset_preconditions:
      - PRESETn == 1
  guarantee:
    state_relation:
      - DATA_OUT_Q_next == PWDATA[GPIO_WIDTH-1:0]
    forbidden_relation:
      - unmapped writes do not mutate DATA_OUT_Q
  oracle:
    behavior_refs:
      - behavior_model.registers.DATA_OUT.write
    cycle_rule_refs:
      - cycle_rules.apb.write_sample_enable_phase
  verification_projection:
    scenarios:
      - SCN_DATA_OUT_WRITE
    scoreboard_rows:
      - EVT_DATA_OUT_WRITE_MATCH
```

RTL agents implement guarantees.

TB agents use assumptions to generate legal/illegal stimulus and use the oracle
to compute expected behavior.

Validators check that the RTL trace and TB expected source resolve to the same
contract oracle.

## Phenomena And Boundary Model

For hardware IP, it is important to separate environment phenomena from DUT
signals and state.

Example:

```yaml
phenomena:
  monitored_variables:
    - apb_write_transfer
    - gpio_i_external_level
  controlled_variables:
    - DATA_OUT architectural value
    - gpio_o pin value
    - irq_o level
  dut_inputs:
    - PSEL
    - PENABLE
    - PWRITE
    - PADDR
    - PWDATA
    - gpio_i
  dut_outputs:
    - PRDATA
    - PREADY
    - PSLVERR
    - gpio_o
    - irq_o
  natural_assumptions:
    - gpio_i may change asynchronously to PCLK
  input_relations:
    - gpio_i_external_level is sampled through a two-stage synchronizer
  output_relations:
    - gpio_o reflects DATA_OUT_Q masked by DIR_Q
```

This helps prevent an agent from treating asynchronous environment signals as
safe synchronous DUT state.

## TB As Proof Instrument

TB is not a simulator wrapper.

TB is not only stimulus.

TB is a proof instrument for contracts.

Every closure-grade TB should declare proof roles:

```yaml
tb_proof_architecture:
  scenario_intent:
    source: req/evidence_plan.yaml
  stimulus:
    role: driver_or_sequence
    legal_space: []
    illegal_space: []
    constraints: []
  monitor:
    dut_facing: true
    observed_source: bus_monitor
  predictor:
    expected_source:
      kind: behavior_model
      refs: []
    forbidden:
      - dut_output
      - rtl_expression
      - post_hoc_sim_result
  scoreboard:
    emits: scoreboard_rows.v1
  coverage:
    maps_to:
      - requirement
      - obligation
      - contract
      - passing_check
  assertions:
    local_protocol: []
    temporal: []
    reset: []
    invariant: []
  result_writer:
    artifacts:
      - sim/results.xml
      - sim/scenario_mapping.json
      - sim/scoreboard_events.jsonl
      - cov/coverage.json
```

## Coverage And Fault Relevance

Coverage is not just "what was hit." Closure-grade coverage should explain why
the hit matters.

Better shape:

```yaml
coverage_contract:
  id: COV_IRQ_W1C_PRIORITY
  requirement: REQ_IRQ
  obligation: OBL_IRQ_SET_CLEAR_PRIORITY
  contract: CONTRACT_IRQ_W1C_PRIORITY
  bins:
    - event_set
    - apb_w1c_clear
    - same_cycle_overlap
  must_be_checked_by:
    - scoreboard.EVT_IRQ_PRIORITY
    - assertion.irq_priority_p
  fault_models:
    - FM_PRIORITY_REVERSED
    - FM_CLEAR_DROPS_SET
    - FM_MASK_APPLIED_TOO_EARLY
  mutation_results_required:
    development: optional_with_rationale
    signoff: required_for_load_bearing
```

## Benefits Of V2

Adding the semantic layer improves OAG in seven ways:

1. It prevents short-request runaway.
2. It improves requirement quality by forcing trigger, condition, response,
   timing, and exceptions.
3. It separates environment assumptions from DUT guarantees.
4. It makes it harder for RTL agents to invent reset values, W1C priority,
   overflow policy, backpressure, or protocol semantics.
5. It reduces circular verification where TB follows RTL.
6. It makes bug triage clearer: requirement ambiguity, bad decomposition, weak
   contract, RTL bug, or TB expected-source bug.
7. It scales from simple timer/GPIO IP to UART, SPI, DMA, MCTP, packet parser,
   bridge, and other complex stateful IP.

## Recommended Thin V2 Extension

Do not rewrite OAG V1. Add a thin semantic layer.

Applied MVP files:

```text
.claude/oag/deep-semantic-intake-policy.md
.claude/oag/requirements-quality-policy.md
.claude/oag/decision-matrix-policy.md
.claude/oag/verification-strategy-policy.md
.claude/oag/requirement-decomposition-principles.md
.claude/oag/assume-guarantee-contracts.md
.claude/oag/phenomena-boundary-model.md
.claude/rules/oag-requirements-quality.rules.md
.claude/rules/oag-verification-strategy.rules.md
.claude/rules/oag-requirement-decomposition.rules.md
.claude/rules/oag-lock-readiness.rules.md
.claude/schemas/oag_source_claims.schema.json
.claude/schemas/oag_ambiguity_register.schema.json
.claude/schemas/oag_decision_matrix.schema.json
.claude/schemas/oag_verification_plan.schema.json
.claude/schemas/oag_requirement_atom.schema.json
.claude/scripts/oag_req_quality_check.py
.claude/scripts/oag_verification_plan_check.py
.claude/scripts/oag_lock_readiness_check.py
.claude/scripts/oag_requirement_atom_check.py
.claude/agents/oag-verification-strategy-agent.md
```

IP canonical seed now created by scaffold:

```text
req/deep_semantic_intake/
req/source_claims.yaml
req/ambiguity_register.yaml
ontology/decision_matrix.yaml
ontology/verification_plan.yaml
ontology/requirement_atoms.yaml
```

The MVP is intentionally a thin extension:

- New scaffolds preserve source intent, unresolved ambiguities, lock-required
  decisions, and requirement atoms before any implementation authority exists.
- `oag_req_quality_check.py` passes draft scaffolds as advisory but fails lock
  readiness when source claims, ambiguity resolution, requirement type,
  verification method, or ambiguity status are missing.
- `oag_lock_readiness_check.py` now aggregates decision blockers, requirement
  quality blockers, requirement atom blockers, shallow obligations, and
  assume/guarantee contract weakness.
- `oag-verification-strategy-agent` and `ontology/verification_plan.yaml` split
  proof strategy from TB implementation. The strategy layer owns verification
  objectives, proof methods, scenarios, coverage goals, assertion/formal
  candidates, fault-model hooks, and residual risk. The TB implementation agent
  consumes the strategy instead of defining it.
- OAG mode and the `oag-ip-workflow` skill now point agents to requirement
  quality, decisions, and requirement atoms before lock, then to
  `oag_req_quality_check.py`, `oag_requirement_atom_check.py`, and
  `oag_lock_readiness_check.py` after lock.
- Protected-field policy includes requirement atom semantic fields.
- Release checks require the new docs, rule files, schemas, and checkers.
- The checkers pass draft scaffolds but fail post-lock/proof mode when source
  intent is unresolved, lock-required decisions are open, atoms are ambiguous,
  obligations are prose-only, or closure-grade contracts lack assume/guarantee
  sections.

Next wave:

```text
.claude/schemas/oag_contract_v2.schema.json
.claude/scripts/oag_contract_strength_check.py
ontology/assurance_argument.yaml
ontology/coverage_fault_models.yaml
ontology/coverage_model.yaml
```

## Minimum Gate Rules

Initial V2 should enforce only a few high-value rules:

```text
No locked requirement without requirement atoms.
No closure-grade obligation from prose-only semantics.
No closure-grade contract without explicit assume/guarantee.
No TB closure without independent proof roles.
No coverage closure from failed checks or unresolved coverage refs.
```

## Final Summary

OAG V1 is already a strong LLM-assisted IP development operating layer.

OAG V2 should not replace it. OAG V2 should make requirement meaning,
environment boundaries, obligations, and assume-guarantee contracts mechanically
checkable.

The direction is:

```text
Good IP development is not "spec -> RTL -> tests pass."

Good IP development is:

need -> requirement atom -> obligation -> assume/guarantee contract
     -> oracle -> RTL trace + TB proof -> evidence -> validation -> decision
```
