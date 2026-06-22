# OAG Tool-call Contract

OAG is the common interface for Claude Code, CI, and human shells. Runtimes should
call OAG instead of implementing ontology policy.

## Envelope

```json
{
  "tool": "oag.context",
  "arguments": {
    "ip_dir": "example_ip",
    "stage": "sim",
    "intent": "coverage blocked scoreboard"
  }
}
```

Responses always use:

```json
{
  "schema_version": "oag_tool_response.v1",
  "ok": true,
  "tool": "oag.context",
  "result": {},
  "errors": []
}
```

## Tools

- `oag.scaffold`: create ontology-first IP folders and seed ROCEV files.
- `oag.inspect`: read-only scan of legacy IP artifacts.
- `oag.init`: create `<ip>/knowledge`.
- `oag.context`: return structured records plus a prompt block.
- `oag.compile`: compile ontology YAML into
  `ontology/generated/design_truth_graph.json`, generated design work packets,
  and an extracted RTL design facts graph.
- `oag.record`: append actor-provenanced ROCEV record.
- `oag.draft`: persist requirement interview facts without promoting them to
  locked truth.
- `oag.ticket`: write a contract-linked failure ticket for owner-routed repair.
- `oag.check`: validate knowledge ledger presence/schema, protected fields,
  append-only hash chain, monotonic closure, closure matrix, evidence file
  hashes, and stage receipts.
- `oag.decide`: allow/block an action such as `claim_complete`; with
  `record_decision: true`, write a decision receipt. Completion actions are
  blocked when this flag is omitted after other gates pass.
- `oag.run.start`: start a durable run under `ontology/runs/<run_id>/` and
  derive the first target obligation.
- `oag.run.next`: refresh and return exactly one next action for an active run.
- `oag.run.record`: record ROCEV evidence for the active run target and refresh
  the next action.
- `oag.run.checkpoint`: compile/check/decide for the active run and update run
  status.
- `oag.stop_check`: return whether an active run is incomplete and provide a
  prompt block for the next action.
- `oag.graph`: build a Requirement -> Obligation -> Contract -> Evidence ->
  Validation graph and optional self-contained HTML viewer.

## Object Vocabulary

- Requirement: what must be true.
- Obligation: smaller promise that can be judged.
- Contract: method and pass condition for judging the obligation.
- Evidence: files, test node IDs, commits, logs, waves, or proofs.
- Validation: decision from evidence.
- Actor: human, ai, system, or tool that made the claim.
- KnowledgeRecord: event/finding/decision that links ROCEV objects.
- InterviewDraft: pre-lock requirement knowledge captured from a deep interview.
- ScoreboardRow: simulator-independent expected-vs-observed row emitted by any
  TB implementation or adapter.
- StageContract: stage-local inputs, outputs, owner, and gate.
- StageRunReceipt: input/output fingerprints from one stage execution.
- DecisionReceipt: durable allow/block decision under `ontology/validations/`.
- FailureTicket: one unclosed contract routed to the owning repair workflow.
- GateSelfTest: proof that a validator rejects known-bad mutations.
- DesignRule: reusable semantic rule such as same-cycle priority,
  event/state commit consistency, scoreboard evidence schema, or
  contract-to-proof coverage, plus reusable coding policy such as module file
  boundaries and the RTL language subset.
- DesignRuleInstance: an IP-local application of a DesignRule tied to concrete
  Requirement, Obligation, Contract, and Evidence objects.
- StructureNamespace: one declaration point for ports, signals, registers,
  state, derived signals, clocks, resets, and interfaces.
- Decomposition: module graph, structure profile, edit ownership, legacy
  preservation policy, and obligation/contract ownership.
- GeneratedDesignSpec: read-only `ontology/generated/design_spec.json`
  projection compiled from authored ontology.
- DesignFactsGraph: read-only `ontology/generated/design_facts_graph.json`
  implementation fact graph extracted from current RTL. It records modules,
  ports, parameters, registers, memories, instances, source file SHA-256 hashes,
  extractor backend, and git HEAD when available. It is evidence/provenance, not
  locked design intent.
