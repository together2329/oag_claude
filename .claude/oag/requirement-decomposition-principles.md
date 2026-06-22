# OAG Requirement Decomposition Principles

OAG V1 already preserves design truth through ROCEV:

```text
Requirement -> Obligation -> Contract -> Evidence -> Validation -> Decision
```

OAG V2 adds one thin semantic layer before obligations:

```text
Requirement Statement -> Requirement Atom -> Atomic Obligation
```

The purpose is not to make the workflow heavier. The purpose is to stop an
agent from turning vague prose into architecture, RTL, TB, or closure.

## Requirement Atoms

A requirement atom is a normalized, verifiable slice of a requirement. It names
the event, condition, response, timing, responsible boundary, observable
phenomena, and ambiguity status before an obligation or contract becomes
closure-grade.

For short IP requests such as `I need mctp rx ip`, the correct behavior is:

1. create at most a draft workspace;
2. write draft knowledge and open questions;
3. produce candidate requirement atoms;
4. wait for user lock before canonical ontology, RTL, TB, or closure work.

No lock, no RTL. No lock, no TB. No prose-only closure.

## Minimum Semantic Slots

Closure-grade requirement atoms should identify:

- source requirement;
- normalized text;
- trigger or event;
- condition or precondition;
- required response;
- timing, latency, or valid-cycle rule when applicable;
- exception and error policy when applicable;
- responsible agent boundary;
- environment assumptions;
- DUT guarantees;
- monitored variables, controlled variables, DUT inputs, and DUT outputs;
- ambiguity/open question state.

Unknown fields should remain explicit open questions. Do not infer transport
binding, buffering, ordering, backpressure, reset priority, interrupt policy,
packet reassembly, filtering, error/drop behavior, or status/counter semantics
from a short request.

## Good Atom Example

```yaml
requirement_atoms:
  - id: ATOM_DATA_OUT_WRITE
    source_requirement_id: REQ_DATA_OUT_APB_ACCESS
    status: draft
    normalized_text: >
      When an APB write transfer to DATA_OUT completes while reset is inactive,
      the IP shall update DATA_OUT_Q from PWDATA on the next rising PCLK edge.
    pattern:
      trigger: PSEL && PENABLE && PWRITE && PADDR == DATA_OUT_ADDR
      condition: PRESETn == 1
      response: DATA_OUT_Q_next == PWDATA[GPIO_WIDTH-1:0]
      timing: next rising PCLK edge
      exception: reset dominates write
    boundary:
      responsible_agent: dut
      environment_agents: [apb_master]
    assumptions:
      environment:
        - APB master follows setup/enable phase protocol.
      dut:
        - Reset behavior is defined by the reset contract.
    phenomena:
      dut_inputs: [PSEL, PENABLE, PWRITE, PADDR, PWDATA, PRESETn]
      controlled_state: [DATA_OUT_Q]
      observable_outputs: [PRDATA]
    ambiguity:
      missing_terms: []
      open_questions: []
```

## Bad Atom Shape

```yaml
id: ATOM_APB_WRITE
text: APB write behavior works.
```

This is not useful because RTL, TB, assertions, coverage, and validation cannot
derive a precise proof obligation from it.

## Promotion Rule

A requirement atom may be draft during interview. Once scope is locked or an
obligation claims closure, shallow atoms become blockers. The agent must either
complete the semantic slots or return to draft with explicit open questions.
