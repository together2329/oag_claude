# Verification Methodology Principles

OAG TB work follows methodology principles, not a mandatory framework.

The TB agent is not a UVM generator, cocotb generator, or simulator wrapper. It
is a verification methodology agent. It chooses the smallest sufficient
verification structure for the IP profile and emits ROCEV evidence that a
validator can check.

## Methodology Kernel

Use these principles from eRM/eVC, VMM, OVM, UVM, OSVVM, UVVM, cocotb, PSS,
CDV, MDV, ABV, and formal verification:

- start from a verification plan and contracts;
- use transaction abstraction when it clarifies stimulus and observation;
- separate driver, monitor, predictor, scoreboard, coverage, and tests;
- compute expected behavior from an independent oracle;
- make the environment self-checking;
- use assertions for local protocol and temporal invariants;
- use functional coverage to measure what requirements have been exercised;
- use metrics to decide what is still open;
- keep scenario intent separate from TB implementation;
- emit evidence artifacts, not only log prose.

Do not force a framework when its overhead does not buy verification strength.
Do not avoid methodology just because the chosen TB is simple.

## Framework Choice

Frameworks are tools:

- Use UVM or UVM-like architecture when reuse, scalability, sequence libraries,
  or VIP-style composition matter.
- Use cocotb or Python when fast executable oracles, JSON evidence, and
  coroutine-based drivers make the flow clearer.
- Use simple SystemVerilog or Verilog tasks when the IP is small and directed
  checks are enough.
- Use PSS-style scenario planning when the same scenario intent should move
  across simulation, formal, emulation, FPGA, or post-silicon.
- Use OSVVM/UVVM-style readability when simple BFMs, logs, checks, and coverage
  make the TB easier to maintain.

Methodology is required. A specific framework is not.

## Independence

RTL is observed behavior. It is not expected behavior.

The predictor or scoreboard expected value must resolve to one of:

- `behavior_model`;
- `cycle_rules`;
- approved FL/CL artifact;
- formal property;
- golden vector;
- approved equivalent oracle with decision receipt.

Expected behavior must not come from:

- observed DUT outputs;
- copied RTL expressions;
- post-hoc simulation results;
- untraceable prose;
- a monitor replaying DUT output as expected.

## Coverage And Metrics

Coverage is useful only when it is tied to checks.

Functional coverage should map to requirements, obligations, contracts, and
scoreboard rows or assertions. Code coverage can support review, but it is not
the same as functional closure.

Failed tests do not contribute to closure coverage. Coverage from a failing
scenario can help debug, but it must not be counted as closed proof.

Random stimulus needs constraints and coverage goals. Random without a goal is
noise.

## Assertions And Formal

Scoreboards check end-to-end behavior. Assertions check local protocol,
temporal, reset, and invariant rules.

Formal candidates should be recorded when exhaustive proof is more appropriate
than simulation, especially for:

- protocol invariants;
- reset safety;
- impossible states;
- priority conflicts;
- bounded liveness;
- FIFO/order properties;
- CDC/RDC assumptions and constraints.

The TB agent may identify formal candidates even when it does not run the
formal tool.

## Special Closure Domains

Ordinary simulation does not close CDC/RDC, low-power, safety, or AMS claims by
itself.

For these domains, TB evidence is supporting evidence. Closure requires the
domain-specific intent, evidence strength, validation record, and gate decision
required by policy.

## Core Rule

Use the smallest sufficient methodology:

- simple IPs get directed, readable, self-checking TBs;
- moderate IPs get transaction drivers, monitors, randomization, coverage, and
  assertion hooks;
- complex IPs get reusable agents, reference models, sequence libraries,
  coverage-driven closure, formal candidates, and portable scenario intent.

Do not claim closure from tests, coverage, or framework presence alone.