- AuthoringPacket: read-only module work packet under
  `ontology/generated/authoring_packets/` for Claude Code, Claude, CI, or an
  orchestrator worker.
- ProtectedField: locked truth or policy field that cannot be semantically
  changed by an unapproved AI action.
- EvidenceLedger: append-only `knowledge/ledger.jsonl` hash chain for records,
  drafts, tickets, decisions, and approvals.
- MonotonicClosure: invariant that closed/passed objects cannot be weakened back
  to draft/open/stale without an approved decision.
- ClosureMatrix: check that each Obligation is linked to a Contract and a closed
  Validation record.
- OagRun: durable execution state under `ontology/runs/<run_id>/` that drives
  one next action until verified completion.

Execution style is metadata, not an ontology branch. A record may say it came
from a single worker, orchestrator, CI, human shell, Claude Code, or Claude, but the
closure policy is shared.

## Run Loop

Use the run loop when the agent should continue across edits, tests, stop hooks,
or different agent surfaces:

```json
{
  "tool": "oag.run.start",
  "arguments": {
    "ip_dir": "example_ip",
    "stage": "rtl",
    "intent": "close RTL decomposition obligations"
  }
}
```

This writes:

- `ontology/runs/<run_id>/run_state.json`
- `ontology/runs/<run_id>/next_action.json`
- `ontology/runs/<run_id>/checkpoint_history.jsonl`
- `ontology/runs/active_run.json`

The returned next action names one obligation, its contracts, owning module, any
missing evidence, and the command shape for recording evidence. The run loop is
not a second source of truth. It derives from the closure matrix and closes only
through normal ROCEV records and decision receipts.

Typical loop:

```text
oag.run.start
oag.run.next
agent edits/builds/tests
oag.run.record
oag.run.checkpoint
oag.stop_check
```

`oag.stop_check` returns `should_continue: true` while the active run is
unfinished and includes an `OAG NEXT ACTION` prompt block. After repeated
identical checkpoint blockers, run status becomes `needs_human` instead of
spinning forever.

## Minimum Record Shape

```json
{
  "actor": {"kind": "ai", "id": "claude", "surface": "cli"},
  "rocev": {
    "requirement": {"id": "REQ_ID", "source": "req/locked_truth.md"},
    "obligation": {"id": "OBL_ID", "text": "small checkable promise"},
    "contract": {"id": "CONTRACT_ID", "method": "scoreboard", "pass_condition": "mismatch count is zero"},
    "evidence": {"files": ["sim/results.xml"], "tests": [], "commit": ""},
    "validation": {"status": "closed", "verdict": "pass", "rationale": "why this evidence closes the obligation"}
  }
}
```

Closed records must have `rocev.validation.status` explicitly set to a closed
status and must have explicit evidence: file, test node ID, or commit. Evidence
files are stored with SHA-256 hashes in the generated knowledge record; if a
file changes later, `oag.check` reports stale evidence. Every `oag.record` call
appends an EvidenceLedger event. Human approvals should use
`actor.kind: "human"` and `type: "decision"` when changing protected truth or
signoff policy.

## Interview Drafts

Deep interviews should be durable before the user explicitly promotes them to
locked truth. Call `oag.draft` after each meaningful answer round and before any
long context transition:

```json
{
  "tool": "oag.draft",
  "arguments": {
    "ip_dir": "example_ip",
    "stage": "req",
    "title": "Architecture interview round 1",
    "summary": "Draft notes for the IP architecture before locked-truth promotion.",
    "facts": ["Ingress data width is not locked yet"],
    "decisions": ["Reset behavior must be captured as a checkable obligation"],
    "assumptions": ["Register map details remain draft until human confirmation"],
    "open_questions": ["Exact interface timing and byte-lane policy"]
  }
}
```

This writes:

- `knowledge/records/<id>.json`
- `ontology/drafts/<id>.json`
- `req/interview_draft.md`

