# OAG Deep Semantic Intake Policy

Deep semantic intake preserves the user's compressed intent before OAG turns it
into requirements, obligations, contracts, RTL, TB, or evidence.

## Purpose

User phrases such as "AXI WDATA carries the PCIe TLP" or "make MCTP RX" are
valuable source intent, but they are not implementation contracts. Intake
captures the phrase, extracts hidden design implications, and records
ambiguities before an agent fills the gaps with plausible defaults.

## Canonical Artifacts

Each IP should carry:

```text
req/deep_semantic_intake/
req/source_claims.yaml
req/ambiguity_register.yaml
```

`source_claims.yaml` stores source-level claims and normalized meaning.
`ambiguity_register.yaml` stores unresolved questions that may block lock.
Detailed Markdown notes under `req/deep_semantic_intake/` preserve interview
rounds, spec notes, and layer worksheets.

## Intake Responsibilities

For each load-bearing user/spec statement, capture:

- source quote or summary;
- source location or conversation round;
- normalized meaning;
- hidden implementation implications;
- affected design layers;
- candidate requirement refs;
- decision refs and ambiguity refs.

For protocol IPs, decompose at least boundary, protocol profile, ordering or
reassembly, buffering/backpressure, storage/commit, firmware visibility,
interrupt/status, error/drop policy, and verification scenario implications.

## Draft Versus Lock

Draft intake may contain unresolved ambiguity. Lock-ready intake must resolve or
waive lock-required ambiguities before implementation dispatch.

Deep intake does not slow implementation down. It turns natural-language intent
into implementation-grade design truth so RTL and TB agents can work from the
same source without reading each other.
