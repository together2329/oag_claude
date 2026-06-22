# .claude OAG Pack

This file governs maintenance of the OAG pack under `.claude/`. The repository
root intentionally does not carry `AGENTS.md`; runtime OAG behavior is activated
by the exact `oag` keyword through `.claude/oag/oag-mode-directive.md` and the
UserPromptSubmit hook.

Primary assets:

- `oag/oag-mode-directive.md`
- `oag/modeling-contract-principles.md`
- `oag/agent-common-preamble.md`
- `oag/principles.md`
- `oag/modeling-policy.md`
- `oag/deep-semantic-intake-policy.md`
- `oag/requirements-quality-policy.md`
- `oag/requirement-decomposition-principles.md`
- `oag/assume-guarantee-contracts.md`
- `oag/contract-strength-policy.md`
- `oag/phenomena-boundary-model.md`
- `oag/decision-matrix-policy.md`
- `oag/authoring-packet-policy.md`
- `oag/traceability-policy.md`
- `oag/wavefront-policy.md`
- `oag/wavefront-task-graph.md`
- `oag/contract-projection.md`
- `oag/rtl-implementation.md`
- `oag/rtl-dialect-policy.md`
- `oag/rtl-ppa-principles.md`
- `oag/domain-crossing-principles.md`
- `oag/clock-reset-architecture.md`
- `oag/cdc-rdc-evidence.md`
- `oag/verification-methodology-principles.md`
- `oag/verification-strategy-policy.md`
- `oag/tb-methodology-policy.md`
- `oag/tb-architecture-patterns.md`
- `oag/coverage-closure-policy.md`
- `oag/assertion-formal-policy.md`
- `oag/scoreboard-evidence.md`
- `oag/recovery-playbook.md`
- `rules/oag-invariants.rules.md`
- `rules/oag-rule-index.yaml`
- `rules/oag-requirements-quality.rules.md`
- `rules/oag-requirement-decomposition.rules.md`
- `rules/oag-lock-readiness.rules.md`
- `rules/oag-contract-strength.rules.md`
- `rules/oag-authoring-packet.rules.md`
- `rules/oag-traceability.rules.md`
- `rules/oag-wavefront.rules.md`
- `rules/oag-verification-strategy.rules.md`
- `rules/oag-rtl-ppa.rules.md`
- `rules/oag-cdc-rdc.rules.md`
- `rules/oag-tb-methodology.rules.md`
- `skills/oag-ip-workflow/SKILL.md`
- `skills/oag-deep-semantic-intake/SKILL.md`
- `skills/oag-decision-matrix/SKILL.md`
- `skills/oag-contract-projection/SKILL.md`
- `skills/oag-authoring-packet/SKILL.md`
- `skills/oag-evidence-closure/SKILL.md`
- `skills/oag-wavefront/SKILL.md`
- `rules/oag-rocev.rules.md`
- `agents/oag-*.md`
- `oag/agent-catalog.toml`
- `oag/ip-dev-agent.md`
- `oag/subagent-workflows.md`
- `hooks/oag_pre_work.py`
- `hooks/oag_interview_draft.py`
- `hooks/oag_stop_check.py`
- `hooks/oag_hook_utils.py`
- `hooks/claude_context_inject.py`
- `hooks/claude_draft_pressure.py`
- `hooks/claude_native_subagent_guard.py`
- `hooks/claude_stop_gate.py`
- `hooks/claude_subagent_oag_start.py`
- `hooks/claude_subagent_oag_gate.py`
- `hooks.json`
- `scripts/oag_cli.py`
- `scripts/oag_scaffold_ip.py`
- `scripts/oag_graph.py`
- `scripts/oag_portable_db.py`
- `scripts/oag_okf.py`
- `scripts/oag_eval.py`
- `scripts/oag_agent_catalog_check.py`
- `scripts/oag_claude_config_doctor.py`
- `scripts/oag_closure_check.py`
- `scripts/oag_dispatch.py`
- `scripts/oag_ppa_check.py`
- `scripts/oag_pyslang_lint.py`
- `scripts/oag_domain_crossing_check.py`
- `scripts/oag_req_quality_check.py`
- `scripts/oag_requirement_atom_check.py`
- `scripts/oag_lock_readiness_check.py`
- `scripts/oag_contract_strength_check.py`
- `scripts/oag_authoring_packet_check.py`
- `scripts/oag_trace_graph_check.py`
- `scripts/oag_wavefront.py`
- `scripts/oag_deep_semantic_intake.py`
- `scripts/oag_decision_matrix_generate.py`
- `scripts/oag_verification_plan_check.py`
- `scripts/oag_validate_json.py`
- `scripts/oag_protected_receipt_audit.py`
- `scripts/oag_pack_release_check.py`
- `scripts/oag_workflow_whole_db.py`
- `scripts/oag_exec_auto_research.py`
- `schemas/*.schema.json`
- `config.toml`

