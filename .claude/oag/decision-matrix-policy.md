# OAG Decision Matrix Policy

The decision matrix is the lock-readiness layer between draft requirements and
implementation. It exists to prevent an agent from silently turning unknown
product choices into RTL semantics.

## Principle

A requirement can be drafted while decisions are open. Implementation cannot
start while lock-blocking decisions are open.

For simple IPs, the matrix may contain only a few reset/interface/register
decisions. For protocol, packet, DMA, bridge, cache, or queueing IPs, the
matrix should be split by design layer: boundary, ingress protocol, decode,
state/ordering, storage, firmware visibility, interrupts/status, and
verification.

## Canonical Artifact

Each IP should carry:

```text
ontology/decision_matrix.yaml
```

The artifact is authored truth. Generated projections may refer to it, but must
not replace it.

## Required Shape

Each decision row should include:

- `id`: stable decision id.
- `question`: the product or design question.
- `status`: `unresolved`, `proposed`, `decided`, `waived`, or `blocked`.
- `lock_required`: whether this decision must be resolved before implementation
  lock-readiness.
- `owner`: human, integrator, requirement agent, IP contract agent, or similar.
- `decision`: required when `status=decided`.
- `waiver_reason`: required when `status=waived`.
- `recommended`: optional proposed default, never locked truth by itself.
- `rationale`: why the decision or recommendation exists.
- `affects`: requirements, atoms, obligations, contracts, interfaces, storage,
  verification, RTL, TB, or evidence.
- `refs`: specs, user answers, source files, OAG records, or decision receipts.

## Lock Readiness

`lock_required: true` decisions must reach `decided` or `waived` before the IP
is implementation-ready. A proposed recommendation is not a decision. A blocked
decision is a blocker, not a default.

After lock, run:

```bash
python3 .claude/scripts/oag_lock_readiness_check.py --ip-dir <ip> --json
```

This check composes the decision matrix with the requirement atom and
assume/guarantee gate. Passing lock readiness does not close the IP; it only
means requirements are specific enough to dispatch implementation work.

## Short Request Rule

For prompts like "I need mctp rx ip", create or update draft decision rows
instead of picking defaults. Unknown transport binding, packet scope,
buffering, filtering, ordering, backpressure, output, storage, or error policy
must stay unresolved until confirmed by the user or a concrete source.
