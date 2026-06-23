// ----------------------------------------------------------------------------
// cortex_m7_systick.v
//
// ARMv7-M / Cortex-M7 SysTick 24-bit system timer (v1, single-clock).
// OAG-generated RTL. Implements the 12 locked contracts CONTRACT_SYST_* defined
// in ontology/contracts.yaml against the frozen interface in
// doc/v1_interface.md. Internal organization is the RTL agent's choice; external
// ports, register/field map, reset values, timing, and protocol semantics are
// locked design truth and are NOT changed here.
//
// Source authority: ARMv7-M ARM (DDI0403) B3.3; Cortex-M7 TRM (DDI0489) 3.2.
//
// Behavior model refs implemented (behavior_model.syst.*):
//   regmap, count, reload, reload_zero, cvr, countflag, tickint, clksource,
//   reset, disable, boundary.
// Cycle rule refs implemented (cycle_rules.syst.*):
//   access, period, cvr_reload, tick_timing, reset_release, boundary.
//
// Architecture: a single 24-bit down-counter plus a small APB-lite CSR block.
// The simplest implementation that satisfies the contract for a simple_leaf
// peripheral: zero-wait combinational read, explicit register write enables,
// flat paddr[3:2] decode, no pipeline. The counter register bank is the only
// notable datapath; there is no global combinational feedback and no manual
// clock gating (enable is a synchronous decrement qualifier inferred by synth).
//
// RTL dialect: OAG SV-lite, Verilog-2001 style for iverilog/verilator.
//   - reg/wire only (no SystemVerilog `logic`)
//   - always @(posedge clk or negedge rst_sync_n) for sequential
//   - always @(*) for combinational
//   - no always_ff / always_comb
//   - no procedural for/while/repeat/forever loops outside generate
//
// Domain: single clock `clk` (FCLK; NOREF=1). No CDC crossings in v1. `rst_n`
// is async-assert / sync-deassert via a 2-FF reset-deassertion synchronizer.
// RDC: no_known_rdc (single reset domain RST_MAIN). See domain_intent.yaml.
//
// Trace: REQ_SYST_* -> OBL_SYST_* -> CONTRACT_SYST_* -> this RTL.
// ----------------------------------------------------------------------------

