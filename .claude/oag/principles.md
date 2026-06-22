# OAG Principles

OAG is the IP development operating system for this repository. It is not only
a rule list. It teaches agents how to preserve design truth, choose sufficient
proof depth, and close hardware IP work through ROCEV.

## Agent Posture

Use this posture for all OAG IP work:

```text
You are not filling templates.
You are preserving design truth.
Use the smallest sufficient proof.
Do not create heavyweight artifacts unless they buy verification strength.
Do not remove oracle responsibility just because FL/CL files are skipped.
```

LLMs should have room to exercise engineering judgment. Validators should guard
the invariants that cannot be compromised.

## Design Truth

RTL is not the source of truth. RTL is an implementation of truth.

The source of truth is the locked requirement, obligation, contract, approved
ontology, and recorded decision history.

TB is an independent observer of truth. It must not infer intent from RTL.
Scoreboard expected values must not be derived from observed DUT behavior.

LLMs may generate RTL, but generated RTL still cannot become truth. RTL
generation agents implement the locked contract. They may choose internal
structure, but they may not invent behavior, timing, reset values, address maps,
priorities, or protocol semantics.

## Contract Strength

A contract is strong when a different engineer can implement a checker without
guessing the intended behavior.

A prose-only pass condition is weak:

```yaml
pass_condition: APB register behavior is correct
```

A closure-grade contract should resolve to at least one of:

- a `behavior_model` rule;
- a `cycle_rules` rule;
- an approved FL/CL artifact;
- a formal assertion or proof target;
- an explicitly approved equivalent oracle with `decision_receipt_id`.

## Modeling Sufficiency

Full FL/CL artifacts are profile-dependent.

FL/CL responsibilities are not optional when a behavioral or temporal
obligation is claimed closed.

For simple IPs, the sufficient model may be small:

- register behavior;
- state update rules;
- reset behavior;
- bus timing rules;
- synchronization latency;
- priority rules;
- scoreboard expected-source mapping.

For complex IPs, escalate to full FL/CL when the oracle cannot otherwise
predict behavior, timing, ordering, or priority without ambiguity.

## Smallest Sufficient Proof

Do not create heavyweight artifacts just to satisfy a template.

Choose the smallest proof that independently determines expected behavior and
timing for the obligation being closed.

A simple IP deserves a simple oracle, not an absent oracle. A complex IP
deserves enough modeling depth to make expected behavior independent and
reviewable.

PPA-aware RTL follows the same principle. The agent should choose the smallest,
fastest, lowest-toggle implementation that preserves the locked contract. PPA
is not permission to change behavior; it is a reasoned implementation choice
recorded as a design decision.

CDC/RDC-aware RTL is a domain-safety requirement. Clock and reset domain intent
is design truth. RTL may implement crossings, but it may not invent crossing
safety. Every asynchronous clock or reset boundary must be classified, protected
by an approved pattern, proven stable/constant/unreachable, covered by a scoped
decision receipt, or left open with a precise blocker.

Verification methodology is a proof-shaping requirement. The TB agent is not a
framework generator. UVM, cocotb, SV, Verilog, OSVVM, UVVM, PSS-style planning,
assertions, and formal are choices. The invariant is that TB evidence must be
verification-plan driven, self-checking, independently predicted, coverage
aware, and ROCEV traceable.

## Evidence And Closure

Evidence is not closure.

A passing simulation is not closure. A summary is not closure. A child-agent
handoff is not closure.

A passing simulation is also not CDC/RDC closure. CDC/RDC closure requires
domain intent, crossing classification, approved mitigation, validation, and
static/formal/tool-grade or explicitly approved equivalent evidence when the
closure profile requires release strength.

Coverage is not closure. Coverage from failed checks must not count toward
closure coverage. Random stimulus is not closure methodology unless it has
constraints, coverage goals, and a contract-linked reason to exist.

Closure requires:

- evidence;
- validation record;
- traceability to requirement, obligation, and contract;
- a fresh gate decision when the closure profile or OAG policy requires gate
  review.

## Waiver Vs Applicability

Skipping a full FL/CL file is not a waiver when the IP profile does not require
it.

Skipping the oracle responsibility is not allowed for closure.

Applicability decisions must name the substitute proof:

```text
Full FL/CL artifacts: not applicable for simple_leaf_apb_peripheral.
Required substitute: behavior oracle + cycle contract + scoreboard trace +
scenario mapping + ROCEV validation for closed obligations.
```

An approved equivalent oracle is only valid when it has durable decision
receipt data: `decision_receipt_id`, `approver`, `scope`,
`substitute_artifact`, `reason_full_model_not_required`, and
`obligations_covered`.

## Full Power Boundary

The right division of labor is:

```text
LLM: choose the smallest sufficient proof.
Workflow: guide small IPs toward micro-oracles and large IPs toward full models.
Validator: block closure claims that lack independence, traceability, or freshness.
```

For RTL generation, that means:

```text
RTL agent: implement contract truth.
TB agent: independently predict from the same contract truth.
Validator: check that RTL and TB both trace to the same contract oracle.
```

For TB methodology, that means:

```text
TB agent: choose the smallest sufficient verification method.
Coverage: measure exercised contract intent only for passing checks.
Assertions/formal: capture local temporal rules and proof candidates.
Validator: block circular expected values, unresolved coverage refs, and
sim-only closure for special domains.
```

When uncertain, leave the obligation open with a precise blocker rather than
closing it with weak evidence.
