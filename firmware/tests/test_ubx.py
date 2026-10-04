"""UBX decoding and encoding in gnss_ubx.c.

Every message is built with pyubx2, so the payload layouts are checked
against an independent implementation of the u-blox interface description.
"""

from __future__ import annotations

import io

import pytest
from pyubx2 import SET, UBX_PROTOCOL, UBXMessage, UBXReader

from conftest import FIXTURES


def parse(ffi, lib, state, msg: UBXMessage) -> int:
    raw = msg.serialize()
    payload = raw[6:-2]
    return lib.gnss_ubx_parse(state, raw[2], raw[3], payload, len(payload))


def text(ffi, field) -> str:
    return ffi.string(field).decode()


def pvt(**kw) -> UBXMessage:
    fields = dict(iTOW=25000000, year=2026, month=10, day=4, hour=7, min=13, second=49,
                  validDate=1, validTime=1, fullyResolved=1, tAcc=25, nano=-12345, fixType=3,
                  gnssFixOk=1, numSV=16, lon=138.6007, lat=-34.9285, height=24500, hMSL=25700,
                  hAcc=1500, vAcc=2300, gSpeed=36, headMot=123.45, sAcc=410, pDOP=1.62)
    fields.update(kw)
    return UBXMessage("NAV", "NAV-PVT", 0, **fields)


# -- NAV ---------------------------------------------------------------------

def test_nav_pvt(ffi, lib, state):
    assert parse(ffi, lib, state, pvt()) == lib.GNSS_UBX_NAV_PVT
    assert (state.year, state.month, state.day, state.hour, state.minute, state.second) == (2026, 10, 4, 7, 13, 49)
    assert state.time_valid and state.date_valid and state.time_accuracy_ns == 25
    assert state.fix_type == lib.GNSS_FIX_3D and state.quality == lib.GNSS_QUALITY_GPS
    assert state.position_valid
    assert (state.lat_e7, state.lon_e7) == (-349285000, 1386007000)
    assert (state.alt_ellipsoid_mm, state.alt_msl_mm, state.geoid_sep_mm) == (24500, 25700, -1200)
    assert (state.h_acc_mm, state.v_acc_mm) == (1500, 2300)
    assert (state.speed_mm_s, state.course_e5, state.speed_acc_mm_s) == (36, 12345000, 410)
    assert state.pdop == 162 and state.sats_used_reported == 16


def test_nav_pvt_same_epoch_as_nmea_gga(ffi, lib, state):
    """NAV-PVT a few microseconds before the second and GGA for that second
    are one epoch, not two."""
    lib.gnss_nmea_parse(state, b"$GNGGA,071349.00,,,,,1,,,,,,,,")
    epoch = state.epoch
    parse(ffi, lib, state, pvt(nano=-12345))
    assert state.epoch == epoch
    parse(ffi, lib, state, pvt(second=50, nano=3000))
    assert state.epoch == epoch + 1


@pytest.mark.parametrize("flags,quality", [
    (dict(diffSoln=1), "DGPS"),
    (dict(diffSoln=1, carrSoln=1), "RTK_FLOAT"),
    (dict(diffSoln=1, carrSoln=2), "RTK_FIXED"),
    (dict(gnssFixOk=0), "INVALID"),
    (dict(fixType=0, gnssFixOk=0), "INVALID"),
    (dict(fixType=4), "ESTIMATED"),
])
def test_nav_pvt_quality(ffi, lib, state, flags, quality):
    parse(ffi, lib, state, pvt(**flags))
    assert state.quality == getattr(lib, f"GNSS_QUALITY_{quality}")
    assert state.diff_soln == bool(flags.get("diffSoln", 0))
    assert state.carr_soln == flags.get("carrSoln", 0)


def test_nav_pvt_without_fix_keeps_last_position(ffi, lib, state):
    parse(ffi, lib, state, pvt())
    parse(ffi, lib, state, pvt(fixType=0, gnssFixOk=0, lat=0, lon=0))
    assert not state.position_valid
    assert state.lat_e7 == -349285000  # the last good position is kept, flagged invalid


def test_nav_pvt_ublox7_length(ffi, lib, state):
    """The u-blox 7's NAV-PVT is 84 bytes: the same fields, without the last 8."""
    raw = pvt().serialize()
    payload = raw[6:-2][:84]
    assert lib.gnss_ubx_parse(state, 0x01, 0x07, payload, 84) == lib.GNSS_UBX_NAV_PVT
    assert state.pdop == 162
    assert lib.gnss_ubx_parse(state, 0x01, 0x07, payload, 83) == lib.GNSS_UBX_SHORT


