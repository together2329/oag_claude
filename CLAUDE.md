# IP Dev Claude Configuration

This project uses the Ontology Agent Gateway (OAG) workflow for hardware IP development. OAG preserves design truth through Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision (ROCEV). Claude Code should treat `.claude/` as the project-local OAG pack.

## Core Behavior

Use the exact `oag` keyword to enter OAG mode. Hardware IP work must keep requirements, lock decisions, RTL, testbench work, simulation evidence, coverage, and closure decisions separate. Short requests such as "make uart" or "I need mctp rx ip" are draft intake only: capture source claims, ambiguity, and decision candidates before proposing implementation.

No scope lock, no RTL. No scope lock, no TB. No scope lock, no closure. `ontology/scope_lock.json` is the implementation permission switch. Locked implementation and verification writes should be delegated to the appropriate OAG subagent and backed by dispatch receipts unless the user explicitly records a waiver.

## Claude Code Surfaces

- Project instructions live here in `CLAUDE.md`.
- Reusable workflows live in `.claude/skills/<name>/SKILL.md` and can be invoked as slash commands such as `/oag-ip-workflow`.
- Specialized OAG roles live in `.claude/agents/*.md` with Claude Code subagent frontmatter.
- Permissions and hooks live in `.claude/settings.json`.
- Shared policy, schemas, scripts, and rule documents live under `.claude/oag`, `.claude/rules`, `.claude/scripts`, and `.claude/schemas`.
- This pack intentionally does not register MCP servers by default; OAG is script, skill, hook, and subagent based.

## Required OAG Checks

Before hardware IP implementation or closure, use the OAG skills and scripts rather than inventing architecture from prose. Common commands:

```bash
python3 .claude/scripts/oag_req_quality_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_requirement_atom_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_contract_strength_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_trace_graph_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_lock_readiness_check.py --ip-dir <ip> --json
python3 .claude/scripts/oag_verification_plan_check.py --ip-dir <ip> --json
```

Use `/oag-ip-workflow` as the umbrella workflow and narrower skills for intake, decision matrix, contract projection, authoring packets, wavefront planning, and evidence closure.
