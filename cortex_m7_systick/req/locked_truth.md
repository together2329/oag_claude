# cortex_m7_systick — Proposed Lock Scope (DRAFT, awaiting human lock)

**IP**: ARMv7-M / Cortex-M7 **SysTick** 24-bit system timer
**Source authority**: ARMv7-M Architecture Reference Manual (ARM DDI0403) §B3.3; Cortex-M7 TRM (ARM DDI0489) §3.2. All implementation-defined values are carried as ambiguities/decisions, never invented as truth.

## v1 Scope (recommended)

The IP implements the four SysTick registers and the counter behavior as a single
synchronous leaf peripheral:

- **SYST_CSR** (0xE000E010, RW): ENABLE[0], TICKINT[1], CLKSOURCE[2], COUNTFLAG[16]
- **SYST_RVR** (0xE000E014, RW): RELOAD[23:0]
- **SYST_CVR** (0xE000E018, RW): CURRENT[23:0], any write clears CVR+COUNTFLAG, no exception
- **SYST_CALIB** (0xE000E01C, RO): TENMS[23:0], SKEW[30], NOREF[31] (integrator tie-off)
- 24-bit down-counter: decrement when ENABLE=1, 1→0 sets COUNTFLAG, reload from RVR next clock, period = RELOAD+1
- RELOAD=0 legal-but-inert; CVR-write side effects; init sequence; disable-freeze; reserved-bit policy
- A single qualified **tick interrupt request** output (1→0 ∧ TICKINT=1)

**IN scope**: registers + 24-bit counter + wrap/COUNTFLAG + tick request output.
**OUT of scope (external boundary)**: SCB ICSR PENDSTSET/PENDSTCLR, the pending latch,
priority, preemption, vectoring, vector-table entry 15 (SCB/NVIC own these).

## Requirements / atoms / decisions

- 27 requirements (structural / interface / behavioral / temporal / reset) — see `ontology/requirements.yaml`
- 25 source claims (citation-backed) — see `req/source_claims.yaml`
- 24 ambiguities (all implementation-defined items) — see `req/ambiguity_register.yaml`
- 9 decisions (8 lock-required) — see `ontology/decision_matrix.yaml`

## Lock-required decisions (recommended defaults, awaiting human decision)

| ID | Decision | Recommended default |
|----|----------|---------------------|
| DEC_CSR_BUS_PROFILE | Register bus | APB-lite slave (word-only, addr[4:2] decode) |
| DEC_CLOCK_CDC | Clock source | **Single-clock v1: NOREF=1, CLKSOURCE forced to processor clock; defer external-refclk CDC to a minor follow-on** |
| DEC_RESET_STRATEGY | Reset | Async active-low assert / sync deassert; SYST_CSR resets 0x00000000 |
| DEC_EXC_BOUNDARY | Exception interface | Single-cycle set-pending pulse on qualified wrap; SCB owns the latch |
| DEC_CALIB_STRATEGY | CALIB values | Integrator tie-off; default NOREF=1, SKEW=1, TENMS=0 (CALIB=0xC0000000) |
| DEC_RELOAD_WIDTH | Counter width | Architectural 24-bit; reserved [31:24] RAZ/WI |
| DEC_COUNTFLAG_SEMANTICS | COUNTFLAG | bit[16] RO, set on 1→0, clear on functional CSR read or any CVR write |
| DEC_CVR_DISABLE_BEHAVIOR | CVR write / disable | CVR-write clear unconditional; disable freezes; no spurious reload on re-enable |

(DEC_DEBUG_HALT_SCOPE is advisory: recommend "no debug-halt qualifier" as an explicit environment assumption for the standalone IP.)

## Lock status

`ontology/scope_lock.json` = **draft**. No RTL, no TB, no closure until a human locks.
