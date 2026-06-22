# OAG CDC/RDC Hard Rules

1. Clock and reset domain intent is design truth.
2. Any multi-clock or multi-reset IP must have `ontology/domain_intent.yaml`.
3. Any external asynchronous input must be classified.
4. Single-bit CDC requires an approved synchronizer or explicit stable
   assumption.
5. Multi-bit CDC must not use independent bit synchronizers unless the crossing
   is Gray-coded, stable, sampled-level, or explicitly approved.
6. RDC is not waived by single-clock operation.
7. Asynchronous reset deassertion policy must be explicit before reset closure.
8. Reset-domain crossings require sequencing, isolation, synchronizer,
   qualifier, no-known-RDC basis, or blocker.
9. CDC/RDC closure cannot be claimed from RTL simulation alone.
10. CDC/RDC waivers require decision receipts and scoped assumptions.
11. Release-grade CDC/RDC closure requires static, formal, tool-grade, or
    explicitly approved equivalent evidence.
