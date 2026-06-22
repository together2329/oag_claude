// ----------------------------------------------------------------------------
// mctp_tx_assembler.v
//
// MCTP TX Assembler v0 (DSP0236 packetizer / message-to-packet fragmenter).
// OAG-generated RTL. Implements the 9 locked contracts CONTRACT_TX_* defined in
// ontology/contracts.yaml against the frozen interface in
// doc/v0_parameters_interface.md. Internal organization is the RTL agent's
// choice; external ports, CSR map, header byte layout, timing, reset values,
// priorities, and protocol semantics are locked design truth and are NOT
// changed here.
//
// Architecture: store-and-forward. A whole message body is buffered into a
// 256-byte RAM and validated (zero-length / oversize / underrun) BEFORE any
// egress byte is produced. This structurally guarantees CONTRACT_TX_ERR's
// "no partial message is ever emitted".
//
// RTL dialect: OAG SV-lite, Verilog-2001 style for iverilog compatibility.
//   - reg/wire only (no SystemVerilog `logic`)
//   - always @(posedge clk or negedge rst_n) for sequential
//   - always @(*) for combinational
//   - no always_ff / always_comb
//   - no procedural for/while/repeat/forever loops outside generate
// Indexed RAM access uses a byte-pointer register instead of procedural loops.
//
// Domain: single clock `clk`; no CDC crossings. `rst_n` is async-assert /
// sync-deassert (a 2-FF reset deassertion synchronizer is provided). RDC:
// no_known_rdc for v0 (see ontology/domain_intent.yaml).
//
// Trace: REQ_TX_* -> OBL_TX_* -> CONTRACT_TX_* -> this RTL.
// ----------------------------------------------------------------------------

