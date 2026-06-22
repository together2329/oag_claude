# OAG Wavefront Review Guide

This file is a single-review summary for the OAG Wavefront P0 change in
`ip_dev/.claude`.

Implementation commit:

```text
5d32aab Add OAG wavefront scheduler primitive
```

## One-Sentence Summary

OAG Wavefront is a dependency-aware runtime scheduler that lets parallel agents
work only when their dependencies, file ownership, and evidence boundaries are
safe.

It is not a new source of design truth.

## Why This Exists

Before Wavefront, the parent agent could fan out multiple RTL/TB workers, but
there was no durable runtime object saying:

- this task is ready
- this task is blocked by another task
- this task owns these files
- another task cannot claim the same file
- this worker may only produce handoff evidence
- closure still belongs to parent/gate review

That caused wasted retries in flows like TB generation:

```text
scenario tests started
  before tb_common.py / scoreboard schema existed
    -> blocked receipts / retries / drift risk
```

Wavefront fixes the P0 version of that problem.

## Core Principle

```text
ROCEV / ontology / contracts = what is true
Wavefront                 = what work can safely run now
```

Wavefront may read locked OAG truth and authoring packets. It must not create or
change locked requirements, obligations, contracts, validation records, or gate
decisions.

## What It Adds

### Policy / Skill / Rule

```text
.claude/oag/wavefront-policy.md
.claude/oag/wavefront-task-graph.md
.claude/skills/oag-wavefront/SKILL.md
.claude/rules/oag-wavefront.rules.md
```

These define Wavefront as an operational execution layer:

- read-only triage can fan out aggressively
- write tasks require disjoint ownership
- shared integration artifacts need a single owner
- workers may claim handoff only
- gate/parent keeps closure authority

### Runtime CLI

```text
.claude/scripts/oag_wavefront.py
```

P0 commands:

```bash
python3 .claude/scripts/oag_wavefront.py plan   --ip-dir <ip> --run-id <run> --template <template> --json
python3 .claude/scripts/oag_wavefront.py ready  --ip-dir <ip> --run-id <run> --json
python3 .claude/scripts/oag_wavefront.py claim  --ip-dir <ip> --run-id <run> --task-id <task> --json
python3 .claude/scripts/oag_wavefront.py record --ip-dir <ip> --run-id <run> --task-id <task> --status handoff_pass --json
python3 .claude/scripts/oag_wavefront.py status --ip-dir <ip> --run-id <run> --json
python3 .claude/scripts/oag_wavefront.py verify --ip-dir <ip> --run-id <run> --json
```

`close` also exists as a small operational helper, but P0 does not depend on
automatic closure through Wavefront.

### Schemas

```text
.claude/schemas/oag_wavefront_task_graph.schema.json
.claude/schemas/oag_ownership_locks.schema.json
.claude/schemas/oag_wavefront_event.schema.json
```

These define task graph, ownership lock, and event shape.

### Generic Templates

```text
.claude/oag/wavefront-templates/rtl_module_fanout.yaml
.claude/oag/wavefront-templates/tb_common_then_scenario_fanout.yaml
```

No IP-specific profile was added.

The TB template intentionally models the dependency barrier:

```text
TB_COMMON_API
TB_SCOREBOARD_SCHEMA
  -> TB_SCENARIO_A
    -> TB_INTEGRATION_RUNNER
```

Scenario work cannot start until common helper and scoreboard schema work pass
and publish their barrier outputs.

### Dispatch Linkage

`oag_dispatch.py` now supports these optional P0 fields:

```text
wavefront_run_id
task_id
ownership_mode
```

The child receipt schema can echo the same fields. Dispatch verification checks
mismatches when both sides provide them.

This is intentionally minimal. P0 does not include pre-edit hashes, worktree
isolation, automatic subagent spawning, or rich mailbox semantics.

## Runtime State Location

Wavefront writes operational state under the IP directory:

```text
<ip>/ontology/runs/<run_id>/wavefront_task_graph.json
<ip>/ontology/runs/<run_id>/ownership_locks.json
<ip>/ontology/runs/<run_id>/barriers.json
<ip>/ontology/runs/<run_id>/claims/<task_id>.lock
<ip>/knowledge/wavefront/<run_id>/events.jsonl
```

