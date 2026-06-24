# OAG Artifact Lifecycle Policy

OAG artifacts carry two independent lifecycle axes:

```text
processing_stage = how far the artifact has been transformed
approval_state   = how much authority the artifact has
validity_state   = whether dependency changes still allow use
```

This policy does not replace ROCEV. ROCEV explains what an artifact means in
the Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision
chain. The lifecycle axes decide whether that artifact is allowed to feed a
consumer such as an RTL authoring packet, TB oracle, validation report, or
baseline manifest.

## Processing Stage

- `raw_source`: user prose, imported spec text, logs, waveform-derived notes, or
  other unprocessed material.
- `parsed`: extracted source claims, ambiguity notes, deep semantic intake, or
  mechanically parsed evidence.
- `canonical`: authored design-truth artifacts such as requirements,
  requirement atoms, obligations, contracts, decision matrices, behavior
  models, cycle rules, and verification plans.
- `curated`: reviewed canonical/evidence artifacts that have validation or
  reviewer context attached.
- `serving`: generated packets, graph views, baseline manifests, or compact
  evidence summaries that are consumed by agents, CI, reviewers, or gates.

## Approval State

- `draft`: captured but not proposed as a decision or implementation basis.
- `candidate`: proposed or recommended, but not approved truth.
- `reviewed`: examined by an agent, checker, or reviewer, but not yet approved.
- `approved`: authorized design/evidence input for the listed consumers.

`golden` is not an artifact approval state. Golden is a baseline class applied
to a baseline manifest after validation and gate review.

## Validity State

- `current`: dependency hashes still match the artifact's recorded sources.
- `stale`: at least one dependency changed after this artifact was approved or
  served.
- `unknown`: freshness cannot be established.
- `invalidated`: a reviewer, checker, or decision explicitly rejected current
  use.

Approval and validity are separate. A historically approved artifact can become
`stale` and must not feed new implementation or closure packets until refreshed.

## Consumer Firewall

Consumers must fail closed:

- missing lifecycle metadata blocks use;
- unknown enum values block use;
- approved artifacts require `approval_ref`;
- canonical, curated, and serving artifacts require `derived_from` unless they
  are explicit root source registries;
- a consumer may only use an artifact if it is listed in `allowed_consumers`;
- stale, unknown, or invalidated inputs cannot feed RTL/TB authoring packets or
  closure evidence.

RTL authoring packets may consume only `canonical`, `curated`, or `serving`
artifacts with `approval_state: approved` and `validity_state: current`.

TB expected oracles may consume only approved, current, independent oracle
sources such as contracts, behavior models, cycle rules, formal properties, or
evidence plans. TB expected sources must not derive from RTL output, DUT output,
waveforms, simulation results, or post-hoc observed behavior.

## Granularity

P0 lifecycle records are file-level. P1 may add object-level records. The schema
therefore separates:

```text
path        = file path
object_id   = optional object identifier inside that file
granularity = file | object
```

Use object-level records when a file contains mixed lifecycle authority, such as
one approved contract and one candidate contract in the same YAML file.
