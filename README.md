# IP Dev Claude — OAG Pack

This repository maintains the project-local **OAG (Ontology Agent Gateway)** pack for Claude Code,
under `.claude/`. OAG is a workflow for hardware IP development that preserves design truth instead
of letting implementers re-interpret a spec from prose.

Enter OAG mode with the explicit `oag` keyword. See [`CLAUDE.md`](CLAUDE.md) for the operating rules.

## What This Repository Is

This repo is the **Claude Code port** of the OAG pack originally developed for Codex under
`ip_dev/.codex`. The same ontology-first methodology is re-expressed using Claude Code's native
surfaces — subagents, skills (slash commands), hooks, and `settings.json` — under `.claude/`.

The repository tracks **only the pack**. Individual IP workspaces (e.g. `cortex_m7_systick/`,
`mctp_tx_assembler/`) are scratch/test artifacts and are gitignored; the only tracked paths are
`.claude/`, `CLAUDE.md`, `.mcp.json`, `.gitignore`, and this README.

- Pack source of truth: `.claude/`
- Agent operating rules: [`CLAUDE.md`](CLAUDE.md) and [`.claude/AGENTS.md`](.claude/AGENTS.md)
- Counterpart pack (Codex): `ip_dev/.codex` — changes are ported here, not authored twice.

## The Problem OAG Solves

When an LLM implements hardware IP directly from a prose spec, it silently re-interprets the
requirements: it invents timing, reset values, address maps, priorities, or protocol semantics, then
"proves" them with tests it also wrote. OAG breaks that loop by separating **design truth** from
**implementation** from **evidence**, and by forcing every "done" claim to trace back through
Requirement → Obligation → Contract → Evidence → Validation → Decision (ROCEV). Generated work inputs
are read-only; closure requires independent evidence, not green tests.

## Repository Layout

```text
ip_dev_claude/
├── CLAUDE.md            # project operating rules (loaded every session)
├── README.md           # this file
├── .mcp.json           # MCP config (OAG registers none by default)
├── .gitignore          # tracks only the pack; ignores all IP workspaces
└── .claude/            # the OAG pack
    ├── AGENTS.md           # agent-facing directive / entry rules
    ├── settings.json       # permissions + hook wiring
    ├── config.toml         # native-subagent feature flags
    ├── agents/    (18)     # OAG subagent roles (frontmatter-defined)
    ├── skills/    (8)      # invocable workflows = slash commands
    ├── scripts/   (56)     # oag_cli.py + checkers / generators / validators
    ├── hooks/              # session / prompt / stop / subagent hooks
    ├── rules/     (14)     # hard rule packs (invariants, CDC/RDC, lock, …)
    ├── oag/       (38)     # reasoning / policy docs (the "why")
    └── schemas/   (20)     # JSON Schemas for evidence / receipts
```

IP workspaces such as `cortex_m7_systick/` may exist on disk for testing but are not tracked.

## Claude Code Integration

OAG is script-, skill-, hook-, and subagent-based; it does not register MCP servers by default.

| Surface | Where | Role |
|---|---|---|
| Project rules | `CLAUDE.md`, `.claude/rules/*.md` | OAG-mode behavior + hard invariants |
| Skills (slash commands) | `.claude/skills/<name>/SKILL.md` | invocable workflows, e.g. `/oag-ip-workflow` |
| Subagents | `.claude/agents/*.md` | bounded OAG roles (RTL, TB, sim, gate, …) |
| Hooks | `.claude/hooks/`, `.claude/settings.json` | inject context, draft-pressure guard, stop gate, subagent gating |
| Policy / reasoning | `.claude/oag/*.md` | modeling, contracts, CDC/RDC, PPA, coverage, evidence |
| Scripts | `.claude/scripts/*.py` | `oag_cli.py` tools + readiness / closure checkers |
| Schemas | `.claude/schemas/*` | validate receipts, scoreboard rows, evidence |

Hooks fire on `SessionStart`, `UserPromptSubmit` (auto-inject `oag.context` and a draft-pressure
guard), `Stop` (closure / stop gate), `SubagentStart` / `SubagentStop` (OAG subagent gating), and
`PostCompact`.

