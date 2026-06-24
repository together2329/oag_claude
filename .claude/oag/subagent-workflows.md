# OAG Claude Code Subagent Workflows

Claude Code subagents are native Claude Code collaboration workers. Do not run a Python
script, shell wrapper, or manual role-play substitute to spawn them. The main
agent uses a prompt/directive to ask Claude Code to start native subagents, waits for
their results, integrates the result, then records durable OAG evidence through
the normal ROCEV flow.

Project-scoped custom agent definitions live in `.claude/agents/*.md`. OAG
metadata for those roles lives in `.claude/oag/agent-catalog.toml`.

Native subagent assignments should include the posture from
`.claude/oag/agent-common-preamble.md`: preserve design truth, use the smallest
sufficient proof, do not infer expected behavior from RTL, and leave weak
closure claims open with precise blockers.

For team use, ask for OAG mode explicitly with the exact `oag` keyword. Terms
like `auto research`, `subagent`, and `signoff` describe work, but do not
activate OAG mode by themselves. Project config requests native subagent
support through `[features].multi_agent = true` and
`[features].child_agents_md = true`, and forces
`[features.multi_agent_v2].enabled = false`. This mirrors the OMO Claude Code runtime
pattern: v1 is not directly enabled; v2 is re-disabled so Claude Code can resolve to
the v1 multi-agent path when native subagents are available. Use
`python3 .claude/scripts/oag_claude_config_doctor.py --include-omo-plugin-features --apply` to
patch user-level Claude Code config for team members, or rely on the SessionStart hook
to do the same at startup. The active Claude Code runtime still has to expose the
native subagent facility after restart or a fresh trusted project session. Do
not narrate speculative tool-namespace probes. Missing `multi_agent_v1` in one
agent surface is not proof that native subagents are unavailable; Claude Code CLI/App
may surface the same operation as an internal `spawn_agent` collaboration event.
Before reporting a native-subagent blocker, first attempt a minimal explicit
native spawn in the current surface and wait for the child result. Do not decide
availability from the visible callable tool namespace alone; in Claude Code CLI/App
traces, explicitly request the native `spawn_agent` collaboration event even
when no `multi_agent_v1` tool namespace is visible. If the actual spawn attempt
fails or the active runtime reports spawning is unavailable, report the observed
native-spawn blocker and ask the user to restart/open a fresh trusted `ip_dev`
session. Do not continue by pretending a child agent ran, and do not manually
apply a child role as a substitute unless the user explicitly waives the native
subagent requirement.

## Native Trigger

The native spawn may appear as a Claude Code native tool call when the current surface
exposes it:

```text
multi_agent_v1.spawn_agent({
  "message": "TASK: act as <role>. DELIVERABLE: ... SCOPE: ... VERIFY: ...",
  "agent_type": "<oag-agent-name>",
  "fork_context": false
})
```

In Claude Code CLI/App traces the same native path can appear as a collaboration event
such as `spawn_agent`, followed by a `wait` event and a child thread id. Both
are native Claude Code subagents. A Python process that role-plays the instructions is
not.

## Exec-Resume Auto Research

For unattended or pane-independent auto research, use the wrapper:

```bash
python3 .claude/scripts/oag_exec_auto_research.py \
  --ip-dir <ip> \
  --session-id <exact-claude-session-id> \
  --objective "<bounded research objective>" \
  --yolo \
  --bypass-hook-trust
```

The wrapper invokes `claude exec` or `claude exec resume`, captures JSONL events,
and writes a manifest under `.claude/runs/auto_research/`. Prefer an exact
session id over `--last`; `--last` can select the wrong pane or older thread.
Do not count an auto-research run as native subagent-backed unless the manifest
observes a `spawn_agent` collaboration event. The wrapper is orchestration
evidence; it does not replace OAG records, dispatch receipts, validator reports,
or gate review. Read-only wrapper runs should use a built-in explorer-style
subagent. Use OAG custom/write-capable roles only after creating an OAG dispatch
record and passing the dispatch id, path, allowed writes, side effects, and
receipt path into the child assignment.