Drafts are not signoff truth. Promote them into `req/locked_truth.md` and
canonical `ontology/requirements.yaml` only after explicit human confirmation.
If a runtime exposes context usage, treat about 70% or higher as a pressure
point and save a draft before continuing.

## Compile And Closure Policy

Run `oag.compile` after changing ontology files:

```json
{
  "tool": "oag.compile",
  "arguments": {"ip_dir": "my_timer_ip"}
}
```

The compiler writes `ontology/generated/design_truth_graph.json`,
`ontology/generated/design_spec.json`,
`ontology/generated/design_facts_graph.json`, and
`ontology/generated/authoring_packets/*.json`. These are derived views. Do not
hand-edit them. The design facts graph is extracted from RTL using `pyslang`
when available, with a conservative parser fallback, and is compared against
`ontology/decomposition.yaml` so current-IP modules cannot silently drift from
the authored module map. The source remains `ontology/requirements.yaml`,
`ontology/obligations.yaml`, `ontology/contracts.yaml`,
`ontology/structure.yaml`, `ontology/decomposition.yaml`,
`ontology/design_rules.yaml`, `ontology/stages.yaml`, and
`ontology/policies.yaml`.

For lint evidence, generated scaffolds support an optional pyslang backend:

```bash
OAG_LINT_BACKEND=pyslang scripts/run_lint.sh
```

This writes `lint/dut_lint.json` through
`.claude/scripts/oag_pyslang_lint.py`. It is syntax/static evidence only and does
not replace Verilator lint, simulation, scoreboard, or closure validation.

`ontology/policies.yaml` uses one closure strictness field:

```yaml
closure_profile: development   # draft | development | signoff
```

There is no separate Run Mode / Exec Mode split in OAG. `closure_profile`
controls whether a signoff-grade action is allowed; execution details belong in
the actor/execution metadata of records and receipts.

## Structure, Decomposition, And Generated Work Packets

OAG separates design truth from implementation shape:

- `ontology/structure.yaml`: shared namespace. Contracts and modules reference
  structure ids instead of redeclaring signal/register names and widths.
- `ontology/decomposition.yaml`: module ownership graph. Every obligation and
  contract should be owned by a module.
- `ontology/policies.yaml: structure_policy`: allowed structure profiles.
- `ontology/generated/design_spec.json`: worker-friendly projection.
- `ontology/generated/authoring_packets/*.json`: one packet per module.
- `ontology/generated/design_facts_graph.json`: extracted current RTL module,
  port, register, memory, and instance facts with source hashes.

Supported decomposition profiles:

- `small_leaf_single_file`: one small editable leaf module is allowed with a
  rationale.
- `greenfield_modular`: new nontrivial IPs require at least two current-IP
  modules, explicit ownership boundaries, and a unique RTL file per current-IP
  module by default. Shared files require explicit `shared_file_rationale`.
- `legacy_preserve`: imported existing hierarchy is preserved; requirements and
  evidence are mapped onto legacy modules before repair/signoff.
- `wrapper_adapter`: legacy or child core remains protected while editable
  wrapper/adapter modules own new integration obligations.

This is intentionally flexible. OAG does not force every IP into a new hierarchy
and does not let greenfield complex IPs hide all behavior in one unowned top
module. If a generated packet is wrong, fix authored ontology and rerun
`oag.compile`.
If the design facts graph reports an unmapped extracted module or a missing
current-IP module, fix the RTL file/module name or fix the authored
decomposition. Do not hand-edit the generated facts file.

`oag.decide action=signoff` requires:

- `closure_profile: signoff`
- compiled truth graph
- no artifact evidence gaps
- closed closure matrix
- explicit closed ROCEV validation records
- fresh evidence file hashes
- at least one fresh `stage_run_receipt.v1`
- knowledge/evidence records that pass `oag.check`
- clean `ontology/protection.yaml` protected-field snapshot
- valid append-only `knowledge/ledger.jsonl` hash chain
- no monotonic closure downgrade
- decision receipt for the completion action

The policy transition to `closure_profile: signoff` is itself protected. Record a
human decision after the edit before expecting signoff to pass.

