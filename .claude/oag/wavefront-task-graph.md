# OAG Wavefront Task Graph

The task graph is the durable runtime plan for dependency-safe OAG parallelism.
It lives under:

```text
<ip>/ontology/runs/<run_id>/wavefront_task_graph.json
<ip>/ontology/runs/<run_id>/ownership_locks.json
<ip>/ontology/runs/<run_id>/barriers.json
<ip>/knowledge/wavefront/<run_id>/events.jsonl
```

## Task Shape

```json
{
  "task_id": "TB_AXI_VDM",
  "kind": "write",
  "phase": "tb_scenario",
  "agent_type": "oag-tb-implementation-agent",
  "depends_on": ["TB_COMMON_API", "TB_SCOREBOARD_SCHEMA"],
  "barrier_inputs": ["tb_common_import_clean", "scoreboard_schema_frozen"],
  "barrier_outputs": ["scenario_import_clean"],
  "allowed_write_paths": ["tb/cocotb/test_axi_vdm.py"],
  "shared_artifacts": [],
  "ownership_mode": "exclusive_file",
  "status": "pending",
  "may_claim_complete": false
}
```

## Status Values

- `pending`: not claimed and may become ready.
- `claimed`: owned by an active worker.
- `handoff_pass`: worker produced bounded handoff evidence.
- `blocked`: worker found a blocker.
- `failed`: worker failed its scoped task.
- `inconclusive`: worker could not determine result.
- `waived`: dependency waived by decision receipt.
- `closed`: parent/integration accepted the result.

## Ownership Modes

- `none`: read-only or report-only task.
- `exclusive_file`: all write paths require exclusive locks.
- `integration_owner`: task may own shared artifacts for one phase.

## Anti-Patterns

- Starting TB scenario shards before helper/API/schema barriers exist.
- Letting two workers edit the same helper, runner, filelist, or result file.
- Allowing a worker receipt to claim closure.
- Repairing failing simulation before read-only failure triage.
