# TB Methodology Policy

TB methodology depth is profile-dependent. The profile chooses the minimum
verification structure that can independently judge the obligations being
closed.

## Principle

Do not require UVM, cocotb, OSVVM, UVVM, or any other framework by default.

Do require the role responsibility:

- stimulus intent;
- driver or BFM;
- monitor;
- predictor or oracle adapter;
- scoreboard;
- coverage collector when coverage is load-bearing;
- assertion or formal hooks when local temporal rules need them;
- OAG evidence writer.

## Profiles

### simple_leaf_apb_peripheral

Examples:

- GPIO;
- timer;
- simple interrupt/status block;
- small APB register bank.

Default methodology:

- directed smoke first;
- table-driven register tests;
- micro-UVM style role split without UVM class overhead;
- RAL-lite expected state from `behavior_model.registers`;
- simple monitor or sampled DUT-facing signals;
- scoreboard rows in `sim/scoreboard_events.jsonl`;
- coverage JSON with contract-linked bins;
- optional protocol assertions.

Not required by default:

- full UVM environment;
- constrained-random regression;
- PSS model;
- full executable FL/CL file;
- release-grade formal proof.

### moderate_stateful_peripheral

Examples:

- UART;
- SPI;
- I2C;
- PWM with nontrivial modes;
- FIFO-like controller.

Default methodology:

- transaction abstraction;
- driver and monitor separation;
- predictor from behavior/cycle oracle;
- constrained-random with coverage goals;
- assertion hooks for protocol/local invariants;
- regression seeds and failure reproduction;
- coverage report tied to contracts.

Full UVM or UVM-like structure is recommended when it improves reuse or
maintainability.

### complex_stateful_ip

Examples:

- DMA;
- cache;
- bus bridge;
- packet parser;
- accelerator;
- reorder buffer;
- protocol converter.

Default methodology:

- reusable verification agents;
- sequence library;
- independent reference model;
- coverage-driven random;
- assertions and formal candidates;
- portable scenario planning when useful;
- metric-driven closure.

Full UVM, UVM-like, or another reusable architecture is usually justified.

### special profiles

Special profiles add evidence requirements:

- `low_power_ip`: power-state, isolation, retention, and UPF-related scenarios;
- `safety_ip`: fault injection, safety mechanism checks, diagnostic coverage;
- `mixed_signal_ip`: AMS or real-number bridge evidence, not digital-only
  scoreboard closure;
- `domain_crossing_ip`: CDC/RDC intent, mitigation, and static/formal/tool
  evidence as required by policy.

## Stage Severity

```yaml
severity_policy:
  draft:
    missing_tb_methodology: info
    missing_coverage_goals: info
    missing_scenario_mapping: ignore
  lock_proposal:
    missing_tb_methodology_policy: warn
    random_without_coverage_goals: warn
  tb:
    missing_scenario_mapping_after_sim: block
    missing_scoreboard_rows_after_sim: block
    random_without_constraints_or_coverage_goals: block
  development_closure:
    missing_independent_expected_source: block
    failed_rows_counted_for_coverage: block
    unresolved_coverage_refs: block
    sim_only_special_domain_closure: block
  release:
    unresolved_methodology_gap: block
```

The enforcement point is the claim. Do not block early exploration because the
final TB architecture is not complete. Do block a closure claim that lacks
independent checking and traceable evidence.
