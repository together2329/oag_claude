# OAG Evaluation Ideas

This is a non-blocking backlog for future evaluation scenarios. These ideas are
not required for the current OAG run-loop v1; they document the next useful
checks if we want the harness to prove more of its behavior.

## Current Baseline

`scripts/oag_eval.py` already checks the core loop behavior:

- incomplete active runs block Claude Code Stop with the next OAG action
- complete runs pass Stop silently
- repeated blockers become `needs_human`
- completion claims require an explicit decision receipt
- UserPromptSubmit can inject `oag.context` for inferred IP work, suppress
  identical repeated context with a durable content-hash cache, keep
  `context_pressure=high` deduped, and re-inject on the next UserPromptSubmit
  after a silent PostCompact recovery marker
- context pressure during requirement interviews injects an `oag.draft` guard
- evidence mutation makes prior file-hash evidence stale
- an empty ontology cannot pass compile/check/decide as complete
- greenfield modular IPs cannot share one RTL file across current-IP modules
  without an explicit `shared_file_rationale`
- `oag.compile` creates `ontology/generated/design_facts_graph.json` from RTL
  via `pyslang` when available, flags decomposition/RTL module drift, and passes
  once current-IP module names/files match extracted facts
- active `interleaved_context_coverage` rule instances require observed coverage
  refs before closing
- active `fault_model_coverage` rule instances require observed coverage refs
  plus killed requirement-relevant mutation evidence before closing
- active `verification_role_decomposition` rule instances require UVM-style
  roles and independent expected/observed/compare responsibilities
- closed signoff domain rule instances for CDC/RDC, protocol compliance,
  timing/STA, functional coverage closure, and reset/X-prop require real
  evidence files; coverage-bearing instances also require observed coverage refs
  and functional coverage must meet its declared goal. Timing closure also
  requires target frequency/clocks and CDC-aware SDC policy.
- signoff/promote requires an independent reviewer receipt when the profile is
  signoff, and an `allowed` reviewer receipt with `independent: false` is still
  rejected
- committed hook configuration exposes UserPromptSubmit, Stop, and PostCompact
  hook adapters

## Candidate Scenarios

### Git-Backed Version Management

Purpose: make RTL/TB/SDC/docs/signoff evidence durable across agents and time,
not just across one chat turn.

Evaluation idea:

- create a git repo around a scaffolded IP
- record a closed validation with commit ID plus file hashes for RTL, TB,
  filelist, SDC, generated facts, and signoff artifacts
- mutate a file without committing and confirm `oag.check` reports dirty/stale
  evidence
- commit the mutation with a new validation record and confirm the new commit
  becomes the baseline

Notes: design facts graph already records file hashes and git HEAD when
available; the remaining work is a stricter policy gate for dirty worktrees and
commit-tagged stage receipts.

### Claude Code Runtime Hook Firing

Purpose: prove that `.claude/hooks.json` is not only syntactically valid, but
also approved and invoked by the Claude Code runtime.

Evaluation idea:

- create an incomplete active run
- attempt to stop in a real Claude Code session
- confirm Stop is blocked by `claude_stop_gate.py`

Notes: this needs runtime approval/state, so it is better as a manual or
integration evaluation than a pure script test.

## Priority If We Implement More

1. Git-backed version/evidence baseline gate
2. Claude Code runtime hook firing
3. Reviewer quality benchmark with intentionally flawed signoff claims
4. Draft promotion workflow from `ontology/drafts` to locked truth
5. Cross-surface compatibility tests for Claude Code, CI, and human shell workflows
