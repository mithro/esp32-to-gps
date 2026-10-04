"""Receiver identification and configuration in gnss_module.c.

Every command is decoded by pyubx2 (UBX) or checked against a command
string Quectel published (NMEA), so the bytes the firmware sends are
checked independently of the code that builds them.
"""

from __future__ import annotations

import pytest
from pyubx2 import SET, UBXReader

MODULES = ("UBLOX7", "UBLOX_M8", "UBLOX_M10", "QUECTEL_LC29H")


def commands(ffi, lib, module: str):
    """[(bytes, switch_baud)] for one receiver."""
    out, baud = ffi.new("uint8_t[512]"), ffi.new("uint32_t *")
    cmds = []
    for i in range(256):
        n = lib.gnss_module_config(getattr(lib, f"GNSS_MODULE_{module}"), i, out, 512, baud)
        if n == 0:
            break
        cmds.append((bytes(ffi.buffer(out, n)), baud[0]))
    return cmds


def ubx(raw: bytes):
    return UBXReader.parse(raw, msgmode=SET)


def test_probes(ffi, lib):
    out = ffi.new("uint8_t[64]")
    n = lib.gnss_module_probe(0, out, 64)
    assert bytes(ffi.buffer(out, n)) == b"\xb5\x62\x0a\x04\x00\x00\x0e\x34"  # MON-VER poll
    n = lib.gnss_module_probe(1, out, 64)
    assert bytes(ffi.buffer(out, n)) == b"$PQTMVERNO*58\r\n"
    assert lib.gnss_module_probe(2, out, 64) == 0


def test_nmea_command_checksum_matches_quectel(ffi, lib):
    """Quectel's forum gives '$PAIR062,8,1*37' as the command that enables
    GST on the LC29H(AA)."""
    out = ffi.new("char[64]")
    n = lib.gnss_nmea_command(out, 64, b"PAIR062,8,1")
    assert bytes(ffi.buffer(out, n)) == b"$PAIR062,8,1*37\r\n"


def test_ublox7(ffi, lib):
    cmds = commands(ffi, lib, "UBLOX7")
    prt = ubx(cmds[0][0])
    assert prt.identity == "CFG-PRT" and prt.portID == 1 and prt.baudRate == 38400
    assert (prt.charLen, prt.parity, prt.nStopBits) == (3, 4, 0)  # 8N1
    assert (prt.inUBX, prt.inNMEA, prt.inRTCM) == (1, 1, 1) and prt.inRTCM3 == 0
    assert (prt.outUBX, prt.outNMEA) == (1, 1)
    assert cmds[0][1] == 38400 and all(b == 0 for _, b in cmds[1:])
    rates = {(m.msgClass, m.msgID): m.rateDDC for m in (ubx(c) for c, _ in cmds[1:-1])}
    assert rates[(0x01, 0x07)] == 1 and rates[(0x01, 0x30)] == 1  # NAV-PVT, NAV-SVINFO
    assert (0x01, 0x35) not in rates  # no NAV-SAT on a u-blox 7
    assert rates[(0xF0, 0x03)] == 0 and rates[(0xF0, 0x00)] == 1  # GSV off, GGA on
    assert ubx(cmds[-1][0]).identity == "MON-VER"


def test_m8(ffi, lib):
    cmds = commands(ffi, lib, "UBLOX_M8")
    prt = ubx(cmds[0][0])
    assert prt.baudRate == 38400 and prt.inRTCM3 == 1 and prt.inRTCM == 1
    rates = {(m.msgClass, m.msgID): m.rateDDC for m in (ubx(c) for c, _ in cmds[1:-1])}
    assert rates[(0x01, 0x35)] == 1 and rates[(0x02, 0x32)] == 1 and rates[(0x0D, 0x01)] == 1  # NAV-SAT, RXM-RTCM, TIM-TP
    assert (0x01, 0x30) not in rates


def test_m10(ffi, lib):
    cmds = commands(ffi, lib, "UBLOX_M10")
    assert len(cmds) == 1 and cmds[0][1] == 0
    m = ubx(cmds[0][0])
    assert m.identity == "CFG-VALSET" and (m.ram, m.bbr, m.flash) == (1, 0, 0)
    got = {k: v for k, v in m.__dict__.items() if k.startswith("CFG_")}
    assert got == {
        "CFG_UART1INPROT_UBX": 1, "CFG_UART1INPROT_NMEA": 1, "CFG_UART1INPROT_RTCM3X": 1,
        "CFG_UART1OUTPROT_UBX": 1, "CFG_UART1OUTPROT_NMEA": 1,
        "CFG_MSGOUT_UBX_NAV_PVT_UART1": 1, "CFG_MSGOUT_UBX_NAV_DOP_UART1": 1, "CFG_MSGOUT_UBX_NAV_SAT_UART1": 1,
        "CFG_MSGOUT_UBX_MON_RF_UART1": 5, "CFG_MSGOUT_UBX_RXM_RTCM_UART1": 1,
        "CFG_MSGOUT_NMEA_ID_GGA_UART1": 1, "CFG_MSGOUT_NMEA_ID_RMC_UART1": 1,
        "CFG_MSGOUT_NMEA_ID_GSA_UART1": 0, "CFG_MSGOUT_NMEA_ID_GSV_UART1": 0, "CFG_MSGOUT_NMEA_ID_GLL_UART1": 0,
        "CFG_MSGOUT_NMEA_ID_VTG_UART1": 0, "CFG_MSGOUT_NMEA_ID_ZDA_UART1": 0,
        "CFG_MSGOUT_UBX_NAV_SIG_UART1": 0, "CFG_MSGOUT_UBX_NAV_POSECEF_UART1": 0, "CFG_MSGOUT_UBX_NAV_VELECEF_UART1": 0,
        "CFG_MSGOUT_UBX_NAV_TIMEGPS_UART1": 0, "CFG_MSGOUT_UBX_NAV_CLOCK_UART1": 0, "CFG_MSGOUT_UBX_NAV_EOE_UART1": 0,
    }


def test_lc29h(ffi, lib):
    cmds = [c for c, _ in commands(ffi, lib, "QUECTEL_LC29H")]
    assert cmds == [b"$PAIR021*39\r\n", b"$PAIR062,8,1*37\r\n"]


def test_unknown_module_gets_nothing(ffi, lib):
    assert commands(ffi, lib, "UNKNOWN") == []
    assert lib.gnss_module_baud(lib.GNSS_MODULE_UNKNOWN) == 0


@pytest.mark.parametrize("module,baud,mount", [
    ("UBLOX7", 38400, b"ADDE_RTCM23"),
    ("UBLOX_M8", 38400, b"ADDE_RTCM3"),
    ("UBLOX_M10", 38400, b"ADDE_RTCM3"),
    ("QUECTEL_LC29H", 115200, b"ADDE_RTCM3"),
])
def test_speed_and_mountpoint(ffi, lib, module, baud, mount):
    m = getattr(lib, f"GNSS_MODULE_{module}")
    assert lib.gnss_module_baud(m) == baud
    assert ffi.string(lib.gnss_module_mount(m)) == mount


def test_commands_fit_the_driver_buffer(ffi, lib):
    """The driver sends from a 256-byte buffer."""
    for module in MODULES:
        for cmd, _ in commands(ffi, lib, module):
            assert len(cmd) <= 256
