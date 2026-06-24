# Bounded Loop Hook Integration Plan

This plan connects the bounded open-item planner to the product OAG runtime
surface under `.claude/`. Phase 1 is implemented as a boundary-aware planning,
hook-decision, and plan-only/dispatch-safe runner surface. It is not yet an
automatic RTL/TB/ROCEV execution contract.

## Goal

Enable controlled OAG loops such as:

```bash
python3 .claude/scripts/oag_loop_runner.py --ip-dir <ip> --until rtl --limit 3
python3 .claude/scripts/oag_loop_runner.py --ip-dir <ip> --until tb --requirement REQ_X
python3 .claude/scripts/oag_loop_runner.py --ip-dir <ip> --until record --owner-module pl330_channel_thread
```

The loop must stop at the requested boundary even when broader open work exists.
The planner remains the source of truth; hooks and runners only consume planner
decisions.

## Implementation Status

Implemented in Phase 1:

- `scripts/oag_loop_core.py` parses loop policy, projects graph-ready tasks into
  bounded planner batches, and emits stable stop reasons.
- `scripts/oag_loop_hook.py` emits `continue` or `stop` JSON by calling
  `oag.run.next` with a loop policy.
- `scripts/oag_loop_runner.py` supports `plan_only` and `dispatch` decisions and
  writes `ontology/runs/<run_id>/loop_decision.json`.
- `oag.run.next` returns `next_batch`, `loop_policy`, `loop_plan`, and
  `loop_stop_reason` only when a loop policy is active.
- `oag.stop_check` stops on loop boundaries before advancing beyond the selected
  boundary.
- `oag.configure` can persist or clear `execution_policy.loop_policy`.

Deferred:

- automatic RTL/TB/evidence execution;
- automatic ROCEV record execution;
- Claude Code stop-hook automatic invocation of `oag_loop_hook.py`;
- wavefront materialization directly from `next_batch`.

## Existing Surfaces

- `scripts/oag_cli.py` already owns `oag.run.start`, `oag.run.next`,
  `oag.run.record`, `oag.run.checkpoint`, `oag.stop_check`, and
  `oag.configure`.
- `hooks/claude_stop_gate.py` already blocks stops for incomplete runs and
  respects `hook_auto_continue_until`.
- `hooks/claude_context_inject.py` already accepts short run-limit commands and
  writes `execution_policy.hook_auto_continue_until`.
- `scripts/oag_wavefront.py` already materializes dependency-aware graph work.

The missing piece is a bounded planner consumer that can route:

```text
open diagnosis -> bounded planner -> loop hook/runner -> oag.run.next/wavefront
```

without duplicating planner priority logic.

## Loop Policy

Introduce a common loop policy object:

```json
{
  "schema_version": "oag_loop_policy.v1",
  "until": "contract|target_lock|rtl|tb|evidence|record|gate|all",
  "requirements": ["REQ_ID"],
  "obligations": ["OBL_ID"],
  "owner_modules": ["module"],
  "job_types": ["RTL_IMPLEMENT_JOB"],
  "limit": 3,
  "max_iterations": 8,
  "mode": "plan_only|dispatch|execute"
}
```

Environment aliases:

```text
OAG_LOOP_UNTIL
OAG_LOOP_REQUIREMENT
OAG_LOOP_OBLIGATION
OAG_LOOP_OWNER
OAG_LOOP_JOB_TYPE
OAG_LOOP_LIMIT
OAG_LOOP_MAX_ITERATIONS
OAG_LOOP_MODE
```

`hook_auto_continue_until` remains a coarse stop-hook cap. The new loop policy
is the fine-grained planner cap and should be stored under
`ontology/policies.yaml` as `execution_policy.loop_policy` when persisted.

## Planner Contract

The bounded planner must return a stable batch envelope:

```json
{
  "schema_version": "oag_bounded_plan.v1",
  "status": "pass|blocked",
  "policy": {},
  "recommended_batch": {
    "batch_id": "batch hash or stable id",
    "job_type": "RTL_IMPLEMENT_JOB",
    "boundary_stage": "rtl",
    "requirements": ["REQ_ID"],
    "obligations": ["OBL_ID"],
    "owner_module": "module",
    "contracts": ["CONTRACT_ID"],
    "required_evidence": [],
    "dispatch_profile": "rtl|tb|record|gate",
    "can_execute": false,
    "stop_after_batch": false
  },
  "filtered_counts": {
    "total_open": 0,
    "within_boundary": 0,
    "outside_boundary": 0
  },
  "stop_reason": ""
}
```

If the requested boundary has no runnable work, `recommended_batch` is `null`
and `stop_reason` is `boundary_reached` or `no_runnable_batch`.

## Hook Driver

Add `scripts/oag_loop_hook.py`.

Responsibilities:

- read loop policy from CLI args, environment, and `ontology/policies.yaml`;
- call the bounded planner with `--until`, filters, and `--limit`;
- emit JSON only;
- never pick open items directly;
- never execute RTL, TB, evidence, record, or gate work;
- never write closure records.

Output:

```json
{
  "schema_version": "oag_loop_hook_decision.v1",
  "decision": "continue|stop",
  "reason": "batch_available|boundary_reached|no_runnable_batch|check_failed|needs_human",
  "loop_policy": {},
  "recommended_batch": {}
}
```

This hook can be called manually, by `claude_stop_gate.py`, or by a future Claude Code
hook event. It must fail open for hook runtime errors but report deterministic
errors in manual CLI mode.

## Loop Runner

