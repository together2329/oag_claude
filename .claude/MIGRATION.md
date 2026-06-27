# OAG Codex-to-Claude Migration Notes

This `.claude` pack was generated from `ip_dev/.codex` and adapted to Claude Code's current configuration surfaces.

Official Claude Code mapping used:

- `CLAUDE.md`: startup project instructions.
- `.claude/settings.json`: permissions, environment, and hooks.
- `.claude/skills/<name>/SKILL.md`: reusable slash-invoked OAG workflows.
- `.claude/agents/*.md`: specialized subagents with YAML frontmatter.
- `.mcp.json`: project MCP servers. OAG intentionally keeps this empty by default.

Runtime caches and historical `.codex/runs` were not copied. OAG source policy, scripts, schemas, skills, hooks, and rules were copied with `.codex` path references rewritten to `.claude`.

## Feature sync — 2026-06-23

Re-synced the full feature set from `ip_dev/.codex` after upstream additions.

Transform rules used (in order): `.codex`→`.claude`, `codex_`→`claude_`, `Codex`→`Claude Code`, lowercase `codex`→`claude`. The all-caps Python identifier `CODEX_ROOT` is the established target convention and is left untouched. Codex TOML agents (`agents/*.toml` with `developer_instructions`/`sandbox_mode`/`model_reasoning_effort`) are converted to Claude Markdown agents (`agents/*.md` with YAML frontmatter `name`/`description`/`tools`/`model`/`effort`); read-only `sandbox_mode` → `tools: Read, Glob, Grep, Bash`. Canonical interpreter for the pack is `python3.12` (the OAG scripts require `tomllib`).

New features ported in this sync:

