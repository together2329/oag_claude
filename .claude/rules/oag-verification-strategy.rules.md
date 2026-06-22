# OAG Verification Strategy Rules

These rules govern the split between verification strategy and TB
implementation.

## Hard Rules

- Locked or closure-bound TB work must have `ontology/verification_plan.yaml`.
- The verification plan must contain at least one objective.
- Each objective must map to requirement, obligation, and contract ids.
- Each objective must name proof methods and scenarios.
- Coverage goals used by an objective must be explicit.
- Negative/error behavior must have negative scenarios or an explicit rationale
  when the related contract is error, malformed, drop, overflow, timeout,
  priority, or illegal-stimulus related.
- Assertion/formal candidates are advisory for development, but a strategy
  blocker must be recorded when the objective is temporal/protocol-heavy and no
  stronger proof path is named.
- TB implementation agents consume the verification plan. They do not invent
  the proof strategy after lock.

## Draft Behavior

In draft, missing or incomplete verification strategy is advisory. After user
lock or when `--require-locked` is used, missing or shallow strategy is a hard
gate for TB implementation and closure claims.
