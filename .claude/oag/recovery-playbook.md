# OAG Recovery Playbook

Use this playbook when an agent finds weak evidence, missing oracle refs, stale
gates, or over/under-modeled IP work.

## Missing Behavior Oracle

Symptom:

```text
Behavioral obligation is being closed but no behavior_model, FL model, formal
property, or approved equivalent oracle with decision_receipt_id resolves.
```

Action:

- keep the obligation open;
- add or request the smallest behavior rule that predicts expected output;
- update contract `behavior_refs`;
- rerun evidence generation and validation.

Do not infer the expected behavior from RTL.

## Missing Cycle Contract

Symptom:

```text
Temporal obligation is being closed but no cycle rule or CL/equivalent timing
oracle resolves.
```

Action:

- keep the obligation open;
- record the missing sampling, latency, valid-cycle, sync, or priority rule;
- update contract `cycle_rule_refs`;
- rerun TB evidence that depends on timing.

## Manual Spec Used For Closure

Symptom:

```text
scoreboard expected_source.kind = manual_spec
```

Action:

- allow as provisional smoke/debug evidence;
- for development closure, replace with behavior/cycle/model refs or record an
  explicit decision receipt;
- for release signoff, block unless explicitly approved.

## DUT-Derived Expected Value

Symptom:

```text
The scoreboard expected value is copied from DUT output, RTL expression, or
post-hoc simulation behavior.
```

Action:

- block the evidence;
- create a failure ticket if this was used in a closing claim;
- rebuild the expected source from an independent oracle.

## Missing Scenario Mapping

Symptom:

```text
Evidence rows exist but do not map back to scenarios, contracts, and
obligations.
```

Action:

- before TB/sim, add planned scenarios to the evidence plan;
- after TB/sim, require actual `sim/scenario_mapping.json`;
- keep closure open until mapping resolves.

## Framework Overkill

Symptom:

```text
A simple IP is being forced into full UVM or another heavy framework without a
reuse, scalability, or proof-strength reason.
```

Action:

- keep the methodology profile small;
- use directed/table-driven micro-TB roles instead;
- preserve driver, monitor, predictor, scoreboard, coverage, and result writer
  responsibilities;
- record the framework choice in `ontology/tb_methodology.yaml` or the TB
  receipt.

## Random Without Coverage Goals

Symptom:

```text
Random or constrained-random tests are proposed without constraints, coverage
goals, or seed/reproducibility notes.
```

Action:

- classify the random run as exploration, not closure evidence;
- add constraints, coverage goals, and seed strategy;
- connect coverage goals to requirements, obligations, contracts, and passing
  checks before closure.

## Coverage From Failed Checks

Symptom:

```text
A failed test or failed scoreboard row carries coverage_refs that are counted
as closed coverage.
```

Action:

- block closure coverage;
- keep the failure as debug evidence only;
- rerun the scenario until the check passes or remove the coverage ref from
  closure accounting.

## Missing TB Methodology Intent

Symptom:

```text
TB/sim evidence is used for closure but ontology/tb_methodology.yaml does not
name the methodology profile, roles, coverage strategy, or result artifacts.
```

Action:

- keep the closing claim open;
- add the smallest sufficient TB methodology intent;
- map scenarios, scoreboard rows, coverage refs, assertion hooks, and formal
  candidates to the relevant contracts;
- rerun `oag.compile`, `oag.check`, and evidence validation.

## Stale Gate

Symptom:

```text
Evidence changed after gate PASS.
```

Action:

- mark the gate stale;
- rerun evidence validation;
- rerun gate review with current artifact hashes.

## Missing Domain Intent

Symptom:

```text
CDC/RDC, async input, multi-clock, or multi-reset closure is being claimed but
ontology/domain_intent.yaml is missing or incomplete.
```

Action:

- keep the crossing-sensitive obligation open;
- record clock domains, reset domains, async inputs, crossing type, and reset
  deassertion policy;
- add mitigation refs or an explicit scoped assumption with decision receipt;
- rerun `oag.compile`, `oag.check`, and lightweight domain crossing checks.

Do not let RTL invent crossing safety.

## Simulation-Only CDC/RDC Closure

Symptom:

```text
CDC/RDC closure is claimed from passing RTL simulation or scoreboard rows only.
```

Action:

- downgrade simulation to supporting evidence;
- require domain intent, crossing classification, mitigation evidence, and
  validation;
- for release claims, require static/formal/tool-grade evidence or an approved
  equivalent decision receipt;
- rerun gate review after the evidence set changes.

## Over-Modeling

Symptom:

```text
A simple leaf IP is being forced to produce full FL/CL files just to satisfy a
template.
```

Action:

- classify the IP profile from actual behavior;
- record an applicability decision;
- use micro behavior/cycle oracles if sufficient;
- keep full FL/CL optional unless ambiguity demands it.

## Under-Modeling

Symptom:

```text
Full FL/CL was skipped and no substitute oracle exists.
```

Action:

- keep the closing claim blocked;
- add behavior/cycle/oracle refs for the relevant obligation;
- rerun scoreboard or formal evidence.

## Post-Lock Semantic Addition

Symptom:

```text
An agent needs to add behavior/cycle truth after scope is locked.
```

Action:

- do not silently edit protected truth;
- record a human-approved decision receipt or draft the proposed change;
- refresh contracts, evidence, and validation after approval.