- **IP versioning / baseline / data-lifecycle**: scripts `oag_ip_version_check.py`, `oag_lifecycle_check.py`, `oag_stale_check.py`, `oag_baseline_check.py`, `oag_baseline_cut.py`, `oag_baseline_verify.py`; schemas `oag_ip_version`, `oag_baseline_manifest`, `oag_artifact_lifecycle`; rule `oag-ip-versioning.rules.md`; OAG policies `ip-versioning-policy.md`, `baseline-git-policy.md`, `data-lifecycle-policy.md`; skill `oag-ip-versioning`; agent `oag-ip-version-steward-agent` (read-only, effort xhigh) — pack now has 18 agents (15 core + 3 custom).
- `oag_authoring_packet_check.py` gained `--require-lifecycle`; `smoke_test.py` gained the versioning/baseline/lifecycle coverage (with the target's `OAG_CALL_TIMEOUT_SECONDS` call-timeout safety preserved); agent-catalog and pack-release checks updated for the new agent and skills.

Verified with `python3.12`: `oag_pack_release_check.py` status=pass (0 issues), `oag_agent_catalog_check.py` status=pass (core 15 / custom 3 / total 18), `smoke_test.py` exit 0, all scripts compile, all schemas valid, no residual Codex naming outside this migration note.

## Feature sync — 2026-06-24

Mirrored the current `ip_dev/.codex` working tree (uncommitted WIP on top of commit `d986421`).

- **Agent model pinned**: all 18 agents set to `model: opus` + `effort: xhigh` (the source's `gpt-5.5` is Codex-native and broke a Claude subagent resume; `opus` resolves to the current Opus 4.8).
- **`oag-doc-to-markdown` removed**: the skill (`SKILL.md` + `scripts/doc_to_markdown.py`) was added upstream (commit `d986421`) and then reverted in the working tree; the target now mirrors the removal (skill deleted; references dropped from `AGENTS.md`, `oag_pack_release_check.py`, `smoke_test.py`, prose docs).
- **Synced WIP edits**: `AGENTS.md` (rewritten upstream into a pack-maintenance index; Markdown agent-model preserved), `hooks.json` + `settings.json` Stop hook hardened to a fail-safe `/bin/sh` wrapper, hooks (`claude_stop_gate`, `claude_subagent_oag_gate`, `oag_hook_utils`), `oag_cli.py`, `oag_eval.py`, `oag_pack_release_check.py`, `smoke_test.py`, `oag-mode-directive.md`, `subagent-workflows.md`, `oag-ip-workflow/SKILL.md`.

`oag_pack_release_check.py`'s Codex agent-TOML-parse loop is dropped in the port (`.md` agents are not TOML; Markdown agent validation is done by `oag_agent_catalog_check`). Re-verified `python3.12`: pack-release status=pass, catalog status=pass (15/3/18), smoke exit 0.

### Complete re-sync — 2026-06-24 (after `.codex` settled, git clean)

`.codex` then received a large committed update; mirrored the whole pack with `scratchpad/fullsync.py` (a complete walker), not a hand-picked subset. Result: 168 source files → 170 target (= 168 + the two Claude-only files `settings.json`, `MIGRATION.md`). New scripts `oag_migrate_layout.py`, `oag_paths.py` added; `oag-rtl-implementation-agent` / `oag-rtl-lint-static-agent` bodies re-derived; all 18 agents kept `model: opus` / `effort: xhigh`.

Per-file transform in `fullsync.py`: `agents/*.toml`→`*.md`, `AGENTS.md` / `oag_pack_release_check.py` / `oag/agent-catalog.toml` / prose docs get the Markdown agent-model adaptation, `oag_agent_catalog_check.py` keeps its Markdown-validator version (source↔target differ only on TOML-vs-frontmatter agent parsing; all other catalog checks identical), `smoke_test.py` via `transform.py` (fnorm + `OAG_CALL_TIMEOUT_SECONDS` + `.toml`→`.md` assertions), everything else plain `fnorm`. Verified: residual Codex naming clean (outside this note + `CODEX_ROOT` idents), all scripts/hooks compile, pack-release pass(0), catalog pass(15/3/18).

### Sync — 2026-06-25 (wavefront / dispatch / bounded-loop batch)

`fullsync.py` mirror after a large `.codex` feature batch (source 184 → target 186). Added 16 new scripts/docs — the wavefront/dispatch refactor (`oag_wavefront_core.py`, `oag_wavefront_ops.py`, `oag_wavefront_graph.py`, `oag_wavefront_records.py`, `oag_wavefront_validation.py`, `oag_wavefront_templates.py`, `oag_dispatch_wavefront.py`, `oag_dispatch_prompt.py`, `oag_dispatch_support.py`, `oag_dispatch_verify.py`, `oag_run_authority.py`, `oag_run_promotion.py`) and bounded-loop (`oag_loop_core.py`, `oag_loop_hook.py`, `oag_loop_runner.py`, `oag/bounded-loop-hook-integration-plan.md`) — all plain `fnorm` copies (0 agent-model markers). 18 agents unchanged (15/3). `fullsync.py` orphan deletion was tightened to pack-content dirs only (never `.omc`/`.cache`/other runtime dirs). Verified: pack-release pass(0), catalog pass(15/3/18), smoke ok:true, all compile, residual Codex naming clean.

### Sync — 2026-06-27 (wavefront handoff decision-gating)

`fullsync.py` mirror after `.codex` settled (git clean on `master`, source 186 files). Ports the `770d7c7 feat(oag): gate wavefront handoff with decisions` batch on top of the last-synced `9135eba`. Dry-run scan first (`scratchpad/scan.py`): 174 identical, 2 new, 9 changed, 0 orphans, 1 intentional divergence (`oag_agent_catalog_check.py` keeps the Markdown-validator version). The only target-extra files are `.cache/*` runtime hook caches (not pack content). Result: target mirrors all 186 source files + the 2 Claude-only files (`settings.json`, `MIGRATION.md`).

New approval/decision-gating feature: schema `oag_wavefront_decision.schema.json` (the `oag_wavefront_decision.v1` review record) and `scripts/oag_decision_harness.py`. `oag_wavefront_records.py` now enforces the `claimed → review_pending → handoff_pass` state machine, where `handoff_pass` requires an approved review decision (`HANDOFF_DECISION_REQUIRED`; worker `HANDOFF_PASS` receipt only reaches `review_pending`, and an approved `oag_wavefront_decision.v1` is needed to promote and unlock downstream barriers). `oag_wavefront.py`, `oag_wavefront_graph.py`, `oag_wavefront_task_graph.schema.json`, `oag/wavefront-policy.md`, `oag/wavefront-task-graph.md`, and `skills/oag-wavefront/SKILL.md` updated to route receipts through `oag-custom-reviewer` review. `agents/oag-custom-reviewer.md` body re-derived (opus/xhigh kept). `smoke_test.py` via `transform.py` (+231 lines of decision-flow coverage; `OAG_CALL_TIMEOUT_SECONDS` and `.toml`→`.md` assertions preserved). All other files plain `fnorm`; 18 agents unchanged (15/3). Verified `python3.12`: pack-release status=pass (0 issues, 18 agent_markdowns, 21 schemas), catalog status=pass (15/3/18), smoke `ok:true` exit 0, all `.py` compile, residual Codex naming clean (outside this note + `CODEX_ROOT`).
