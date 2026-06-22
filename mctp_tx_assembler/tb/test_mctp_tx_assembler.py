"""OAG cocotb testbench for mctp_tx_assembler (TX side).

Methodology: directed_table_driven_micro_tb (profile simple_leaf_apb_peripheral,
see ontology/tb_methodology.yaml). Framework-neutral choice: cocotb + icarus.

EXPECTED-SOURCE POLICY (hard, from tb authoring packet):
    expected values come ONLY from the contract oracle / independent Python
    reference model below, which encodes behavior_model.tx.* and
    cycle_rules.tx.* . Forbidden expected sources: dut_output, rtl_expression,
    post_hoc_simulation, observed DUT behavior.

Roles (kept separate):
    - ReferenceModel : predictor. expected = f(input message + attrs + CSR cfg).
    - Driver         : drives ingress s_* and APB-lite CSR (stimulus only).
    - EgressMonitor  : samples DUT-facing egress (m_valid&m_ready, m_data,
                       m_sop, m_eop) and decodes packets (observation only).
    - Scoreboard     : compares expected vs observed, emits scoreboard_rows.v1.

The DUT interface is the FROZEN one in doc/v0_parameters_interface.md. This TB
is black-box against that interface; RTL internals are irrelevant.
"""

import json
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer


# ---------------------------------------------------------------------------
# Frozen constants from doc/v0_parameters_interface.md
# ---------------------------------------------------------------------------
HDR_VERSION = 0x1            # byte0 = {4'b0000, HDR_VERSION} = 0x01
HDR_BYTE0 = (0x0 << 4) | (HDR_VERSION & 0xF)

# CSR address map (APB-lite, byte addresses)
REG_CTRL = 0x00      # [0] enable
REG_SRC_EID = 0x04   # [7:0]
REG_MTU = 0x08       # [7:0], reset 0x40
REG_MAX_MSG = 0x0C   # [15:0], reset 0x00C0
REG_STATUS = 0x10    # [0] busy RO, [1] done_latched W1C, [2] err_latched W1C
REG_IRQ_EN = 0x14    # [0] done_en, [1] err_en
REG_ERR_FLAGS = 0x18  # [0] underrun, [1] oversize, [2] zero_len (W1C)
REG_SENT_CNT = 0x1C  # [31:0] RO
REG_DROP_CNT = 0x20  # [31:0] RO

DEFAULT_MTU = 64
DEFAULT_MAX_MSG = 192

# Coverage goal ids per verification objective (ontology/verification_plan.yaml).
COV = {
    "SCN_TX_INTAKE": ["COV_TX_INTAKE"],
    "SCN_TX_FRAGMENT": ["COV_TX_FRAGMENT_BOUNDARIES"],
    "SCN_TX_SOM_EOM": ["COV_TX_SOM_EOM"],
    "SCN_TX_SEQNUM": ["COV_TX_SEQNUM_WRAP"],
    "SCN_TX_HEADER": ["COV_TX_HEADER_FIELDS"],
    "SCN_TX_SINGLEMSG": ["COV_TX_SINGLEMSG"],
    "SCN_TX_ERR_BACKPRESSURE": ["COV_TX_ERR_MATRIX"],
    "SCN_TX_ERR_UNDERRUN": ["COV_TX_ERR_MATRIX"],
    "SCN_TX_ERR_OVERSIZE": ["COV_TX_ERR_MATRIX"],
    "SCN_TX_ERR_ZEROLEN": ["COV_TX_ERR_MATRIX"],
    "SCN_TX_STATUS": ["COV_TX_STATUS"],
    "SCN_TX_RESET": ["COV_TX_RESET"],
}

# Contract / objective ids used as goal_id per scenario.
GOAL = {
    "SCN_TX_INTAKE": "CONTRACT_TX_INTAKE",
    "SCN_TX_FRAGMENT": "CONTRACT_TX_FRAGMENT",
    "SCN_TX_SOM_EOM": "CONTRACT_TX_SOM_EOM",
    "SCN_TX_SEQNUM": "CONTRACT_TX_SEQNUM",
    "SCN_TX_HEADER": "CONTRACT_TX_HEADER",
    "SCN_TX_SINGLEMSG": "CONTRACT_TX_SINGLEMSG",
    "SCN_TX_ERR_BACKPRESSURE": "CONTRACT_TX_ERR",
    "SCN_TX_ERR_UNDERRUN": "CONTRACT_TX_ERR",
    "SCN_TX_ERR_OVERSIZE": "CONTRACT_TX_ERR",
    "SCN_TX_ERR_ZEROLEN": "CONTRACT_TX_ERR",
    "SCN_TX_STATUS": "CONTRACT_TX_STATUS",
    "SCN_TX_RESET": "CONTRACT_TX_RESET",
}

# expected_source per scenario, matching req/evidence_plan.yaml.
EXP_SRC = {
    "SCN_TX_INTAKE": {"kind": "behavior_model", "refs": ["behavior_model.tx.intake"]},
    "SCN_TX_FRAGMENT": {"kind": "behavior_model", "refs": ["behavior_model.tx.fragment"]},
    "SCN_TX_SOM_EOM": {"kind": "behavior_model", "refs": ["behavior_model.tx.som_eom"]},
    "SCN_TX_SEQNUM": {"kind": "cycle_rules", "refs": ["cycle_rules.tx.seqnum"]},
    "SCN_TX_HEADER": {"kind": "behavior_model", "refs": ["behavior_model.tx.header"]},
    "SCN_TX_SINGLEMSG": {"kind": "cycle_rules", "refs": ["cycle_rules.tx.singlemsg"]},
    "SCN_TX_ERR_BACKPRESSURE": {"kind": "behavior_model", "refs": ["behavior_model.tx.err"]},
    "SCN_TX_ERR_UNDERRUN": {"kind": "behavior_model", "refs": ["behavior_model.tx.err"]},
    "SCN_TX_ERR_OVERSIZE": {"kind": "behavior_model", "refs": ["behavior_model.tx.err"]},
    "SCN_TX_ERR_ZEROLEN": {"kind": "behavior_model", "refs": ["behavior_model.tx.err"]},
    "SCN_TX_STATUS": {"kind": "behavior_model", "refs": ["behavior_model.tx.status"]},
    "SCN_TX_RESET": {"kind": "behavior_model", "refs": ["behavior_model.tx.reset"]},
}

