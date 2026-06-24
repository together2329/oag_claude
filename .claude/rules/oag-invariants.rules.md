# OAG Hard Invariants

These are the short rules that validators and gate reviewers must protect.
Detailed reasoning lives under `.claude/oag/*.md`.

1. RTL is not truth.
2. Passing tests are not closure.
3. Evidence without validation is not closure.
4. Child summaries are not closure.
5. Custom subagent output alone is not final closure.
6. After lock, implementation/evidence writes require native subagent dispatch
   and receipt.
7. Evidence added after gate PASS makes the gate stale.
8. A closure claim must trace to requirement, obligation, contract, evidence,
   validation, and gate decision when the profile requires a gate.
9. Expected scoreboard values must be independent of observed DUT behavior.
10. Skipping full FL/CL requires an applicability decision or profile rule, and
    the oracle responsibility must be satisfied by a substitute.
11. Generated RTL implements locked contract truth; it must not invent behavior,
    timing, reset values, address maps, priorities, or protocol semantics.
12. RTL implementation agents may not modify ontology/spec truth unless an
    explicit human-approved decision receipt permits it.
13. Default RTL uses Verilog-2001 plus `logic` and static `generate`
    constructs; `function`, `task`, `always_ff`, `always_comb`,
    `always_latch`, and procedural loops outside generate are forbidden by
    default.
14. PPA optimization must preserve locked behavior; it cannot justify protocol,
    timing, reset, priority, or address-map drift.
15. Nontrivial RTL handoffs must record PPA intent or PPA notes covering
    performance, power, area, and tradeoffs.
16. Clock/reset domain intent is design truth; RTL must not invent CDC/RDC
    safety.
17. Any CDC/RDC closure claim must trace to domain intent, crossing
    classification, mitigation, evidence, validation, and gate decision when a
    gate is required.
18. CDC/RDC closure cannot be claimed from simulation alone.