This state is operational. It is not product truth.

## How It Works

### 1. Plan

Creates a task graph from a template.

```bash
python3 .claude/scripts/oag_wavefront.py plan \
  --ip-dir mctp_rx_assembler \
  --run-id RUN_TB_001 \
  --template .claude/oag/wavefront-templates/tb_common_then_scenario_fanout.yaml \
  --json
```

### 2. Ready

Returns only tasks whose dependencies and barrier inputs are satisfied.

```bash
python3 .claude/scripts/oag_wavefront.py ready \
  --ip-dir mctp_rx_assembler \
  --run-id RUN_TB_001 \
  --json
```

### 3. Claim

Atomically claims a task and creates ownership locks for its write paths.

It rejects:

- unknown task
- already active task
- dependency-unmet task
- barrier-unmet task
- same-file double writer

### 4. Record

Updates task status and can publish barrier outputs.

Example:

```bash
python3 .claude/scripts/oag_wavefront.py record \
  --ip-dir mctp_rx_assembler \
  --run-id RUN_TB_001 \
  --task-id TB_COMMON_API \
  --status handoff_pass \
  --barrier-output tb_common_import_clean \
  --barrier-output helper_api_manifest \
  --json
```

### 5. Verify

Checks graph consistency and active lock consistency.

## Status Values

Worker-oriented statuses:

```text
ready
claimed
in_progress
handoff_pass
blocked
failed
inconclusive
waived
closed
```

Closure semantics remain outside Wavefront. A worker `handoff_pass` is not OAG
closure.

## Why This Helps

### Dependency Safety

Before:

```text
scenario test agent starts before common TB API exists
```

After:

```text
TB_SCENARIO_A is not ready until TB_COMMON_API and TB_SCOREBOARD_SCHEMA pass
```

### File Ownership Safety

Before:

```text
two agents can both edit tb/common.py
```

After:

```text
first exclusive_file claim wins
second claim is rejected with OWNERSHIP_CONFLICT
```

### Evidence Boundary Safety

Before:

```text
worker might overclaim complete/signoff
```

After:

```text
worker records handoff only
parent/gate validates evidence and decides closure
```

### Reviewability

The parent can inspect:

- ready task list
- blocked dependencies
- active claims
- active ownership locks
- task event history

## P0 Scope

Included:

- policy, skill, rule
- task graph schema
- ownership lock schema
- event schema
- `oag_wavefront.py`
- dispatch optional fields
- generic RTL/TB templates
- smoke coverage for dependency block and double-writer reject

Excluded intentionally:

- pre-edit hashes
- object-level hashes
- worktree isolation
- automatic subagent spawning
- rich mailbox events
- sim failure triage template
- hook auto-continuation
- IP-specific profiles

## Verification Performed

After implementation:

```bash
python3 -m py_compile \
  .claude/scripts/oag_wavefront.py \
  .claude/scripts/oag_dispatch.py \
  .claude/scripts/oag_pack_release_check.py \
  .claude/scripts/smoke_test.py \
  .claude/scripts/oag_answer_key_eval.py

python3 .claude/scripts/smoke_test.py
python3 .claude/scripts/oag_pack_release_check.py --json
python3 .claude/scripts/oag_eval.py --json
```

Results:

```text
smoke_test.py: pass
oag_pack_release_check.py: pass
oag_eval.py: pass, 47/47
```

`oag_answer_key_eval.py` still preserves default speed thresholds. Full smoke
uses `--speed-scale 5` for this evaluator because the pack-level smoke runs many
subprocess-heavy cases and host load can make duration-only checks flaky.

## Review Checklist

Use this checklist to review whether Wavefront stays in the right lane.

1. Does Wavefront avoid creating locked design truth?
2. Does `ready` block dependency-unmet tasks?
3. Does `claim` reject same-file double writers?
4. Are workers still limited to handoff statuses?
5. Are shared integration artifacts modeled as single-owner tasks?
6. Are runtime artifacts kept under `ontology/runs` and `knowledge/wavefront`?
7. Are dispatch fields minimal: `wavefront_run_id`, `task_id`,
   `ownership_mode`?
8. Are IP-specific profiles absent from P0?

## Short Mental Model

```text
OAG contracts tell agents what correct means.
Wavefront tells agents when they may safely work.
```