## Verified Completion

OAG completion is not "tests passed." Completion is:

1. `oag.record` stores ROCEV with explicit `rocev.validation.status`.
2. `oag.check` proves the closure matrix has every obligation linked to a
   contract and a closed validation record.
3. `oag.check` proves closed record evidence still matches recorded SHA-256
   hashes.
4. `oag.decide` allows the action.
5. `oag.decide` is called with `record_decision: true`, producing
   `ontology/validations/<decision_id>.json` and a ledger event.

Example:

```json
{
  "tool": "oag.decide",
  "arguments": {
    "ip_dir": "my_timer_ip",
    "action": "claim_complete",
    "stage": "sim",
    "intent": "close reset scoreboard obligation",
    "record_decision": true,
    "actor": {"kind": "ai", "id": "claude", "surface": "cli"}
  }
}
```

Decision receipts use `schema_version: oag_decision_receipt.v1` and include the
action, allow/block result, check issues, closure matrix, truth graph state, and
ledger event hash.

## Protected Fields, Ledger, And Monotonic Closure

New scaffolds include:

- `ontology/protection.yaml`: declares protected paths and fields such as
  locked truth, requirements, obligations, contracts, and closure policy.
- `knowledge/ledger.jsonl`: append-only JSONL ledger. Each event stores
  `prev_hash`, `payload_hash`, `event_hash`, protected-file snapshots, and
  monotonic subject statuses.

OAG treats the model as an untrusted client. If a protected file changes after a
ledger baseline and the next event is not human-approved, `oag.check` blocks.
If a ledger event is edited, the hash chain breaks. If a previously
closed/passed object is recorded as draft/open/stale by AI, monotonic closure
blocks the claim. A discovered defect should be recorded as `refuted`, not by
silently weakening prior closure.

## Common Design Rules

`ontology/design_rules.yaml` is the IP-local rulebook seeded by
`oag.scaffold`. The required rule kinds are:

- `event_state_commit_consistency`: side-effect event generation and the state
  update it implies must use the same effective commit condition.
- `same_cycle_priority_declared`: collisions such as write-vs-hardware-update,
  clear-vs-set, disable-vs-terminal-tick, or reset-vs-valid must name the
  winning action in requirement truth.
- `scoreboard_evidence_schema`: expected-vs-observed evidence must use
  `scoreboard_rows.v1` with DUT-facing `observed_source`.
- `contract_to_proof_coverage`: a contract may only claim a proof scope that is
  backed by matching assertion, formal, scoreboard, coverage, log, or waveform
  evidence.
- `cdc_crossing_coverage`: a CDC/RDC claim must identify clock/reset domains or
  crossings and cite CDC/RDC review or tool evidence.
- `protocol_compliance`: an interface protocol claim such as AXI, APB,
  streaming, or valid/ready must cite assertion, monitor, VIP, or protocol
  scoreboard evidence.
- `timing_closure`: a timing claim must declare target frequency or target
  clocks, cite SDC constraints derived from those clocks and CDC policy, cite
  timing reports, and report setup/hold status.
- `functional_coverage_closure`: functional coverage closure must cite observed
  coverage refs and show `coverage_actual >= coverage_goal`.
- `reset_xprop_coverage`: reset/X-prop closure must name reset scenarios or
  X-prop checks and cite observed evidence.

The last five are SSOT-aligned signoff domain gates for clock/reset domains,
CDC/RDC requirements, interface protocols, timing/STA expectations, and coverage
outputs. DFT and power are deliberately not default OAG v1 gates.

The scaffold leaves semantic hazard examples as `status: template`. When an IP
actually has the hazard, create or activate an instance:

```yaml
instances:
  - id: TIMER_DISABLE_VS_EXPIRY_PRIORITY
    rule: RULE_SAME_CYCLE_PRIORITY_DECLARED
    status: active
    conflict: [ctrl_disable_write, terminal_tick]
    priority: ctrl_disable_write
    requirement: REQ_TIMER_DISABLE_PRIORITY
    obligation: OBL_TIMER_NO_EXPIRY_ON_DISABLE
    contract: CONTRACT_TIMER_DISABLE_PRIORITY
```

