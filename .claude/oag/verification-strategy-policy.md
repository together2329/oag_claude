# OAG Verification Strategy Policy

Verification strategy is separate from testbench implementation.

The strategy role owns what must be proven, what proof methods are sufficient,
what negative/fault scenarios are required, and what residual risk remains. The
TB implementation role owns the harness, drivers, monitors, predictors,
scoreboards, coverage collectors, and runnable artifacts that satisfy the
strategy.

Core rule:

```text
TB writer must not define the proof strategy it is trying to satisfy.
```

## Canonical File

`ontology/verification_plan.yaml` is the canonical verification strategy file.
It should exist before post-lock TB implementation or load-bearing verification
evidence is dispatched.

The plan maps:

```text
Requirement/Obligation/Contract
  -> verification objective
    -> proof methods
      -> scenarios, checkers, coverage goals, assertion/formal candidates
        -> residual risk
```

`ontology/tb_methodology.yaml` remains the implementation-methodology file. It
describes driver/monitor/predictor/scoreboard/coverage architecture and
framework choices. It must consume the verification plan, not replace it.

## Minimum Objective Shape

Each verification objective should name:

- `id`;
- `requirement`;
- `obligation`;
- `contract`;
- `intent`;
- `proof_methods`;
- `scenarios`;
- `coverage_goals`;
- `negative_scenarios` when error/drop/illegal behavior is in scope;
- `assertion_candidates` or `formal_candidates` when local temporal/protocol
  proof is stronger than simulation;
- `residual_risks` with explicit status.

## Strategy Agent Duties

The verification strategy agent is read-only for RTL/TB. It may write strategy
and planning evidence only. It should:

1. read locked requirements, requirement atoms, decisions, obligations,
   contracts, behavior/cycle/domain/modeling truth, and evidence plan;
2. convert contracts into verification objectives;
3. classify proof method depth by risk, not by convenience;
4. add positive, negative, boundary, error, interleaving, reset, and priority
   scenarios where applicable;
5. identify assertion/formal candidates;
6. identify coverage goals and fault-model/mutation hooks;
7. record residual risk and open strategy blockers;
8. hand off to TB implementation, coverage, mutation, evidence validation, or
   gate review.

The strategy agent must not implement RTL or TB, must not edit expected values,
and must not claim final closure.
