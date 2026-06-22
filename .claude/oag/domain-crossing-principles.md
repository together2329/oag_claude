# OAG Domain Crossing Principles

CDC/RDC is a domain-safety contract. It is stricter than PPA because a weak
crossing can become a silicon escape even when RTL simulation passes.

## Design Truth

Clock and reset domain intent is design truth.

RTL may implement crossings. RTL may not invent crossing safety.

Every asynchronous clock or reset boundary must be classified. Every crossing
must be one of:

- avoided by architecture;
- protected by an approved pattern;
- proven stable, constant, or unreachable;
- covered by a scoped decision receipt;
- left open with a precise blocker.

## CDC Mental Model

CDC is not only a two-flop synchronizer problem.

Core risks:

- metastability;
- data loss;
- multi-bit data incoherence;
- reconvergence or correlation loss;
- glitchy combinational logic before the synchronizer.

Single-bit level crossings usually need a source-registered signal and a
destination 2FF/3FF synchronizer. Pulse crossings need a pulse stretcher,
toggle synchronizer, or handshake after fast-to-slow loss analysis. Multi-bit
crossings need an explicit safe representation or transfer protocol.

Do not independently synchronize every bit of a multi-bit bus unless the
crossing is classified as Gray-coded, stable during capture, sampled level
vector, or explicitly approved.

## RDC Mental Model

RDC is not waived by single-clock operation.

Asynchronous reset assertion/deassertion can create metastability and ordering
hazards even when all flops share one clock. Reset-less sequential paths can
propagate reset-domain hazards into later resettable state.

RDC mitigation is not always a generic synchronizer. First decide whether the
right solution is:

- reset-domain architecture alignment;
- reset sequencing;
- data isolation;
- clock isolation;
- reset synchronizer;
- qualifier protocol;
- explicit stable or constant assumption.

## Evidence Strength

CDC/RDC evidence is not ordinary simulation evidence.

Development closure may use lightweight structural checks plus functional
supporting tests. Release closure requires tool-grade, formal, static, or
explicitly approved equivalent evidence.

A passing simulation can support a crossing claim. It cannot by itself close a
CDC/RDC signoff claim.
