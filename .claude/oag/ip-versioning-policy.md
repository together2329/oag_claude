# OAG IP Versioning Policy

OAG IP versioning manages the functional version of one IP workspace. It is
separate from pack development versioning and assumes the IP directory can own
its own `.git` repository.

```text
IP-local git repo     = exact file tree for one IP
semantic IP version   = functional baseline lineage
baseline manifest     = audited truth/implementation/evidence scope
annotated git tag     = durable named baseline pointer
```

The product pack may live in a separate development repository. A user's IP
workspace may not have a parent git repository at all. For OAG baseline work,
the stewarded repository is the IP folder itself.

## Canonical Ledger

The version steward reads and validates:

```text
<ip>/ontology/ip_version.yaml
```

Minimal shape:

```yaml
schema_version: oag_ip_version.v1
ip: example_ip
current_version: 0.1.1
version_policy:
  git_scope: ip_local_repo
  tag_prefix: oag/example_ip/
versions:
  - version: 0.1.0
    baseline_class: golden
    state: superseded
    change_class: initial
    functional_truth_changed: true
    baseline_manifest: ontology/baselines/example_ip_golden_v0.1.0.yaml
    git_tag: oag/example_ip/v0.1.0
    approval_ref: ontology/validations/example_ip_version_review.json
  - version: 0.1.1
    baseline_class: golden
    state: active
    change_class: patch
    functional_truth_changed: false
    baseline_manifest: ontology/baselines/example_ip_golden_v0.1.1.yaml
    git_tag: oag/example_ip/v0.1.1
    approval_ref: ontology/validations/example_ip_version_review.json
```

There must be exactly one `active` version, and `current_version` must match
it. Golden and release versions require an approval reference, baseline
manifest, and git tag.

## Version Classes

- `patch`: implementation, TB, evidence, script, or tool repair with unchanged
  functional truth. `functional_truth_changed` must be `false`.
- `minor`: requirement, decision, contract, interface, storage, timing, or
  oracle meaning changed in a backward-compatible way for the project.
- `major`: release/signoff meaning, incompatible interface behavior, or
  external contract changed in a way downstream users must consciously adopt.
- `initial`: first recorded version in an IP ledger.

Patch does not mean "small". It means the approved design truth is unchanged.
If the requirement, obligation, contract, decision matrix, locked truth,
behavior model, cycle rule, or firmware-visible meaning changes, the bump is
not patch.

## Golden Baseline

`golden` is a baseline class, not an artifact approval state. Artifact lifecycle
still uses approval and validity metadata. A golden baseline means the selected
truth, implementation, compact evidence, validation, gate record, and external
artifact references are frozen by a manifest and tag.

Golden promotion requires:

1. IP-local `.git` exists.
2. `ontology/ip_version.yaml` passes `oag_ip_version_check.py`.
3. The active version points to a baseline manifest.
4. The baseline manifest passes `oag_baseline_check.py`.
5. The manifest is committed in the IP-local repository.
6. The active version tag is an annotated git tag.
7. `oag_baseline_verify.py --verify-git-tag` passes.

The version steward may recommend a bump and report blockers. It must not create
golden/release tags or claim closure without an explicit human approval and gate
decision path.

## Git Relation

Use IP-local tags:

```text
oag/<ip>/v<major>.<minor>.<patch>
```

The baseline manifest should keep:

```yaml
git:
  tag: oag/<ip>/v0.1.0
  commit: resolved_by_tag
  tag_type: annotated
```

Do not store a concrete self commit hash inside the manifest. Resolve the tag
when verification is requested.

## Agent Input Governance

The version ledger does not create design truth. It tells agents which approved
baseline lineage they may rely on.

- RTL/TB workers may consume active approved/golden baseline data only through
  generated authoring packets.
- Candidate, stale, or unapproved version entries are not implementation truth.
- A patch bump cannot hide a functional truth change.
- Superseded versions remain audit history but are not the current input unless
  a user explicitly requests comparison or rollback analysis.

Use:

```bash
python3 .claude/scripts/oag_ip_version_check.py --ip-dir <ip> --require-ip-git --json
```

Use `--verify-git-tag` after the baseline commit and annotated tag exist.
