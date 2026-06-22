# Coverage Closure Policy

Coverage is a measurement of exercised intent. It is not closure by itself.

## Functional Coverage

Functional coverage must map to OAG truth:

```text
coverage_ref -> requirement -> obligation -> contract -> scenario -> check
```

Coverage refs that are load-bearing for closure should appear in one or more
of:

- `req/evidence_plan.yaml`;
- `ontology/tb_methodology.yaml`;
- `ontology/design_rules.yaml`;
- `sim/scenario_mapping.json`;
- `sim/scoreboard_events.jsonl`;
- `cov/coverage.json`.

## Passing-Check Rule

Coverage from failed checks must not count toward closure.

A failing row may still emit coverage data for debug, but validators should
block closure when a failed scoreboard row carries load-bearing coverage refs or
when a coverage report cannot distinguish passing and failing contribution.

## Random Stimulus

Random or constrained-random stimulus requires:

- named constraints or legal stimulus space;
- coverage goals;
- seed/reproducibility strategy;
- evidence that coverage holes guide new scenarios.

Random without goals is exploration, not closure methodology.

## Code Coverage

Code coverage supports review and can reveal unexercised logic. It does not
prove requirements by itself. Code coverage may support closure only when
functional coverage, scoreboard/assertion evidence, and ROCEV mapping are also
present.

## Metric-Driven Closure

Use metrics to decide what is still open:

- obligations closed/open/stale;
- scenarios planned/executed;
- scoreboard rows passed/failed;
- coverage goals hit/missed;
- assertions passed/failed/untested;
- formal candidates proven/open;
- stale evidence and gate freshness.

The question is not "Did many tests run?" The question is "Which obligations
are independently judged, validated, and fresh?"
