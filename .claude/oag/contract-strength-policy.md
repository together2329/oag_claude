# OAG Contract Strength Policy

OAG contracts are the proof adapter between locked design truth and
implementation or verification work. A contract is strong enough for
implementation readiness only when it separates environment assumptions from
DUT guarantees and names the machine-readable oracle and proof projection that
RTL and TB agents must consume.

## Contract Strength Levels

- `draft`: useful for interview notes and scaffolds only.
- `implementation_ready`: specific enough for RTL/TB authoring packets.
- `closure_grade`: strong enough to support validation and gate decisions.
- `signoff_grade`: closure-grade plus freshness, independent validation, and
  profile-required signoff evidence.

## Minimum Implementation-Ready Shape

Implementation-ready contracts must define:

- `id`
- `obligation` or `obligation_refs`
- `contract_type`
- `variables`
- `assume`
- `guarantee`
- `oracle`
- `verification_projection` or equivalent top-level scenario/proof refs

The `assume` section describes legal environment behavior. The `guarantee`
section describes DUT responsibility under those assumptions.

## Type-Specific Requirements

Behavioral contracts require one of:

- `oracle.behavior_refs`
- top-level `behavior_refs`
- `oracle.approved_equivalent_oracle_refs`

Temporal, protocol, ordering, backpressure, interrupt, and reset contracts
require one of:

- `oracle.cycle_rule_refs`
- top-level `cycle_rule_refs`
- `oracle.protocol_refs`
- `oracle.approved_equivalent_oracle_refs`

Storage or commit-order contracts must make ordering visible in the guarantee
and name an observable proof source through scenarios, scoreboard rows,
assertions, or formal goals.

Error/drop/negative contracts must name negative scenarios or explicitly record
why the negative behavior is covered elsewhere.

## Weak Contract Patterns

These patterns are not closure-grade:

- `pass_condition: simulation passes`
- prose-only `text`
- missing `assume`
- missing `guarantee`
- missing `variables`
- no behavior/cycle/protocol/domain oracle
- no scenario, assertion, formal, or scoreboard projection

Weak contracts may remain in draft intake, but they must not feed locked RTL,
TB, validation, gate review, or closure claims.
