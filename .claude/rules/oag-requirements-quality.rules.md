# OAG Requirements Quality Rules

These rules govern source claims, ambiguity registers, and lock-ready
requirement shape.

## Hard Rules

1. Post-lock implementation requires `oag_req_quality_check.py --ip-dir <ip>
   --json` to pass.
2. Each lock-ready requirement must have a stable id, text, type,
   source/source_refs, verification_method, and `ambiguity_status`.
3. `ambiguity_status` must be `clear` or `waived` for post-lock implementation.
4. Requirements derived from intake should reference `source_claim_refs`.
5. Requirements controlled by product choices should reference
   `decision_refs`.
6. `req/ambiguity_register.yaml` lock-required rows must be `resolved` or
   `waived`; `open`, `unresolved`, `proposed`, or `blocked` rows block
   implementation.
7. `resolved` ambiguity rows require a `resolution`.
8. `waived` ambiguity rows require a `waiver_reason`.
9. Requirement quality is not closure. It only gates projection into contracts
   and implementation packets.
