# OAG TB Methodology Hard Rules

1. The TB agent implements verification methodology, not a preferred framework.
2. UVM, cocotb, SV, Verilog, OSVVM, UVVM, or simulator adapters are choices, not truth.
3. Scenario intent must trace to requirement, obligation, and contract before closure.
4. Expected behavior must come from an independent oracle source, not observed DUT behavior.
5. Driver and monitor responsibilities must stay separate in closure-grade TB evidence.
6. Scoreboard evidence must emit `scoreboard_rows.v1` semantics.
7. Actual `sim/scenario_mapping.json` is required after TB/sim evidence is used for closure.
8. Random or constrained-random stimulus requires constraints and coverage goals before it can support closure.
9. Failed tests or failed scoreboard rows must not contribute to closure coverage.
10. Coverage refs used for closure must resolve to contract-linked coverage goals or evidence.
11. Assertions are preferred for local protocol, temporal, reset, and invariant rules.
12. Formal candidates should be recorded when simulation would be weak or incomplete.
13. CDC/RDC, low-power, safety, and AMS claims cannot close from ordinary simulation alone.
14. TB handoff receipts are evidence handoffs only; they must not claim final closure.
