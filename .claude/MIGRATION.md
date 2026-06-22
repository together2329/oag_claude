# OAG Codex-to-Claude Migration Notes

This `.claude` pack was generated from `ip_dev/.codex` and adapted to Claude Code's current configuration surfaces.

Official Claude Code mapping used:

- `CLAUDE.md`: startup project instructions.
- `.claude/settings.json`: permissions, environment, and hooks.
- `.claude/skills/<name>/SKILL.md`: reusable slash-invoked OAG workflows.
- `.claude/agents/*.md`: specialized subagents with YAML frontmatter.
- `.mcp.json`: project MCP servers. OAG intentionally keeps this empty by default.

Runtime caches and historical `.codex/runs` were not copied. OAG source policy, scripts, schemas, skills, hooks, and rules were copied with `.codex` path references rewritten to `.claude`.