module mctp_tx_assembler (
    // Clock / reset (CONTRACT_TX_RESET)
    input  wire        clk,
    input  wire        rst_n,        // active-low, async assert / sync deassert

    // Ingress - message body stream (CONTRACT_TX_INTAKE)
    input  wire        s_valid,
    input  wire [7:0]  s_data,       // body byte; first body byte is MCTP type/IC byte (opaque)
    input  wire        s_last,       // final body byte of the message
    input  wire        s_empty,      // with s_last -> zero-length message
    input  wire        s_abort,      // caller aborts in-flight message -> underrun
    input  wire [7:0]  s_dest_eid,   // latched at message start
    input  wire [2:0]  s_msg_tag,    // latched at message start
    input  wire        s_to,         // tag owner bit, latched at message start
    output wire        s_ready,      // DUT accepts a body beat

    // Egress - MCTP packet stream (CONTRACT_TX_HEADER / FRAGMENT / SOM_EOM / SEQNUM)
    output wire        m_valid,
    output wire [7:0]  m_data,       // 4 header bytes then payload bytes
    output wire        m_sop,        // header byte 0 of each packet
    output wire        m_eop,        // final byte of each packet
    input  wire        m_ready,      // sink ready; low -> stall without losing data

    // CSR - APB-lite, single clock, zero-wait (CONTRACT_TX_STATUS)
    input  wire        psel,
    input  wire        penable,
    input  wire        pwrite,
    input  wire [7:0]  paddr,
    input  wire [31:0] pwdata,
    output reg  [31:0] prdata,
    output wire        pready,       // tie high

    // Interrupts (CONTRACT_TX_STATUS)
    output wire        irq_done,     // 1-cycle pulse on EOM packet egress completion
    output wire        irq_err       // 1-cycle pulse on error event
);

    // ------------------------------------------------------------------
    // Parameters / constants (frozen)
    // ------------------------------------------------------------------
    localparam [3:0]  HDR_VERSION    = 4'h1;   // DSP0236 header version
    localparam        MSG_CAP        = 256;    // internal buffer depth (bytes)
    localparam [8:0]  MSG_CAP_LEN    = 9'd256; // length representation capacity

    // CSR byte addresses (APB-lite). paddr is byte address; decode on [7:2].
    localparam [7:0]  ADDR_CTRL      = 8'h00;
    localparam [7:0]  ADDR_SRC_EID   = 8'h04;
    localparam [7:0]  ADDR_MTU       = 8'h08;
    localparam [7:0]  ADDR_MAX_MSG   = 8'h0C;
    localparam [7:0]  ADDR_STATUS    = 8'h10;
    localparam [7:0]  ADDR_IRQ_EN    = 8'h14;
    localparam [7:0]  ADDR_ERR_FLAGS = 8'h18;
    localparam [7:0]  ADDR_SENT_CNT  = 8'h1C;
    localparam [7:0]  ADDR_DROP_CNT  = 8'h20;

    // FSM states
    localparam [2:0]  ST_IDLE     = 3'd0;
    localparam [2:0]  ST_INTAKE   = 3'd1;
    localparam [2:0]  ST_VALIDATE = 3'd2;
    localparam [2:0]  ST_EMIT_HDR = 3'd3;
    localparam [2:0]  ST_EMIT_PAY = 3'd4;
    localparam [2:0]  ST_ERR      = 3'd5;
    localparam [2:0]  ST_DONE     = 3'd6;

    // ------------------------------------------------------------------
    // Reset deassertion synchronizer (async assert, sync deassert).
    // rst_n is asynchronous; rst_sync_n deasserts synchronously to clk.
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
    // CSR registers
    // ------------------------------------------------------------------
    reg        ctrl_enable;          // CTRL[0]
    reg [7:0]  csr_src_eid;          // SRC_EID[7:0]
    reg [7:0]  csr_mtu;              // MTU[7:0]
    reg [15:0] csr_max_msg;          // MAX_MSG[15:0]
    reg        status_done_latched;  // STATUS[1] W1C
    reg        status_err_latched;   // STATUS[2] W1C
    reg        irq_en_done;          // IRQ_EN[0]
    reg        irq_en_err;           // IRQ_EN[1]
    reg        err_underrun;         // ERR_FLAGS[0] W1C
    reg        err_oversize;         // ERR_FLAGS[1] W1C
    reg        err_zero_len;         // ERR_FLAGS[2] W1C
    reg [31:0] sent_cnt;             // SENT_CNT
    reg [31:0] drop_cnt;             // DROP_CNT

    // ------------------------------------------------------------------
    // Message buffer + datapath state
    // ------------------------------------------------------------------
    reg [7:0]  mem [0:MSG_CAP-1];
    reg [8:0]  wr_ptr;               // bytes buffered so far (0..256)
    reg [8:0]  msg_len;              // captured body length at s_last
    reg [7:0]  rd_ptr;               // egress read pointer into mem (0..255)

    // Latched message attributes (CONTRACT_TX_INTAKE / HEADER)
    reg [7:0]  lat_dest_eid;
    reg [2:0]  lat_msg_tag;
    reg        lat_to;

    // Fragmentation / packet state (CONTRACT_TX_FRAGMENT / SOM_EOM / SEQNUM)
    reg [2:0]  state;
    reg [1:0]  seq;                  // 2-bit sequence number
    reg        som;                  // current packet SOM
    reg        eom;                  // current packet EOM
    reg [8:0]  bytes_remaining;      // body bytes not yet emitted
    reg [8:0]  pay_left;             // payload bytes left in current packet
    reg [1:0]  hdr_idx;              // header byte index 0..3 within a packet

    // ------------------------------------------------------------------
    // Combinational helpers
    // ------------------------------------------------------------------
    // s_ready: accept body beats only when enabled and intake-capable.
    // Stays low while emitting or finishing a message (CONTRACT_TX_SINGLEMSG):
    // a new message cannot start until the cycle after the EOM m_eop completes,
    // which is the cycle the FSM returns to ST_IDLE.
    assign s_ready = ctrl_enable &&
                     ((state == ST_IDLE) || (state == ST_INTAKE));

    // Effective MTU payload bytes for the current packet.
    // mtu_eff is csr_mtu (1..255); guarded to a minimum of 1 to avoid a zero MTU
    // stalling forever (defensive; MAX_MSG/MTU programming is host policy).
    wire [8:0] mtu_eff = (csr_mtu == 8'd0) ? 9'd1 : {1'b0, csr_mtu};

    // Header byte composition for current packet (DSP0236 layout).
    reg [7:0] hdr_byte;
    always @(*) begin
        case (hdr_idx)
            2'd0:    hdr_byte = {4'b0000, HDR_VERSION};           // 8'h01
            2'd1:    hdr_byte = lat_dest_eid;
            2'd2:    hdr_byte = csr_src_eid;
            default: hdr_byte = {som, eom, seq, lat_to, lat_msg_tag}; // byte3
        endcase
    end

    // Egress mux: header bytes first, then payload bytes from mem.
    assign m_sop  = (state == ST_EMIT_HDR) && (hdr_idx == 2'd0);
    // m_eop: final payload byte of the packet (pay_left == 1 on the last byte).
    assign m_eop  = (state == ST_EMIT_PAY) && (pay_left == 9'd1);
    assign m_valid = (state == ST_EMIT_HDR) || (state == ST_EMIT_PAY);
    assign m_data  = (state == ST_EMIT_HDR) ? hdr_byte : mem[rd_ptr];

    // Egress beat completion qualifier (a header/payload byte transfers).
    wire m_beat = m_valid && m_ready;

    assign pready = 1'b1;

    // ------------------------------------------------------------------
    // Interrupt pulses (CONTRACT_TX_STATUS / cycle_rules.tx.status_irq_timing).
    // irq_done pulses the cycle the EOM packet completes on egress.
    // irq_err  pulses the cycle an error event is flagged.
    // ------------------------------------------------------------------
    reg done_event;   // pulses one cycle on EOM emission completion
    reg err_event;    // pulses one cycle on a flagged error
    assign irq_done = done_event && irq_en_done;
    assign irq_err  = err_event  && irq_en_err;

    // ------------------------------------------------------------------
    // CSR write strobe (APB access phase: psel & penable).
    // ------------------------------------------------------------------
    wire csr_wr = psel && penable && pwrite;

    // ------------------------------------------------------------------
    // CSR read data (combinational)
    // ------------------------------------------------------------------
    wire busy_flag = (state != ST_IDLE);
    always @(*) begin
        prdata = 32'h0;
        case (paddr)
            ADDR_CTRL:      prdata = {31'b0, ctrl_enable};
            ADDR_SRC_EID:   prdata = {24'b0, csr_src_eid};
            ADDR_MTU:       prdata = {24'b0, csr_mtu};
            ADDR_MAX_MSG:   prdata = {16'b0, csr_max_msg};
            ADDR_STATUS:    prdata = {29'b0, status_err_latched,
                                             status_done_latched, busy_flag};
            ADDR_IRQ_EN:    prdata = {30'b0, irq_en_err, irq_en_done};
            ADDR_ERR_FLAGS: prdata = {29'b0, err_zero_len, err_oversize,
                                             err_underrun};
            ADDR_SENT_CNT:  prdata = sent_cnt;
            ADDR_DROP_CNT:  prdata = drop_cnt;
            default:        prdata = 32'h0;
        endcase
    end

    // ------------------------------------------------------------------
    // Intake handshake + length / oversize comparison (combinational).
    // wr_ptr/msg_len are <=256; MAX_MSG default 192, programmable up to 16 bits.
    // ------------------------------------------------------------------
    wire        s_beat       = s_valid && s_ready;     // accepted body beat
    wire [8:0]  next_len     = wr_ptr + 9'd1;          // length after this byte
    wire [15:0] max_msg_full = csr_max_msg;
    wire        len_exceeds  = ({7'b0, next_len} > max_msg_full); // after this byte
    wire        cur_exceeds  = ({7'b0, wr_ptr}   > max_msg_full); // already over

    // ------------------------------------------------------------------
    // Main sequential process (single clock, async-assert reset).
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // CONTRACT_TX_RESET: post-reset defaults.
            ctrl_enable         <= 1'b0;
            csr_src_eid         <= 8'h00;
            csr_mtu             <= 8'h40;   // 64
            csr_max_msg         <= 16'h00C0; // 192
            status_done_latched <= 1'b0;
            status_err_latched  <= 1'b0;
            irq_en_done         <= 1'b0;
            irq_en_err          <= 1'b0;
            err_underrun        <= 1'b0;
            err_oversize        <= 1'b0;
            err_zero_len        <= 1'b0;
            sent_cnt            <= 32'd0;
            drop_cnt            <= 32'd0;

            state               <= ST_IDLE;
            wr_ptr              <= 9'd0;
            msg_len             <= 9'd0;
            rd_ptr              <= 8'd0;
            lat_dest_eid        <= 8'h00;
            lat_msg_tag         <= 3'b000;
            lat_to              <= 1'b0;
            seq                 <= 2'b00;
            som                 <= 1'b0;
            eom                 <= 1'b0;
            bytes_remaining     <= 9'd0;
            pay_left            <= 9'd0;
            hdr_idx             <= 2'b00;
            done_event          <= 1'b0;
            err_event           <= 1'b0;
        end else begin
            // Default: interrupt event pulses are single-cycle.
            done_event <= 1'b0;
            err_event  <= 1'b0;

            // ----------------------------------------------------------
            // CSR writes (host). W1C semantics for STATUS/ERR_FLAGS.
            // ----------------------------------------------------------
            if (csr_wr) begin
                case (paddr)
                    ADDR_CTRL:    ctrl_enable <= pwdata[0];
                    ADDR_SRC_EID: csr_src_eid <= pwdata[7:0];
                    ADDR_MTU:     csr_mtu     <= pwdata[7:0];
                    ADDR_MAX_MSG: csr_max_msg <= pwdata[15:0];
                    ADDR_STATUS: begin
                        if (pwdata[1]) status_done_latched <= 1'b0; // W1C
                        if (pwdata[2]) status_err_latched  <= 1'b0; // W1C
                    end
                    ADDR_IRQ_EN: begin
                        irq_en_done <= pwdata[0];
                        irq_en_err  <= pwdata[1];
                    end
                    ADDR_ERR_FLAGS: begin
                        if (pwdata[0]) err_underrun <= 1'b0; // W1C
                        if (pwdata[1]) err_oversize <= 1'b0; // W1C
                        if (pwdata[2]) err_zero_len <= 1'b0; // W1C
                    end
                    default: ; // SENT_CNT/DROP_CNT/STATUS busy are RO
                endcase
            end

            // ----------------------------------------------------------
            // Datapath FSM
            // ----------------------------------------------------------
            case (state)
                // ------------------------------------------------------
                ST_IDLE: begin
                    wr_ptr  <= 9'd0;
                    rd_ptr  <= 8'd0;
                    if (s_beat) begin
                        // Latch attributes from the first accepted beat.
                        lat_dest_eid <= s_dest_eid;
                        lat_msg_tag  <= s_msg_tag;
                        lat_to       <= s_to;

                        if (s_abort) begin
                            // Abort on the very first beat -> underrun.
                            err_underrun <= 1'b1;
                            err_event    <= 1'b1;
                            status_err_latched <= 1'b1;
                            drop_cnt     <= drop_cnt + 32'd1;
                            state        <= ST_IDLE;
                        end else if (s_last && s_empty) begin
                            // Zero-length message -> drop, flag, no emission.
                            err_zero_len <= 1'b1;
                            err_event    <= 1'b1;
                            status_err_latched <= 1'b1;
                            drop_cnt     <= drop_cnt + 32'd1;
                            state        <= ST_IDLE;
                        end else if (s_last && !s_empty) begin
                            // Single-beat (1-byte) complete message.
                            mem[wr_ptr[7:0]] <= s_data;
                            msg_len <= 9'd1;
                            // 1 byte cannot exceed MAX_MSG (>=1); validate anyway.
                            if (16'd1 > max_msg_full) begin
                                err_oversize <= 1'b1;
                                err_event    <= 1'b1;
                                status_err_latched <= 1'b1;
                                drop_cnt     <= drop_cnt + 32'd1;
                                state        <= ST_IDLE;
                            end else begin
                                state <= ST_VALIDATE;
                            end
                        end else begin
                            // First body byte of a multi-beat message.
                            mem[wr_ptr[7:0]] <= s_data;
                            wr_ptr <= 9'd1;
                            if (len_exceeds) begin
                                // length already exceeds MAX_MSG after 1 byte
                                err_oversize <= 1'b1;
                                err_event    <= 1'b1;
                                status_err_latched <= 1'b1;
                                drop_cnt     <= drop_cnt + 32'd1;
                                state        <= ST_IDLE;
                            end else begin
                                state <= ST_INTAKE;
                            end
                        end
                    end
                end

                // ------------------------------------------------------
                ST_INTAKE: begin
                    if (s_beat) begin
                        if (s_abort) begin
                            // Mid-message abort -> underrun, drop buffered data.
                            err_underrun <= 1'b1;
                            err_event    <= 1'b1;
                            status_err_latched <= 1'b1;
                            drop_cnt     <= drop_cnt + 32'd1;
                            wr_ptr       <= 9'd0;
                            state        <= ST_IDLE;
                        end else if (s_empty && s_last) begin
                            // Trailing empty/last with body already buffered:
                            // finalize at current length (no new byte).
                            msg_len <= wr_ptr;
                            if (cur_exceeds) begin
                                err_oversize <= 1'b1;
                                err_event    <= 1'b1;
                                status_err_latched <= 1'b1;
                                drop_cnt     <= drop_cnt + 32'd1;
                                wr_ptr       <= 9'd0;
                                state        <= ST_IDLE;
                            end else begin
                                state <= ST_VALIDATE;
                            end
                        end else begin
                            // Buffer this body byte.
                            mem[wr_ptr[7:0]] <= s_data;
                            wr_ptr <= next_len;
                            if (len_exceeds) begin
                                // Accepting this byte exceeds MAX_MSG -> oversize.
                                err_oversize <= 1'b1;
                                err_event    <= 1'b1;
                                status_err_latched <= 1'b1;
                                drop_cnt     <= drop_cnt + 32'd1;
                                wr_ptr       <= 9'd0;
                                state        <= ST_IDLE;
                            end else if (s_last) begin
                                msg_len <= next_len;
                                state   <= ST_VALIDATE;
                            end
                        end
                    end
                end

                // ------------------------------------------------------
                // ST_VALIDATE: message buffered and length-valid. Set up the
                // first packet. (Errors already handled during intake.)
                ST_VALIDATE: begin
                    rd_ptr          <= 8'd0;
                    bytes_remaining <= msg_len;
                    seq             <= 2'b00;
                    som             <= 1'b1;
                    eom             <= (msg_len <= mtu_eff);
                    pay_left        <= (msg_len <= mtu_eff) ? msg_len : mtu_eff;
                    hdr_idx         <= 2'b00;
                    state           <= ST_EMIT_HDR;
                end

                // ------------------------------------------------------
                // ST_EMIT_HDR: drive 4 header bytes; advance on m_ready only.
                ST_EMIT_HDR: begin
                    if (m_beat) begin
                        if (hdr_idx == 2'd3) begin
                            state <= ST_EMIT_PAY;
                        end else begin
                            hdr_idx <= hdr_idx + 2'd1;
                        end
                    end
                end

                // ------------------------------------------------------
                // ST_EMIT_PAY: drive payload bytes from mem; advance on m_ready.
                ST_EMIT_PAY: begin
                    if (m_beat) begin
                        rd_ptr <= rd_ptr + 8'd1;
                        if (pay_left == 9'd1) begin
                            // Last byte of this packet just transferred.
                            bytes_remaining <= bytes_remaining - 9'd1;
                            if (eom) begin
                                // EOM packet complete -> message done.
                                done_event          <= 1'b1;
                                status_done_latched <= 1'b1;
                                sent_cnt            <= sent_cnt + 32'd1;
                                state               <= ST_DONE;
                            end else begin
                                // Set up next packet.
                                seq      <= seq + 2'd1; // (+1) mod 4 via 2-bit wrap
                                som      <= 1'b0;
                                hdr_idx  <= 2'b00;
                                // remaining after this byte = bytes_remaining-1
                                if ((bytes_remaining - 9'd1) <= mtu_eff) begin
                                    eom      <= 1'b1;
                                    pay_left <= (bytes_remaining - 9'd1);
                                end else begin
                                    eom      <= 1'b0;
                                    pay_left <= mtu_eff;
                                end
                                state <= ST_EMIT_HDR;
                            end
                        end else begin
                            bytes_remaining <= bytes_remaining - 9'd1;
                            pay_left        <= pay_left - 9'd1;
                        end
                    end
                end

                // ------------------------------------------------------
                // ST_DONE: one cycle after EOM m_eop completes; release to IDLE.
                // This realizes "s_ready stays low until the cycle after the
                // EOM packet completes" (CONTRACT_TX_SINGLEMSG): s_ready is low
                // in ST_DONE and asserts again in ST_IDLE next cycle.
                ST_DONE: begin
                    wr_ptr <= 9'd0;
                    state  <= ST_IDLE;
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule
