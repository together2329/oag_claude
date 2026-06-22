---
name: oag-ip-workflow
description: Use when working on hardware IP requirements, RTL, testbench, simulation, coverage, signoff, common design-rule review, or evidence review through the Ontology Agent Gateway. Calls OAG before acting, records ROCEV-backed findings with explicit validation status, checks closure matrix and completion decisions, keeps scoreboard evidence TB/simulator agnostic through scoreboard_rows.v1, protects locked truth fields, preserves append-only evidence ledger events, enforces monotonic closure and evidence freshness hashes, writes decision receipts, and applies common design rules such as same-cycle priority, event/state commit consistency, contract-to-proof coverage, fault-model coverage, verification methodology, verification role decomposition, CDC/RDC domain safety, PPA-aware RTL, and RTL language subset.
---

# OAG IP Workflow

Use this skill for hardware IP work where requirement, obligation, contract,
evidence, and validation must stay explicit.

## Skill Router

Treat this skill as the umbrella workflow. Use the narrower OAG skills when a
task enters one of these lanes:

- `oag-deep-semantic-intake`: compressed natural-language intent, source
  claims, hidden implications, ambiguity rows, and first decision candidates.
- `oag-decision-matrix`: lock-blocking product/design choices, profile-seeded
  decisions, recommended/default separation, and unresolved decision audits.
- `oag-contract-projection`: requirement atoms, obligations, assume/guarantee
  contracts, behavior/cycle refs, and proof projection.
- `oag-authoring-packet`: post-lock `oag.compile`, role-specific `rtl__*.json`
  and `tb__*.json` packet checks, and native subagent packet handoff.
- `oag-wavefront`: dependency-aware parallel work planning, ownership locks,
  barrier tokens, read-only triage, disjoint write shards, and single
  integration owners.
- `oag-evidence-closure`: scoreboard, coverage, validation, trace graph,
  freshness, gate, and `claim_complete` readiness.

Do not let this umbrella skill hide ownership. Intake and decisions are draft
workflow. Contract projection prepares implementation truth. Authoring packets
feed RTL/TB subagents. Wavefront scheduling opens only safe parallel work
boundaries. Evidence closure audits proof strength and decision freshness.

## Start

### New IP Intake Guard

If the user gives only a short IP request, such as "I need mctp rx ip",
"make uart", or "create dma ip", do not treat that as permission to decide the
architecture. Enter requirement interview mode.

Allowed first actions for a short IP request:

- read this skill and repo-local OAG guidance;
- check whether the requested IP already exists and keep it separate from other
  IP workspaces;
- create at most a draft scaffold/workspace when needed to store interview
  notes;
- run `oag.inspect`, `oag.compile`, and `oag.context` only to understand the
  draft workspace state;
- attempt bounded spec/source discovery;
- write `oag.draft` records with facts, assumptions, open questions, and
  proposed scope.
- capture load-bearing source intent in `req/source_claims.yaml` and unresolved
  questions in `req/ambiguity_register.yaml`; use `req/deep_semantic_intake/`
  for detailed interview notes and layer worksheets.
- derive candidate `ontology/requirement_atoms.yaml` entries for nontrivial
  requirements, keeping unknown trigger, condition, response, boundary,
  phenomena, assumption, timing, and proof-shape fields as draft ambiguity
  instead of architecture decisions.
- create or update `ontology/decision_matrix.yaml` rows for lock-blocking
  product choices, keeping unknown transport, feature scope, buffering,
  filtering, output, storage, interrupt/status, and error/drop policy as
  unresolved or blocked instead of architecture decisions.
- use `oag_deep_semantic_intake.py` for compressed natural-language intent and
  `oag_decision_matrix_generate.py` for profile-seeded decision rows when a
  protocol profile such as `mctp-rx` applies.

Forbidden until the user confirms scope or supplies a concrete spec:

- do not enrich or rewrite `req/locked_truth.md`;
- do not edit canonical requirement, obligation, contract, structure,
  decomposition, policy, waiver, or signoff ontology files beyond scaffold seed
  placeholders;
- do not create or modify RTL, TB, tests, filelists, or signoff evidence;
- do not spawn RTL/TB/sim implementation agents;
- do not choose protocol architecture defaults such as transport binding,
  single-packet versus multi-packet support, buffering depth, filtering policy,
  output interface, or error/drop behavior as locked truth.

