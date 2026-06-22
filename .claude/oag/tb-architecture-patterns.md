# TB Architecture Patterns

Use a framework-neutral architecture. Names can change by language, but the
responsibilities should stay visible.

## Roles

Driver:

Drives legal and intentionally illegal stimulus according to scenario intent.
The driver should not observe DUT results to decide expected values.

Monitor:

Passively observes DUT-facing signals, interfaces, transactions, logs, or
assertions. The monitor is an observed source, not an oracle.

Predictor:

Computes expected behavior from `behavior_model`, `cycle_rules`, approved
FL/CL, formal properties, golden vectors, or approved equivalent oracles.

Scoreboard:

Compares predictor expected values against monitor observations and emits
`scoreboard_rows.v1`.

Coverage Collector:

Records functional coverage bins that map to contracts and passing checks.
Failed scenario coverage may be recorded for debug but must not close coverage.

Assertion Hook:

Checks local protocol, timing, reset, or invariant rules that are more precise
as properties than as end-to-end scoreboard rows.

Result Writer:

Emits `sim/results.xml`, `sim/scenario_mapping.json`,
`sim/scoreboard_events.jsonl`, `cov/coverage.json`, and run receipts when those
artifacts are in scope.

## Micro-UVM Style

Small IPs should keep the UVM role split without forcing UVM code.

For a simple APB GPIO, this may be:

```text
apb_write/read task -> driver
APB sample task     -> monitor
behavior_model      -> predictor
JSON row writer     -> scoreboard
coverage bins       -> coverage collector
APB assertions      -> assertion hooks
```

This is enough if it is self-checking, independent, and traceable.

## Scenario Mapping

Planned scenarios live in `req/evidence_plan.yaml`.

Actual executed scenarios live in `sim/scenario_mapping.json` after TB/sim has
produced evidence. The actual mapping should name:

- `scenario_id`;
- obligations;
- contracts;
- behavior and cycle refs when known;
- scoreboard rows;
- coverage refs;
- assertion or formal refs when used.

## Evidence Artifacts

Minimum TB/sim evidence for closure-grade scoreboard claims:

- `sim/results.xml`;
- `sim/scenario_mapping.json`;
- `sim/scoreboard_events.jsonl`;
- independent `expected_source`;
- DUT-facing `observed_source`.

Coverage closure additionally needs:

- `cov/coverage.json` or equivalent coverage report;
- coverage refs resolving to goals or contracts;
- proof that failed rows did not contribute to closure coverage.

## Anti-Patterns

Do not use:

- a test that prints PASS without a scoreboard or assertion;
- a monitor output as expected behavior;
- random stimulus without coverage goals;
- coverage from failed tests as closure coverage;
- a full UVM environment for a tiny IP just to satisfy a template;
- a bare directed TB for complex stateful IP closure when ordering, buffering,
  arbitration, or backpressure needs a reference model.