Use OAG as the common interface for Requirement -> Obligation -> Contract ->
Evidence -> Validation IP work.
Use the OAG principle documents as the reasoning layer, not as templates to
fill. `oag/principles.md` defines design-truth preservation,
`oag/modeling-policy.md` defines profile-based FL/CL and oracle depth,
`oag/deep-semantic-intake-policy.md` defines source claims and ambiguity
capture for compressed user/spec intent, `oag/requirements-quality-policy.md`
defines lock-ready requirement shape and source traceability,
`oag/requirement-decomposition-principles.md` defines the OAG V2 semantic atom
layer before obligations, `oag/assume-guarantee-contracts.md` defines
environment assumptions versus DUT guarantees,
`oag/contract-strength-policy.md` defines implementation-ready contract
strength, oracle projection, and weak-contract blockers,
`oag/phenomena-boundary-model.md` defines monitored/controlled phenomena and
DUT boundary ownership, `oag/decision-matrix-policy.md` defines unresolved,
proposed, decided, waived, and blocked product decisions before lock-ready
implementation, `oag/authoring-packet-policy.md` defines role-specific
`rtl__*.json` and `tb__*.json` packets, `oag/traceability-policy.md` defines
source-to-contract-to-evidence ID governance, `oag/contract-projection.md`
defines ROCEV projection,
`oag/rtl-implementation.md` defines how generated RTL implements locked
contract truth without inventing semantics, `oag/rtl-dialect-policy.md` defines
the portable RTL subset, `oag/rtl-ppa-principles.md` defines correctness-first
PPA-aware RTL structure, `oag/domain-crossing-principles.md` and
`oag/clock-reset-architecture.md` define CDC/RDC domain-safety intent, domain
inventory, and allowed crossing patterns, `oag/cdc-rdc-evidence.md` defines
development vs release CDC/RDC evidence strength,
`oag/verification-methodology-principles.md` defines framework-neutral TB
methodology, `oag/verification-strategy-policy.md` defines the split between
verification strategy and TB implementation, `oag/tb-methodology-policy.md`
defines profile-scaled TB depth, `oag/tb-architecture-patterns.md` defines driver/monitor/predictor/scoreboard
roles, `oag/coverage-closure-policy.md` defines coverage that can and cannot
support closure, `oag/assertion-formal-policy.md` defines assertion/formal
escalation, `oag/scoreboard-evidence.md` defines expected/observed
independence, and `oag/agent-common-preamble.md` defines the common OAG agent
posture. The principle is that full FL/CL artifacts are profile-dependent, but
the responsibilities carried by FL/CL are not optional when an obligation is
claimed closed. Likewise, UVM, cocotb, SV, Verilog, OSVVM, UVVM, and simulator
adapters are implementation choices; verification methodology responsibilities
are not optional for TB closure.

Use `rules/oag-rule-index.yaml` as the stable ID map from hard rules to policy
documents and executable checkers. For example, `RULE-LOCK-003` maps
lock-required decisions to `oag/decision-matrix-policy.md` and
`scripts/oag_lock_readiness_check.py`. Validation and gate reports should prefer
stable rule IDs when they need durable blocker names.

