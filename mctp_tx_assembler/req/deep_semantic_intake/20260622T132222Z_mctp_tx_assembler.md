# Deep Semantic Intake: MCTP TX Assembler

- ip: `mctp_tx_assembler`
- profile: `protocol-packet-ip` (TX-corrected; the generic seed was RX-leaning)
- status: draft
- intake corrected from packet-RX framing to message->packet TX-assembly framing

## Source Claim

```text
I need mctp tx assembler
```

## Normalized Intent (draft)

An MCTP **transmit-side assembler**: accept a logical outbound MCTP message
(message body + addressing/tag attributes) and emit one or more MCTP transport
packets. Assembly = fragment the message into payload-bounded packets, mark
`SOM` on the first packet, `EOM` on the last, increment the 2-bit packet
sequence number mod 4, and build each transport header. This is the opposite
data direction from an MCTP RX/reassembler.

## Hidden Implications

- "Assembler" on the TX path means **fragmentation + header construction**, not
  packet reassembly. The seed's RX wording (ingress parser, "AXI write burst =
  PCIe TLP") does not apply.
- The IP must own packetization fields (SOM/EOM/sequence number) while the
  caller likely owns addressing fields (dest EID, source EID, TO, message tag,
  message type/IC) - the ownership split must be explicit.
- Per-packet payload limit (transport unit / MTU) is load-bearing: it sets how
  many packets a message produces and where boundaries fall.
- Single-packet messages are a special case (SOM=1 and EOM=1 on one packet).
- Message-source interface, egress transport binding, tag handling,
  single-vs-multi message interleaving, and error/abort behavior are all
  undefined and must be decided or waived before lock.

## Ambiguity Questions (lock-required)

See `req/ambiguity_register.yaml` (10 open rows). Key ones:

- `AMB_TX_MSG_SOURCE_IF` - how is an outbound message delivered, and what
  attributes travel with it?
- `AMB_TX_EGRESS_BINDING` - egress transport binding and per-packet payload/MTU?
- `AMB_TX_FRAGMENTATION` - max payload, short last packet, zero-length policy?
- `AMB_TX_HEADER_OWNERSHIP` - which header fields does the IP compute vs caller?
- `AMB_TX_TAG_POLICY` - allocate/track tags+TO or pass through; outstanding count?
- `AMB_TX_INTERLEAVE` - single message at a time or multiple in flight?
- `AMB_TX_ERROR_ABORT` - underrun / oversize / egress-error / abort handling?
- `AMB_TX_STATUS_IRQ` - completion/error status, IRQ, counters, CSR interface?
- `AMB_TX_SPEC_SUBSET` - DSP0236 version/subset, fixed header version value?
- `AMB_MCTP_TX_ASSEMBLER_RESET_BOUNDARY` - reset signal/polarity/default state?

## Candidate Lock Decisions

Captured in `ontology/decision_matrix.yaml` as `DT001`..`DT009` (TX-specific),
plus retained generic seeds `D001`..`D004` and `DEC_..._RESET_BOUNDARY`. All are
`unresolved` and `lock_required`. Recommendations are draft guidance only.

## Guardrail

This report is draft intake. It is not locked truth and does not authorize RTL,
TB, validation, gate review, or closure. 14 lock-required decisions are
currently unresolved; scope cannot be locked until they are decided or waived.