def test_nav_dop(ffi, lib, state):
    msg = UBXMessage("NAV", "NAV-DOP", 0, iTOW=1, gDOP=1.91, pDOP=1.62, tDOP=1.01, vDOP=1.34, hDOP=0.91, nDOP=0.6, eDOP=0.7)
    assert parse(ffi, lib, state, msg) == lib.GNSS_UBX_NAV_DOP
    assert (state.gdop, state.pdop, state.tdop, state.vdop, state.hdop) == (191, 162, 101, 134, 91)


def test_nav_sat(ffi, lib, state):
    msg = UBXMessage("NAV", "NAV-SAT", 0, iTOW=1, version=1, numSvs=3,
                     gnssId_01=0, svId_01=5, cno_01=40, elev_01=45, azim_01=123, svUsed_01=1, qualityInd_01=7,
                     gnssId_02=2, svId_02=7, cno_02=33, elev_02=12, azim_02=300, svUsed_02=0,
                     gnssId_03=3, svId_03=21, cno_03=0, elev_03=-91, azim_03=0, svUsed_03=0)
    assert parse(ffi, lib, state, msg) == lib.GNSS_UBX_NAV_SAT
    got = {("GSECMJRI"[state.sats[i].gnss], state.sats[i].svid):
           (state.sats[i].elev, state.sats[i].azim, state.sats[i].cno, bool(state.sats[i].used))
           for i in range(state.n_sats)}
    assert got == {("G", 5): (45, 123, 40, True), ("E", 7): (12, 300, 33, False), ("C", 21): (-91, 0, 0, False)}


def test_nav_sat_truncated(ffi, lib, state):
    raw = UBXMessage("NAV", "NAV-SAT", 0, iTOW=1, version=1, numSvs=2, gnssId_01=0, svId_01=5, gnssId_02=0, svId_02=6).serialize()
    payload = raw[6:-2]
    assert lib.gnss_ubx_parse(state, 0x01, 0x35, payload, len(payload) - 1) == lib.GNSS_UBX_SHORT


def test_nav_svinfo(ffi, lib, state):
    """The u-blox 7 reports satellites in NAV-SVINFO, with its own numbering."""
    msg = UBXMessage("NAV", "NAV-SVINFO", 0, iTOW=1, numCh=3, chipGen=1,
                     chn_01=0, svid_01=12, svUsed_01=1, cno_01=41, elev_01=60, azim_01=10,
                     chn_02=1, svid_02=72, svUsed_02=0, cno_02=30, elev_02=20, azim_02=200,
                     chn_03=2, svid_03=133, svUsed_03=1, cno_03=36, elev_03=50, azim_03=330)
    assert parse(ffi, lib, state, msg) == lib.GNSS_UBX_NAV_SVINFO
    got = {("GSECMJRI"[state.sats[i].gnss], state.sats[i].svid): (state.sats[i].cno, bool(state.sats[i].used))
           for i in range(state.n_sats)}
    assert got == {("G", 12): (41, True), ("R", 8): (30, False), ("S", 133): (36, True)}


@pytest.mark.parametrize("svid,expected", [
    (1, ("G", 1)), (32, ("G", 32)), (33, ("C", 6)), (64, ("C", 37)), (65, ("R", 1)), (96, ("R", 32)),
    (120, ("S", 120)), (158, ("S", 158)), (159, ("C", 1)), (163, ("C", 5)), (193, ("J", 1)),
    (211, ("E", 1)), (246, ("E", 36)), (0, None), (97, None), (255, None),
])
def test_ubx_satellite_numbering(ffi, lib, svid, expected):
    gnss, sat = ffi.new("uint8_t *"), ffi.new("uint8_t *")
    ok = lib.gnss_ubx_svid(svid, gnss, sat)
    assert (("GSECMJRI"[gnss[0]], sat[0]) if ok else None) == expected


# -- MON -------------------------------------------------------------------

def mon_ver(sw: bytes, hw: bytes, *ext: bytes) -> UBXMessage:
    """MON-VER as a receiver sends it: NUL-padded fixed-size fields (CH[30]
    software, CH[10] hardware, CH[30] per extension). pyubx2's builder does
    not pad character fields, so the payload is built here and pyubx2's
    parser checks it is well formed."""
    payload = sw.ljust(30, b"\0") + hw.ljust(10, b"\0") + b"".join(e.ljust(30, b"\0") for e in ext)
    msg = UBXReader.parse(UBXMessage("MON", "MON-VER", 0, payload=payload).serialize())
    assert msg.swVersion.rstrip(b"\0") == sw and msg.hwVersion.rstrip(b"\0") == hw
    return msg