For protocol IPs, ask or draft open questions for at least: spec version,
transport boundary, input/output interfaces, supported feature scope, buffering
and backpressure, filtering/addressing, and error/drop/status policy. Store
unconfirmed answers only as draft knowledge.

## Scope Lock

Each IP has one implementation permission switch:
`ontology/scope_lock.json`.

- `draft`: questions, summaries, draft requirements, and options only.
- `locked`: user has confirmed the scope; canonical ontology enrichment, RTL,
  TB, validation, gate review, and closure may proceed.

No lock, no RTL. No lock, no TB. No lock, no closure.

Check status before implementation or closure:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.lock_status","arguments":{"ip_dir":"<ip>"}}'
```

When the user explicitly says `lock`, `lock this`, `lock scope`, or `lock
requirements`, record the approval:

```bash
python3 .claude/scripts/oag_cli.py call --json '{
  "tool": "oag.lock",
  "arguments": {
    "ip_dir": "<ip>",
    "summary": "Human-confirmed scope summary.",
    "confirmed_scope": ["confirmed requirement or boundary"],
    "actor": {"kind": "human", "id": "user", "surface": "claude"}
  }
}'
```

If the user changes requirements after lock, save the new answer with
`oag.draft`; that returns the IP to draft state. Ask for a fresh lock before
continuing implementation. Use `oag.unlock` only when the user explicitly
withdraws approval.

After lock and before implementation or closure, run the OAG V2 semantic gate:

```bash
python3 .claude/scripts/oag_req_quality_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_requirement_atom_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_contract_strength_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_trace_graph_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_lock_readiness_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_verification_plan_check.py --ip-dir <ip> --json
```

Resolve failures before relying on obligations or contracts. These checks block
locked scopes that still have unresolved source ambiguity, weak requirement
shape, unresolved requirement-atom ambiguity, prose-only obligations, or
closure-grade contracts without explicit assume/guarantee. For locked TB work,
`ontology/verification_plan.yaml` must define the proof objectives before the
TB implementation agent satisfies them.
The lock-readiness check also blocks lock-required decision rows that are still
unresolved, proposed, or blocked. Passing it is implementation readiness, not
IP closure.

Before dispatching RTL or TB agents after lock, run:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.compile","arguments":{"ip_dir":"<ip>"}}'
python3 .claude/scripts/oag_authoring_packet_check.py --ip-dir <ip> --require-packets --json
```

The generated `ontology/generated/authoring_packets/rtl__*.json` and
`tb__*.json` files are the role-specific implementation and proof inputs.
RTL/TB agents should not reinterpret original prose once these packets exist.

When multiple RTL/TB/sim tasks should run in parallel, use wavefront scheduling
instead of unconstrained fan-out:

```bash
python3 .claude/scripts/oag_wavefront.py plan --ip-dir <ip> --run-id <run> --template .claude/oag/wavefront-templates/tb_common_then_scenario_fanout.yaml --json
python3 .claude/scripts/oag_wavefront.py ready --ip-dir <ip> --run-id <run> --json
python3 .claude/scripts/oag_wavefront.py claim --ip-dir <ip> --run-id <run> --task-id <task> --json
```

Read-only triage can fan out aggressively. Write tasks require disjoint
`allowed_write_paths`. Shared artifacts such as filelists, run scripts,
aggregate results, coverage JSON, and closure packages require a single
integration owner. Simulation failures should be classified by read-only
triage before repair agents are opened.

After user lock, main agent orchestrates; subagents implement and verify. The
main agent must not directly create or substantially edit RTL, TB, sim, lint,
coverage, formal, SDC, signoff, or implementation filelist artifacts. Those
writes require native OAG subagent dispatch + receipt. If native subagents are
unavailable, stop with BLOCKED unless the user records a human
`main_agent_subagent_waiver` decision receipt.

For a new IP, scaffold the ontology-first folder layout before creating RTL,
TB, or evidence artifacts:

```bash
python3 .claude/scripts/oag_scaffold_ip.py create <ip> --owner <owner>
```