## Completion Standard (ROCEV)

Every meaningful IP claim must flow through:

```text
Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision
```

"Tests are green" is **not** completion. Final closure requires `oag.compile`, `oag.check`, no
`oag.inspect` artifact gaps, `oag.decide` with a recorded decision, and — for release-grade
packages — `.claude/scripts/oag_closure_check.py` plus gate-review evidence.

## Architecture: 8 Layers

The pack separates **"what is true"** (layers 1–4) from **"how it is safely executed and closed"**
(layers 5–8). The ontology layer defines truth/contracts; the wavefront layer schedules parallel
execution without breaking that truth.

```text
User / Spec
  ↓
1  Intake / Draft        ─ capture intent, do not decide truth yet
  ↓
2  Ontology Truth (SSOT) ─ requirements, contracts, structure
  ↓
3  Projection / Compile  ─ generate read-only work inputs
  ↓
4  Readiness Gates       ─ is the truth implementation-ready?
  ↓
5  Run / Orchestration   ─ what obligation to close next
  ↓
6  Wavefront             ─ dependency/ownership-aware parallel schedule
  ↓
7  Dispatch / Receipt    ─ bounded write permission + verified receipt
  ↓
8  Evidence / Closure    ─ ROCEV evidence, gate decision, signoff
```

### 1. Intake / Draft Layer
Captures user requests, spec notes, and open questions as drafts — **without** deciding truth.
- Artifacts: `req/source_claims.yaml`, `req/ambiguity_register.yaml`, `req/deep_semantic_intake/`, `ontology/decision_matrix.yaml`
- Skills: `oag-deep-semantic-intake`, `oag-decision-matrix`
- Scripts: `oag_deep_semantic_intake.py`, `oag_decision_matrix_generate.py`

### 2. Ontology Truth Layer (SSOT)
The single source of truth. Requirements, contracts, and structure that implementers may not
reinterpret freely.
- Artifacts: `ontology/requirements.yaml`, `requirement_atoms.yaml`, obligations, contracts, structure, decomposition, modeling, `domain_intent`, `verification_plan.yaml`, design rules, policies, `ontology/scope_lock.json`
- Skill: `oag-contract-projection`
- Policy: `.claude/oag/*.md` (principles, modeling, contract strength, traceability, …)

### 3. Projection / Compile Layer
Converts ontology truth into read-only, work-ready outputs so RTL/TB agents never re-read the
source intent.
- Driven by: `oag.compile`
- Outputs: `ontology/generated/design_spec.json`, `design_truth_graph.json`, `authoring_packets/rtl__*.json`, `tb__*.json`
- Skill: `oag-authoring-packet`
- Generated packets are **work inputs**, not truth. To fix them, fix the ontology and recompile — never hand-edit.

### 4. Readiness / Schema / Quality Gate Layer
Checks whether the truth and projections are actually implementation-ready (not just present).
- Scripts: `oag_req_quality_check.py`, `oag_requirement_atom_check.py`, `oag_contract_strength_check.py`, `oag_lock_readiness_check.py`, `oag_verification_plan_check.py`, `oag_authoring_packet_check.py`, `oag_trace_graph_check.py`
- These checkers also run JSON-Schema validation via `oag_validate_json.py` (`.claude/schemas/`).

### 5. Run / Orchestration Layer
Tracks which obligation to close next and keeps work coherent across turns.
- Tools: `oag.run.start`, `oag.run.next`, `oag.run.record`, `oag.run.checkpoint`
- Enforced by the Stop hook.

### 6. Wavefront Layer
A scheduler for parallel work. It does **not** create truth — it splits already-ready work by
dependency and ownership.
- Script: `oag_wavefront.py`
- Concepts: task graph, ready task, claim, barrier token, ownership lock, single integration owner
- Skill: `oag-wavefront` · Policy: `.claude/oag/wavefront-policy.md`, `wavefront-task-graph.md`

