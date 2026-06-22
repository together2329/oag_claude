# OAG Clock And Reset Architecture

Use `ontology/domain_intent.yaml` as the canonical clock/reset-domain intent
projection for each IP.

## Required Inventory

Domain intent should record:

- clock domains and generated clocks;
- reset domains, polarity, assertion policy, and deassertion policy;
- reset sequencing relationships;
- external asynchronous inputs;
- CDC crossings and crossing taxonomy;
- RDC crossings or a no-known-RDC basis;
- approved synchronizer, handshake, FIFO, isolation, sequencing, or waiver
  references.

## Allowed CDC Patterns

Use the smallest approved pattern that matches the transfer:

- `single_bit_level`: source register plus 2FF/3FF destination synchronizer;
- `pulse`: pulse stretcher, toggle synchronizer, or handshake;
- `multi_bit_level_sample`: per-bit synchronization only when per-bit sampled
  level semantics are explicitly acceptable;
- `multi_bit_data`: handshake, MCP with stable data, async FIFO, or other
  reviewed transfer protocol;
- `counter_or_pointer`: Gray code or async FIFO pointer scheme;
- `constant_or_static`: stable assumption with decision receipt or formal/static
  evidence.

## Disallowed CDC Patterns

Do not use:

- direct asynchronous sampling for a crossing;
- combinational logic fed by an async source before the first synchronizer flop;
- independent bit synchronizers for a coherent multi-bit bus;
- multiple unsynchronized destinations for one async source;
- reconvergent synchronized controls without review;
- a CDC waiver without scoped assumptions and decision receipt.

## RDC Policy

Record reset-domain intent even for single-clock IPs.

For each reset domain, define:

- reset signal;
- active polarity;
- asynchronous or synchronous assertion;
- synchronous or asynchronous deassertion;
- controlled state;
- relation to other reset domains;
- sequencing, isolation, synchronizer, qualifier, or no-known-RDC basis.

If reset deassertion policy is unspecified, the closure claim must stay open or
carry a decision receipt.

## Simple Leaf Policy

Simple APB leaf peripherals usually do not need release-grade CDC/RDC tooling
during development. They still need domain intent.

For APB GPIO-style sampled inputs:

```yaml
crossing_type: multi_bit_level_sample
coherency_requirement: per_bit_sampled_level_only
not_a_bus_transaction: true
allowed_pattern: per_bit_two_stage_sync
```

This classification prevents both mistakes: building an unnecessary FIFO for a
sampled GPIO vector and directly sampling external async inputs without
synchronization.