The default OAG workflow is script/skill based, not MCP based. Keep MCP server
registration out of `.claude/config.toml`, and do not ship `.claude/mcp.json` in
the pack. Use `.claude/scripts/oag_cli.py`, `.claude/scripts/oag_dispatch.py`,
hooks, and the `oag-ip-workflow` skill as the primary runtime surface.
`oag-ip-workflow` is the umbrella router skill. Use the narrower skills for
their specific lanes: `oag-deep-semantic-intake` for source claims and
ambiguity, `oag-decision-matrix` for lock-blocking decisions,
`oag-contract-projection` for requirement atom to assume/guarantee contract
projection, `oag-authoring-packet` for role-specific `rtl__*.json` and
`tb__*.json` packet handoff, `oag-wavefront` for dependency-aware parallel
dispatch planning, ownership locks, barriers, and failure-triage fan-out, and
`oag-evidence-closure` for trace, scoreboard, coverage, validation, and gate
readiness.
`oag_claude_config_doctor.py --apply` removes known OAG MCP server registrations
from user config while preserving unrelated Claude Code MCP tools such as browser or
editor helpers.
Native subagents must not depend on MCP startup for APB/RTL/TB/lint/sim/gate
execution.
Use `.claude/scripts/oag_protected_receipt_audit.py` to audit protected
post-lock IP artifacts in ignored/untracked product directories against
dispatch-backed native subagent receipts.
Use `.claude/scripts/oag_ppa_check.py <rtl-file> --json` as the lightweight
PPA/dialect screen for generated RTL changes when RTL files are available.
Use `.claude/scripts/oag_pyslang_lint.py --ip-dir <ip> --json` as the optional
pyslang syntax lint backend for `lint/dut_lint.json`. It complements Verilator
lint and design-facts extraction; it does not prove behavior.
Use `.claude/scripts/oag_domain_crossing_check.py --ip-dir <ip> --json` as the
lightweight CDC/RDC intent screen when domain intent or RTL crossings are in
scope. It does not replace release CDC/RDC tools.
Use `.claude/scripts/oag_req_quality_check.py --ip-dir <ip> --json` as the
lightweight requirement quality screen for `req/source_claims.yaml`,
`req/ambiguity_register.yaml`, and lock-ready requirement shape. After scope
lock it becomes a hard gate for implementation and closure claims.
Use `.claude/scripts/oag_requirement_atom_check.py --ip-dir <ip> --json` as the
lightweight OAG V2 semantic screen for requirement atoms, shallow obligations,
and assume/guarantee contract strength. In draft it supports interview hygiene;
after scope lock it becomes a hard gate for implementation and closure claims.
Use `.claude/scripts/oag_contract_strength_check.py --ip-dir <ip> --json` as the
dedicated contract-strength screen for variables, assume/guarantee, oracle refs,
and proof projection. After lock, weak simulation-pass contracts are blockers,
not closure evidence.
Use `.claude/scripts/oag_lock_readiness_check.py --ip-dir <ip> --json` as the
post-lock readiness screen for `ontology/decision_matrix.yaml` plus the
requirement atom, contract-strength, VPlan, and trace graph gates. It blocks
implementation when any lock-required decision is still unresolved, proposed,
or blocked.
Use `.claude/scripts/oag_verification_plan_check.py --ip-dir <ip> --json` as the
verification strategy screen for `ontology/verification_plan.yaml`. After lock,
TB implementation should consume the verification plan rather than define the
proof strategy it is trying to satisfy.
Use `.claude/scripts/oag_authoring_packet_check.py --ip-dir <ip> --require-packets --json`
before RTL/TB native subagent dispatch to ensure `oag.compile` produced
role-specific `rtl__*.json` and `tb__*.json` packets with independent truth
sources.
Use `.claude/scripts/oag_wavefront.py` when RTL/TB/sim work should be
parallelized. It writes runtime state under `ontology/runs/<run_id>/` and
`knowledge/wavefront/<run_id>/`; it consumes ontology truth and authoring
packets but must not create locked requirements, contracts, or closure
decisions. Read-only triage can fan out aggressively, write tasks need disjoint
ownership locks, shared artifacts need a single integration owner, and workers
must keep `may_claim_complete=false`.
Use `.claude/scripts/oag_trace_graph_check.py --ip-dir <ip> --json` to audit the
source claim -> requirement -> atom -> obligation -> contract -> scenario ->
evidence trace graph.
Use `.claude/scripts/oag_deep_semantic_intake.py` and
`.claude/scripts/oag_decision_matrix_generate.py` to seed draft intake reports
and unresolved profile-driven decision rows such as the `mctp-rx` profile. Seed
recommendations are not locked truth.
Use `.claude/scripts/oag_workflow_whole_db.py` to generate a single Markdown
review bundle of the `.claude` workflow pack as `oag_workflow_whole_db.md`.
The bundle is generated review evidence, not canonical OAG truth.
Use `ontology/verification_plan.yaml` and
`.claude/oag/verification-strategy-policy.md` to define verification objectives,
proof methods, scenarios, coverage goals, assertion/formal candidates, and
residual risk. Use `ontology/tb_methodology.yaml` and
`.claude/oag/tb-methodology-policy.md` to scale TB implementation depth by IP
profile. The TB agent should prefer the smallest self-checking architecture
that satisfies the verification plan while preserving independent expected
behavior, scenario mapping, scoreboard rows, contract-linked coverage, and
assertion or formal hooks when those hooks improve proof strength.