For event/state consistency:

```yaml
instances:
  - id: TIMER_EXPIRY_COMMIT_CONDITION
    rule: RULE_EVENT_STATE_COMMIT_CONSISTENCY
    status: active
    event: expiry_event
    state_update: irq_status_set
    commit_condition: enable_next && prescale_terminal && value_q <= 1
    contract: CONTRACT_TIMER_EXPIRY_COMMIT
```

For RTL language policy:

```yaml
rules:
  - id: RULE_RTL_LANGUAGE_SUBSET
    kind: rtl_language_subset
    status: active
    severity: block
    allowed_constructs: [logic, generate, genvar, generate_for]
    forbidden_constructs:
      - procedural_for
      - procedural_while
      - procedural_repeat
      - procedural_forever
      - package
      - import
      - interface
      - modport
      - typedef
      - enum
      - always_ff
      - always_comb
      - always_latch
```

This rule means `logic` is allowed, and Verilog generate constructs are allowed
for static elaboration. Ordinary procedural loops are not part of the generated
RTL subset unless they are expressed as generate-time structure.

For greenfield module/file ownership:

```yaml
rules:
  - id: RULE_MODULE_FILE_BOUNDARY
    kind: module_file_boundary
    status: active
    severity: block
    text: Greenfield modular IPs map each current_ip module to a unique RTL file by default.
```

In `ontology/decomposition.yaml`, shared current-IP module files in
`greenfield_modular` require `shared_file_rationale` on the profile or on each
module sharing the file. `small_leaf_single_file`, `legacy_preserve`, and
`wrapper_adapter` are the normal escape hatches for intentionally different
shapes.

OAG does not try to infer all RTL semantics in v1. It blocks malformed active
instances and formal/assertion contracts that claim proof without proof refs.
In `closure_profile: signoff`, active contract-to-proof instances must carry
evidence refs.

Closed signoff domain instances must carry requirement, obligation, contract,
and evidence refs. Coverage-bearing domain instances must use `coverage_refs`
that are observed in `sim/scoreboard_events.jsonl` or `cov/coverage.json`;
`functional_coverage_closure` also requires `coverage_goal` and
`coverage_actual` and blocks when actual coverage is below the goal.
`timing_closure` also requires `target_frequency_mhz`, `target_period_ns`, or
`target_clocks` entries with `frequency_mhz` or `period_ns`. For multiple
target clocks or CDC/RDC-relevant timing, declare `async_clock_groups` or
`cdc_constraints`. Input/output delay ratios default to 0.5 of the clock period
when omitted; if specified, `input_delay_ratio`, `output_delay_ratio`, or
`io_delay_ratio` must be between 0.0 and 1.0.

## Stage Receipts

Stage receipts live under `ontology/evidence/stage_runs/*.json`:

```json
{
  "schema_version": "stage_run_receipt.v1",
  "stage": "sim",
  "owner": "sim",
  "status": "pass",
  "command": "make sim",
  "actor": {"kind": "tool", "id": "ci"},
  "started_at": "2026-06-13T00:00:00Z",
  "completed_at": "2026-06-13T00:00:04Z",
  "input_fingerprints": [{"path": "rtl/rtl_compile.json", "sha256": "..."}],
  "output_fingerprints": [{"path": "sim/results.xml", "sha256": "..."}]
}
```

For signoff, every listed path must exist and match the recorded SHA-256.

## Graph Output

The graph shape is:

```json
{
  "schema_version": "oag_ontology_graph.v1",
  "graph": {
    "nodes": [
      {"id": "requirement::REQ_RESET", "type": "requirement", "label": "REQ_RESET"}
    ],
    "edges": [
      {"source": "requirement::REQ_RESET", "target": "obligation::OBL_RESET", "label": "has_obligation"}
    ]
  }
}
```