The scaffold creates `req`, `ontology`, `knowledge`, `rtl`, `tb`, `sim`,
`lint`, `cov`, `formal`, `syn`, `sdc`, `list`, `doc`, and `signoff` with seed
Requirement -> Obligation -> Contract -> Evidence -> Validation files.
It also creates stage contracts, closure policy, protected-field policy, gate
registry, stage receipt schema, decision receipt schema, failure-ticket schema,
an append-only `knowledge/ledger.jsonl`, and a common
`ontology/design_rules.yaml` rulebook. It also creates
`ontology/structure.yaml` for the shared signal/register/interface namespace and
`ontology/decomposition.yaml` for module ownership and structure profile. It
also creates `ontology/modeling.yaml` for micro behavior/cycle oracle truth and
`ontology/domain_intent.yaml` for clock/reset-domain intent. It also creates
`ontology/tb_methodology.yaml` for framework-neutral verification methodology
intent, `req/source_claims.yaml` and `req/ambiguity_register.yaml` for deep
semantic intake, `ontology/requirement_atoms.yaml` for semantic decomposition
before obligations, and `ontology/decision_matrix.yaml` for decisions that must
be resolved before lock-ready implementation. `oag.compile` also generates
role-specific authoring packets under `ontology/generated/authoring_packets/`.
For short IP intake, these scaffold files are placeholders for draft capture;
do not enrich locked truth or canonical ontology from assumptions.

Do not require a specific testbench implementation. Verilog, SystemVerilog,
UVM, Python, cocotb, or a simulator adapter are all valid if they emit the
standard evidence rows in `sim/scoreboard_events.jsonl`.
Do require verification methodology responsibilities when TB evidence is used
for closure: scenario intent, driver/BFM, monitor, independent predictor,
scoreboard, coverage collector when load-bearing, assertion/formal hooks when
useful, and OAG evidence writer. Random or constrained-random tests require
constraints and coverage goals before they can support closure. Failed tests do
not count toward closure coverage.

Before editing or claiming analysis, call OAG for the active IP:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.inspect","arguments":{"ip_dir":"<ip>","stage":"<stage>","intent":"<task>"}}'
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.compile","arguments":{"ip_dir":"<ip>"}}'
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.context","arguments":{"ip_dir":"<ip>","stage":"<stage>","intent":"<task>"}}'
```

Use `oag.inspect` for legacy IP folders with no knowledge ledger. Use
`oag.compile` after ontology edits. Use `oag.context` for prompt-ready ontology
records. When Claude Code hooks are enabled, `claude_context_inject.py` can inject this
context automatically on relevant UserPromptSubmit events.

For work that should keep moving across edit/test/stop boundaries, start a
durable run loop:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.run.start","arguments":{"ip_dir":"<ip>","stage":"<stage>","intent":"<task>","actor":{"kind":"ai","id":"claude","surface":"cli"}}}'
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.run.next","arguments":{"ip_dir":"<ip>"}}'
```

`oag.run.start` derives the active obligation from the closure matrix and writes
`ontology/runs/<run_id>/run_state.json`, `next_action.json`, and
`checkpoint_history.jsonl`. `oag.run.next` always returns one action to take
next. The run loop is a driver; it does not replace ROCEV records or decision
receipts.

After `oag.compile`, treat `ontology/generated/design_spec.json`,
`ontology/generated/authoring_packets/*.json`,
`ontology/generated/design_facts_graph.json`, and
`ontology/generated/domain_crossing_matrix.json` as read-only work inputs. The
design spec and authoring packets are compiled projections from authored
ontology. The design facts graph is extracted from current RTL with `pyslang`
when available, falling back to a conservative parser when needed. If a
projection is wrong, edit `ontology/requirements.yaml`,
`ontology/obligations.yaml`, `ontology/contracts.yaml`,
`ontology/structure.yaml`, `ontology/decomposition.yaml`, or
`ontology/policies.yaml`, then compile again. If extracted facts disagree with
decomposition, fix the RTL module names/files or the authored decomposition,
not the generated facts file.

For deep requirement interviews, do not wait for the user to say "save this" to
preserve draft knowledge. After each meaningful user answer or before a long
context transition, call `oag.draft` with the current facts, decisions,
assumptions, and open questions. Drafts are not locked truth; they are captured
under `req/interview_draft.md`, `ontology/drafts/`, and `knowledge/records/`.

## Subagents

Claude Code-facing OAG roles are individual `.claude/agents/oag-*.md` custom agent
files. OAG metadata for those roles lives in `.claude/oag/agent-catalog.toml`.
The stable set is 14 core duties plus 3 custom dynamic duties:

- `oag-custom-researcher`: bounded research shard.
- `oag-custom-worker`: bounded implementation or repair shard.
- `oag-custom-reviewer`: bounded review shard.