Use `.claude/agents/*.md` as Claude Code custom agent definitions. Each Markdown file must be a standalone Claude Code subagent file with YAML frontmatter fields such as `name`, `description`, and `tools`, followed by role instructions. OAG metadata for those agents lives outside that
loader path in `.claude/oag/agent-catalog.toml`.

The OAG role catalog defines 14 core duties plus 3 custom dynamic duties. The
role Markdown files are prompts and guardrails; durable state is still the IP ontology,
ledger, records, receipts, and evidence artifacts.

Critical OAG reasoning lanes must use `model_reasoning_effort = "xhigh"`:
requirement/contract, legacy/reference analysis, IP contract derivation,
verification strategy, RTL implementation, TB implementation, evidence
validation, and gate review.
Procedural lanes such as lint/static checks, sim execution, coverage, and custom
worker shards may stay lower for throughput.

Before using a subagent role, run:

```bash
python3 .claude/scripts/oag_agent_catalog_check.py
```

Project config must keep `[features].multi_agent = true`,
`[features].child_agents_md = true`, `[features].hooks = true`, and
`[agents].max_depth = 1`. It must also keep
`[features.multi_agent_v2].enabled = false` with the v2 tuning table. This
follows the OMO Claude Code runtime pattern: v1 is not directly forced; v2 is
force-disabled so Claude Code falls back to the v1 multi-agent path when native
subagents are available. Use
`python3 .claude/scripts/oag_claude_config_doctor.py --include-omo-plugin-features --apply` to
patch a team member's user config, then restart Claude Code or open a fresh trusted
project session. Do not treat missing tool-namespace visibility in one agent
surface as proof that native subagents are unavailable; Claude Code CLI/App may
surface the native collaboration path as an internal `spawn_agent` event. Before
reporting a native-subagent blocker, first attempt a minimal explicit native
spawn in the current surface and wait for the child result. Do not decide
availability from the visible callable tool namespace alone; in Claude Code CLI/App
traces, explicitly request the native `spawn_agent` collaboration event even
when no `multi_agent_v1` tool namespace is visible. If the actual spawn attempt
fails or the active runtime reports spawning is unavailable, report the observed
native-spawn blocker and ask the user to restart/open a fresh trusted `ip_dev`
session. Do not replace the child agent with Python, shell scripts, or manual
role-play unless the user explicitly waives the native-subagent requirement.

Use the exact `oag` keyword for OAG mode in team workflows. Hooks should not
inject OAG mode merely because a prompt mentions generic RTL, testing,
subagent, auto-research, or signoff terms unless an IP directory is explicit.

