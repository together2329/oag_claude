# OAG ROCEV Rule Pack

Use these rules through the OAG directive, `.claude/AGENTS.md`, skills, hooks,
or future managed config.

```text
Before IP work:
  read .claude/rules/oag-invariants.rules.md as the hard invariant layer when closure, validation, scoreboard, or gate claims are involved
  use .claude/oag/principles.md, .claude/oag/modeling-policy.md, .claude/oag/contract-projection.md, .claude/oag/rtl-implementation.md, .claude/oag/rtl-dialect-policy.md, .claude/oag/rtl-ppa-principles.md, .claude/oag/domain-crossing-principles.md, .claude/oag/clock-reset-architecture.md, .claude/oag/cdc-rdc-evidence.md, .claude/oag/verification-methodology-principles.md, .claude/oag/tb-methodology-policy.md, .claude/oag/tb-architecture-patterns.md, .claude/oag/coverage-closure-policy.md, .claude/oag/assertion-formal-policy.md, and .claude/oag/scoreboard-evidence.md as the OAG reasoning layer for modeling, RTL, CDC/RDC, TB methodology, coverage, assertion/formal, and evidence choices
  if the IP is new, call oag.scaffold or run .claude/scripts/oag_scaffold_ip.py
  call oag.inspect
  call oag.compile after ontology edits
  call oag.context
  when Claude Code hooks are enabled, UserPromptSubmit may inject oag.context automatically
  for goal-driven work, call oag.run.start and then follow oag.run.next
  keep ontology/design_rules.yaml present with required common rule kinds
  keep ontology/structure.yaml and ontology/decomposition.yaml present
  keep ontology/protection.yaml and knowledge/ledger.jsonl present
  validate Claude Code agent roles with .claude/scripts/oag_agent_catalog_check.py before subagent-style sharding
  use the exact oag keyword when team prompts should activate OAG mode; auto research, subagent, and signoff are work terms, not trigger words
  keep .claude/config.toml [features].multi_agent=true, [features].child_agents_md=true, [features.multi_agent_v2].enabled=false, and [agents].max_depth=1 for trusted-project subagent support
  use .claude/scripts/oag_claude_config_doctor.py --include-omo-plugin-features --apply to patch team user config when native subagents are not enabled
  trigger subagents through native Claude Code subagents, using multi_agent_v1.spawn_agent where exposed or the equivalent Claude Code CLI/App spawn_agent collaboration event
  before reporting BLOCKED_NATIVE_SUBAGENT, first attempt a minimal native spawn in the active surface and wait for the child result; do not decide availability from the visible callable tool namespace alone, and explicitly request the native spawn_agent collaboration event in Claude Code CLI/App traces
  only report the observed blocker if the actual spawn attempt fails or the runtime reports spawning unavailable
  do not substitute Python, shell wrappers, or manual child-role impersonation unless the user waives native subagents
  every spawn message starts with TASK and includes DELIVERABLE, SCOPE, and VERIFY
  use fork_context=false unless the child truly needs full parent history

During IP work:
  keep claims linked to requirement, obligation, contract, evidence, validation
  record findings with actor.kind and actor.id
  when using subagents, the main prompt must name agent_type, shard scope, owned obligation or contract target, expected summary shape, and evidence outputs
  treat agent_type as routing hint; paste role requirements into the child message
  wait_agent timeout is mailbox silence, not failure; do not count a child result as approval without delivered evidence
  do not allow custom subagents to claim final closure, edit protected ontology, or work outside their prompted shard
  evidence-producing OAG subagents must end with OAG_EVIDENCE_RECORDED: <relative-path>
  rely on oag.record, oag.draft, and oag.ticket to append ledger events
  if an OAG run is active, use oag.run.record at evidence boundaries
  keep ontology/runs/<run_id>/run_state.json as durable execution state, not source truth
  during deep requirement interviews, call oag.draft after each meaningful answer round
  if context usage/compaction pressure is high, call oag.draft before continuing
  when Claude Code hooks are enabled, high-pressure requirement prompts inject an oag.draft guard
  never treat an interview draft as locked truth without explicit human promotion
  never silently edit protected locked-truth or closure-policy fields
  do not require a specific TB language, framework, simulator, or generator
  do require the TB methodology responsibilities appropriate to the IP profile: scenario intent, driver/BFM, monitor, predictor, scoreboard, coverage collector when load-bearing, assertion/formal hooks when useful, and OAG evidence writer
  use ontology/tb_methodology.yaml as the canonical TB methodology intent file when present
  choose the smallest sufficient TB method: directed/table-driven micro-TB for simple IPs, transaction/random/coverage/assertion-assisted TB for moderate IPs, reusable agents/reference models/coverage-driven closure/formal candidates for complex IPs
  do not force UVM, cocotb, SV, Verilog, OSVVM, UVVM, or PSS files unless the IP profile and proof need justify them
  require random or constrained-random stimulus to name constraints and coverage goals before it supports closure
  do not count failed tests or failed scoreboard rows toward closure coverage
  require coverage refs used for closure to resolve to contract-linked coverage goals or evidence
  use assertions for local protocol, temporal, reset, and invariant checks when they are more precise than end-to-end scoreboard rows
  record formal candidates when simulation would be weak or incomplete
  do not require full FL/CL artifacts for simple leaf peripherals by default; require the behavior oracle, cycle contract, scoreboard trace, and traceability roles when an obligation is claimed closed
  apply modeling enforcement by stage: guide/warn during draft and exploration, require profile rationale at lock/promotion, and block unsupported closure/signoff claims
  enforce modeling completeness per closing obligation, not as a whole-IP all-or-nothing gate
  use contract-type-specific refs: structural contracts require structure refs, behavioral contracts require behavior refs, temporal contracts require cycle-rule refs, verification contracts require scenario and scoreboard-row refs, and signoff contracts require validation and gate refs
  for RTL generation, allow implementation freedom for internals but forbid changing design truth: no invented behavior, timing, reset values, address map, priorities, protocol semantics, or side effects
  require RTL implementation handoffs to name rtl_dialect, implemented contracts, behavior refs, cycle-rule refs, changed paths, checks run, ppa_notes for nontrivial RTL, and may_claim_complete=false
  require PPA-aware RTL reasoning: identify likely critical paths, high-toggle state/datapath, and area-risk structures before nontrivial RTL edits
  require PPA optimization to preserve locked contract behavior; never accept timing, power, or area improvements that alter protocol, reset, priority, address map, or externally visible behavior
  require CDC/RDC-aware RTL reasoning when clocks, resets, async inputs, generated clocks, or crossing contracts are in scope: read ontology/domain_intent.yaml, classify crossings, choose approved mitigation patterns, and record domain_crossing_notes
  require domain intent for multi-clock or multi-reset IPs, and require external async inputs to be classified before RTL implementation claims
  do not accept independent bit synchronizers for coherent multi-bit CDC unless the crossing is Gray-coded, stable, sampled-level, or explicitly approved
  use .claude/scripts/oag_domain_crossing_check.py for lightweight development CDC/RDC intent screening when domain crossings or async inputs are in scope; do not treat it as a release signoff tool
  allow manual_spec expected_source only as provisional smoke/debug evidence unless an explicit decision receipt approves its closure use
  require planned scenarios before implementation closure and actual sim/scenario_mapping.json only after TB/sim execution has produced scenario evidence
  require scoreboard_rows.v1 semantics when scoreboard evidence is submitted
  require observed_source to prove DUT-facing observation, not model output
  activate design-rule instances for same-cycle priority conflicts, event/state commit consistency, contract-to-proof coverage, interleaved-context coverage, fault-model coverage, verification role decomposition, CDC/RDC crossing coverage, protocol compliance, timing closure, functional coverage closure, reset/X-prop coverage, and RTL language subset policy
  for load-bearing coverage closure, link coverage_refs -> fault_models -> killed mutation_results, or record mutation_not_required with rationale
  for signoff-grade TB architecture, model UVM-style roles without requiring UVM: sequence, driver, monitor, reference_model, scoreboard, coverage, env, and test
  for signoff-grade domain closure, require concrete evidence refs for CDC/RDC, protocol, timing/STA, functional coverage, and reset/X-prop claims; timing/STA must declare target frequency or target clocks, derive SDC from target clocks plus CDC/RDC async groups/exceptions, and use 50% clock-period input/output delays by default; DFT and power are not OAG v1 default gates
  keep the RTL language subset rule active: OAG SV-lite is Verilog-2001 baseline plus logic and static generate/genvar/generate-for; always_ff/always_comb and procedural for/while/repeat/forever loops outside generate blocks are forbidden by default
  use .claude/scripts/oag_ppa_check.py for lightweight generated-RTL PPA/dialect screening when RTL files are available
  model RTL structure through decomposition profiles, not blanket rules:
    small_leaf_single_file for tiny leaf IPs, greenfield_modular for new nontrivial IPs,
    legacy_preserve for imported existing hierarchy, wrapper_adapter for protected cores plus new integration wrappers
  for greenfield_modular, require each current_ip module to use a unique RTL file by default;
    shared files require explicit shared_file_rationale
  use ontology/generated/design_spec.json and ontology/generated/authoring_packets/*.json as generated read-only work inputs after oag.compile
  use ontology/generated/design_facts_graph.json as generated read-only current-RTL facts after oag.compile; fix RTL or authored decomposition when extracted modules drift from ontology, never hand-edit generated facts
  keep implementation and evidence versioned through git-aware records/receipts: RTL, TB, filelists, SDC, docs, generated facts, and signoff artifacts should carry commit IDs or SHA-256 fingerprints before closure
  after meaningful improvement boundaries, call oag.metrics so closure ratio, issue counts, evidence counts, stage receipts, ledger events, and blocked/partial next-action counts are recorded numerically
  call oag.handoff when progress needs to be carried forward; the handoff must derive development_ready, signoff_ready, ranked next actions, and blockers from OAG metrics and auto-research evidence
  never mark signoff_ready=true from development closure alone; signoff readiness requires signoff profile, no blockers, no partial actions, and independent review evidence
  do not hard-code a fixed number of obligations or signoff slots for progress; derive totals and percentages from the active IP ontology and evidence graph
  route failures through failure_ticket.v1 instead of raw log prose
  write stage_run_receipt.v1 for evidence intended for signoff
  when bounded formal/assertion evidence is submitted through signoff/formal_assertion_report.json,
    treat status=development_pass as partial development evidence unless a promoted formal contract,
    full signoff proof scope, independent review, and matching ROCEV evidence exist

Before closure:
  call oag.compile
  call oag.check
  call .claude/scripts/oag_closure_check.py when validating a release-grade closure package
  call oag.decide action=claim_complete with record_decision=true
  if an OAG run is active, call oag.run.checkpoint before claiming completion
  if oag.stop_check returns should_continue=true, continue with its OAG NEXT ACTION
  if allowed=false, do not claim completion
  require explicit rocev.validation.status for closed records
  require every obligation to close through the obligation -> contract -> validation closure matrix
  require behavioral or temporal closing claims to resolve to behavior_model, cycle_rules, approved FL/CL artifacts, or explicitly approved equivalent oracle refs with decision_receipt_id
  require CDC/RDC closing claims to resolve to domain intent, crossing classification, approved mitigation, evidence refs, validation, and gate freshness when required
  block CDC/RDC closure from simulation-only evidence
  block low-power, safety, and AMS closure from ordinary simulation-only evidence unless a scoped policy decision explicitly permits development-grade limitation
  for release-grade CDC/RDC closure, require static/formal/tool-grade evidence or an approved equivalent decision receipt
  require closure-grade scoreboard expected sources to resolve to behavior/cycle/model refs unless an explicit decision receipt approves otherwise
  require random-based closure to have constraints, coverage goals, and passing scoreboard/assertion evidence
  require load-bearing coverage closure to exclude failed checks and resolve coverage refs to contract-linked goals
  require closed evidence file hashes to match current disk content
  require protected fields clean, append-only ledger valid, and monotonic closure intact
  require a decision receipt under ontology/validations for completion claims
  require validator and gate-review reports for release-grade closure packages
  include improvement_metrics in check/context/decision evidence so progress can be compared between snapshots
  keep readiness handoff reports consistent with embedded improvement_metrics so next actions and blockers can be checked numerically
  for signoff, require closure_profile=signoff, human-approved policy transition, fresh stage receipts, and an independent reviewer receipt
  do not claim a formal/assertion contract without proof/assertion evidence refs
  do not weaken closed/passed objects back to draft/open/stale without an approved decision

When asked to understand the whole IP:
  call oag.inspect
  build an ontology graph with .claude/scripts/oag_graph.py
  use the graph to explain requirements, obligations, contracts, evidence, validations, actors, records, artifacts, and gaps

Promotion:
  AI may propose local knowledge and candidates
  human decision is required for enterprise promotion, waivers, and signoff
  human decision is required for protected semantic truth or policy changes
  discovered defects should become refuted records, not silent closure downgrades
  execution style (single worker, orchestrator, CI, human shell) is record metadata, not a separate ontology mode
```

Completion report shape:

```text
Requirement:
Obligation:
Contract:
Evidence:
Validation:
OAG Decision:
```