# scoreboard_row_ref (EVT_TX_*) per scenario, matching req/evidence_plan.yaml
# and contracts.yaml scoreboard_row_refs. Emitted as row "event_id" so the
# closure check can resolve a contract's scoreboard_row_ref. All four error
# scenarios share EVT_TX_ERR (CONTRACT_TX_ERR scoreboard_row_refs: [EVT_TX_ERR]).
EVT = {
    "SCN_TX_INTAKE": "EVT_TX_INTAKE",
    "SCN_TX_FRAGMENT": "EVT_TX_FRAGMENT",
    "SCN_TX_SOM_EOM": "EVT_TX_SOM_EOM",
    "SCN_TX_SEQNUM": "EVT_TX_SEQNUM",
    "SCN_TX_HEADER": "EVT_TX_HEADER",
    "SCN_TX_SINGLEMSG": "EVT_TX_SINGLEMSG",
    "SCN_TX_ERR_BACKPRESSURE": "EVT_TX_ERR",
    "SCN_TX_ERR_UNDERRUN": "EVT_TX_ERR",
    "SCN_TX_ERR_OVERSIZE": "EVT_TX_ERR",
    "SCN_TX_ERR_ZEROLEN": "EVT_TX_ERR",
    "SCN_TX_STATUS": "EVT_TX_STATUS",
    "SCN_TX_RESET": "EVT_TX_RESET",
}

# Top-level (contract_id, obligation_id) per scenario. The closure check
# (TB_CHECK_SCOREBOARD_ROWS_HAVE_CONTRACT_AND_OBLIGATION) reads these directly;
# goal_id is not used for that check. All four error scenarios map to
# CONTRACT_TX_ERR / OBL_TX_ERR.
CONTRACT_OBL = {
    "SCN_TX_INTAKE": ("CONTRACT_TX_INTAKE", "OBL_TX_INTAKE"),
    "SCN_TX_FRAGMENT": ("CONTRACT_TX_FRAGMENT", "OBL_TX_FRAGMENT"),
    "SCN_TX_SOM_EOM": ("CONTRACT_TX_SOM_EOM", "OBL_TX_SOM_EOM"),
    "SCN_TX_SEQNUM": ("CONTRACT_TX_SEQNUM", "OBL_TX_SEQNUM"),
    "SCN_TX_HEADER": ("CONTRACT_TX_HEADER", "OBL_TX_HEADER"),
    "SCN_TX_SINGLEMSG": ("CONTRACT_TX_SINGLEMSG", "OBL_TX_SINGLEMSG"),
    "SCN_TX_ERR_BACKPRESSURE": ("CONTRACT_TX_ERR", "OBL_TX_ERR"),
    "SCN_TX_ERR_UNDERRUN": ("CONTRACT_TX_ERR", "OBL_TX_ERR"),
    "SCN_TX_ERR_OVERSIZE": ("CONTRACT_TX_ERR", "OBL_TX_ERR"),
    "SCN_TX_ERR_ZEROLEN": ("CONTRACT_TX_ERR", "OBL_TX_ERR"),
    "SCN_TX_STATUS": ("CONTRACT_TX_STATUS", "OBL_TX_STATUS"),
    "SCN_TX_RESET": ("CONTRACT_TX_RESET", "OBL_TX_RESET"),
}

# Default DUT-facing observed-source locator for egress/packet rows: the
# monitor samples exactly these signals on m_valid&m_ready.
EGRESS_OBS_SRC = {"kind": "monitor", "signal": "m_valid,m_ready,m_data,m_sop,m_eop"}


# ---------------------------------------------------------------------------
# Independent reference model (PREDICTOR)
# ---------------------------------------------------------------------------
# This computes the expected MCTP packet byte stream and error outcome purely
# from the input message + attributes + CSR configuration, encoding:
#   behavior_model.tx.fragment : packet_count = ceil(len/MTU);
#                                payload[i] = min(MTU, len - i*MTU)
#   behavior_model.tx.som_eom  : SOM=(i==0), EOM=(i==count-1)
#   cycle_rules.tx.seqnum      : seq=0 on SOM else (prev+1) mod 4
#   behavior_model.tx.header   : DSP0236 4-byte header layout + body order
#   behavior_model.tx.err      : zero_len / oversize / underrun -> error,
#                                drop++, no egress packet
# NOTHING here reads the DUT. It is the oracle.

class ExpectedPacket:
    def __init__(self, index, packet_count, dest_eid, src_eid, to, msg_tag,
                 seq, payload):
        self.index = index
        self.som = 1 if index == 0 else 0
        self.eom = 1 if index == packet_count - 1 else 0
        self.seq = seq
        # byte3 = {SOM, EOM, SEQ[1:0], TO, MSG_TAG[2:0]}
        byte3 = ((self.som & 1) << 7) | ((self.eom & 1) << 6) | \
                ((seq & 0x3) << 4) | ((to & 1) << 3) | (msg_tag & 0x7)
        self.header = [HDR_BYTE0, dest_eid & 0xFF, src_eid & 0xFF, byte3]
        self.payload = list(payload)
        self.bytes = self.header + self.payload  # full packet byte stream

    def as_dict(self):
        return {
            "index": self.index,
            "som": self.som,
            "eom": self.eom,
            "seq": self.seq,
            "header": list(self.header),
            "payload": list(self.payload),
            "bytes": list(self.bytes),
        }