Claude Code subagents are native Claude Code collaboration workers, not Python-triggered
workers. Ask Claude Code to spawn named custom agents from `.claude/agents/*.md`
using the native subagent facility (`multi_agent_v1.spawn_agent` where exposed,
or the equivalent Claude Code CLI/App `spawn_agent` collaboration event), give each
one a bounded self-contained `TASK/DELIVERABLE/SCOPE/VERIFY` message, wait for
summaries, and then let the main agent validate and record ROCEV evidence.
`agent_type` is a routing hint, so role requirements must also be pasted into
the message. Prompt patterns live in
`.claude/oag/subagent-workflows.md`. Evidence-producing OAG subagents are checked
by the `SubagentStop` hook when they write implementation, validation, coverage,
or gate-review evidence, and must end with `OAG_EVIDENCE_RECORDED:
<relative-path>`. Subagents may never claim final completion from a receipt;
final closure requires OAG check/decide and the gate reviewer role.
The `SubagentStart` hook injects the OAG child-work contract and records a
start event; it must not spawn subagents or replace native Claude Code orchestration.
Before spawning a write-capable child, create a dispatch record with
`python3 .claude/scripts/oag_dispatch.py create`. Put the resulting
`dispatch_id`, `dispatch_path`, allowed write paths, allowed tool side effects,
and receipt path in the spawn prompt. The child receipt must include those
dispatch fields plus `changed_paths` and `generated_side_effects`. The
`SubagentStop` hook calls `python3 .claude/scripts/oag_dispatch.py verify` and
blocks receipts that fail schema validation, dispatch matching, or path scope
checks. Use `python3 .claude/scripts/oag_validate_json.py` for direct schema
validation when debugging records.
After user lock, main agent orchestrates; subagents implement and verify. The
main agent must not directly create or substantially edit RTL, TB, sim, lint,
coverage, formal, SDC, signoff, or implementation filelist artifacts. The Stop
hook runs `python3 .claude/scripts/oag_main_write_gate.py` and blocks locked
implementation or verification writes that do not have a covering native OAG
subagent receipt or a human `main_agent_subagent_waiver` decision receipt.
For release-grade closure packages, `.claude/scripts/oag_closure_check.py` must
pass with `oag.check`, `oag.inspect`, an `oag_validation_report.v1` from
`oag-evidence-validator`, and an `oag_gate_decision.v1` PASS from
`oag-gate-reviewer`. Gate decisions must include `checked_artifact_hashes` for
current closure artifacts; evidence added or changed after gate PASS makes the
gate decision stale and requires re-validation and re-gate.
For post-lock implementation or closure, run
`python3 .claude/scripts/oag_req_quality_check.py --ip-dir <ip> --json`,
`python3 .claude/scripts/oag_requirement_atom_check.py --ip-dir <ip> --json` and
`python3 .claude/scripts/oag_lock_readiness_check.py --ip-dir <ip> --json`, and
`python3 .claude/scripts/oag_verification_plan_check.py --ip-dir <ip> --json`, then
resolve failures before relying on obligations or contracts. This prevents
requirements without source claims or clear ambiguity status, prose-only
obligations such as "APB works", closure-grade contracts without explicit
assume/guarantee sections, and implementation from unresolved lock-required
product decisions.

Before releasing this pack to a team, run:

```bash
python3 .claude/scripts/oag_claude_config_doctor.py --include-omo-plugin-features
python3 .claude/scripts/oag_pack_release_check.py
python3 .claude/scripts/smoke_test.py
python3 .claude/scripts/oag_eval.py --json
```

Use the OAG run loop when a task should continue across edits, tests, stops, or
agent surfaces. `oag.run.start` writes `ontology/runs/<run_id>/run_state.json`,
`oag.run.next` returns exactly one next action, `oag.run.record` records
ROCEV-backed evidence, `oag.run.checkpoint` performs verified completion, and
`oag.stop_check` can re-inject the next action while the run is incomplete.
Use `oag.metrics` after meaningful improvement boundaries to persist numeric
progress snapshots under `ontology/metrics/`. The counts are derived from each
IP's own ontology and evidence graph; do not treat progress as a fixed list of
slots shared by every IP.
Use `oag.handoff` when progress needs to be explained or continued by another
agent/user. It writes `handoff/readiness_handoff.json` and history entries that
derive `development_ready`, `signoff_ready`, blockers, and ranked next actions
from current OAG metrics plus auto-research reports; development closure must
not be presented as signoff readiness.
Use `python3 .claude/scripts/oag_exec_auto_research.py` when auto research should
run through a resumable `claude exec` or `claude exec resume` session. Prefer an
exact `--session-id` over `--last`, keep JSONL traces and manifests under
`.claude/runs/auto_research/`, and require observed native `spawn_agent`
collaboration before counting the run as native subagent-backed.
The Claude Code Stop hook in `hooks/claude_stop_gate.py` adapts this to the Claude Code hook
contract: incomplete active runs print `{"decision":"block","reason":"..."}` and
complete/no-run cases stay silent.
The Claude Code context hook in `hooks/claude_context_inject.py` adapts
`oag.context` to `UserPromptSubmit`: identical context is deduped by content
hash under `.claude/.cache/`. The PostCompact hook stays silent for Claude Code's
stateless output contract and records a recovery marker that the next
UserPromptSubmit consumes to force one context re-injection.
Run `python3 .claude/scripts/oag_eval.py` for scenario-level evaluation of the
run-loop, context injection dedup/recovery, draft pressure, reviewer
independence, fault-model coverage, verification role decomposition, and hook
behavior. Local aliases are available as `make eval`, `make smoke`, and
`make test`.