Add `scripts/oag_loop_runner.py`.

Initial modes:

- `plan_only`: repeatedly calls the hook/planner and reports what would run.
- `dispatch`: creates dispatch packets or wavefront tasks, but does not perform
  closure.
- `execute`: only allowed for explicitly safe job classes.

Runner loop:

```text
for iteration in max_iterations:
  decision = oag_loop_hook(policy)
  if decision.stop:
      stop with reason
  materialize batch according to job policy
  run oag.compile/check equivalents for the IP
  stop if validation fails
```

The runner must write a loop receipt under
`ontology/runs/<run_id>/loop_decision.json` or the matching active run directory
when attached to `oag.run.start`.

## Job Execution Policy

Default automation policy:

| Job type | Default mode | Rule |
| --- | --- | --- |
| `VALIDATION_RECORD_JOB` | `execute` | Only when evidence exists, is fresh, and parent authority is active. |
| `STALE_REFRESH_JOB` | `dispatch` | Refresh evidence through the owning worker; do not supersede silently. |
| `TB_SCOREBOARD_COVERAGE_JOB` | `dispatch` | Use TB or evidence worker dispatch and receipt. |
| `FORMAL_ASSERTION_JOB` | `dispatch` | Use formal/evidence worker dispatch and receipt. |
| `SIM_RUN_JOB` | `dispatch` | Use sim/evidence worker dispatch and receipt. |
| `RTL_IMPLEMENT_JOB` | `dispatch` | Use RTL implementation agent dispatch; main agent does not write locked RTL. |
| `WRITE_CONTRACT_JOB` | `plan_only` | Contract semantics need explicit review before lock. |
| `TARGET_LOCK_JOB` | `plan_only` | Requires human or decision-matrix authority. |
| `GATE_REVIEW_JOB` | `plan_only` | Requires independent reviewer/gate authority. |

Any `execute` mode must still run compile/check after the action.

## `oag.run.next` Integration

`oag.run.next` should become a scheduler consumer:

1. If an active loop policy exists, call the bounded planner.
2. If a recommended batch exists, return `next_batch` and a compatible
   `next_action`.
3. If no batch exists inside the boundary, return terminal stop metadata without
   checkpointing the full IP.
4. If no loop policy exists, keep the current graph-backed behavior.

Extended response shape:

```json
{
  "schema_version": "oag_run_next.v1",
  "next_batch": {},
  "next_action": {},
  "loop_policy": {},
  "loop_stop_reason": ""
}
```

`next_action` remains for prompt compatibility. `next_batch` becomes the
machine-readable scheduler contract.

## Wavefront Materialization

The wavefront layer should consume a planner batch, not raw open diagnosis.

```text
planner batch
  -> wavefront materializer
  -> N dependency-safe tasks
  -> native subagent dispatches
  -> receipts
  -> parent verification
```

Rules:

- batch is the execution unit;
- leaf obligation is the closure accounting unit;
- requirement is the reporting unit;
- parallel tasks may produce evidence shards;
- parent records ROCEV closure only after shard evidence and integration merge.

## Stop Reasons

Use stable stop reasons:

- `boundary_reached`: no runnable work remains at or before `until`;
- `limit_reached`: current planner batch limit is consumed;
- `max_iterations_reached`: runner safety cap hit;
- `check_failed`: compile/check failed after a batch;
- `needs_human`: target lock, gate, waiver, or decision authority is required;
- `dispatch_inflight`: native subagent or wavefront task is still active;
- `no_runnable_batch`: dependencies block all in-bound work;
- `planner_error`: bounded planner failed.

Hooks must not turn `boundary_reached` into a failure. It means "stop here by
policy."

## Implementation Order

1. Add the loop policy parser and JSON schema coverage. Phase 1 implements the
   parser and runtime schema versions; standalone JSON schema coverage remains
   deferred.
2. Add `oag_loop_hook.py` in `plan_only` mode. Done.
3. Add smoke tests for `--until rtl`, `--until tb`, requirement filtering,
   owner filtering, and `--limit`.
4. Add `oag_loop_runner.py --mode plan_only` with stop reason reporting. Done.
5. Teach `oag.run.next` to include `next_batch` when loop policy is active. Done.
6. Add dispatch materialization for RTL/TB/evidence jobs.
7. Allow `VALIDATION_RECORD_JOB` execute mode only after evidence freshness,
   graph dependency, and parent authority checks pass.
8. Connect `claude_stop_gate.py` to the hook only after manual runner behavior is
   covered by smoke tests.
9. Add wavefront materializer support for planner batches.

## Acceptance Criteria

- `--until rtl` never schedules TB, evidence, record, or gate jobs.
- `--until tb` never schedules record or gate jobs.
- Requirement, obligation, owner-module, job-type, and limit filters compose.
- Hook output is deterministic JSON with `continue` or `stop`.
- Runner stops on `boundary_reached`, `check_failed`, and
  `max_iterations_reached`.
- `oag.run.next` can expose `next_batch` while preserving legacy `next_action`
  prompt compatibility.
- RTL/TB jobs are dispatch-only by default.
- Record jobs execute only with fresh evidence and parent authority.
- Stop hook remains fail-open for hook runtime errors.
- Smoke tests cover policy parsing, planner invocation, and stop reasons.

## Non-Goals

- Do not put planner priority logic into hooks.
- Do not let hooks directly inspect and choose open obligations.
- Do not auto-lock targets.
- Do not auto-run independent reviewer or signoff gates.
- Do not let main-agent writes bypass native subagent dispatch after lock.
