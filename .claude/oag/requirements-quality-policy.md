# OAG Requirements Quality Policy

Requirements are not a task list. They are claim sources that must be traceable
to source intent, decomposable into requirement atoms, and verifiable by
contracts and evidence.

## Canonical Inputs

Requirement quality uses:

```text
req/source_claims.yaml
req/ambiguity_register.yaml
ontology/decision_matrix.yaml
ontology/requirements.yaml
ontology/requirement_atoms.yaml
```

## Required Requirement Shape

For lock-ready implementation, each requirement should include:

- `id`
- `text`
- `status`
- `requirement_type` or `type`
- `source` or `source_refs`
- `source_claim_refs` when derived from intake claims
- `decision_refs` when a product decision controls the requirement semantics
- `verification_method`
- `ambiguity_status`

`ambiguity_status` must be `clear` or `waived` for post-lock implementation.
Draft, ambiguous, blocked, or missing ambiguity status blocks lock readiness.

## Quality Rules

- A locked requirement must not be vague prose.
- Every load-bearing requirement must trace to source intent.
- Every open lock-required ambiguity blocks implementation.
- A recommendation is not a decision.
- A requirement that depends on an unresolved decision remains draft or blocked.
- Verification method must be named before the requirement can support RTL/TB
  authoring.

Passing requirement quality does not prove behavior. It only says requirements
are specific enough to project into obligations and contracts.