Do not fix the testbench implementation style. Verilog, SystemVerilog, UVM,
Python, cocotb, or simulator adapters are valid when they produce
`scoreboard_rows.v1` evidence with DUT-facing `observed_source`.

Use `oag.compile` after ontology edits. The compiled
`ontology/generated/design_truth_graph.json` is derived; do not hand-edit it.
Use `closure_profile` for strictness (`draft`, `development`, `signoff`), and
record execution style as actor/execution metadata rather than separate ontology
modes.

Use `oag.draft` during deep requirement interviews. Save draft facts,
decisions, assumptions, and open questions after meaningful user answers and
before context pressure/compaction risk. Drafts are durable interview memory, not
locked truth.

Short IP requests are not implementation authorization. If the user only says
something like "I need <protocol> rx ip" or "make <ip>", create at most a draft
scaffold/workspace and record `oag.draft` interview knowledge. Do not enrich
`req/locked_truth.md`, canonical requirement/obligation/contract ontology,
structure/decomposition, RTL, TB, tests, filelists, or signoff evidence until
the user confirms scope or provides a concrete spec. For protocol IPs, first
surface open questions for spec version, transport boundary, interfaces,
single-packet versus multi-packet scope, buffering/backpressure,
filtering/addressing, and error/drop/status policy.
Before promoting a short request into locked requirements, derive
`req/source_claims.yaml` and `req/ambiguity_register.yaml` from
`.claude/oag/deep-semantic-intake-policy.md` and
`.claude/oag/requirements-quality-policy.md`, then derive
`ontology/requirement_atoms.yaml` from
`.claude/oag/requirement-decomposition-principles.md`. If trigger, condition,
response, boundary, phenomena, assumptions, timing, exception, or observable
proof shape is unknown, keep the atom in draft or blocked state and ask the
user instead of inventing architecture.
Also create or update `ontology/decision_matrix.yaml` from
`.claude/oag/decision-matrix-policy.md`. For protocol IPs, leave transport,
feature scope, queueing, storage, firmware readout, interrupt/status, and
error/drop policy as unresolved lock blockers until the user or a concrete spec
decides them. A recommendation is not a decision.

Use `ontology/scope_lock.json` as the implementation permission switch.
`state=draft` allows only questions, summaries, options, and `oag.draft`
records. `state=locked` means the user explicitly approved scope and
implementation may proceed. No lock, no RTL. No lock, no TB. No lock, no
closure. When the user says `lock`, `lock this`, `lock scope`, or
`lock requirements`, call `oag.lock` with `actor.kind=human`. If a new
requirement draft is recorded after lock, OAG returns the IP to draft and a
fresh lock is required.
After lock, `oag_lock_readiness_check.py` must pass before implementation
dispatch. Lock readiness is not closure; it only says requirements are specific
enough for bounded RTL/TB/verification subagents to start.
It includes requirement quality, ambiguity, decision matrix, requirement atom,
shallow-obligation, and assume/guarantee checks.

Keep protected-field policy and ledger artifacts active. `ontology/protection.yaml`
declares locked truth and policy fields that require human-approved decisions
for semantic edits. `knowledge/ledger.jsonl` is append-only and hash chained;
never hand-edit it.

Keep reusable RTL semantic checks in `ontology/design_rules.yaml`. OAG expects
common rules for same-cycle priority, event/state commit consistency,
scoreboard evidence schema, contract-to-proof coverage, module file boundary,
and RTL language subset. It also supports signoff-grade fault-model coverage for
load-bearing coverage claims. The default subset allows `logic` and Verilog
`generate`, while procedural `for`/`while` loops outside generate blocks are
forbidden. Active instances must link to ROCEV objects and proof evidence as
they mature.
When a coverage point is load-bearing evidence, connect `coverage_refs` to
requirement-relevant `fault_models` and killed `mutation_results`; use
`mutation_not_required` only with a rationale.
For signoff-grade TB structure, use `verification_role_decomposition` to model
UVM-style roles independent of framework choice: sequence, driver, monitor,
reference_model, scoreboard, coverage, env, and test.
For signoff-grade domain closure, use SSOT-aligned rule instances:
`cdc_crossing_coverage`, `protocol_compliance`, `timing_closure`,
`functional_coverage_closure`, and `reset_xprop_coverage`. These mirror the
portable SSOT concepts for clock/reset domains, CDC/RDC requirements, interface
protocols, timing/STA expectations, coverage goals, and reset/X-prop robustness.
Closed instances must carry ROCEV links and real evidence files;
coverage-related instances must cite coverage refs observed in scoreboard or
coverage JSON. Timing instances must declare target frequency or target clocks,
and their SDC should be derived from target clocks plus CDC async clock
groups/exceptions; default input/output delay is 50% of clock period unless
explicitly overridden. DFT and power are intentionally not seeded as OAG v1
gates.

