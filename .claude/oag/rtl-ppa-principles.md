# RTL PPA Principles

PPA is not post-processing. PPA is architectural intent expressed in RTL
structure.

Synthesis optimizes the structure it receives. It does not rescue a confused
architecture.

PPA does not replace CDC/RDC safety. CDC/RDC crossings are governed by
`.claude/oag/domain-crossing-principles.md` and
`ontology/domain_intent.yaml`.

## Correctness Before PPA

Never optimize by changing locked behavior.

Correctness is mandatory. PPA optimization is allowed only when it preserves the
contract.

```text
Correctness first.
Then choose the smallest, fastest, lowest-toggle implementation that preserves the contract.
Do not optimize by changing behavior.
Do not add cleverness without a stated PPA reason.
Do not create timing-hostile structures accidentally.
```

## Performance

Ask before writing RTL:

- Where is the likely critical path?
- Are wide compare, wide mux, adder, priority encoder, or decode logic stacked
  in one cycle?
- Is a pipeline or register boundary required by timing or throughput?
- Is there high fanout on enable, reset, select, or address decode?
- Is ready/valid or APB response timing simple enough for the target profile?

Prefer:

- simple decode;
- local enables;
- separated control and datapath;
- reduced select width before wide muxes;
- registered boundaries only when required;
- no unnecessary pipeline for simple peripherals.

Pipeline only when there is a timing reason or throughput requirement. Do not
pipeline simple APB register peripherals by default.

## Power

Dynamic power is strongly tied to switching activity. RTL should ask:

```text
Does this signal need to toggle in this cycle?
```

Prefer:

- explicit register write enables;
- avoiding updates to unchanged state;
- isolating wide datapaths when idle;
- avoiding glitchy deep combinational cones;
- avoiding unnecessary reset on non-architectural state;
- allowing synthesis to infer enables from RTL structure.

Use this pattern when it matches the contract:

```verilog
if (write_en) begin
  reg_q <= next_value;
end
```

Avoid manual clock gates unless the policy explicitly allows them. Express
intent with enables and let synthesis or downstream low-power flow implement
clock gating.

## Area

Avoid accidental hardware:

- unintended latches;
- accidental priority muxes;
- duplicated large logic;
- oversized counters and registers;
- unnecessary parallel resources;
- unnecessary pipeline registers;
- excessive parameter expansion.

Prefer simple decode. Avoid accidental priority unless priority is required by
contract. Use `case` when choices are mutually exclusive and a default behavior
is defined.

Resource sharing versus parallelism is a tradeoff:

```text
parallel resources -> faster, larger
shared resources   -> smaller, slower/control-heavy
```

For small APB peripherals, simplicity usually wins. For complex datapaths, use
the PPA intent to choose.

## State Encoding

Choose encoding for purpose:

- binary: usually smaller area;
- one-hot: often simpler/faster decode, more flops;
- gray: useful for some CDC/counter transition-power cases.

When the RTL dialect does not allow enums, use `localparam` encodings.

Gray encoding for a crossing is a CDC design decision, not only a PPA choice.
It must trace to domain intent and crossing evidence.

## Tradeoff Rule

Every non-obvious PPA choice must state:

- what it improves;
- what it costs;
- which contract it preserves.

Example:

```text
Single-cycle APB decode favors simplicity and area over high-frequency
pipelining; acceptable for simple_leaf_apb_peripheral because the contract
requires PREADY always 1 and no throughput target beyond APB response.
```

## PPA Intent Shape

The canonical policy can live in `ontology/policies.yaml` or a future
`ontology/implementation_policy.yaml`:

```yaml
rtl_policy:
  dialect: oag_sv_lite_v1
  base: verilog_2001
  allowed_extensions:
    - logic
    - generate
  disallowed_constructs:
    - always_ff
    - always_comb
    - typedef
    - enum
    - struct
    - interface
    - package
    - class
    - assertions
    - covergroups
ppa_policy:
  mode: ppa_aware_correctness_first
  require_ppa_notes_for_nontrivial_rtl: true
  simple_leaf_peripheral:
    default_strategy:
      performance: single_cycle_simple_decode
      power: explicit_write_enable
      area: no_unnecessary_pipeline_or_duplication
    pipeline_default: false
    clock_gating_default: infer_enable_only
```

Simple APB GPIO:

```yaml
ppa_intent:
  ip_profile: simple_leaf_apb_peripheral
  priority_order:
    - correctness
    - simplicity
    - low_area
    - low_power
    - adequate_performance
  performance_target:
    type: qualitative
    value: single_cycle_apb_response
  power_target:
    type: qualitative
    value: avoid_unnecessary_register_updates
  area_target:
    type: qualitative
    value: no_unnecessary_pipeline_or_duplication
```

Datapath pipeline:

```yaml
ppa_intent:
  ip_profile: datapath_pipeline
  priority_order:
    - correctness
    - throughput
    - timing
    - power
    - area
  performance_target:
    type: throughput
    value: one_result_per_cycle
```

## APB GPIO Guidance

APB GPIO should not use elaborate PPA machinery.

Good defaults:

- single-cycle APB response;
- `PREADY` always 1 when specified by contract;
- simple address decode;
- no pipeline;
- register write enables for DATA_OUT, DIR, and IRQ state;
- DATA_IN synchronizer updates every cycle because it samples asynchronous input;
- no manual clock gating;
- no duplicated register bank;
- no pipeline registers beyond required synchronizer and architectural state.

For APB GPIO, good RTL is small, explicit, contract-traceable, and easy for
synthesis to optimize.
