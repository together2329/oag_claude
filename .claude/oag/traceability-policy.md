# OAG Traceability Policy

OAG closure depends on an unbroken trace graph:

```text
source claim
  -> requirement
    -> requirement atom
      -> obligation
        -> contract
          -> oracle
            -> scenario
              -> scoreboard/assertion/formal evidence
                -> validation
                  -> gate
```

Traceability is not a documentation nicety. It prevents orphan requirements,
orphan contracts, DUT-derived expected values, stale evidence, and gate
decisions that reviewed the wrong artifact set.

## Minimum ID Governance

- Every requirement has a source claim.
- Every requirement atom references a requirement.
- Every obligation references a requirement.
- Every contract references an obligation.
- Every contract references a machine-readable oracle or approved equivalent.
- Every planned scenario references a contract or obligation.
- Every scoreboard row references a scenario and contract.
- Every coverage goal maps to a requirement, obligation, or contract and a
  passing check before it supports closure.

Draft work may keep gaps as open findings. Locked implementation and closure
must not proceed with orphan load-bearing objects.