Common node types: `ip`, `requirement`, `obligation`, `rule`,
`rule_instance`, `contract`, `evidence`, `validation`, `decision`, `policy`,
`protection`, `ledger`, `stage`, `gate`, `ticket`, `receipt`, `actor`,
`record`, `artifact`, and `gap`.

## Failure Tickets

Use `oag.ticket` when a stage fails and repair should be routed:

```json
{
  "tool": "oag.ticket",
  "arguments": {
    "ip_dir": "my_timer_ip",
    "stage": "sim",
    "reason": "scoreboard mismatch",
    "failing_contract": {"id": "CONTRACT_SIM_SCOREBOARD"},
    "expected": {"count": 3},
    "observed": {"count": 2},
    "evidence": {"files": ["sim/scoreboard_events.jsonl"]},
    "editable_files": ["rtl/timer.sv"],
    "forbidden_edits": ["req/locked_truth.md", "ontology/requirements.yaml"],
    "required_evidence_after_patch": ["sim/results.xml", "sim/scoreboard_events.jsonl"]
  }
}
```

The repair unit is one unclosed contract. If the locked truth is ambiguous, write
a ticket or record that requires human decision instead of patching truth.

## Scoreboard Rows

OAG does not standardize the TB language, framework, simulator, or generator.
It standardizes the submitted evidence row:

```json
{
  "goal_id": "GOAL_RESET",
  "scenario_id": "SC_RESET_001",
  "cycle": 12,
  "stimulus": {"rst_n": 0},
  "expected": {"count": 0},
  "expected_source": {"kind": "manual_spec", "ref": "req/locked_truth.md"},
  "observed": {"count": 0},
  "observed_source": {"kind": "dut_signal", "path": "dut.count"},
  "passed": true,
  "mismatch": "",
  "coverage_refs": ["COV_RESET"]
}
```

Required fields for `scoreboard_rows.v1`: `goal_id`, `scenario_id`, `cycle`,
`stimulus`, `expected`, `observed`, `observed_source`, `passed`, `mismatch`,
and `coverage_refs`.

`expected_source.kind` may be `fl_model`, `cl_model`, `golden_vector`,
`assertion`, `manual_spec`, or `reference_log`. `observed_source.kind` must be
DUT-facing: `dut_signal`, `monitor`, `waveform`, `transaction`, `assertion`,
`interface_sample`, or `bus_monitor`.

Adapters may convert Verilog, SystemVerilog, UVM, Python, cocotb, commercial
simulator, or waveform evidence into this JSONL shape. A row fails validation
when `observed_source` is missing or points at a model/reference source.

## Scaffold Layout

`oag.scaffold` creates a local IP operating-system skeleton:

- Source truth: `req/locked_truth.md`, `req/requirements.yaml`,
  `req/evidence_plan.yaml`.
- Canonical ontology: `ontology/ip.yaml`, `ontology/requirements.yaml`,
  `ontology/obligations.yaml`, `ontology/contracts.yaml`,
  `ontology/design_rules.yaml`, `ontology/drafts/`, `ontology/stages.yaml`,
  `ontology/policies.yaml`,
  `ontology/actors.yaml`, `ontology/actions.yaml`, `ontology/graph.json`,
  `ontology/generated/`, `ontology/evidence/scoreboard_rows.v1.yaml`,
  `ontology/evidence/stage_run_receipt.v1.yaml`,
  `ontology/decision_receipt.v1.yaml`,
  `ontology/gates/gate_self_test_registry.yaml`, `ontology/validations/`.
- Agent memory: `knowledge/_index.json`, `knowledge/records/`,
  `knowledge/views/`, `knowledge/views/_generated/`, `knowledge/views/promoted/`.
- Handoff: `handoff/failure_tickets/`.
- Artifact homes: `rtl/`, `tb/`, `sim/`, `lint/`, `cov/`, `formal/`,
  `syn/`, `sdc/`, `list/`, `doc/`, `signoff/`.

Tool-call example:

```json
{
  "tool": "oag.scaffold",
  "arguments": {
    "ip_dir": "my_timer_ip",
    "owner": "brian",
    "force": false
  }
}
```
