---
name: oag-ip-versioning
description: Use when managing an IP workspace's functional semantic version, IP-local git readiness, golden baseline lineage, baseline manifest/tag relation, or version bump recommendation before RTL/TB/evidence consumers rely on a baseline.
---

# OAG IP Versioning

Use this skill when an IP needs functional version governance: major/minor/patch
bump selection, golden baseline readiness, IP-local git initialization checks,
or baseline tag verification.

## Purpose

This skill does not create design truth. It governs whether an IP's approved
truth, implementation, evidence, validation, and gate artifacts are versioned
well enough to become an auditable baseline.

OAG traceability still flows through:

```text
Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision
```

The version ledger records which baseline lineage is active and which semantic
bump is appropriate.

## Inputs

Read:

- `.claude/oag/ip-versioning-policy.md`
- `.claude/rules/oag-ip-versioning.rules.md`
- `<ip>/ontology/ip_version.yaml`
- `<ip>/ontology/baselines/*.yaml`
- `<ip>/ontology/validations/*.json`
- `<ip>/ontology/gates/*.json`

For golden/release checks, use the IP-local `.git`, not the product-pack
development repository.

## Required Checks

Before treating a baseline as version-ready:

```bash
python3 .claude/scripts/oag_ip_version_check.py --ip-dir <ip> --require-ip-git --json
python3 .claude/scripts/oag_baseline_check.py --manifest <ip>/ontology/baselines/<baseline>.yaml --json
```

After the baseline commit and annotated tag exist:

```bash
python3 .claude/scripts/oag_ip_version_check.py --ip-dir <ip> --require-ip-git --verify-git-tag --json
python3 .claude/scripts/oag_baseline_verify.py --manifest <ip>/ontology/baselines/<baseline>.yaml --verify-git-tag --json
```

## Bump Selection

Recommend:

- `patch` only when functional truth is unchanged.
- `minor` when approved design meaning changes but the project treats it as a
  compatible baseline evolution.
- `major` when external users or downstream systems must consciously adopt the
  change.
- `initial` for the first recorded IP version entry.

If a patch candidate changes requirements, contracts, locked decisions,
behavior/cycle rules, firmware-visible storage/IRQ behavior, or interface
semantics, return BLOCKED and recommend minor or major instead.

## Agent Handoff

Use `oag-ip-version-steward-agent` for read-only version/baseline review. The
steward may write reports or versioning evidence under allowed evidence paths,
but it must not implement RTL/TB, create golden/release tags without human
approval, or claim final closure.

## Output

Useful outputs:

- version bump recommendation;
- golden baseline readiness report;
- IP-local git initialization blocker;
- missing manifest/approval/tag blocker;
- patch truth-change blocker;
- tag verification result.