Keep structure and implementation shape in ontology, not in prose. The authored
source files are `ontology/structure.yaml` and `ontology/decomposition.yaml`;
`oag.compile` generates `ontology/generated/design_spec.json` and
`ontology/generated/authoring_packets/*.json` as read-only projections for
workers. `oag.compile` also generates
`ontology/generated/design_facts_graph.json` from current RTL using `pyslang`
when available, with a conservative parser fallback. Treat it as extracted
implementation fact/provenance, not authored truth: mismatches tell you to fix
RTL or `ontology/decomposition.yaml`, never to hand-edit generated facts. Use
the decomposition `profile.mode` to preserve flexibility:
`small_leaf_single_file`, `greenfield_modular`, `legacy_preserve`, or
`wrapper_adapter`. Do not force legacy IPs into new hierarchy, and do not let
greenfield nontrivial IPs hide all behavior in one unowned top module. For
`greenfield_modular`, each current-IP module should map to a unique RTL file by
default; shared files require explicit `shared_file_rationale`.

For routed failures, write `failure_ticket.v1` through `oag.ticket`. For
signoff-grade evidence, write fresh `stage_run_receipt.v1` files under
`ontology/evidence/stage_runs/`.

Before closure, `oag.check` must report explicit validation status for closed
records, a closed obligation-to-contract-to-validation matrix, fresh evidence
file hashes, clean protected fields, a valid append-only ledger, and monotonic
closure. Do not weaken a closed/passed object back to draft/open/stale without
an approved decision; use a `refuted` record for newly discovered defects.
Completion decisions must be written as `oag_decision_receipt.v1` files under
`ontology/validations/`; completion actions are blocked unless
`record_decision` is true.
For signoff/promote, a reviewer receipt must be passing and independent; an
`allowed` receipt with `independent: false` is not sufficient.
Use git as the durable version baseline for OAG-managed implementation and
evidence over time: records, stage receipts, and facts graph provenance should
carry commit IDs or file hashes for RTL, TB, filelists, SDC, docs, generated
facts, and signoff artifacts.
Use `.claude/scripts/oag_portable_db.py` to move durable OAG DB state between agent
surfaces or workspaces. The portable DB archive is platform-neutral: it carries
IP `req/`, `ontology/`, `knowledge/`, compact evidence artifacts, optional
source directories, optional common rules/adapters, a manifest, file SHA-256
fingerprints, and git provenance. Treat import/export as a bridge between
Claude Code, Cursor, CI, and future OAG UIs; do not copy chat transcripts as the
source of continuity.
Use `.claude/scripts/oag_okf.py` for Open Knowledge Format views. OKF exports are
generated markdown/frontmatter concepts for sharing, review, search, and other
agents. They are not locked truth and do not replace OAG checks. OKF imports
must enter as draft knowledge first, then be promoted through human-approved OAG
gates if they should affect requirements or signoff. OKF import must preserve
existing authored OAG concepts and Locked Truth: it may append draft knowledge,
but it must not rewrite canonical requirement or ontology source files.
Use `python3 .claude/scripts/oag_okf.py export --profile obsidian` or `make okf-export-obsidian`
for Obsidian vault output. The Obsidian profile is still a generated view; it
adds wiki links, aliases, graph-friendly frontmatter, and an `OAG Knowledge.base`
file without changing canonical OAG concepts.

To create a new IP, scaffold the ontology-first structure before RTL/TB work:

```bash
python3 .claude/scripts/oag_scaffold_ip.py create <ip> --owner <owner>
```

For a short new-IP request, this scaffold is only a draft workspace. Do not
promote scaffold seed files into product truth without explicit user
confirmation and OAG decision evidence.

To visualize an IP as a filterable ontology graph:

```bash
python3 .claude/scripts/oag_graph.py build \
  --ip-dir <ip> \
  --stage <stage> \
  --intent "<task>" \
  --html-out <ip>/ontology/generated/oag_graph.html
```