Before using these roles, validate the catalog:

```bash
python3 .claude/scripts/oag_agent_catalog_check.py
```

Team prompts should use the exact `oag` keyword when they want OAG context and
subagent workflow guidance. Terms such as `auto research`, `subagent`, and
`signoff` describe work, but do not activate OAG mode by themselves. The
project config requests native subagents with
`[features].multi_agent = true` and `[features].child_agents_md = true`, while
forcing `[features.multi_agent_v2].enabled = false`. This matches the OMO Claude Code
runtime pattern: v1 is not directly enabled; v2 is re-disabled so Claude Code can
resolve to the v1 multi-agent path when native subagents are available. Team
members can run
`python3 .claude/scripts/oag_claude_config_doctor.py --include-omo-plugin-features --apply`
to patch their user Claude Code config, or let the SessionStart hook apply the same
guard at startup. Restart Claude Code or open a fresh trusted project session after a
config patch. Do not narrate speculative tool-namespace probes such as
"checking whether multi_agent_v1 is available." Missing `multi_agent_v1`
visibility in one agent surface is not proof that native subagents are
unavailable; Claude Code CLI/App can surface the same operation as an internal
`spawn_agent` collaboration event. Before reporting a native-subagent blocker,
first attempt a minimal explicit native spawn in the current surface and wait
for the child result. Do not decide availability from the visible callable tool
namespace alone; in Claude Code CLI/App traces, explicitly request the native
`spawn_agent` collaboration event even when no `multi_agent_v1` tool namespace
is visible. If the actual spawn attempt fails or the active runtime reports
spawning is unavailable, report the observed native-spawn blocker and ask the
user to restart/open a fresh trusted `ip_dev` session. Do not continue by
manually applying the child role unless the user explicitly waives the native
subagent requirement.

Subagents are native Claude Code collaboration workers, not Python runners. Use
self-contained spawn assignments like this when the v1 tool is directly
exposed:

```text
multi_agent_v1.spawn_agent({
  "message": "TASK: act as the OAG legacy/reference IP analyzer. DELIVERABLE: source paths, extracted behavior, inferred requirements, gaps, leakage risks, and evidence needs. SCOPE: <reference paths>. VERIFY: cite exact files/lines or return INCONCLUSIVE. This is an executable assignment, not a context handoff.",
  "agent_type": "oag-legacy-ip-analyzer",
  "fork_context": false
})
```

In Claude Code CLI/App traces, the same native operation can appear as a `spawn_agent`
collaboration event, followed by a `wait` event and a child thread id. Treat
that as native. Treat Python/shell worker processes or manual role-play as
non-native and do not use them for "use subagent" requests.

For implementation splits:

```text
multi_agent_v1.spawn_agent({
  "message": "TASK: act as the OAG PPA-aware RTL implementation agent. DELIVERABLE: the smallest RTL change that implements assigned contracts plus rtl_dialect, changed paths, implemented_contracts, behavior_refs_implemented, cycle_rule_refs_implemented, ppa_notes, checks_run, blockers, and ROCEV links. SCOPE: rtl/<module>.sv only. DISPATCH: include dispatch_id, dispatch_path, allowed write paths, allowed tool side effects, and receipt path from oag_dispatch.py create. VERIFY: compile, run oag_ppa_check.py when applicable, run optional oag_pyslang_lint.py syntax lint when available, or return the exact blocker. Use OAG SV-lite: Verilog-2001 plus logic and static generate by default. Write a non-empty receipt with may_claim_complete=false and end with OAG_EVIDENCE_RECORDED: <relative-path>. Do not claim final completion.",
  "agent_type": "oag-rtl-implementation-agent",
  "fork_context": false
})
```

Use native waiting/mailbox behavior for child results; timeout means no new
update, not failure. Use native child steering for targeted follow-up and close
child threads after integrating a completed or inconclusive lane.
Treat `agent_type` as a routing hint and paste role requirements into the child
message. See `.claude/oag/subagent-workflows.md` for more prompt shapes. Custom
subagents are execution actors only. They must stay inside the prompted shard,
preserve ROCEV traceability, and produce evidence paths. They cannot claim final
completion, approve protected ontology edits, or replace `oag.check`,
`oag.decide`, evidence validation, or gate review.

Requirement detail work before lock stays main-owned, but use read-heavy
subagents when they help: spec extraction, reference RTL comparison, ambiguity
lists, or candidate obligation/contract review. Their output is draft evidence
until the user locks scope.