Use `agent_type` as a routing hint, not as proof that a Markdown role, model,
reasoning effort, or service tier was selected. Always paste the role
requirements into `message` so the child has a self-contained executable
assignment.

Use `fork_context: false` unless the child truly needs full parent history. Full
history can make the child continue stale parent context instead of the assigned
task.

Use native waiting/mailbox behavior for child results. A wait timeout means "no
new update arrived"; it is not proof that the child failed. For long work,
require the child to send:

```text
WORKING: <task> - <current phase>
BLOCKED: <reason>
```

Use native child steering only for targeted follow-up, and close child threads
after integrating a completed or inconclusive lane.
Do not mark a dependent step complete while an active child owns evidence for
that step.

Use subagents when the work is naturally parallel and bounded:

- Read-heavy extraction: multiple specs, reference RTL trees, logs, waveform
  slices, or VIP patterns.
- Independent implementation shards: different files or modules with no shared
  edit surface.
- Independent review shards: evidence freshness, coverage gaps, protocol
  checks, or gate review.

Avoid subagents when a single edit surface needs tight sequential reasoning.
Write-heavy subagents must be assigned non-overlapping files or modules.
For larger fan-out, use `python3 .claude/scripts/oag_wavefront.py` first. The
wavefront graph records dependency barriers, ownership locks, and the single
integration owner for shared artifacts. A task that has unmet dependencies or a
conflicting ownership lock must not be dispatched.

After user lock, main agent orchestrates; subagents implement and verify. Locked
RTL, TB, sim, lint, coverage, formal, SDC, signoff, and implementation filelist
writes require native OAG subagent dispatch + receipt. If native subagents are
unavailable, stop with BLOCKED unless the user records a human
`main_agent_subagent_waiver` decision receipt. Requirement detail work before
lock may stay with main, but read-heavy spec/reference/obligation research
should use subagents when useful and remains draft evidence until lock.

Before spawning a write-capable subagent, the main agent must create a dispatch
record and paste its fields into the child task:

For implementation, validation, coverage, mutation, evidence-validator,
gate-review, or closure subagents, the IP scope must already be locked:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.lock_status","arguments":{"ip_dir":"<ip>"}}'
```

If `ontology/scope_lock.json` is missing or `state=draft`, do not spawn the
child. Ask the user to confirm scope and run `oag.lock` first. No lock, no
RTL/TB/closure.

Before RTL or TB dispatch, compile the authored ontology and verify
role-specific packet projection:

```bash
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.compile","arguments":{"ip_dir":"<ip>"}}'
python3 .claude/scripts/oag_authoring_packet_check.py --ip-dir <ip> --require-packets --json
```

RTL agents should consume `ontology/generated/authoring_packets/rtl__*.json`.
TB agents should consume `ontology/generated/authoring_packets/tb__*.json`.
If the packets are weak or missing refs, repair authored requirements,
contracts, modeling, or verification plan and compile again. Do not hand-edit
generated packets.

```bash
python3 .claude/scripts/oag_dispatch.py create \
  --ip-dir <ip> \
  --agent-type <oag-write-agent> \
  --stage <stage> \
  --allowed-write-path <ip>/rtl/<file>.sv \
  --allowed-write-path <ip>/knowledge/subagents/ \
  --allowed-tool-side-effect <ip>/ontology/generated/ \
  --receipt-path <ip>/knowledge/subagents/<receipt>.json \
  --json
