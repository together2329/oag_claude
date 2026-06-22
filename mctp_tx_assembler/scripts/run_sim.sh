#!/usr/bin/env bash
# Reproduce the mctp_tx_assembler cocotb/icarus simulation.
# All generated artifacts land UNDER sim/ so tb/ stays clean:
#   sim/results.xml            cocotb JUnit results
#   sim/scoreboard_events.jsonl  scoreboard_rows.v1 evidence (written by the TB)
#   sim/sim_run.log            full transcript
#   sim/sim_build/             icarus build dir
#
# Tooling: iverilog/vvp (icarus) + cocotb 1.9.2 installed under the system
# python3 (3.9). cocotb-config lives in the per-user Python bin dir; put it on
# PATH so tb/Makefile's `cocotb-config --makefiles` resolves.
set -euo pipefail

IP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_DIR="${IP_DIR}/sim"
TB_DIR="${IP_DIR}/tb"

# cocotb-config is installed at the user Python 3.9 scripts dir on this host.
COCOTB_BIN="${COCOTB_BIN:-$HOME/Library/Python/3.9/bin}"
export PATH="${COCOTB_BIN}:${PATH}"

mkdir -p "${SIM_DIR}"

cd "${TB_DIR}"
PYTHONDONTWRITEBYTECODE=1 \
COCOTB_RESULTS_FILE="${SIM_DIR}/results.xml" \
SIM_BUILD="${SIM_DIR}/sim_build" \
make SIM=icarus 2>&1 | tee "${SIM_DIR}/sim_run.log"

# Keep tb/ pristine: cocotb may drop a results.xml / __pycache__ into CWD.
rm -f "${TB_DIR}/results.xml"
rm -rf "${TB_DIR}/__pycache__"

echo "Artifacts written under: ${SIM_DIR}"
