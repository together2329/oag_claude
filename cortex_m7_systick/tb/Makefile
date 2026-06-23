# OAG cocotb Makefile for cortex_m7_systick (ARMv7-M / Cortex-M7 SysTick).
# Methodology: directed_table_driven_micro_tb
# (profile simple_leaf_register_peripheral, ontology/tb_methodology.yaml).
# Simulator and framework are TB choices, not design truth.
#
# Run:  make            (uses SIM=icarus by default)
#       make clean
#
# The DUT RTL is produced by the RTL agent at ../rtl/cortex_m7_systick.v.
# The scoreboard writes ../sim/scoreboard_events.jsonl and
# ../sim/scenario_mapping.json at run time.

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../rtl/cortex_m7_systick.v

TOPLEVEL = cortex_m7_systick
MODULE   = test_cortex_m7_systick

# Icarus needs -g2012 only for SV-2012 constructs; the RTL is Verilog-2001
# (OAG SV-lite), so -g2012 is harmless and tolerant of `logic`/generate.
ifeq ($(SIM),icarus)
    COMPILE_ARGS += -g2012
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
