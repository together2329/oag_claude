# OAG IP Versioning Rules

These hard rules govern functional IP versions, golden baselines, and IP-local
git readiness.

## RULE-IPVER-001: IP-Local Git

Golden or release baseline promotion requires an IP-local `.git` repository.
The product pack development repository is not a substitute for the IP
workspace repository.

Checker:

```bash
python3 .claude/scripts/oag_ip_version_check.py --ip-dir <ip> --require-ip-git --json
```

## RULE-IPVER-002: Patch Cannot Change Truth

Patch versions are allowed only when functional design truth is unchanged.
If requirements, obligations, contracts, locked decisions, behavior rules,
cycle rules, interface meaning, storage visibility, or firmware-visible
semantics changed, use minor or major.

## RULE-IPVER-003: One Active Version

`ontology/ip_version.yaml` must have exactly one active version, and
`current_version` must match it.

## RULE-IPVER-004: Golden Baseline Has Manifest, Approval, and Tag

Golden and release entries require:

- `baseline_manifest`
- `approval_ref`
- `git_tag`

The active golden/release entry's manifest and approval ref must exist under
the IP directory.

## RULE-IPVER-005: Annotated Tags for Verified Baselines

When git tag verification is requested, the active golden/release tag must
exist in the IP-local repository and must be an annotated tag.

Checker:

```bash
python3 .claude/scripts/oag_ip_version_check.py --ip-dir <ip> --require-ip-git --verify-git-tag --json
```