def test_mon_ver_max_m10s(ffi, lib, state):
    # As ten64's MAX-M10S reports itself.
    msg = mon_ver(b"ROM SPG 5.10 (7b202e)", b"000A0000", b"ROM BASE 0x118B2060", b"FWVER=SPG 5.10",
                  b"PROTVER=34.10", b"MOD=MAX-M10S", b"GPS;GLO;GAL;BDS", b"SBAS;QZSS")
    assert parse(ffi, lib, state, msg) == lib.GNSS_UBX_MON_VER
    assert state.module == lib.GNSS_MODULE_UBLOX_M10
    assert text(ffi, state.model) == "MAX-M10S"
    assert text(ffi, state.sw_version) == "SPG 5.10"
    assert text(ffi, state.hw_version) == "000A0000"
    assert text(ffi, state.protocol) == "34.10"


def test_mon_ver_lea_m8t(ffi, lib, state):
    msg = mon_ver(b"EXT CORE 3.01 (1ec93f)", b"00080000", b"ROM BASE 2.01 (75331)", b"FWVER=TIM 1.10",
                  b"PROTVER=22.00", b"MOD=LEA-M8T-0", b"FIS=0xEF4015 (100111)", b"GPS;GLO;GAL;BDS", b"SBAS;IMES;QZSS")
    parse(ffi, lib, state, msg)
    assert state.module == lib.GNSS_MODULE_UBLOX_M8
    assert text(ffi, state.model) == "LEA-M8T-0"
    assert text(ffi, state.sw_version) == "TIM 1.10"
    assert text(ffi, state.protocol) == "22.00"


def test_mon_ver_ublox7(ffi, lib, state):
    """The u-blox 7 has no MOD= extension and writes 'PROTVER 14.00' with a space."""
    msg = mon_ver(b"1.00 (59842)", b"00070000", b"PROTVER 14.00", b"GPS;SBAS;GLO;QZSS")
    parse(ffi, lib, state, msg)
    assert state.module == lib.GNSS_MODULE_UBLOX7
    assert text(ffi, state.model) == "u-blox 7"
    assert text(ffi, state.sw_version) == "1.00 (59842)"
    assert text(ffi, state.protocol) == "14.00"


def test_mon_hw(ffi, lib, state):
    msg = UBXMessage("MON", "MON-HW", 0, noisePerMS=82, agcCnt=5000, aStatus=2, aPower=1, jamInd=17)
    assert parse(ffi, lib, state, msg) == lib.GNSS_UBX_MON_HW
    assert (state.noise, state.antenna, state.jamming, state.rf_valid) == (82, lib.GNSS_ANT_OK, 17, True)


def test_mon_rf(ffi, lib, state):
    msg = UBXMessage("MON", "MON-RF", 0, version=0, nBlocks=1,
                     blockId_01=0, jammingState_01=1, antStatus_01=4, antPower_01=0, noisePerMS_01=95, agcCnt_01=4000, jamInd_01=9)
    assert parse(ffi, lib, state, msg) == lib.GNSS_UBX_MON_RF
    assert (state.noise, state.antenna, state.jamming) == (95, lib.GNSS_ANT_OPEN, 9)


# -- RXM / TIM / ACK -----------------------------------------------------------

def test_rxm_rtcm(ffi, lib, state):
    used = UBXMessage("RXM", "RXM-RTCM", 0, version=2, crcFailed=0, msgUsed=2, refStation=200, msgType=1077)
    unused = UBXMessage("RXM", "RXM-RTCM", 0, version=2, crcFailed=0, msgUsed=1, refStation=200, msgType=1230)
    failed = UBXMessage("RXM", "RXM-RTCM", 0, version=2, crcFailed=1, msgUsed=0, refStation=200, msgType=1005)
    for m in (used, used, unused, failed):
        assert parse(ffi, lib, state, m) == lib.GNSS_UBX_RXM_RTCM
    assert (state.rtcm_used, state.rtcm_failed, state.rtcm_last_type) == (2, 1, 1005)


def test_tim_tp(ffi, lib, state):
    parse(ffi, lib, state, UBXMessage("TIM", "TIM-TP", 0, towMS=1, qErr=-1234, week=2400))
    assert state.qerr_ps == -1234 and state.qerr_valid
    parse(ffi, lib, state, UBXMessage("TIM", "TIM-TP", 0, towMS=2, qErr=55, qErrInvalid=1))
    assert not state.qerr_valid


def test_ack_and_nak(ffi, lib, state):
    assert parse(ffi, lib, state, UBXMessage("ACK", "ACK-ACK", 0, clsID=0x06, msgID=0x8A)) == lib.GNSS_UBX_ACK
    assert parse(ffi, lib, state, UBXMessage("ACK", "ACK-NAK", 0, clsID=0x06, msgID=0x01)) == lib.GNSS_UBX_NAK
    assert (state.ack, state.last_ack_cls, state.last_ack_id) == (1, 0x06, 0x8A)
    assert (state.nak, state.last_nak_cls, state.last_nak_id) == (1, 0x06, 0x01)


