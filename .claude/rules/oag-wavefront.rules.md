# OAG Wavefront Rules

## RULE-WAVE-001

Wavefront tasks must not create or change locked design truth. They may only
consume existing ontology, authoring packets, and evidence plans.

## RULE-WAVE-002

Write-capable wavefront tasks require disjoint `allowed_write_paths` or a single
declared `integration_owner`.

## RULE-WAVE-003

Tasks with unmet `depends_on` or missing `barrier_inputs` must not be claimed.

## RULE-WAVE-004

Shared artifacts such as run scripts, filelists, aggregate results, coverage,
and closure packages must have a single integration owner.

## RULE-WAVE-005

Failing simulation should enter read-only triage before scoped repair agents are
opened.

## RULE-WAVE-006

Worker receipts must keep `may_claim_complete=false`; closure remains gate-owned.