When assigning a write-capable subagent, create a dispatch record before native
spawn:

```bash
python3 .claude/scripts/oag_dispatch.py create \
  --ip-dir <ip> \
  --agent-type <oag-write-agent> \
  --stage <stage> \
  --allowed-write-path <ip>/<owned-path> \
  --allowed-write-path <ip>/knowledge/subagents/ \
  --allowed-tool-side-effect <ip>/ontology/generated/ \
  --receipt-path <ip>/knowledge/subagents/<receipt>.json \
  --json
```

State the resulting `dispatch_id`, `dispatch_path`, allowed write paths, allowed
tool side effects, and receipt path in the child message. `oag.compile` is
allowed only when assigned; it may refresh `<ip>/ontology/generated/*` as
generated tool output. The child must not manually edit generated ontology
files, must not claim ownership of those outputs, and must report them
separately from owned changed paths. After child completion, verify the dispatch
and receipt before integration:

```bash
python3 .claude/scripts/oag_dispatch.py verify \
  --dispatch <ip>/knowledge/dispatches/<dispatch>.json \
  --receipt <ip>/knowledge/subagents/<receipt>.json \
  --json
```

The verifier compares the child receipt and actual
`git status --short -uall -- <ip>` delta against the dispatch baseline. Reject or explain any path outside
the child scope.

Subagent receipts should use `HANDOFF_PASS`, `STATIC_HANDOFF_PASS`, or
`RTL_HANDOFF_PASS` for a bounded worker result. Do not use `PASS`, `COMPLETE`,
`DONE`, `SIGNOFF`, `RELEASED`, or `CLOSED` to describe the IP.

When hooks are enabled, `SubagentStart` injects the child-work contract and
records that an OAG child started. It must not spawn subagents or replace native
Claude Code orchestration. `SubagentStop` verifies write-capable child receipts.
`Stop` runs `oag_main_write_gate.py` so locked implementation or verification
artifact changes without a covering native subagent receipt block parent stop.

When checking instruction files, avoid unbounded parent-directory scans such as
`find .. -name AGENTS.md`. Use repo-local bounded search such as
`rg --files -g 'AGENTS.md' -g '!**/.git/**'` or explicit expected paths.

## During Work

When a meaningful stage boundary is reached, append one record:

```bash
python3 .claude/scripts/oag_cli.py call --json '{
  "tool": "oag.record",
  "arguments": {
    "ip_dir": "<ip>",
    "stage": "sim",
    "type": "finding",
    "claim": "scoreboard reset rows closed",
    "summary": "Observed reset rows matched expected state.",
    "actor": {"kind": "ai", "id": "claude", "surface": "cli"},
    "rocev": {
      "requirement": {"id": "REQ_RESET", "source": "req/locked_truth.md"},
      "obligation": {"id": "OBL_RESET_STATE", "text": "reset state is observable and stable"},
      "contract": {"id": "CONTRACT_SIM_SCOREBOARD", "method": "scoreboard", "pass_condition": "mismatch count is zero"},
      "evidence": {"files": ["sim/results.xml", "sim/scoreboard_events.jsonl"], "tests": [], "commit": ""},
      "validation": {"status": "closed", "verdict": "pass", "rationale": "simulation and scoreboard evidence are clean"}
    }
  }
}'
```

