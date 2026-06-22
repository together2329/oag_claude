# mctp_tx_assembler Verification

## Contracts
- `CONTRACT_MCTP_TX_ASSEMBLER_SIM_SCOREBOARD`

## Scoreboard Evidence
- TB implementation is free: Verilog, SystemVerilog, UVM, Python, cocotb, or simulator adapter.
- The submitted evidence row schema is fixed: `ontology/evidence/scoreboard_rows.v1.yaml`.

## Methodology
- Methodology intent lives in `ontology/tb_methodology.yaml`.
- The TB should choose the smallest sufficient method for the IP profile.
- Random evidence needs constraints and coverage goals before closure.
- Failed rows do not count toward closure coverage.

## Evidence
- sim/results.xml
- sim/scoreboard_events.jsonl
