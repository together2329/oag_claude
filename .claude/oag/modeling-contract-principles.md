# OAG Modeling Contract Principles

This file is the compatibility entry point for the OAG modeling-contract
philosophy. The detailed guidance is split by responsibility:

- `principles.md`: design-truth preservation principles.
- `modeling-policy.md`: profile-based FL/CL and oracle-depth decisions.
- `contract-projection.md`: Requirement -> Obligation -> Contract -> Evidence
  projection rules.
- `rtl-implementation.md`: generated RTL freedom, forbidden spec drift, trace,
  and handoff receipt rules.
- `rtl-dialect-policy.md`: OAG SV-lite RTL syntax policy.
- `rtl-ppa-principles.md`: correctness-first PPA-aware RTL design principles.
- `scoreboard-evidence.md`: independent expected/observed evidence rules.
- `recovery-playbook.md`: what to do when an oracle, trace, or gate is weak.

Use the split files as the active source of guidance. The core rule remains:

```text
LLMs get principles and judgment.
Validators enforce hard invariants.
The workflow keeps small IPs small and makes large IPs justify deeper models.
```
