# cortex_m7_systick v1 — Frozen Interface (locked design truth)

This interface is **locked design truth** derived from `ontology/contracts.yaml`,
`ontology/decision_matrix.yaml`, and `req/locked_truth.md`. The RTL/TB agents may
choose internal structure but MUST NOT change ports, the register/field map,
reset values, timing, or protocol semantics.

Source: ARMv7-M ARM (DDI0403) §B3.3; Cortex-M7 TRM (DDI0489) §3.2.

## Clock / reset (DEC_RESET_STRATEGY, DEC_CLOCK_CDC)

| Port | Dir | Width | Meaning |
|------|-----|-------|---------|
| `clk` | in | 1 | Processor clock (FCLK). The single SysTick clock domain in v1 (NOREF=1). |
| `rst_n` | in | 1 | Active-low reset, **asynchronous assert / synchronous deassert** (2-FF deassertion synchronizer). |

## APB-lite CSR (DEC_CSR_BUS_PROFILE — word-only)

| Port | Dir | Width | Meaning |
|------|-----|-------|---------|
| `psel` | in | 1 | APB select |
| `penable` | in | 1 | APB enable (access phase) |
| `pwrite` | in | 1 | 1=write, 0=read |
| `paddr` | in | 8 | byte address; decode on `paddr[3:2]` (word offset) |
| `pwdata` | in | 32 | write data (word-only) |
| `prdata` | out | 32 | read data (combinational) |
| `pready` | out | 1 | tied high (zero-wait) |

Sub-word (byte/halfword) access is **unsupported / UNPREDICTABLE** (word-only).

## Tick interrupt request (DEC_EXC_BOUNDARY)

| Port | Dir | Width | Meaning |
|------|-----|-------|---------|
| `tick_irq` | out | 1 | **single-cycle pulse** asserted on a natural counter 1→0 transition when `TICKINT=1`. SCB/NVIC own the pending latch/priority/vectoring (OUT of scope). Never pulses for a CVR-write-to-zero. |

## CALIB tie-off (DEC_CALIB_STRATEGY)

| Param | Default | Meaning |
|-------|---------|---------|
| `CFGSTCALIB` | `26'h3000000` | {NOREF=1, SKEW=1, TENMS[23:0]=0} → `SYST_CALIB = 0xC0000000`. Integrator tie-off; not architectural truth. |

`NOREF = CFGSTCALIB[25]`, `SKEW = CFGSTCALIB[24]`, `TENMS = CFGSTCALIB[23:0]`.
With `NOREF=1`, `SYST_CSR.CLKSOURCE` is forced to 1 and is unclearable.

## Register map (local word offsets; architectural SCS base 0xE000E010)

| Offset | Name | Access | Fields |
|--------|------|--------|--------|
| 0x00 | SYST_CSR | RW | ENABLE[0], TICKINT[1], CLKSOURCE[2] (forced 1 read-only when NOREF=1), COUNTFLAG[16] RO. Other bits reserved RAZ/WI. |
| 0x04 | SYST_RVR | RW | RELOAD[23:0]; [31:24] RAZ/WI. |
| 0x08 | SYST_CVR | RW | CURRENT[23:0] read = live count; **any write clears CURRENT and COUNTFLAG, no exception, reload next clock**; [31:24] RAZ. |
| 0x0C | SYST_CALIB | RO | TENMS[23:0], reserved[29:24]=0, SKEW[30], NOREF[31] from `CFGSTCALIB`. Writes ignored. |

## Counter behavior (locked)

- ENABLE=1: 24-bit counter decrements once per `clk`. On 1→0: set COUNTFLAG; if TICKINT=1 pulse `tick_irq`; reload CURRENT←RELOAD on the **next** clock. Period = RELOAD+1 clocks; CURRENT=0 visible exactly one cycle.
- ENABLE=0: counter frozen (CURRENT and COUNTFLAG retained); re-enable resumes from held value (reload only on wrap-through-0 or after a CVR write).
- RELOAD=0: legal-but-inert — counter loads 0 and holds 0; no 1→0 event; never wraps to 0xFFFFFF.
- COUNTFLAG[16]: set on 1→0; cleared **only** by a functional SYST_CSR read or any SYST_CVR write (not by CSR/RVR writes). (v1: no debug interface — all reads are functional reads.)
- Reset: SYST_CSR = 0x00000000 (CLKSOURCE reads 1 under NOREF=1); SYST_RVR/SYST_CVR power-on UNKNOWN (firmware programs RVR then CVR before ENABLE).

## RTL dialect

OAG SV-lite: Verilog-2001 baseline + `logic` + static `generate`. No `always_ff`/`always_comb`, no procedural loops outside generate. Single clock; `rst_n` async-assert/sync-deassert via a 2-FF synchronizer.