### 7. Subagent Dispatch / Receipt Layer
Grants a write-capable subagent a bounded permission and verifies its output by receipt.
- Script: `oag_dispatch.py create` / `oag_dispatch.py verify`
- Concepts: allowed write paths, receipt path, `OAG_EVIDENCE_RECORDED: <path>`

### 8. Evidence / Closure / Decision Layer
Closes on ROCEV evidence, not on "tests passed". Final complete/signoff lives here.
- Artifacts: `knowledge/ledger.jsonl`, `scoreboard_rows.v1`, stage receipts, validation reports, gate decisions
- Tools/scripts: `oag.check`, `oag_closure_check.py`, `oag.decide`
- Skill: `oag-evidence-closure`

## Layer Connections

| Layer | Input | Output | Feeds |
|---|---|---|---|
| 1 Intake | user words, spec, questions | source claims, ambiguity, decision candidates | Ontology Truth |
| 2 Ontology Truth | confirmed / draft requirements | requirements, atoms, obligations, contracts, structure, vplan | Projection |
| 3 Projection | ontology files | generated design spec, RTL/TB authoring packets | Readiness, Wavefront |
| 4 Readiness Gate | ontology + generated packets | pass / fail / blocker | gates whether Run may start |
| 5 Run | obligation / contract state | next action | Wavefront or a single task |
| 6 Wavefront | packets, contracts, dependencies | ready task, claimed task, barrier | Dispatch |
| 7 Dispatch / Receipt | claimed task | allowed write path, receipt | Evidence |
| 8 Evidence / Closure | sim / lint / scoreboard / coverage / receipts | validation, gate decision, signoff | final judgment |

## Always required vs conditional

Not every layer fires on every task, but OAG's goal — *multi-agent, verifiable IP closure* — needs
most of them.

**Always required (core):**
- **Ontology Truth** — without it there is no standard for requirements/contracts/structure.
- **Projection / Compile** — turns truth into agent-usable packets so implementers don't reinterpret.
- **Readiness / Quality Gates** — separates a well-formed document from an implementation-ready contract.
- **Evidence / Closure / Decision** — "tests pass" ≠ "requirement closed"; mandatory for complete/signoff.

**Conditional:**
- **Intake / Draft** — short if scope is already clear and locked; required for new/ambiguous IP.
- **Run / Orchestration** — for long, multi-obligation, stop/resume work.
- **Wavefront** — only when work is parallelized across agents.
- **Dispatch / Receipt** — only when write-capable subagents act; read-only analysis can skip it.

### Why split it this way

Responsibility separation is the point:

- Wavefront must not create ontology.
- Dispatch must not change contracts.
- Evidence must not define new requirements.
- No "complete" without a Decision.

So in practice: a single task or early draft does not need all 8; a locked IP implementation makes
Ontology + Projection + Gates effectively mandatory; parallel subagent implementation adds Wavefront
+ Dispatch/Receipt; any closure/signoff claim makes Evidence/Closure/Decision non-negotiable.

## Quick start

```bash
# Bootstrap OAG context for an IP
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.inspect","arguments":{"ip_dir":"<ip>","stage":"<stage>","intent":"<task>"}}'
python3 .claude/scripts/oag_cli.py call --json '{"tool":"oag.compile","arguments":{"ip_dir":"<ip>"}}'

# After lock — readiness gates (layer 4)
python3 .claude/scripts/oag_req_quality_check.py        --ip-dir <ip> --json
python3 .claude/scripts/oag_requirement_atom_check.py   --ip-dir <ip> --json
python3 .claude/scripts/oag_contract_strength_check.py  --ip-dir <ip> --json
python3 .claude/scripts/oag_lock_readiness_check.py     --ip-dir <ip> --json
python3 .claude/scripts/oag_verification_plan_check.py  --ip-dir <ip> --json
```

Use `/oag-ip-workflow` as the umbrella workflow, and the narrower skills (`oag-deep-semantic-intake`,
`oag-decision-matrix`, `oag-contract-projection`, `oag-authoring-packet`, `oag-wavefront`,
`oag-evidence-closure`, `oag-ip-versioning`) when a task enters a specific lane.