When an OAG run is active, use `oag.run.record` to record evidence against the
current run target and refresh the next action:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.run.record","arguments":{"ip_dir":"<ip>","run_id":"<run_id>","summary":"evidence inspected and validation recorded"}}'
```

Closed records require `rocev.validation.status` to be explicit. Evidence files
are SHA-256 fingerprinted by `oag.record`; if an evidence file changes later,
`oag.check` treats the record as stale until a fresh validation is recorded.

For interview draft capture:

```bash
python3 .claude/scripts/oag_cli.py call --json '{
  "tool": "oag.draft",
  "arguments": {
    "ip_dir": "<ip>",
    "stage": "req",
    "title": "requirement interview round",
    "summary": "What was learned in this round.",
    "facts": ["confirmed fact"],
    "decisions": ["explicitly chosen default"],
    "assumptions": ["temporary assumption"],
    "open_questions": ["remaining question"]
  }
}'
```

`oag.record`, `oag.draft`, and `oag.ticket` append hash-chained events to
`knowledge/ledger.jsonl`. Do not hand-edit this ledger. If `oag.check` reports
ledger tampering, protected field changes, or a monotonic closure violation,
stop and report the blocker.

When a stage produces evidence that may be used for signoff, write a
`stage_run_receipt.v1` JSON file under `ontology/evidence/stage_runs/` with
input/output SHA-256 fingerprints.

When designing RTL structure, choose the decomposition profile instead of
hard-coding "all one file" or "always split":

- `small_leaf_single_file`: tiny leaf IPs may keep one editable module with a
  rationale.
- `greenfield_modular`: new nontrivial IPs should split behavior into modules
  with explicit obligation/contract ownership and interface boundaries. Each
  current-IP module should map to a unique RTL file by default; shared files
  require explicit `shared_file_rationale`.
- `legacy_preserve`: imported legacy IPs keep existing hierarchy while OAG maps
  requirements and evidence onto that hierarchy.
- `wrapper_adapter`: a legacy/child core remains protected while wrapper or
  adapter modules own new integration obligations.

Every obligation and contract should have an owning module in
`ontology/decomposition.yaml`. Module authoring should begin from the generated
packet for that module when it exists.
`ontology/generated/design_facts_graph.json` is the current implementation fact
view: modules, ports, parameters, registers, memories, instances, source file
hashes, extractor backend, and git HEAD when available. Use it to review large
IP hierarchy/connectivity without treating it as locked truth.

Do not change protected truth or policy fields silently. Protected paths are
declared in `ontology/protection.yaml` and include locked requirements,
obligations, contracts, structure/decomposition policy, and closure policy.
Semantic edits require a human-approved decision record.

When work exposes a common semantic hazard, activate a design-rule instance in
`ontology/design_rules.yaml` instead of leaving it as chat prose. Use this for
same-cycle priority conflicts, event/state commit consistency, and
contract-to-proof coverage. For packet/message designs with multiple active
contexts, use `interleaved_context_coverage` when packet-level interleaving must
be proven, for example `A.SOM -> B.SOM -> A.EOM -> B.EOM`. Keep the RTL
language subset rule active as the coding-policy baseline. Active instances must
point back to the relevant requirement, obligation, contract, and evidence as
the IP matures.

When a coverage point becomes load-bearing evidence, add a
`fault_model_coverage` instance instead of relying on hit count alone. The
instance should connect `coverage_refs` to requirement-relevant `fault_models`
and killed `mutation_results` with an evidence file such as
`mutation/relevant_tc/relevant_mutation_summary.json`. If mutation is not
applicable, set `mutation_not_required: true` and include a rationale.

For signoff-grade testbench architecture, add a
`verification_role_decomposition` instance. This imports UVM concepts without
requiring UVM syntax or SystemVerilog classes: `sequence` owns stimulus intent,
`driver` owns DUT input protocol driving, `monitor` owns DUT-facing observation,
`reference_model` owns expected prediction, `scoreboard` owns compare,
`coverage` owns coverage refs, `env` owns wiring/config/run control, and `test`
owns scenario/seed selection. Closed instances must keep expected_source,
observed_source, and compare_source as separate roles.

For general TB work, use `ontology/tb_methodology.yaml` and the documents under
`.claude/oag/verification-methodology-principles.md`,
`.claude/oag/verification-strategy-policy.md`,
`.claude/oag/tb-methodology-policy.md`,
`.claude/oag/tb-architecture-patterns.md`,
`.claude/oag/coverage-closure-policy.md`, and
`.claude/oag/assertion-formal-policy.md`. Verification strategy belongs in
`ontology/verification_plan.yaml` and should be authored or reviewed by
`oag-verification-strategy-agent` after lock. The TB implementation agent should
consume that plan and choose the smallest sufficient methodology:
directed/table-driven micro-TB for simple IPs, transaction/random/coverage/
assertion-assisted TB for moderate IPs, and reusable agents/reference
models/coverage-driven closure/formal candidates for complex IPs. Framework
presence alone is not evidence.

For signoff-grade domain claims, activate the SSOT-aligned rule kind instead of
leaving the claim as review prose:

- `cdc_crossing_coverage`: clock/reset-domain crossings from
  `clock_reset_domains`, `cdc_requirements`, or `rdc_requirements`.
- `protocol_compliance`: AXI/APB/streaming/valid-ready protocol assertions,
  monitors, VIP, or protocol scoreboard evidence.
- `timing_closure`: target frequency or target clocks, SDC constraints derived
  from those clocks and CDC policy, plus STA/sta-post setup and hold evidence.
- `functional_coverage_closure`: coverage goals versus observed coverage refs
  from `coverage_functional`, `coverage_ssot`, scoreboard rows, or coverage JSON.
- `reset_xprop_coverage`: reset sequencing, async assert/sync deassert, reset
  domain behavior, and X-prop robustness.

Closed instances must link requirement, obligation, contract, and evidence
files. Coverage-bearing instances must cite `coverage_refs` that appear in
scoreboard rows or coverage JSON. For timing, use target clocks or
`target_frequency_mhz` to derive `create_clock`; use CDC/RDC facts to derive
async clock groups or CDC exceptions; default input/output delay is 50% of clock
period unless the IP overrides it. DFT and power are not OAG v1 default gates.

CDC/RDC is a domain-safety contract. Use `ontology/domain_intent.yaml` to record
clock domains, reset domains, async inputs, crossing taxonomy, reset
deassertion policy, and approved mitigation. Development checks may use
`.claude/scripts/oag_domain_crossing_check.py` plus RTL structure notes and
functional scenarios. Release-grade CDC/RDC closure requires static, formal,
tool-grade, or explicitly approved equivalent evidence. Passing simulation alone
does not close CDC/RDC.

When a failure needs routed repair, create one failure ticket:

```bash
python3 .claude/scripts/oag_cli.py call --json '{
  "tool": "oag.ticket",
  "arguments": {
    "ip_dir": "<ip>",
    "stage": "sim",
    "reason": "scoreboard mismatch",
    "failing_contract": {"id": "CONTRACT_SIM_SCOREBOARD"},
    "expected": {},
    "observed": {},
    "evidence": {"files": ["sim/scoreboard_events.jsonl"]},
    "editable_files": ["rtl/<ip>.sv"],
    "required_evidence_after_patch": ["sim/results.xml", "sim/scoreboard_events.jsonl"]
  }
}'
```

## Visualize

When the user asks to understand the ontology, dependency shape, evidence
coverage, or gaps, generate a graph viewer:

```bash
python3 .claude/scripts/oag_graph.py build \
  --ip-dir <ip> \
  --stage <stage> \
  --intent "<task>" \
  --json-out <ip>/ontology/generated/oag_graph.json \
  --html-out <ip>/ontology/generated/oag_graph.html
