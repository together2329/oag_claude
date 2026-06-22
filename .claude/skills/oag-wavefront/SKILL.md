---
name: oag-wavefront
description: Use when planning or executing OAG parallel subagent work with dependency barriers, ownership locks, read-only triage, disjoint write shards, or single integration owners instead of unconstrained fan-out.
---

# OAG Wavefront

Use this skill when OAG work should be parallelized without breaking ontology
truth, file ownership, or evidence boundaries.

## Principle

Parallelism is not "spawn many agents". Parallelism is opening the current
ready wavefront of tasks whose dependencies, ownership, and evidence boundaries
are satisfied.

## Workflow

1. Compile/check the IP ontology and authoring packets first.
2. Plan a wavefront graph from existing contracts, packets, and evidence plan.
3. Check ready tasks.
4. Claim only dependency-satisfied tasks.
5. Create dispatch records for write-capable tasks.
6. Record worker handoff status and barrier outputs.
7. Let a single integration owner write shared run artifacts.
8. Use read-only triage before repair when simulation fails.
9. Let parent/gate decide closure.

## Commands

Create a graph from a generic template:

```bash
python3 .claude/scripts/oag_wavefront.py plan \
  --ip-dir <ip> \
  --run-id <run_id> \
  --template .claude/oag/wavefront-templates/tb_common_then_scenario_fanout.yaml \
  --json
```

List ready tasks:

```bash
python3 .claude/scripts/oag_wavefront.py ready --ip-dir <ip> --run-id <run_id> --json
```

Claim a task:

```bash
python3 .claude/scripts/oag_wavefront.py claim \
  --ip-dir <ip> \
  --run-id <run_id> \
  --task-id <task_id> \
  --json
```

Record bounded worker status:

```bash
python3 .claude/scripts/oag_wavefront.py record \
  --ip-dir <ip> \
  --run-id <run_id> \
  --task-id <task_id> \
  --status handoff_pass \
  --barrier-output <token> \
  --json
```

Verify graph invariants:

```bash
python3 .claude/scripts/oag_wavefront.py verify --ip-dir <ip> --run-id <run_id> --json
```

## Rules

- Read-only extraction and failure triage may fan out aggressively.
- Write tasks require disjoint paths.
- Shared artifacts require one integration owner.
- Scenario TB tasks must wait for helper/API/schema barriers.
- Worker tasks must not claim completion or signoff.