def test_other_messages_are_counted_not_decoded(ffi, lib, state):
    assert parse(ffi, lib, state, UBXMessage("NAV", "NAV-EOE", 0, iTOW=1)) == lib.GNSS_UBX_OTHER
    assert state.ubx_ok == 1


# -- the real capture ------------------------------------------------------------

def test_capture_matches_pyubx2(ffi, lib, state):
    data = (FIXTURES / "max-m10s-ubx.bin").read_bytes()
    st = ffi.new("gnss_stream_t *")
    lib.gnss_stream_init(st)
    for b in data:
        if lib.gnss_stream_byte(st, b) == lib.GNSS_FRAME_UBX:
            lib.gnss_ubx_parse(state, st.buf[0], st.buf[1], st.buf + 4, st.ubx_len)
    msgs = [m for _, m in UBXReader(io.BytesIO(data), protfilter=UBX_PROTOCOL, quitonerror=2)]
    assert state.ubx_ok == len(msgs) == 186
    dop = [m for m in msgs if m.identity == "NAV-DOP"][-1]
    assert (state.gdop, state.hdop, state.vdop) == (round(dop.gDOP * 100), round(dop.hDOP * 100), round(dop.vDOP * 100))
    p = [m for m in msgs if m.identity == "NAV-PVT"][-1]
    assert state.fix_type == p.fixType == 0 and not state.position_valid  # pluto had no fix
    # Every NAV-SAT in the capture, decoded on its own, against pyubx2.
    sats = [m for m in msgs if m.identity == "NAV-SAT"]
    assert sum(m.numSvs for m in sats) > 30  # pluto's antenna is poor, but not silent
    for m in sats:
        one = ffi.new("gnss_state_t *")
        lib.gnss_state_init(one)
        raw = m.serialize()
        lib.gnss_ubx_parse(one, raw[2], raw[3], raw[6:-2], len(raw) - 8)
        want = {(m.__dict__[f"gnssId_{i:02d}"], m.__dict__[f"svId_{i:02d}"]):
                (m.__dict__[f"cno_{i:02d}"], m.__dict__[f"elev_{i:02d}"], bool(m.__dict__[f"svUsed_{i:02d}"]))
                for i in range(1, m.numSvs + 1)}
        got = {(one.sats[i].gnss, one.sats[i].svid): (one.sats[i].cno, one.sats[i].elev, bool(one.sats[i].used))
               for i in range(one.n_sats)}
        assert got == want


# -- encoding ----------------------------------------------------------------

def decode(raw: bytes) -> UBXMessage:
    return UBXReader.parse(raw, msgmode=SET)


def test_poll(ffi, lib):
    out = ffi.new("uint8_t[16]")
    n = lib.gnss_ubx_poll(out, 16, 0x0A, 0x04)
    assert bytes(ffi.buffer(out, n)) == UBXMessage("MON", "MON-VER", 2).serialize()


def test_frame_too_small_for_buffer(ffi, lib):
    out = ffi.new("uint8_t[7]")
    assert lib.gnss_ubx_poll(out, 7, 0x0A, 0x04) == 0


def test_cfg_msg(ffi, lib):
    out = ffi.new("uint8_t[16]")
    n = lib.gnss_ubx_cfg_msg(out, 16, 0x01, 0x07, 1)
    m = decode(bytes(ffi.buffer(out, n)))
    assert m.identity == "CFG-MSG" and (m.msgClass, m.msgID, m.rateDDC) == (0x01, 0x07, 1)


def test_cfg_valset(ffi, lib):
    """Keys of every size, as the M10 configuration uses them."""
    keys = [0x20910007, 0x10730004, 0x40520001, 0x30210001]  # NAV_PVT_UART1 (U1), UART1INPROT-RTCM3X (L), UART1-BAUDRATE (U4), CFG-RATE-MEAS (U2)
    values = [1, 1, 38400, 1000]
    out = ffi.new("uint8_t[128]")
    n = lib.gnss_ubx_cfg_valset(out, 128, 1, ffi.new("uint32_t[]", keys), ffi.new("uint64_t[]", values), len(keys))
    m = decode(bytes(ffi.buffer(out, n)))
    assert m.identity == "CFG-VALSET" and (m.ram, m.bbr, m.flash) == (1, 0, 0)
    assert (m.CFG_MSGOUT_UBX_NAV_PVT_UART1, m.CFG_UART1INPROT_RTCM3X, m.CFG_UART1_BAUDRATE, m.CFG_RATE_MEAS) == (1, 1, 38400, 1000)


def test_cfg_valset_rejects_unknown_size(ffi, lib):
    out = ffi.new("uint8_t[64]")
    n = lib.gnss_ubx_cfg_valset(out, 64, 1, ffi.new("uint32_t[]", [0x70000001]), ffi.new("uint64_t[]", [0]), 1)
    assert n == 0