class ReferenceModel:
    """Oracle. Given the message and config, predict the expected outcome."""

    def __init__(self, src_eid, mtu, max_msg):
        self.src_eid = src_eid & 0xFF
        self.mtu = mtu
        self.max_msg = max_msg

    def predict(self, body, dest_eid, msg_tag, to,
                zero_len=False, abort=False):
        """Return (error_kind, expected_packets).

        error_kind in {None, 'zero_len', 'oversize', 'underrun'}.
        When error_kind is not None, expected_packets is [] (no partial emit).
        """
        body = list(body)
        # behavior_model.tx.err ordering: zero-length and abort are intake-time
        # outcomes; oversize is a length threshold. A real abort mid-message
        # always yields underrun regardless of length.
        if abort:
            return ("underrun", [])
        if zero_len or len(body) == 0:
            return ("zero_len", [])
        if len(body) > self.max_msg:
            return ("oversize", [])

        # behavior_model.tx.fragment
        n = (len(body) + self.mtu - 1) // self.mtu  # ceil
        packets = []
        seq = 0
        for i in range(n):
            payload = body[i * self.mtu:(i + 1) * self.mtu]
            # cycle_rules.tx.seqnum: seq=0 on SOM (i==0), else (prev+1) mod 4
            this_seq = 0 if i == 0 else (seq + 1) % 4
            seq = this_seq
            packets.append(ExpectedPacket(
                index=i, packet_count=n, dest_eid=dest_eid,
                src_eid=self.src_eid, to=to, msg_tag=msg_tag,
                seq=this_seq, payload=payload))
        return (None, packets)


# ---------------------------------------------------------------------------
# Scoreboard : emits scoreboard_rows.v1 JSONL
# ---------------------------------------------------------------------------
_SIM_DIR = os.path.join(os.path.dirname(__file__), "..", "sim")
_SB_PATH = os.path.join(_SIM_DIR, "scoreboard_events.jsonl")


