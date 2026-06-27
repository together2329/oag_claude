# OAG Wavefront Policy

OAG Wavefront is the dependency-aware parallel execution layer above ROCEV
truth. It decides which already-defined work shards may run in parallel; it
does not create requirements, contracts, locked truth, or closure decisions.

## Definition

Wavefront parallelism means opening only tasks whose dependency, ownership, and
evidence boundaries are currently satisfied.

```text
locked ontology truth
  -> authoring packets / evidence plan
    -> wavefront task graph
      -> dispatch + ownership lock
        -> subagent receipt
          -> review_pending
            -> reviewer decision
              -> handoff_pass
                -> evidence validation
                  -> gate decision
```

## Boundaries

- `read_only` tasks may fan out aggressively. They may write only reports,
  receipts, or wavefront events.
- `write` tasks may fan out only when their `allowed_write_paths` are disjoint
  from active writer locks.
- `integration` tasks own shared artifacts such as filelists, run scripts,
  aggregate results, coverage JSON, and generated closure summaries.
- `closure` tasks are not worker-owned. Closure remains parent/gate authority.

## Required Conditions

A task is ready only when:

1. every `depends_on` task has reached `handoff_pass`, `closed`, or `waived`;
2. every `barrier_inputs` token exists in the run barrier set;
3. no active ownership lock conflicts with its write paths;
4. the task keeps `may_claim_complete=false`.

`handoff_pass` is not a worker self-claim. A worker receipt moves a task to
`review_pending`. Only an approved `oag_wavefront_decision.v1` review record
may move `review_pending` to `handoff_pass` and unlock downstream barriers.

## Worker Language

Wavefront workers may say `HANDOFF_PASS`, `BLOCKED`, `FAIL`, or
`INCONCLUSIVE`. They must not say completion, signoff, release, or closure.
Parent orchestration records worker `HANDOFF_PASS` receipts as
`review_pending` until `oag-custom-reviewer` or a narrower reviewer approves
the handoff rationale.

## TB Barrier Pattern

TB scenario tasks must wait for common helper/API and scoreboard schema tasks.

```text
Wave TB-0: read-only extraction
Wave TB-1: common helper, scoreboard, coverage schema
Barrier: import-clean + helper API manifest + scoreboard schema
Wave TB-2: scenario tests
Wave TB-3: single runner owner
Wave TB-4: read-only failure triage
```

## Ontology Coupling

Wavefront reads ontology truth and authoring packets, then writes runtime state
under `ontology/runs/<run_id>/` and receipts under `knowledge/`. It is runtime
state, not authored design truth.
