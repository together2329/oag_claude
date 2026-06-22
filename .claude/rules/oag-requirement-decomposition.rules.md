# OAG Requirement Decomposition Rules

Use this rule pack when requirements are promoted, scope is locked, or closure
is claimed.

```text
Before lock:
  requirement atoms may be draft
  open questions are allowed
  canonical RTL/TB/signoff work is not allowed

After lock:
  every locked requirement must have at least one requirement atom
  every requirement atom must name source_requirement_id, normalized_text, trigger, response, boundary, and phenomena
  every non-draft atom must have no missing_terms or open_questions
  every behavioral atom must identify controlled state/output or observable output
  every temporal atom must identify timing, latency, or valid-cycle semantics
  environment assumptions must be separated from DUT guarantees
  shallow obligations such as "APB works" cannot close
  closure-grade contracts must carry explicit assume and guarantee sections
  behavioral/temporal/protocol contracts must resolve to behavior/cycle/protocol oracle refs or an approved equivalent oracle
```

Minimum hard gates:

```text
No locked requirement without requirement atoms.
No closure-grade obligation from prose-only semantics.
No closure-grade contract without explicit assume/guarantee.
No TB closure without independent proof roles.
No coverage closure from failed checks or unresolved coverage refs.
```

Applicability:

- Draft/interview: warn and record open questions.
- Development closure: block unsupported closing claims.
- Signoff: require explicit atom, obligation, assume/guarantee contract, oracle,
  validation, and gate traceability.
