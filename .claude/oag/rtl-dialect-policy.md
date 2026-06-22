# OAG RTL Dialect Policy

OAG-generated RTL should default to a small, portable synthesizable dialect.
This keeps LLM-generated RTL predictable for lint, synthesis, and review.

## Default Dialect

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
```

## Allowed By Default

- Verilog-2001 module structure.
- `parameter` and `localparam`.
- `input`, `output`, `inout`.
- `wire`, `reg`, and `logic`.
- `always @(*)` and edge-triggered `always @(posedge/negedge ...)`.
- `assign`, `case`, `if`, ternary expressions.
- `generate`, `genvar`, and `for` inside generate blocks.

## Disallowed By Default

- `always_ff` and `always_comb`.
- `typedef`, `enum`, `struct`, `interface`, `package`, `class`.
- assertions, covergroups, DPI, randomization.
- procedural `for`, `while`, `repeat`, or `forever` loops outside generate.
- manual clock gating unless a policy explicitly allows it.
- behavioral delays in synthesizable RTL.

The dialect can be widened by explicit policy, but widening the dialect does
not weaken behavior, cycle, PPA, or evidence obligations.

