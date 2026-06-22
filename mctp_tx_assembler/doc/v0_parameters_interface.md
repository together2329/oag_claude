# MCTP TX Assembler v0 — Parameters & Top Interface (frozen)

Human-approved sub-details (intake open_questions resolved at lock by happygrowth33:
"MTU 64B, header version default, follow recommendation"). This document is the
authoritative interface contract shared by the RTL and TB subagents so the DUT
and testbench agree. It elaborates the locked contracts; it does not change
locked behavior.

## Parameters / constants

| Name | Value | Note |
|---|---|---|
| `HDR_VERSION` | `4'h1` | DSP0236 MCTP header version (fixed) |
| MTU default | `8'd64` | CSR-programmable max packet payload (bytes) |
| MAX_MSG default | `16'd192` | CSR-programmable oversize threshold (max body bytes) |
| `MSG_CAP` | `256` | localparam: internal message buffer depth (bytes); MAX_MSG <= MSG_CAP |
| datapath | byte-serial (8-bit) | ingress body and egress packet are byte streams |

## Module: `mctp_tx_assembler`

### Clock / reset
- `input clk`
- `input rst_n` — active-low, **asynchronous assert, synchronous deassert** (REQ_TX_RESET)

### Ingress — message body stream (byte-serial)
- `input  s_valid`
- `input  [7:0] s_data`     — body byte; the **first** body byte is the MCTP message-type/IC byte (caller-supplied, IP does not interpret it)
- `input  s_last`           — final body byte of the message
- `input  s_empty`          — with `s_last`, marks a **zero-length** message (no body byte this beat)
- `input  s_abort`          — caller aborts the in-flight message (=> underrun)
- `input  [7:0] s_dest_eid` — attribute, stable on the first accepted beat; latched at message start
- `input  [2:0] s_msg_tag`  — attribute, latched at message start
- `input  s_to`             — attribute (tag owner bit), latched at message start
- `output s_ready`          — DUT accepts a body beat (low while busy emitting / not enabled)

A beat transfers when `s_valid & s_ready` (cycle_rules.tx.intake_handshake).

### Egress — MCTP packet stream (byte-serial, header in-band, DSP0236 layout)
- `output m_valid`
- `output [7:0] m_data`     — packet byte: 4 header bytes then payload bytes
- `output m_sop`            — asserted on header byte 0 of each packet
- `output m_eop`            — asserted on the final byte of each packet
- `input  m_ready`          — sink ready; when low, DUT stalls without losing data (no byte dropped)

A beat transfers when `m_valid & m_ready`.

**Per-packet header bytes (emitted first, in order):**
- byte0 = `{4'b0000, HDR_VERSION}`  → `8'h01`
- byte1 = `dest_eid[7:0]`
- byte2 = `src_eid[7:0]` (from CSR SRC_EID)
- byte3 = `{SOM, EOM, SEQ[1:0], TO, MSG_TAG[2:0]}`  (bit7=SOM, bit6=EOM, bit5:4=SEQ, bit3=TO, bit2:0=MSG_TAG)
- then payload bytes (1..MTU). The first payload byte of the **first** packet is the message-type/IC byte.

### CSR — APB-lite, single clock (`clk`/`rst_n`), zero-wait
- `input  psel, penable, pwrite`
- `input  [7:0]  paddr`
- `input  [31:0] pwdata`
- `output [31:0] prdata`
- `output pready` (tie high)

| Addr | Reg | Bits | Reset | Access |
|---|---|---|---|---|
| 0x00 | CTRL | [0] enable | 0 | RW |
| 0x04 | SRC_EID | [7:0] | 0x00 | RW |
| 0x08 | MTU | [7:0] | 0x40 (64) | RW |
| 0x0C | MAX_MSG | [15:0] | 0x00C0 (192) | RW |
| 0x10 | STATUS | [0] busy(RO), [1] done_latched(W1C), [2] err_latched(W1C) | 0 | RO/W1C |
| 0x14 | IRQ_EN | [0] done_en, [1] err_en | 0 | RW |
| 0x18 | ERR_FLAGS | [0] underrun, [1] oversize, [2] zero_len (W1C) | 0 | RO/W1C |
| 0x1C | SENT_CNT | [31:0] | 0 | RO |
| 0x20 | DROP_CNT | [31:0] | 0 | RO |

### Interrupts
- `output irq_done` — asserted (1-cycle pulse) when a message's EOM packet has been accepted on egress and done_en=1
- `output irq_err`  — asserted (1-cycle pulse) when an error is flagged and err_en=1

## Behavior (store-and-forward; satisfies the 9 locked contracts)

Recommended architecture (internal structure is the RTL agent's choice **provided
the contracts hold**, especially "no partial message emission"):

1. **Intake** (CONTRACT_TX_INTAKE): when `enable=1` and idle, latch attributes on the
   first accepted beat; accept body bytes into the buffer until `s_last`. Count length.
2. **Reject/error during intake** (CONTRACT_TX_ERR):
   - zero-length (`s_empty & s_last` at start) → set ERR_FLAGS.zero_len, DROP_CNT++, irq_err, emit nothing.
   - oversize (length > MAX_MSG) → set ERR_FLAGS.oversize, DROP_CNT++, irq_err, emit nothing.
   - `s_abort` mid-message → set ERR_FLAGS.underrun, DROP_CNT++, irq_err, emit nothing.
   Because emission starts only after a complete valid message, **no partial message is ever emitted**.
3. **Fragment** (CONTRACT_TX_FRAGMENT): packet_count = ceil(len/MTU); each payload ≤ MTU; only the final packet may be short; single packet if len ≤ MTU.
4. **SOM/EOM** (CONTRACT_TX_SOM_EOM): SOM on first packet, EOM on last; single-packet → both.
5. **SEQ** (CONTRACT_TX_SEQNUM): SEQ=0 on SOM packet, (+1) mod 4 each subsequent packet.
6. **Header** (CONTRACT_TX_HEADER): compose bytes per layout above; body bytes preserve input order.
7. **Single message** (CONTRACT_TX_SINGLEMSG): `s_ready` for a new message stays low until the cycle after the EOM packet's `m_eop` beat completes; packets never interleave.
8. **Backpressure** (CONTRACT_TX_ERR): when `m_ready=0`, hold `m_valid`/`m_data` (no byte lost).
9. **Status** (CONTRACT_TX_STATUS): SENT_CNT++ and irq_done on EOM emission; counters/status via CSR.
10. **Reset** (CONTRACT_TX_RESET): async-assert/sync-deassert; post-reset busy=0, seq=0, counters=0, CSR at reset values.

## Domain (single clock)
One clock domain (`clk`); no CDC crossings. Reset `rst_n` async-assert/sync-deassert
is the only reset-domain consideration (RDC: no_known_rdc for v0). RTL records this
as `domain_crossing_notes`.

## RTL dialect
OAG SV-lite, **Verilog-2001 style** for iverilog compatibility: `reg`/`wire`,
`always @(posedge clk or negedge rst_n)`, no `always_ff`/`always_comb`, no
procedural loops outside `generate`. Single RTL file `rtl/mctp_tx_assembler.v`
(structure_profile: small_leaf_single_file).
