# OAG Traceability Rules

These rules are enforced by `oag_trace_graph_check.py`.

- Requirements must reference known source claims when source claims exist.
- Requirement atoms must reference known requirements.
- Obligations must reference known requirements.
- Contracts must reference known obligations.
- Contract scenario refs must be declared by evidence planning, verification
  planning, or the contract graph.
- Contract scoreboard row refs must be declared by evidence planning or actual
  scoreboard evidence before closure.
- Verification objectives must reference known requirements, obligations, and
  contracts.
- Scoreboard events must carry `scenario_id`, `contract_refs` or `contracts`,
  and `expected_source`.
- Coverage goals must trace to requirement, obligation, or contract refs.
- Hard gate mode blocks orphan load-bearing refs.