class Scoreboard:
    """Collects rows in scoreboard_rows.v1 form and writes them on flush.

    A single shared instance appends across all scenarios in one sim run, so
    the file is truncated once at construction.
    """

    _initialized = False

    def __init__(self):
        os.makedirs(_SIM_DIR, exist_ok=True)
        if not Scoreboard._initialized:
            # truncate at first construction in this sim process
            open(_SB_PATH, "w").close()
            Scoreboard._initialized = True
        self.rows = []
        self.fail_count = 0

    def record(self, scenario_id, cycle, stimulus, expected, observed,
               passed, mismatch="", observed_source=None,
               coverage_refs=None):
        if observed_source is None:
            # default: egress monitor with its DUT-facing signal locator
            observed_source = dict(EGRESS_OBS_SRC)
        else:
            # ensure every observed_source carries a DUT-facing signal locator;
            # a bare {"kind": ...} without a locator fails the closure check.
            _locator_keys = ("path", "signal", "signals", "monitor", "wave",
                             "transaction", "assertion")
            if not any(k in observed_source for k in _locator_keys):
                if observed_source.get("kind") == "monitor":
                    observed_source = dict(EGRESS_OBS_SRC)
                else:
                    observed_source = dict(observed_source)
                    observed_source["signal"] = "m_valid,m_ready,m_data,m_sop,m_eop"
        if coverage_refs is None:
            coverage_refs = COV.get(scenario_id, [])
        if not passed and not mismatch:
            mismatch = "expected != observed"
        if passed:
            mismatch = ""  # a passing row must not carry a mismatch (schema rule)
        else:
            # failed rows must not contribute coverage (closure policy); drop
            # any coverage_refs so a failing check cannot count toward closure.
            coverage_refs = []
        contract_id, obligation_id = CONTRACT_OBL.get(
            scenario_id, (GOAL.get(scenario_id, scenario_id), scenario_id))
        row = {
            "goal_id": GOAL.get(scenario_id, scenario_id),
            "event_id": EVT.get(scenario_id, scenario_id),
            "contract_id": contract_id,
            "obligation_id": obligation_id,
            "scenario_id": scenario_id,
            "cycle": int(cycle),
            "stimulus": stimulus,
            "expected": expected,
            "observed": observed,
            "expected_source": EXP_SRC.get(scenario_id, {"kind": "behavior_model"}),
            "observed_source": observed_source,
            "passed": bool(passed),
            "mismatch": mismatch,
            "coverage_refs": coverage_refs,
        }
        self.rows.append(row)
        if not passed:
            self.fail_count += 1
        # append immediately so partial runs still leave evidence on disk
        with open(_SB_PATH, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        return row


# ---------------------------------------------------------------------------
# APB-lite CSR helpers (Driver responsibility: stimulus only)
# ---------------------------------------------------------------------------
async def apb_write(dut, addr, data):
    """Zero-wait APB-lite write (psel, then penable, pready tied high)."""
    await RisingEdge(dut.clk)
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 1
    dut.paddr.value = addr
    dut.pwdata.value = data & 0xFFFFFFFF
    await RisingEdge(dut.clk)
    dut.penable.value = 1
    await RisingEdge(dut.clk)
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0


async def apb_read(dut, addr):
    await RisingEdge(dut.clk)
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = addr
    await RisingEdge(dut.clk)
    dut.penable.value = 1
    await RisingEdge(dut.clk)
    val = int(dut.prdata.value)
    dut.psel.value = 0
    dut.penable.value = 0
    return val


# ---------------------------------------------------------------------------
# Egress monitor (MONITOR responsibility: DUT-facing observation only)
# ---------------------------------------------------------------------------
class EgressMonitor:
    """Samples DUT egress on m_valid&m_ready and reassembles observed packets.

    A packet starts on a beat with m_sop=1 and ends on the beat with m_eop=1.
    The monitor decodes the 4 header bytes and the payload, observing the
    SOM/EOM/SEQ fields the same way a sink would.
    """

    def __init__(self, dut):
        self.dut = dut
        self.packets = []   # list of observed-packet dicts
        self._cur = None
        self._running = True

    def stop(self):
        self._running = False

    async def run(self):
        dut = self.dut
        while self._running:
            await RisingEdge(dut.clk)
            # sample after the edge; a transfer occurs when both high
            try:
                mvalid = int(dut.m_valid.value)
                mready = int(dut.m_ready.value)
            except ValueError:
                # X/Z during reset; skip
                continue
            if mvalid != 1 or mready != 1:
                continue
            data = int(dut.m_data.value) & 0xFF
            sop = int(dut.m_sop.value) & 1
            eop = int(dut.m_eop.value) & 1
            if sop:
                self._cur = {"bytes": [], "sop": 1, "eop": 0}
            if self._cur is None:
                # stray beat with no sop seen yet; start a defensive packet
                self._cur = {"bytes": [], "sop": sop, "eop": 0}
            self._cur["bytes"].append(data)
            if eop:
                self._cur["eop"] = 1
                self.packets.append(self._decode(self._cur))
                self._cur = None

    @staticmethod
    def _decode(raw):
        b = raw["bytes"]
        hdr = b[:4]
        payload = b[4:]
        byte3 = hdr[3] if len(hdr) >= 4 else 0
        return {
            "bytes": list(b),
            "header": list(hdr),
            "payload": list(payload),
            "som": (byte3 >> 7) & 1,
            "eom": (byte3 >> 6) & 1,
            "seq": (byte3 >> 4) & 0x3,
            "to": (byte3 >> 3) & 1,
            "msg_tag": byte3 & 0x7,
            "dest_eid": hdr[1] if len(hdr) >= 2 else None,
            "src_eid": hdr[2] if len(hdr) >= 3 else None,
            "version": hdr[0] if len(hdr) >= 1 else None,
        }


# ---------------------------------------------------------------------------
# Driver: ingress message stream (Driver responsibility: stimulus only)
# ---------------------------------------------------------------------------
async def reset_dut(dut, cycles=4):
    """Async-assert / sync-deassert reset (REQ_TX_RESET)."""
    dut.rst_n.value = 0
    # init all inputs to benign values
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.s_last.value = 0
    dut.s_empty.value = 0
    dut.s_abort.value = 0
    dut.s_dest_eid.value = 0
    dut.s_msg_tag.value = 0
    dut.s_to.value = 0
    dut.m_ready.value = 1
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = 0
    dut.pwdata.value = 0
    await Timer(1, units="ns")
    dut.rst_n.value = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
    # synchronous deassert
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def configure(dut, enable=1, src_eid=0x10, mtu=DEFAULT_MTU,
                    max_msg=DEFAULT_MAX_MSG, done_en=1, err_en=1):
    await apb_write(dut, REG_SRC_EID, src_eid)
    await apb_write(dut, REG_MTU, mtu)
    await apb_write(dut, REG_MAX_MSG, max_msg)
    await apb_write(dut, REG_IRQ_EN, (done_en & 1) | ((err_en & 1) << 1))
    await apb_write(dut, REG_CTRL, enable & 1)


async def drive_message(dut, body, dest_eid, msg_tag, to,
                        zero_len=False, abort_at=None, max_wait=20000):
    """Drive one message body over the ingress byte-serial stream.

    body      : list of payload bytes (the first byte is the msg-type/IC byte)
    zero_len  : if True, present a single s_last & s_empty beat with no body
    abort_at  : if not None, after driving this many accepted beats assert
                s_abort for one beat instead of continuing (underrun stimulus)
    Returns number of body beats actually accepted before abort/last.
    Driver only drives; it does not predict or observe egress.
    """
    body = list(body)

    # Drive attribute sideband stable across the message.
    dut.s_dest_eid.value = dest_eid & 0xFF
    dut.s_msg_tag.value = msg_tag & 0x7
    dut.s_to.value = to & 1

    if zero_len:
        # zero-length: s_last & s_empty with no body byte this beat
        waited = 0
        await RisingEdge(dut.clk)
        dut.s_valid.value = 1
        dut.s_empty.value = 1
        dut.s_last.value = 1
        dut.s_data.value = 0
        while True:
            await RisingEdge(dut.clk)
            if int(dut.s_ready.value) == 1:
                break
            waited += 1
            if waited > max_wait:
                break
        dut.s_valid.value = 0
        dut.s_empty.value = 0
        dut.s_last.value = 0
        return 0

    accepted = 0
    n = len(body)
    i = 0
    waited = 0
    while i < n:
        await RisingEdge(dut.clk)
        is_last = (i == n - 1)
        if abort_at is not None and accepted == abort_at:
            # abort mid-message: assert s_abort for one beat (underrun)
            dut.s_valid.value = 0
            dut.s_abort.value = 1
            dut.s_last.value = 0
            dut.s_empty.value = 0
            await RisingEdge(dut.clk)
            dut.s_abort.value = 0
            return accepted
        dut.s_valid.value = 1
        dut.s_data.value = body[i] & 0xFF
        dut.s_last.value = 1 if is_last else 0
        dut.s_empty.value = 0
        dut.s_abort.value = 0
        # wait for handshake (cycle_rules.tx.intake_handshake)
        await Timer(1, units="ps")  # let combinational s_ready settle
        if int(dut.s_ready.value) == 1:
            accepted += 1
            i += 1
            waited = 0
        else:
            waited += 1
            if waited > max_wait:
                break
    await RisingEdge(dut.clk)
    dut.s_valid.value = 0
    dut.s_last.value = 0
    dut.s_data.value = 0
    return accepted


def now_cycle(dut):
    """Best-effort cycle index for scoreboard rows (sim time in ns)."""
    try:
        return int(cocotb.utils.get_sim_time(units="ns"))
    except Exception:
        return 0


async def wait_idle(dut, cycles=400):
    """Wait until egress is quiet and s_ready re-asserts (new message ok)."""
    quiet = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        try:
            mv = int(dut.m_valid.value)
        except ValueError:
            mv = 1
        if mv == 0:
            quiet += 1
        else:
            quiet = 0
        if quiet >= 4:
            return


# ===========================================================================
# Shared run helper: drive a legal message, compare egress to reference model.
# ===========================================================================
async def run_message_and_check(dut, sb, scenario_id, body, dest_eid, msg_tag,
                                 to, src_eid, mtu, max_msg, ref):
    mon = EgressMonitor(dut)
    mon_task = cocotb.start_soon(mon.run())

    err_kind, exp_packets = ref.predict(body, dest_eid, msg_tag, to)
    assert err_kind is None, "this helper is for legal (non-error) messages only"

    await drive_message(dut, body, dest_eid, msg_tag, to)
    await wait_idle(dut)
    mon.stop()
    await RisingEdge(dut.clk)

    obs_packets = mon.packets
    return exp_packets, obs_packets


# ===========================================================================
# Tests : one per SCN_TX_* scenario (directed micro-TB)
# ===========================================================================

@cocotb.test()
async def test_scn_tx_reset(dut):
    """SCN_TX_RESET : post-reset observable state == behavior_model.tx.reset."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)

    # behavior_model.tx.reset expects: busy=0, seq=0, counters=0, CSR defaults.
    expected = {
        "busy": 0,
        "sent_cnt": 0,
        "drop_cnt": 0,
        "err_flags": 0,
        "mtu": DEFAULT_MTU,
        "max_msg": DEFAULT_MAX_MSG,
        "ctrl_enable": 0,
    }
    status = await apb_read(dut, REG_STATUS)
    sent = await apb_read(dut, REG_SENT_CNT)
    drop = await apb_read(dut, REG_DROP_CNT)
    errf = await apb_read(dut, REG_ERR_FLAGS)
    mtu = await apb_read(dut, REG_MTU)
    maxm = await apb_read(dut, REG_MAX_MSG)
    ctrl = await apb_read(dut, REG_CTRL)
    observed = {
        "busy": status & 1,
        "sent_cnt": sent,
        "drop_cnt": drop,
        "err_flags": errf & 0x7,
        "mtu": mtu & 0xFF,
        "max_msg": maxm & 0xFFFF,
        "ctrl_enable": ctrl & 1,
    }
    passed = observed == expected
    sb.record("SCN_TX_RESET", now_cycle(dut),
              stimulus={"action": "async_assert_sync_deassert_reset"},
              expected=expected, observed=observed, passed=passed,
              observed_source={"kind": "dut_signal",
                               "signal": "prdata(STATUS.busy,SENT_CNT,DROP_CNT,"
                                         "ERR_FLAGS,MTU,MAX_MSG,CTRL)"},
              mismatch="" if passed else "post-reset CSR/state != reset defaults")
    assert passed, f"reset defaults mismatch: exp={expected} obs={observed}"


@cocotb.test()
async def test_scn_tx_intake(dut):
    """SCN_TX_INTAKE : body-to-last captured, attribute word latched."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x22
    await configure(dut, src_eid=src_eid, mtu=DEFAULT_MTU)
    ref = ReferenceModel(src_eid, DEFAULT_MTU, DEFAULT_MAX_MSG)

    body = [0x7E, 0x01, 0x02, 0x03, 0x04]  # first byte = msg-type/IC
    dest_eid, msg_tag, to = 0x55, 0x3, 1
    exp, obs = await run_message_and_check(
        dut, sb, "SCN_TX_INTAKE", body, dest_eid, msg_tag, to,
        src_eid, DEFAULT_MTU, DEFAULT_MAX_MSG, ref)

    # Captured body == concatenation of observed payloads (DUT-facing).
    exp_body = []
    for p in exp:
        exp_body += p.payload
    obs_body = []
    for p in obs:
        obs_body += p["payload"]
    # latched attributes observed in every emitted header
    exp_attr = {"dest_eid": dest_eid, "to": to, "msg_tag": msg_tag}
    obs_attr = ({"dest_eid": obs[0]["dest_eid"], "to": obs[0]["to"],
                 "msg_tag": obs[0]["msg_tag"]} if obs else {})
    passed = (obs_body == body) and (obs_attr == exp_attr) and len(obs) == len(exp)
    sb.record("SCN_TX_INTAKE", now_cycle(dut),
              stimulus={"body": body, "dest_eid": dest_eid,
                        "msg_tag": msg_tag, "to": to},
              expected={"captured_body": body, "attr": exp_attr,
                        "packet_count": len(exp)},
              observed={"captured_body": obs_body, "attr": obs_attr,
                        "packet_count": len(obs)},
              passed=passed,
              mismatch="" if passed else "captured body/attribute word mismatch")
    assert passed, "intake capture/latch mismatch"


@cocotb.test()
async def test_scn_tx_fragment(dut):
    """SCN_TX_FRAGMENT : packet_count==ceil(len/MTU), only last short."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    # len = 150 with MTU 64 -> ceil = 3 packets: 64,64,22
    body = [(i & 0xFF) for i in range(150)]
    exp, obs = await run_message_and_check(
        dut, sb, "SCN_TX_FRAGMENT", body, 0x40, 0x1, 0,
        src_eid, mtu, DEFAULT_MAX_MSG, ref)

    exp_lens = [len(p.payload) for p in exp]
    obs_lens = [len(p["payload"]) for p in obs]
    passed = (exp_lens == obs_lens)
    sb.record("SCN_TX_FRAGMENT", now_cycle(dut),
              stimulus={"body_len": len(body), "mtu": mtu},
              expected={"packet_count": len(exp), "payload_lens": exp_lens},
              observed={"packet_count": len(obs), "payload_lens": obs_lens},
              passed=passed,
              mismatch="" if passed else "packet count / payload lengths mismatch")
    assert passed, f"fragment mismatch exp={exp_lens} obs={obs_lens}"


@cocotb.test()
async def test_scn_tx_som_eom(dut):
    """SCN_TX_SOM_EOM : SOM on first packet, EOM on last; single sets both."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    # multi-packet case
    body = [(i & 0xFF) for i in range(130)]  # 3 packets
    exp, obs = await run_message_and_check(
        dut, sb, "SCN_TX_SOM_EOM", body, 0x41, 0x2, 1,
        src_eid, mtu, DEFAULT_MAX_MSG, ref)
    exp_se = [(p.som, p.eom) for p in exp]
    obs_se = [(p["som"], p["eom"]) for p in obs]
    passed_multi = (exp_se == obs_se)
    sb.record("SCN_TX_SOM_EOM", now_cycle(dut),
              stimulus={"body_len": len(body), "mtu": mtu, "case": "multi"},
              expected={"som_eom": exp_se}, observed={"som_eom": obs_se},
              passed=passed_multi,
              mismatch="" if passed_multi else "multi-packet SOM/EOM mismatch")

    # single-packet case: SOM and EOM both set
    await wait_idle(dut)
    body1 = [0xAA, 0xBB, 0xCC]
    exp1, obs1 = await run_message_and_check(
        dut, sb, "SCN_TX_SOM_EOM", body1, 0x42, 0x3, 0,
        src_eid, mtu, DEFAULT_MAX_MSG, ref)
    exp_se1 = [(p.som, p.eom) for p in exp1]
    obs_se1 = [(p["som"], p["eom"]) for p in obs1]
    passed_single = (exp_se1 == [(1, 1)]) and (obs_se1 == exp_se1)
    sb.record("SCN_TX_SOM_EOM", now_cycle(dut),
              stimulus={"body_len": len(body1), "mtu": mtu, "case": "single"},
              expected={"som_eom": exp_se1}, observed={"som_eom": obs_se1},
              passed=passed_single,
              mismatch="" if passed_single else "single-packet SOM/EOM mismatch")
    assert passed_multi and passed_single, "SOM/EOM mismatch"


@cocotb.test()
async def test_scn_tx_seqnum(dut):
    """SCN_TX_SEQNUM : seq=0 on SOM else (prev+1) mod 4, with a real mod-4 wrap.

    Design-truth note: a genuine mod-4 wrap (seq 3 -> 0) needs >=5 packets. With
    the default MTU=64 and MAX_MSG=192 the deepest LEGAL message is only
    ceil(192/64)=3 packets (seq 0,1,2), so the wrap would be unreachable. We
    therefore program a SMALL MTU via the CSR (MTU=16) and drive a fully legal
    body (96 bytes <= MAX_MSG=192): ceil(96/16)=6 packets => seq 0,1,2,3,0,1.
    The wrap IS now demonstrated end-to-end with a non-oversize message. The
    per-packet seq is predicted by cycle_rules.tx.seqnum, never read from the
    DUT (the monitor only observes the emitted header byte3). MAX_MSG stays at
    its default here; oversize behavior is exercised only in SCN_TX_ERR_OVERSIZE.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = 16  # small MTU so a legal body produces >=5 packets (mod-4 wrap)
    await configure(dut, src_eid=src_eid, mtu=mtu)  # MAX_MSG = default 192
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    # 6 packets -> seq 0,1,2,3,0,1 ; body_len 96 <= MAX_MSG 192 (legal)
    body = [(i & 0xFF) for i in range(96)]
    exp, obs = await run_message_and_check(
        dut, sb, "SCN_TX_SEQNUM", body, 0x43, 0x4, 0,
        src_eid, mtu, DEFAULT_MAX_MSG, ref)
    exp_seq = [p.seq for p in exp]
    obs_seq = [p["seq"] for p in obs]

    # One scoreboard_rows.v1 row PER PACKET: expected seq from cycle_rules,
    # observed seq from the DUT-facing header byte3.
    per_packet_pass = True
    for i, e in enumerate(exp):
        o_seq = obs[i]["seq"] if i < len(obs) else None
        row_pass = (o_seq == e.seq)
        per_packet_pass = per_packet_pass and row_pass
        sb.record("SCN_TX_SEQNUM", now_cycle(dut),
                  stimulus={"packet_index": i, "mtu": mtu,
                            "body_len": len(body), "som": e.som},
                  expected={"packet_index": i, "seq": e.seq},
                  observed={"packet_index": i, "seq": o_seq},
                  passed=row_pass,
                  coverage_refs=["COV_TX_SEQNUM_WRAP"],
                  mismatch="" if row_pass else
                           f"packet {i} seq expected {e.seq} observed {o_seq}")

    # Summary row: confirm a genuine 3->0 mod-4 wrap was OBSERVED in the stream.
    exp_has_wrap = any(exp_seq[i] == 3 and exp_seq[i + 1] == 0
                       for i in range(len(exp_seq) - 1))
    obs_has_wrap = any(obs_seq[i] == 3 and obs_seq[i + 1] == 0
                       for i in range(len(obs_seq) - 1))
    summary_pass = (exp_seq == obs_seq) and exp_has_wrap and obs_has_wrap \
        and per_packet_pass and (exp_seq == [0, 1, 2, 3, 0, 1])
    sb.record("SCN_TX_SEQNUM", now_cycle(dut),
              stimulus={"body_len": len(body), "mtu": mtu,
                        "expected_packets": len(exp), "summary": True},
              expected={"seq": exp_seq, "mod4_wrap_3to0": exp_has_wrap},
              observed={"seq": obs_seq, "mod4_wrap_3to0": obs_has_wrap},
              passed=summary_pass,
              coverage_refs=["COV_TX_SEQNUM_WRAP"],
              mismatch="" if summary_pass else
                       "sequence (0,1,2,3,0,1) or observed mod-4 wrap mismatch")
    assert summary_pass, f"seqnum/wrap mismatch exp={exp_seq} obs={obs_seq}"


@cocotb.test()
async def test_scn_tx_header(dut):
    """SCN_TX_HEADER : byte-exact DSP0236 header + body order."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x5A
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    body = [0x7E] + [(0x10 + i) & 0xFF for i in range(70)]  # 2 packets
    dest_eid, msg_tag, to = 0x33, 0x5, 1
    exp, obs = await run_message_and_check(
        dut, sb, "SCN_TX_HEADER", body, dest_eid, msg_tag, to,
        src_eid, mtu, DEFAULT_MAX_MSG, ref)

    exp_hdrs = [p.header for p in exp]
    obs_hdrs = [p["header"] for p in obs]
    # full byte stream including body order
    exp_bytes = [p.bytes for p in exp]
    obs_bytes = [p["bytes"] for p in obs]
    passed = (exp_hdrs == obs_hdrs) and (exp_bytes == obs_bytes)
    sb.record("SCN_TX_HEADER", now_cycle(dut),
              stimulus={"body_len": len(body), "dest_eid": dest_eid,
                        "src_eid": src_eid, "msg_tag": msg_tag, "to": to},
              expected={"headers": exp_hdrs, "packet_bytes": exp_bytes},
              observed={"headers": obs_hdrs, "packet_bytes": obs_bytes},
              passed=passed,
              mismatch="" if passed else "header bytes / body order mismatch")
    assert passed, "header byte-exact mismatch"


@cocotb.test()
async def test_scn_tx_singlemsg(dut):
    """SCN_TX_SINGLEMSG : no interleave; new msg gated until EOM completes."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    mon = EgressMonitor(dut)
    cocotb.start_soon(mon.run())

    body_a = [(i & 0xFF) for i in range(100)]   # 2 packets
    body_b = [(0x80 + (i & 0x7F)) for i in range(40)]  # 1 packet
    exp_a = ref.predict(body_a, 0x44, 0x1, 0)[1]
    exp_b = ref.predict(body_b, 0x45, 0x2, 1)[1]

    # Drive message A; message B is offered right after (driver respects s_ready
    # gating). cycle_rules.tx.singlemsg: s_ready stays low until cycle after EOM.
    await drive_message(dut, body_a, 0x44, 0x1, 0)
    await drive_message(dut, body_b, 0x45, 0x2, 1)
    await wait_idle(dut)
    mon.stop()
    await RisingEdge(dut.clk)

    obs = mon.packets
    # Expected: A's packets fully precede B's packets, no interleaving.
    # Identify message boundaries by SOM markers in observed stream.
    som_positions = [i for i, p in enumerate(obs) if p["som"] == 1]
    # Reconstruct grouped messages from SOM..EOM
    groups = []
    cur = []
    for p in obs:
        cur.append(p)
        if p["eom"] == 1:
            groups.append(cur)
            cur = []
    exp_group_count = 2
    no_interleave = True
    # within each group, exactly one SOM at start and one EOM at end
    for g in groups:
        if g[0]["som"] != 1 or g[-1]["eom"] != 1:
            no_interleave = False
        if any(p["som"] == 1 for p in g[1:]):
            no_interleave = False
    passed = (len(groups) == exp_group_count) and no_interleave and \
             (len(som_positions) == exp_group_count)
    sb.record("SCN_TX_SINGLEMSG", now_cycle(dut),
              stimulus={"msg_a_len": len(body_a), "msg_b_len": len(body_b)},
              expected={"group_count": exp_group_count, "no_interleave": True,
                        "exp_a_packets": len(exp_a), "exp_b_packets": len(exp_b)},
              observed={"group_count": len(groups),
                        "no_interleave": no_interleave,
                        "som_markers": len(som_positions)},
              passed=passed,
              mismatch="" if passed else "packet interleaving or intake-gating violation")
    assert passed, "single-message gating / interleaving mismatch"


@cocotb.test()
async def test_scn_tx_status(dut):
    """SCN_TX_STATUS : irq_done + SENT_CNT on EOM emission."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu, done_en=1, err_en=1)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    sent_before = await apb_read(dut, REG_SENT_CNT)

    # watch irq_done across one message
    irq_done_seen = {"v": 0}

    async def watch_done():
        while True:
            await RisingEdge(dut.clk)
            try:
                if int(dut.irq_done.value) == 1:
                    irq_done_seen["v"] += 1
            except ValueError:
                pass

    watch = cocotb.start_soon(watch_done())
    body = [(i & 0xFF) for i in range(100)]  # 2 packets, single message
    mon = EgressMonitor(dut)
    cocotb.start_soon(mon.run())
    await drive_message(dut, body, 0x46, 0x1, 0)
    await wait_idle(dut)
    mon.stop()
    await RisingEdge(dut.clk)
    sent_after = await apb_read(dut, REG_SENT_CNT)

    # behavior_model.tx.status: one done irq per message, sent_counter += 1
    expected = {"sent_delta": 1, "irq_done_pulses": 1}
    observed = {"sent_delta": (sent_after - sent_before),
                "irq_done_pulses": irq_done_seen["v"]}
    passed = (observed["sent_delta"] == 1) and (observed["irq_done_pulses"] >= 1)
    sb.record("SCN_TX_STATUS", now_cycle(dut),
              stimulus={"body_len": len(body), "messages": 1},
              expected=expected, observed=observed, passed=passed,
              observed_source={"kind": "dut_signal",
                               "signal": "irq_done,prdata(SENT_CNT)"},
              mismatch="" if passed else "SENT_CNT / irq_done mismatch")
    assert passed, f"status mismatch exp={expected} obs={observed}"


@cocotb.test()
async def test_scn_tx_err_backpressure(dut):
    """SCN_TX_ERR_BACKPRESSURE : m_ready=0 stalls without byte loss."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    body = [(i & 0xFF) for i in range(120)]  # 2 packets
    err_kind, exp_packets = ref.predict(body, 0x47, 0x1, 0)
    assert err_kind is None

    mon = EgressMonitor(dut)
    cocotb.start_soon(mon.run())

    # Toggle m_ready to apply backpressure during egress.
    async def toggle_ready():
        while True:
            dut.m_ready.value = 0
            for _ in range(3):
                await RisingEdge(dut.clk)
            dut.m_ready.value = 1
            for _ in range(2):
                await RisingEdge(dut.clk)

    bp = cocotb.start_soon(toggle_ready())
    await drive_message(dut, body, 0x47, 0x1, 0)
    # let egress drain with backpressure still toggling
    for _ in range(600):
        await RisingEdge(dut.clk)
        if int(dut.m_valid.value if str(dut.m_valid.value).isdigit() else 0) == 0:
            pass
    bp.kill()
    dut.m_ready.value = 1
    await wait_idle(dut)
    mon.stop()
    await RisingEdge(dut.clk)

    obs = mon.packets
    exp_bytes = [p.bytes for p in exp_packets]
    obs_bytes = [p["bytes"] for p in obs]
    # No byte lost: observed packet bytes equal expected despite backpressure.
    passed = (exp_bytes == obs_bytes)
    sb.record("SCN_TX_ERR_BACKPRESSURE", now_cycle(dut),
              stimulus={"body_len": len(body), "backpressure": "toggle m_ready"},
              expected={"packet_bytes": exp_bytes, "byte_loss": False},
              observed={"packet_bytes": obs_bytes,
                        "byte_loss": exp_bytes != obs_bytes},
              passed=passed,
              mismatch="" if passed else "byte loss under backpressure")
    assert passed, "backpressure byte-loss mismatch"


@cocotb.test()
async def test_scn_tx_err_underrun(dut):
    """SCN_TX_ERR_UNDERRUN : s_abort mid-message -> err flag, drop++, no emit."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu, err_en=1)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    drop_before = await apb_read(dut, REG_DROP_CNT)
    irq_err_seen = {"v": 0}

    async def watch_err():
        while True:
            await RisingEdge(dut.clk)
            try:
                if int(dut.irq_err.value) == 1:
                    irq_err_seen["v"] += 1
            except ValueError:
                pass

    cocotb.start_soon(watch_err())
    mon = EgressMonitor(dut)
    cocotb.start_soon(mon.run())

    body = [(i & 0xFF) for i in range(80)]
    err_kind, exp_packets = ref.predict(body, 0x48, 0x1, 0, abort=True)
    # abort after 10 accepted beats
    await drive_message(dut, body, 0x48, 0x1, 0, abort_at=10)
    await wait_idle(dut)
    mon.stop()
    await RisingEdge(dut.clk)

    drop_after = await apb_read(dut, REG_DROP_CNT)
    errf = await apb_read(dut, REG_ERR_FLAGS)
    expected = {"error_kind": "underrun", "drop_delta": 1, "emitted_packets": 0,
                "underrun_flag": 1, "irq_err": True}
    observed = {"drop_delta": (drop_after - drop_before),
                "emitted_packets": len(mon.packets),
                "underrun_flag": errf & 1,
                "irq_err": irq_err_seen["v"] >= 1}
    passed = (observed["drop_delta"] == 1 and observed["emitted_packets"] == 0
              and observed["underrun_flag"] == 1 and observed["irq_err"])
    sb.record("SCN_TX_ERR_UNDERRUN", now_cycle(dut),
              stimulus={"body_len": len(body), "abort_at_beat": 10},
              expected=expected, observed=observed, passed=passed,
              observed_source={"kind": "dut_signal",
                               "signal": "irq_err,prdata(DROP_CNT,ERR_FLAGS.underrun),"
                                         "m_valid,m_sop,m_eop"},
              mismatch="" if passed else "underrun flag/drop/no-emit mismatch")
    assert passed, f"underrun mismatch exp={expected} obs={observed}"


@cocotb.test()
async def test_scn_tx_err_oversize(dut):
    """SCN_TX_ERR_OVERSIZE : len>MAX_MSG -> err flag, drop++, no emit."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    max_msg = DEFAULT_MAX_MSG  # 192
    await configure(dut, src_eid=src_eid, mtu=mtu, max_msg=max_msg, err_en=1)
    ref = ReferenceModel(src_eid, mtu, max_msg)

    drop_before = await apb_read(dut, REG_DROP_CNT)
    irq_err_seen = {"v": 0}

    async def watch_err():
        while True:
            await RisingEdge(dut.clk)
            try:
                if int(dut.irq_err.value) == 1:
                    irq_err_seen["v"] += 1
            except ValueError:
                pass

    cocotb.start_soon(watch_err())
    mon = EgressMonitor(dut)
    cocotb.start_soon(mon.run())

    body = [(i & 0xFF) for i in range(max_msg + 5)]  # over threshold
    err_kind, exp_packets = ref.predict(body, 0x49, 0x1, 0)
    # ref says oversize, no packets
    await drive_message(dut, body, 0x49, 0x1, 0)
    await wait_idle(dut)
    mon.stop()
    await RisingEdge(dut.clk)

    drop_after = await apb_read(dut, REG_DROP_CNT)
    errf = await apb_read(dut, REG_ERR_FLAGS)
    expected = {"error_kind": "oversize", "drop_delta": 1, "emitted_packets": 0,
                "oversize_flag": 1, "irq_err": True}
    observed = {"drop_delta": (drop_after - drop_before),
                "emitted_packets": len(mon.packets),
                "oversize_flag": (errf >> 1) & 1,
                "irq_err": irq_err_seen["v"] >= 1}
    passed = (err_kind == "oversize" and observed["drop_delta"] == 1
              and observed["emitted_packets"] == 0
              and observed["oversize_flag"] == 1 and observed["irq_err"])
    sb.record("SCN_TX_ERR_OVERSIZE", now_cycle(dut),
              stimulus={"body_len": len(body), "max_msg": max_msg},
              expected=expected, observed=observed, passed=passed,
              observed_source={"kind": "dut_signal",
                               "signal": "irq_err,prdata(DROP_CNT,ERR_FLAGS.oversize),"
                                         "m_valid,m_sop,m_eop"},
              mismatch="" if passed else "oversize flag/drop/no-emit mismatch")
    assert passed, f"oversize mismatch exp={expected} obs={observed}"


@cocotb.test()
async def test_scn_tx_err_zerolen(dut):
    """SCN_TX_ERR_ZEROLEN : s_empty&s_last at start -> err flag, drop++, no emit."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    sb = Scoreboard()
    await reset_dut(dut)
    src_eid = 0x10
    mtu = DEFAULT_MTU
    await configure(dut, src_eid=src_eid, mtu=mtu, err_en=1)
    ref = ReferenceModel(src_eid, mtu, DEFAULT_MAX_MSG)

    drop_before = await apb_read(dut, REG_DROP_CNT)
    irq_err_seen = {"v": 0}

    async def watch_err():
        while True:
            await RisingEdge(dut.clk)
            try:
                if int(dut.irq_err.value) == 1:
                    irq_err_seen["v"] += 1
            except ValueError:
                pass

    cocotb.start_soon(watch_err())
    mon = EgressMonitor(dut)
    cocotb.start_soon(mon.run())

    err_kind, exp_packets = ref.predict([], 0x4A, 0x1, 0, zero_len=True)
    await drive_message(dut, [], 0x4A, 0x1, 0, zero_len=True)
    await wait_idle(dut)
    mon.stop()
    await RisingEdge(dut.clk)

    drop_after = await apb_read(dut, REG_DROP_CNT)
    errf = await apb_read(dut, REG_ERR_FLAGS)
    expected = {"error_kind": "zero_len", "drop_delta": 1, "emitted_packets": 0,
                "zero_len_flag": 1, "irq_err": True}
    observed = {"drop_delta": (drop_after - drop_before),
                "emitted_packets": len(mon.packets),
                "zero_len_flag": (errf >> 2) & 1,
                "irq_err": irq_err_seen["v"] >= 1}
    passed = (err_kind == "zero_len" and observed["drop_delta"] == 1
              and observed["emitted_packets"] == 0
              and observed["zero_len_flag"] == 1 and observed["irq_err"])
    sb.record("SCN_TX_ERR_ZEROLEN", now_cycle(dut),
              stimulus={"zero_len": True},
              expected=expected, observed=observed, passed=passed,
              observed_source={"kind": "dut_signal",
                               "signal": "irq_err,prdata(DROP_CNT,ERR_FLAGS.zero_len),"
                                         "m_valid,m_sop,m_eop"},
              mismatch="" if passed else "zero_len flag/drop/no-emit mismatch")
    assert passed, f"zero_len mismatch exp={expected} obs={observed}"