```

Open the generated HTML directly in a browser. It is self-contained and supports
search, type/status filters, node lists, and node detail inspection.

## Finish

Before claiming completion:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.compile","arguments":{"ip_dir":"<ip>"}}'
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.check","arguments":{"ip_dir":"<ip>"}}'
python3 .claude/scripts/oag_closure_check.py --ip-dir <ip>
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.decide","arguments":{"ip_dir":"<ip>","action":"claim_complete","stage":"<stage>","intent":"<task>","record_decision":true,"actor":{"kind":"ai","id":"claude","surface":"cli"}}}'
```

For an active run, prefer:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.run.checkpoint","arguments":{"ip_dir":"<ip>","run_id":"<run_id>","stage":"<stage>","intent":"<task>","actor":{"kind":"ai","id":"claude","surface":"cli"}}}'
```

If a stop hook is available, call `oag.stop_check`. If it returns
`should_continue: true`, continue with the returned prompt block instead of
claiming completion. If checkpoint repeats the same blocker three times, the run
status becomes `needs_human`.

If `oag.decide` returns `allowed: false`, report the blocker instead of saying
the IP is complete. If it returns `allowed: true`, the decision receipt under
`ontology/validations/` is the durable completion decision. Completion actions
are blocked unless `record_decision` is true.

`oag_closure_check.py` is the release-grade package gate: it requires a passing
`oag.check`, no `oag.inspect` artifact gaps, a passing
`oag_validation_report.v1` from `oag-evidence-validator`, a PASS
`oag_gate_decision.v1` from `oag-gate-reviewer`, checked artifact hashes for
current closure artifacts, and no custom subagent final closure claim. If RTL,
lint, simulation, scoreboard, coverage, validation, or generated evidence
changes after gate PASS, the gate decision is stale and must be re-run.

For `action=signoff`, OAG requires `ontology/policies.yaml` to use
`closure_profile: signoff`, a compiled truth graph, a closed closure matrix,
fresh evidence hashes, fresh stage receipts, clean protected fields, a valid
append-only ledger, monotonic closure, an independent `oag.review` reviewer
receipt, and a decision receipt. The policy transition itself is protected;
record a human decision when moving into signoff.
Do not model single-worker vs orchestrator as separate ontology modes; record the
actual runner in actor/execution metadata.
Over time, keep OAG-managed implementation and evidence git-backed: RTL, TB,
filelists, SDC, docs, generated facts, and signoff artifacts should be tied to
commit IDs or SHA-256 fingerprints in records and stage receipts.

If the runtime exposes context usage or compaction pressure and it is high
(about 70% or more), save an `oag.draft` before continuing an interview. Do not
rely on context compaction to preserve requirement decisions.
When Claude Code hooks are enabled, `claude_draft_pressure.py` injects this reminder but
does not invent facts; the agent must summarize confirmed facts into `oag.draft`.

## Rule

Do not collapse ROCEV into "tests passed." A compile pass, lint pass,
simulation pass, scoreboard evidence, coverage, waveform, formal proof, and
signoff close different obligations.

For scoreboard evidence, standardize the row semantics, not the TB language.
Use `scoreboard_rows.v1`: `goal_id`, `scenario_id`, `cycle`, `stimulus`,
`expected`, `observed`, `observed_source`, `passed`, `mismatch`, and
`coverage_refs`. `observed_source.kind` must name a DUT observation source such
as `dut_signal`, `monitor`, `waveform`, `transaction`, or `assertion`; it must
not be an FL/CL/model source.

For coverage evidence, standardize the closure rule, not the tool. Coverage
refs used for closure must resolve to contract-linked goals or evidence, and
coverage from failed tests or failed scoreboard rows must not contribute to
closure. Random stimulus without constraints and coverage goals is exploration,
not closure evidence.

For RTL semantics, use the common design rulebook instead of IP-specific prose.
OAG expects rules for event/state commit consistency, same-cycle priority
declaration, scoreboard evidence schema, contract-to-proof coverage,
module/file ownership boundary, the RTL language subset, and optional
signoff-grade CDC/protocol/timing/functional-coverage/reset-X-prop domain
closures. Timing closure requires target frequency/clocks before SDC/STA can be
claimed. Generated RTL is implementation, not truth: RTL agents may choose
internal structure, but must not invent behavior, timing, reset values, address
maps, priorities, or protocol semantics. PPA is architectural intent expressed
in RTL structure; it must preserve locked behavior while considering critical
paths, unnecessary switching, mux/register/memory growth, and synthesis-friendly
structure. The default RTL subset is OAG SV-lite: Verilog-2001 baseline plus
`logic` and static `generate`/`genvar`/`generate for`; `always_ff`,
`always_comb`, and procedural `for`, `while`, `repeat`, or `forever` loops
outside generate blocks are forbidden by default. Use
`.claude/scripts/oag_ppa_check.py` for lightweight generated-RTL PPA/dialect
screening when RTL files are available. Use
`.claude/scripts/oag_domain_crossing_check.py` for lightweight development
screening of domain intent and obvious unsafe crossings. OAG extracts
lightweight RTL facts through `design_facts_graph.json` and domain-crossing
intent through `domain_crossing_matrix.json`; these do not replace lint,
elaboration, static CDC/RDC, formal, protocol VIP, synthesis, or signoff tools.
It checks that declared hazards, crossings, and language policies are tied to
ROCEV objects and that
formal/assertion contracts name proof evidence.

For closure semantics, OAG expects seven platform gates:

- Protected fields: locked truth and signoff policy changes require a
  human-approved decision record.
- Append-only evidence ledger: event records are hash chained in
  `knowledge/ledger.jsonl`.
- Monotonic closure: once an object is closed or passed, an AI record cannot
  silently weaken it back to draft/open/stale; use a decision or a refuted
  record instead.
- Explicit validation: evidence never auto-closes a record; closed records must
  set `rocev.validation.status`.
- Closure matrix: every obligation must map to a contract and a closed
  validation record.
- Evidence freshness: closed records store SHA-256 hashes for evidence files.
- Independent reviewer: signoff/promote requires a passing `oag.review` receipt
  from a different actor when the profile is signoff.
- Decision receipt: completion decisions are written to `ontology/validations/`
  and hash-chained into the ledger.

For the tool schema and object vocabulary, read
`references/oag-tool-call-contract.md`.
