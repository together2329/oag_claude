# OAG Phenomena And Boundary Model

Requirement decomposition must separate environment phenomena from DUT signals,
DUT state, and DUT responsibility.

This borrows the useful hardware interpretation of the four-variable model:

- monitored variables: environment facts the IP observes;
- controlled variables: environment-visible facts the IP controls;
- DUT inputs: concrete input ports or transactions;
- DUT outputs: concrete output ports or transactions.

The boundary matters because RTL can only implement DUT responsibility. It must
not silently assume environment behavior that was never recorded.

## Example

```yaml
phenomena:
  monitored_variables:
    - apb_write_transfer
    - gpio_i_external_level
  controlled_variables:
    - DATA_OUT architectural value
    - gpio_o pin value
    - irq_o level
  dut_inputs:
    - PSEL
    - PENABLE
    - PWRITE
    - PADDR
    - PWDATA
    - gpio_i
  dut_outputs:
    - PRDATA
    - PREADY
    - PSLVERR
    - gpio_o
    - irq_o
  natural_assumptions:
    - gpio_i may change asynchronously to PCLK
  input_relations:
    - gpio_i_external_level is sampled through a two-stage synchronizer
  output_relations:
    - gpio_o reflects DATA_OUT_Q masked by DIR_Q
```

## Boundary Rules

- External asynchronous inputs must be classified before RTL closure.
- Environment assumptions must not be recorded as DUT guarantees.
- DUT outputs and architectural state must have observable proof paths.
- Protocol legality belongs in `assume`; DUT reaction belongs in `guarantee`.
- Unclassified ambiguity remains draft knowledge, not implementation authority.

## Why This Exists

Without boundary modeling, agents tend to write plausible RTL:

```text
gpio_i is just a wire, so read it directly.
```

OAG should instead ask:

```text
Is gpio_i synchronous? If not, what crossing pattern is allowed?
What does the architectural DATA_IN register promise to firmware?
What evidence proves the synchronizer and read semantics?
```

That is the difference between code generation and design-truth preserving IP
development.
