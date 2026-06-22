# OAG cocotb Makefile for mctp_tx_assembler (TX side).
# Methodology: directed_table_driven_micro_tb (profile simple_leaf_apb_peripheral).
# Simulator and framework are TB choices, not design truth.
#
# Run:  make            (uses SIM=icarus by default)
#       make clean
#
# The DUT RTL is produced by the RTL agent at ../rtl/mctp_tx_assembler.v.
# The scoreboard writes ../sim/scoreboard_events.jsonl at run time.

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../rtl/mctp_tx_assembler.v

TOPLEVEL = mctp_tx_assembler
MODULE   = test_mctp_tx_assembler

# Icarus needs -g2012 only for SV-2012 constructs; the RTL is Verilog-2001
# (OAG SV-lite), so -g2012 is harmless and tolerant of `logic`/generate.
ifeq ($(SIM),icarus)
    COMPILE_ARGS += -g2012
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