module cortex_m7_systick #(
    // CALIB tie-off (DEC_CALIB_STRATEGY / CONTRACT_SYST_CLKSOURCE).
    // {NOREF=1, SKEW=1, TENMS[23:0]=0} -> SYST_CALIB = 0xC0000000.
    //   NOREF = CFGSTCALIB[25], SKEW = CFGSTCALIB[24], TENMS = CFGSTCALIB[23:0].
    parameter [25:0] CFGSTCALIB = 26'h3000000
) (
    // Clock / reset (CONTRACT_SYST_RESET)
    input  wire        clk,      // processor clock (FCLK); single SysTick domain
    input  wire        rst_n,    // active-low, async assert / sync deassert

    // APB-lite CSR (CONTRACT_SYST_REGMAP) - word-only, zero-wait
    input  wire        psel,
    input  wire        penable,
    input  wire        pwrite,
    // paddr is an 8-bit APB byte address (frozen interface). Word-only register
    // decode uses paddr[3:2] only (4 word registers at 0x0/0x4/0x8/0xC); the
    // remaining bits are intentionally not used for selection. Waive only this
    // signal's unused-bits warning; the port width is fixed by contract.
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire [7:0]  paddr,    // byte address; decode on paddr[3:2]
    /* verilator lint_on UNUSEDSIGNAL */
    // pwdata is a 32-bit APB bus (frozen interface). The written fields use only
    // the low bits (ENABLE/TICKINT/CLKSOURCE at [2:0], RELOAD/CURRENT at [23:0]);
    // pwdata[31:24] (and CSR upper bits) are reserved RAZ/WI and not stored. Waive
    // only this signal's unused-bits warning; the port width is fixed by contract.
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire [31:0] pwdata,
    /* verilator lint_on UNUSEDSIGNAL */
    output reg  [31:0] prdata,   // combinational read data
    output wire        pready,   // tied high (zero-wait)

    // Qualified SysTick set-pending request (CONTRACT_SYST_TICKINT / BOUNDARY)
    output wire        tick_irq  // single-cycle pulse on natural 1->0 & TICKINT=1
);

    // ------------------------------------------------------------------
    // Register word-offset decode (CONTRACT_SYST_REGMAP / cycle_rules.syst.access)
    // SCS base 0xE000E010; local offsets 0x0/0x4/0x8/0xC via paddr[3:2].
    // ------------------------------------------------------------------
    localparam [1:0] OFF_CSR   = 2'b00; // SYST_CSR   (0x0)
    localparam [1:0] OFF_RVR   = 2'b01; // SYST_RVR   (0x4)
    localparam [1:0] OFF_CVR   = 2'b10; // SYST_CVR   (0x8)
    localparam [1:0] OFF_CALIB = 2'b11; // SYST_CALIB (0xC)

    wire [1:0] reg_sel = paddr[3:2];

    // CALIB fields (read-only integrator tie-off).
    wire        calib_noref = CFGSTCALIB[25];
    wire        calib_skew  = CFGSTCALIB[24];
    wire [23:0] calib_tenms = CFGSTCALIB[23:0];
    // SYST_CALIB = {NOREF, SKEW, reserved[29:24]=0, TENMS[23:0]}.
    wire [31:0] calib_word  = {calib_noref, calib_skew, 6'b0, calib_tenms};

    // NOREF=1 forces CLKSOURCE read-as-1 and unclearable (CONTRACT_SYST_CLKSOURCE).
    wire        clksource_rd = calib_noref;

    // ------------------------------------------------------------------
    // Reset deassertion synchronizer (CONTRACT_SYST_RESET: async assert,
    // SYNC deassert / cycle_rules.syst.reset_release). The external pin rst_n
    // feeds ONLY this 2-FF synchronizer; rst_sync_n is the single internal
    // active-low reset that drives all functional sequential logic below. When
    // rst_n drops, rst_sync_n asserts immediately (async). When rst_n rises,
    // rst_sync_n deasserts only after the 2-FF pipeline fills (synchronous to clk).
    // ------------------------------------------------------------------
    reg rst_meta, rst_sync_n;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rst_meta   <= 1'b0;
            rst_sync_n <= 1'b0;
        end else begin
            rst_meta   <= 1'b1;
            rst_sync_n <= rst_meta;
        end
    end

    // ------------------------------------------------------------------
    // Architectural register state.
    //   SYST_CSR : ENABLE, TICKINT (RW); CLKSOURCE forced (RO); COUNTFLAG (RO)
    //   SYST_RVR : RELOAD[23:0]
    //   SYST_CVR : CURRENT[23:0]
    // CLKSOURCE is not stored (forced from NOREF). Reserved bits store nothing.
    // ------------------------------------------------------------------
    reg        csr_enable;   // SYST_CSR[0]  RW
    reg        csr_tickint;  // SYST_CSR[1]  RW
    reg        countflag;    // SYST_CSR[16] RO, set on 1->0
    reg [23:0] rvr_reload;   // SYST_RVR[23:0]
    reg [23:0] cvr_current;  // SYST_CVR[23:0] live count
    // cvr_reload_pending: a CVR write occurred; on the next enabled clock the
    // counter reloads from RVR (CONTRACT_SYST_CVR / cycle_rules.syst.cvr_reload).
    reg        cvr_reload_pending;

    // ------------------------------------------------------------------
    // APB access-phase strobes (CONTRACT_SYST_REGMAP / cycle_rules.syst.access).
    // A transfer completes in the access phase: psel & penable, pready=1.
    // ------------------------------------------------------------------
    wire apb_access  = psel && penable;
    wire apb_write   = apb_access &&  pwrite;
    wire apb_read    = apb_access && !pwrite;

    wire wr_csr  = apb_write && (reg_sel == OFF_CSR);
    wire wr_rvr  = apb_write && (reg_sel == OFF_RVR);
    wire wr_cvr  = apb_write && (reg_sel == OFF_CVR); // any CVR write: data ignored
    // CALIB is RO; writes ignored (no enable).

    // Functional SYST_CSR read clears COUNTFLAG (v1: all reads are functional).
    wire rd_csr  = apb_read  && (reg_sel == OFF_CSR);

    assign pready = 1'b1;

    // ------------------------------------------------------------------
    // Counter next-state combinational logic
    // (CONTRACT_SYST_COUNT / PERIOD / RELOAD / RELOAD_ZERO / CVR / DISABLE).
    //
    // Priority of effects on CURRENT for the NEXT clock:
    //   1. CVR write          -> clear to 0 now, reload from RVR next clock
    //   2. pending CVR reload  -> load RVR (deferred from a prior CVR write)
    //   3. natural 1->0 wrap   -> load RVR (period = RELOAD+1)
    //   4. enabled decrement   -> CURRENT - 1
    //   5. otherwise (disabled or frozen) -> hold (CONTRACT_SYST_DISABLE)
    //
    // RELOAD=0 is legal-but-inert: loading RVR yields 0, holding 0 produces no
    // further 1->0 event and never wraps to 0xFFFFFF (CONTRACT_SYST_RELOAD_ZERO).
    // ------------------------------------------------------------------

    // A natural wrap event: enabled, not just CVR-cleared, current value is 1
    // transitioning to 0 this clock. (When CURRENT=1 and we decrement, it becomes
    // 0 and is visible for exactly one cycle before reload on the next clock.)
    // The wrap-RELOAD action happens the clock AFTER CURRENT reaches 0, so we
    // detect "CURRENT==0 while enabled" to trigger the reload, and detect the
    // "1->0" edge to set COUNTFLAG / pulse the tick. Implemented below:

    // Event used to set COUNTFLAG and qualify tick_irq: a true 1->0 decrement.
    // Only when enabled, not a CVR-write cycle, and current==1 (so next==0).
    wire natural_to_zero = csr_enable && !wr_cvr && (cvr_current == 24'd1);

    // Reload trigger: when enabled and the count is at 0 (the one cycle CURRENT=0
    // is visible), load RVR on the next clock -> period = RELOAD+1. With RELOAD=0
    // this loads 0 again and holds 0; no new 1->0 edge is generated because
    // natural_to_zero requires current==1, never reached from a held 0.
    wire wrap_reload = csr_enable && !wr_cvr && (cvr_current == 24'd0);

    reg [23:0] cvr_next;
    always @(*) begin
        if (wr_cvr) begin
            // CONTRACT_SYST_CVR: any write clears CURRENT now; reload deferred.
            cvr_next = 24'd0;
        end else if (cvr_reload_pending) begin
            // Deferred reload after a prior CVR write.
            cvr_next = rvr_reload;
        end else if (wrap_reload) begin
            // Natural wrap-through-0 reload (period = RELOAD+1).
            cvr_next = rvr_reload;
        end else if (csr_enable) begin
            // Enabled decrement.
            cvr_next = cvr_current - 24'd1;
        end else begin
            // Disabled / frozen: hold (CONTRACT_SYST_DISABLE).
            cvr_next = cvr_current;
        end
    end

    // COUNTFLAG next-state (CONTRACT_SYST_COUNTFLAG):
    //   set on natural 1->0; cleared by a functional CSR read or any CVR write;
    //   NOT cleared by CSR/RVR writes. Set takes precedence over clear-by-read so
    //   a wrap coincident with a CSR read is still reported (read returns 1) and
    //   then cleared.
    reg countflag_next;
    always @(*) begin
        countflag_next = countflag;
        if (rd_csr || wr_cvr) countflag_next = 1'b0; // clear sources
        if (natural_to_zero)  countflag_next = 1'b1; // set wins on coincidence
    end

    // tick_irq: single-cycle pulse on a NATURAL 1->0 with TICKINT=1. Never for a
    // CVR-write-to-zero (natural_to_zero already excludes wr_cvr) and never when
    // TICKINT=0 (CONTRACT_SYST_TICKINT / cycle_rules.syst.tick_timing).
    assign tick_irq = natural_to_zero && csr_tickint;

    // ------------------------------------------------------------------
    // Sequential update. Driven by the synchronized reset rst_sync_n
    // (async assert / sync deassert) per CONTRACT_SYST_RESET; the raw pin rst_n
    // only feeds the synchronizer above.
    //
    // Reset values (CONTRACT_SYST_RESET): SYST_CSR = 0x00000000
    //   (ENABLE=TICKINT=COUNTFLAG=0; CLKSOURCE reads 1 via NOREF, not stored).
    // RVR/CVR are architecturally UNKNOWN at power-on; reset to 0 here as an
    // IP-specific superset for X-prop cleanliness (recorded as IP choice, not
    // ARM truth). Firmware programs RVR then CVR before ENABLE.
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_sync_n) begin
        if (!rst_sync_n) begin
            csr_enable         <= 1'b0;
            csr_tickint        <= 1'b0;
            countflag          <= 1'b0;
            rvr_reload         <= 24'd0;
            cvr_current        <= 24'd0;
            cvr_reload_pending <= 1'b0;
        end else begin
            // --- SYST_CSR writes: ENABLE/TICKINT only; CLKSOURCE & COUNTFLAG are
            //     unaffected by a CSR write (COUNTFLAG is not cleared by writes). ---
            if (wr_csr) begin
                csr_enable  <= pwdata[0];
                csr_tickint <= pwdata[1];
                // pwdata[2] (CLKSOURCE) ignored: forced by NOREF.
                // pwdata[16] (COUNTFLAG) is RO; CSR writes never clear it.
            end

            // --- SYST_RVR writes: RELOAD[23:0]; does NOT reload CVR now
            //     (applies at the next wrap) and does NOT clear COUNTFLAG. ---
            if (wr_rvr) begin
                rvr_reload <= pwdata[23:0];
            end

            // --- COUNTFLAG ---
            countflag <= countflag_next;

            // --- SYST_CVR / counter ---
            cvr_current <= cvr_next;

            // --- CVR-write deferred-reload bookkeeping
            //     (cycle_rules.syst.cvr_reload): a CVR write clears now and sets
            //     pending; the pending reload consumes on the next clock. ---
            if (wr_cvr) begin
                cvr_reload_pending <= 1'b1;
            end else if (cvr_reload_pending) begin
                cvr_reload_pending <= 1'b0;
            end
        end
    end

    // ------------------------------------------------------------------
    // Combinational read data (CONTRACT_SYST_REGMAP / cycle_rules.syst.access).
    // Word-only, zero-wait. Reserved bits read as zero (RAZ).
    //   SYST_CSR : {COUNTFLAG@16, CLKSOURCE@2, TICKINT@1, ENABLE@0}
    //   SYST_RVR : {RELOAD[23:0]}        (RVR[31:24] RAZ)
    //   SYST_CVR : {CURRENT[23:0]} live  (CVR[31:24] RAZ)
    //   SYST_CALIB: {NOREF, SKEW, 0, TENMS}
    //
    // The CSR COUNTFLAG read value reflects a same-cycle natural 1->0 set so a
    // wrap coincident with the read is reported (and then cleared next clock).
    // ------------------------------------------------------------------
    wire countflag_rd = countflag | natural_to_zero;

    always @(*) begin
        case (reg_sel)
            OFF_CSR:   prdata = {15'b0, countflag_rd,           // [16] COUNTFLAG
                                 13'b0, clksource_rd,           // [2]  CLKSOURCE
                                 csr_tickint, csr_enable};      // [1:0]
            OFF_RVR:   prdata = {8'b0, rvr_reload};             // RELOAD[23:0]
            OFF_CVR:   prdata = {8'b0, cvr_current};            // CURRENT[23:0]
            OFF_CALIB: prdata = calib_word;
            default:   prdata = 32'b0;
        endcase
    end

endmodule