```

The dispatch is the child work permit. The spawn message must include
`dispatch_id`, `dispatch_path`, allowed write paths, allowed tool side effects,
and receipt path. After child completion, run the bounded status/path audit
through `python3 .claude/scripts/oag_dispatch.py verify --dispatch <dispatch>
--receipt <receipt> --json`. It compares the child receipt and actual
`git status --short -uall -- <ip>` delta against the dispatch baseline. Any
path outside the child scope must be identified as pre-existing, rejected, or
explicitly routed to a new task before integration.

The realistic stop boundary is receipt validity, not forced integration
success. In a parallel wave, another worker can legitimately change files under
the same IP after a dispatch baseline is captured. If `verify` fails only with
`ACTUAL_PATH_OUT_OF_SCOPE`, the child must not mutate the dispatch baseline,
widen its own allowed paths, or absorb those files into its receipt. It should
write `BLOCKED`, `INCONCLUSIVE`, or `FAIL` with blockers naming the external
delta and end with `OAG_EVIDENCE_RECORDED`. The `SubagentStop` hook may accept
that bounded blocked receipt so the parent can route or reconcile integration.
Successful handoff statuses still require a verifier pass.
Dispatch IDs include a short nonce after the timestamp so same-second fan-out
does not rely on sleeps for uniqueness.
When a dispatch belongs to a wavefront task, include `--wavefront-run-id`,
`--task-id`, and `--ownership-mode`. The child receipt should echo
`wavefront_run_id`, `task_id`, and `ownership_mode` so parent-side verification
can connect the handoff to the wavefront task graph. Barrier tokens stay in the
wavefront task graph and are recorded with `oag_wavefront.py record`.

At parent Stop, `python3 .claude/scripts/oag_main_write_gate.py` checks the
locked IP's git delta. Locked implementation/verification artifacts without a
covering native OAG subagent receipt block stop.

`oag.compile` is a special verification tool side effect. A subagent may run it
only when the assignment says so. It may refresh
`<ip>/ontology/generated/*` as generated tool output; the child must not
manually edit generated ontology files, must not claim ownership of those
outputs, and must report generated side effects separately from owned changed
paths.

## Prompt Shape

```text
Use Claude Code subagents for this OAG task.

Spawn these agents with fork_context=false:
- agent_type=oag-legacy-ip-analyzer
  message starts:
  TASK: act as the OAG legacy/reference IP analyzer.
  DELIVERABLE: source paths, extracted behavior, inferred requirements, gaps,
  leakage risks, and evidence needs.
  SCOPE: <paths>.
  VERIFY: cite exact files/lines or state INCONCLUSIVE.
- agent_type=oag-requirement-contract-agent
  message starts:
  TASK: act as the OAG requirement-contract agent.
  DELIVERABLE: Requirement -> Obligation -> Contract candidates with IDs,
  assumptions, missing facts, and expected evidence.
  SCOPE: <spec paths>.
  VERIFY: every candidate cites source material or is marked TBD.
- agent_type=oag-ip-contract-agent
  message starts:
  TASK: act as the OAG IP contract agent.
  DELIVERABLE: observable evidence contracts, owner routing, and proof artifacts.
  SCOPE: <active IP>.
  VERIFY: every contract names observable, pass condition, evidence path, and owner.

Wait for all agents. Do not claim completion from subagent summaries. The main
agent must validate outputs, update OAG records, run checks, and call OAG decide
before any closure claim.
```

## RTL/TB Split Prompt

```text
Use Claude Code subagents and wait for all results.

Spawn:
- agent_type=oag-rtl-implementation-agent for rtl/<module>.sv only.
- agent_type=oag-verification-strategy-agent for ontology/verification_plan.yaml
  and strategy evidence only.
- agent_type=oag-tb-implementation-agent for tb/<test_or_monitor> only.
- agent_type=oag-rtl-lint-static-agent as read-only reviewer for filelist,
  compile, lint, optional pyslang syntax lint via oag_pyslang_lint.py, and
  static risks after the write agents report.

The RTL implementation agent must implement assigned behavior/cycle refs, stay
within OAG SV-lite by default, avoid RTL `function`/`task` helper constructs,
identify likely critical paths, high-toggle state/datapath, and area-risk
structures before nontrivial RTL edits, run or assign
`python3 .claude/scripts/oag_ppa_check.py --ip-dir <ip> --json` when applicable,
read `ontology/domain_intent.yaml` when crossings, async inputs, clocks, or resets are in scope, use approved
CDC/RDC patterns only, run or assign `oag_domain_crossing_check.py` when
applicable, and report `rtl_dialect`,
`implemented_contracts`, `behavior_refs_implemented`,
`cycle_rule_refs_implemented`, `ppa_notes`, `domain_crossing_notes`,
`changed_paths`, `checks_run`, and `may_claim_complete=false`.

The verification strategy agent must act as the proof planner, not the TB
writer. It should read locked requirements, obligations, contracts,
behavior_model, cycle_rules, domain_intent, and evidence_plan, then write or
review `ontology/verification_plan.yaml` with verification objectives,
proof_methods, scenarios, coverage_goals, assertion/formal candidates,
fault-model hooks, residual_risks, and open strategy blockers. It must not
implement RTL/TB.

The TB implementation agent must act as a verification methodology implementer,
not the owner of the proof strategy. It should read
`ontology/verification_plan.yaml` and `ontology/tb_methodology.yaml` when
present, classify each target, choose directed/table-driven, transaction-based,
constrained-random, assertion-assisted, formal-candidate, or PSS-style scenario
planning depth as appropriate, and report `tb_methodology_notes` with
methodology_profile, framework, architecture roles, stimulus_strategy,
coverage_strategy, assertion_hooks, formal_candidates, and open blockers. TB
writer must not define the proof strategy it is trying to satisfy. It may test
functional consequences of CDC/RDC rules, such as synchronizer latency or reset
sequencing, but must not claim CDC/RDC, low-power, safety, or AMS closure from
ordinary simulation alone. Failed rows must not count toward closure coverage.

Each subagent must report changed paths, evidence commands, blockers, and ROCEV
links. Write-capable evidence-producing subagents must write a non-empty receipt
under `<ip>/knowledge/subagents/` and end with final line:
`OAG_EVIDENCE_RECORDED: <relative-path>`. JSON receipts must follow
`.claude/schemas/oag_subagent_receipt.schema.json` and include `dispatch_id`,
`dispatch_path`, `changed_paths`, and `generated_side_effects`.

Use `HANDOFF_PASS`, `STATIC_HANDOFF_PASS`, or `RTL_HANDOFF_PASS` for a bounded
worker receipt that passed its assigned handoff. Do not use status language that
implies IP closure, verification closure, release, signoff, or final completion.
No subagent may claim final completion.
```

## Gate Prompt

```text
Use Claude Code subagents for independent review.

Spawn:
- oag-evidence-validator to check records, hashes, scoreboard rows, coverage
  refs, and stale evidence from disk.
- oag-gate-reviewer to independently approve or reject the final claim after
  validator output is available. Gate review must inspect `oag.check`,
  `oag.inspect`, the validation report, and every current closure artifact. Its
  decision must include `checked_artifacts` and `checked_artifact_hashes`.

Wait for both. The main agent reports APPROVE/REJECT with artifact paths and
does not override a blocker. If any closure artifact is added or changed after a
gate PASS, the gate decision is stale and must be re-run.
```

## Start/Stop Hooks

`hooks.json` registers a `SubagentStart` hook for OAG child threads and a
`SubagentStop` hook for evidence-producing OAG agents, including implementation,
validation, and gate-review agents. These hooks do not execute or spawn
subagents; Claude Code native orchestration does that. The start hook injects the
child-work contract and records a start event. The stop hook blocks a stopped
evidence-producing child that lacks a valid
`OAG_EVIDENCE_RECORDED: <relative-path>` receipt, dispatch link, schema-valid
JSON payload, and path-scope verification. This mirrors the oh-my-openagent
executor-verifier pattern while keeping final closure in OAG `check`/`decide`.
