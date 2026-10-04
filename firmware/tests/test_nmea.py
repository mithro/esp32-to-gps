"""NMEA decoding in gnss_nmea.c.

Hand-written sentences pin down each field; the real MAX-M10S capture is
checked against pynmeagps decoding the same sentences.
"""

from __future__ import annotations

import functools
import io

import pytest
from pynmeagps import NMEAReader

from conftest import FIXTURES


def sentence(body: str) -> str:
    """The framed form gnss_nmea_parse takes: '$' + body, no checksum."""
    return "$" + body


def full(body: str) -> bytes:
    ck = functools.reduce(lambda a, c: a ^ ord(c), body, 0)
    return f"${body}*{ck:02X}\r\n".encode()


def parse(lib, state, body: str) -> int:
    return lib.gnss_nmea_parse(state, sentence(body).encode())


def sats(ffi, state):
    """{(constellation letter, svid): (elev, azim, cno, used)}"""
    out = {}
    for i in range(state.n_sats):
        s = state.sats[i]
        letter = "GSECMJRI"[s.gnss]
        out[(letter, s.svid)] = (s.elev, s.azim, s.cno, bool(s.used))
    return out


# -- single sentences ------------------------------------------------------

def test_gga(lib, state):
    k = parse(lib, state, "GNGGA,071349.00,3455.71075,S,13836.04200,E,1,16,0.77,25.1,M,-1.2,M,,")
    assert k == lib.GNSS_NMEA_GGA
    assert (state.hour, state.minute, state.second, state.millisecond) == (7, 13, 49, 0)
    assert state.quality == lib.GNSS_QUALITY_GPS
    assert state.position_valid
    assert state.lat_e7 == -349285125  # 34 deg 55.71075 min
    assert state.lon_e7 == 1386007000
    assert state.sats_used_reported == 16
    assert state.hdop == 77
    assert state.alt_msl_mm == 25100 and state.alt_valid
    assert state.geoid_sep_mm == -1200 and state.geoid_valid
    assert state.alt_ellipsoid_mm == 23900 and state.ellipsoid_valid
    assert state.diff_age_ds == -1 and state.diff_station == -1


def test_gga_with_differential_corrections(lib, state):
    parse(lib, state, "GPGGA,071349.00,3455.71075,S,13836.04200,E,2,08,1.10,25.1,M,-1.2,M,3.4,0200")
    assert state.quality == lib.GNSS_QUALITY_DGPS
    assert state.diff_age_ds == 34 and state.diff_station == 200


def test_gga_without_fix_clears_position(lib, state):
    parse(lib, state, "GNGGA,071349.00,3455.71075,S,13836.04200,E,1,16,0.77,25.1,M,-1.2,M,,")
    parse(lib, state, "GNGGA,071350.00,,,,,0,00,99.99,,,,,,")
    assert state.quality == 0 and not state.position_valid and state.sats_used_reported == 0
    assert state.hdop == 9999


def test_rmc(lib, state):
    k = parse(lib, state, "GNRMC,071349.00,A,3455.71075,S,13836.04200,E,1.000,123.45,041026,,,A,V")
    assert k == lib.GNSS_NMEA_RMC
    assert (state.year, state.month, state.day) == (2026, 10, 4) and state.date_valid
    assert state.speed_mm_s == 514  # 1 knot
    assert state.course_e5 == 12345000
    assert state.lat_e7 == -349285125 and state.position_valid


def test_rmc_void_does_not_set_position(lib, state):
    parse(lib, state, "GNRMC,071349.00,V,3455.71075,S,13836.04200,E,,,041026,,,N,V")
    assert not state.position_valid
    assert state.date_valid


def test_vtg(lib, state):
    parse(lib, state, "GNVTG,45.50,T,,M,0.540,N,1.000,K,A")
    assert state.course_e5 == 4550000
    assert state.speed_mm_s == 278  # 1 km/h = 277.8 mm/s


def test_gll(lib, state):
    parse(lib, state, "GNGLL,3455.71075,S,13836.04200,E,071349.00,A,A")
    assert state.lat_e7 == -349285125 and state.lon_e7 == 1386007000 and state.position_valid


def test_zda(lib, state):
    parse(lib, state, "GNZDA,071349.00,04,10,2026,00,00")
    assert (state.year, state.month, state.day, state.hour) == (2026, 10, 4, 7)
    assert state.date_valid and state.time_valid


def test_gst(lib, state):
    parse(lib, state, "GNGST,071349.00,10.0,2.0,1.0,45.0,3.000,4.000,5.500")
    assert state.h_acc_mm == 5000 and state.v_acc_mm == 5500 and state.acc_valid


def test_gsa_marks_used_and_sets_dops(ffi, lib, state):
    parse(lib, state, "GNGSA,A,3,05,13,15,,,,,,,,,,1.52,0.77,1.31,1")  # NMEA 4.10: system 1 = GPS
    parse(lib, state, "GNGSA,A,3,07,,,,,,,,,,,,1.52,0.77,1.31,3")  # system 3 = Galileo
    assert state.fix_type == lib.GNSS_FIX_3D
    assert (state.pdop, state.hdop, state.vdop) == (152, 77, 131)
    assert {k for k, v in sats(ffi, state).items() if v[3]} == {("G", 5), ("G", 13), ("G", 15), ("E", 7)}


def test_gsa_used_flags_reset_each_epoch(ffi, lib, state):
    parse(lib, state, "GNGGA,071349.00,,,,,1,,,,,,,,")
    parse(lib, state, "GNGSA,A,3,05,13,,,,,,,,,,,1.5,0.8,1.3,1")
    parse(lib, state, "GNGGA,071350.00,,,,,1,,,,,,,,")  # next epoch
    parse(lib, state, "GNGSA,A,3,13,,,,,,,,,,,,1.5,0.8,1.3,1")
    used = {k for k, v in sats(ffi, state).items() if v[3]}
    assert used == {("G", 13)}


def test_gsv(ffi, lib, state):
    k = parse(lib, state, "GPGSV,2,1,05,05,45,123,40,13,10,350,,15,,,32,20,-2,10,22,1")
    assert k == lib.GNSS_NMEA_GSV
    s = sats(ffi, state)
    assert s[("G", 5)] == (45, 123, 40, False)
    assert s[("G", 13)] == (10, 350, 0, False)  # not tracked: no C/N0
    assert s[("G", 15)] == (-91, -1, 32, False)  # tracked, position not known yet
    assert s[("G", 20)] == (-2, 10, 22, False)


def test_gsv_keeps_the_strongest_signal_in_an_epoch(ffi, lib, state):
    parse(lib, state, "GNGGA,071349.00,,,,,1,,,,,,,,")
    parse(lib, state, "GPGSV,1,1,01,05,45,123,40,1")  # L1
    parse(lib, state, "GPGSV,1,1,01,05,45,123,46,7")  # L5, stronger
    parse(lib, state, "GPGSV,1,1,01,05,45,123,31,7")  # weaker again
    assert sats(ffi, state)[("G", 5)][2] == 46
    parse(lib, state, "GNGGA,071350.00,,,,,1,,,,,,,,")  # new epoch: the first reading counts again
    parse(lib, state, "GPGSV,1,1,01,05,45,123,30,1")
    assert sats(ffi, state)[("G", 5)][2] == 30


@pytest.mark.parametrize("talker,system_id,prn,expected", [
    ("GP", 0, 5, ("G", 5)),
    ("GP", 0, 33, ("S", 120)),
    ("GP", 0, 46, ("S", 133)),
    ("GL", 0, 70, ("R", 6)),
    ("GL", 0, 6, ("R", 6)),
    ("GA", 0, 7, ("E", 7)),
    ("GB", 0, 21, ("C", 21)),
    ("BD", 0, 21, ("C", 21)),
    ("GQ", 0, 2, ("J", 2)),
    ("GQ", 0, 194, ("J", 2)),
    ("GN", 0, 70, ("R", 6)),
    ("GN", 0, 305, ("E", 5)),
    ("GN", 0, 421, ("C", 21)),
    ("GN", 0, 194, ("J", 2)),
    ("GN", 2, 70, ("R", 6)),
    ("GN", 3, 7, ("E", 7)),
    ("GN", 4, 21, ("C", 21)),
])
def test_satellite_numbering(ffi, lib, talker, system_id, prn, expected):
    gnss, svid = ffi.new("uint8_t *"), ffi.new("uint8_t *")
    talkers = {"GP": lib.GNSS_GPS, "GL": lib.GNSS_GLONASS, "GA": lib.GNSS_GALILEO, "GB": lib.GNSS_BEIDOU,
               "BD": lib.GNSS_BEIDOU, "GQ": lib.GNSS_QZSS, "GN": lib.GNSS_UNKNOWN}
    assert lib.gnss_nmea_satellite(talkers[talker], system_id, prn, gnss, svid)
    assert ("GSECMJRI"[gnss[0]], svid[0]) == expected


def test_unplaceable_satellite_number(ffi, lib):
    gnss, svid = ffi.new("uint8_t *"), ffi.new("uint8_t *")
    assert not lib.gnss_nmea_satellite(lib.GNSS_UNKNOWN, 0, 150, gnss, svid)
    assert not lib.gnss_nmea_satellite(lib.GNSS_GPS, 0, 0, gnss, svid)


def test_txt_antenna_status(lib, state):
    k = parse(lib, state, "GPTXT,01,01,02,ANTSTATUS=OPEN")
    assert k == lib.GNSS_NMEA_TXT and state.antenna == lib.GNSS_ANT_OPEN
    parse(lib, state, "GPTXT,01,01,02,ANTSTATUS=OK")
    assert state.antenna == lib.GNSS_ANT_OK


def test_quectel_version_reply(ffi, lib, state):
    # As read back from the LC29H(AA) on rpiz-gps, 2026-09-27.
    k = parse(lib, state, "PQTMVERNO,LC29HAANR11A05S,2025/09/12,10:21:16")
    assert k == lib.GNSS_NMEA_PQTMVERNO
    assert state.module == lib.GNSS_MODULE_QUECTEL_LC29H
    assert ffi.string(state.model) == b"LC29H(AA)"
    assert ffi.string(state.sw_version) == b"LC29HAANR11A05S"


def test_quectel_chip_reply(ffi, lib, state):
    k = parse(lib, state, "PAIR021,AG3335M_V3.2.2.AG3335_20250912,S,N,9ad2a7e,2509121021,8e2,3,,,8bd4c7b5,2509121021,9a6b2ec,2509121021,,")
    assert k == lib.GNSS_NMEA_PAIR021
    assert ffi.string(state.hw_version) == b"AG3335M"


def test_quectel_ack(lib, state):
    parse(lib, state, "PAIR001,062,0")
    assert state.ack == 1 and state.last_ack_id == 62
    parse(lib, state, "PAIR001,062,1")  # still processing: neither
    parse(lib, state, "PAIR001,050,3")
    assert state.ack == 1 and state.nak == 1 and state.last_nak_id == 50


def test_unknown_and_malformed_are_harmless(lib, state):
    assert parse(lib, state, "GNXYZ,1,2,3") == lib.GNSS_NMEA_OTHER
    assert parse(lib, state, "PUBX,00") == lib.GNSS_NMEA_OTHER
    assert parse(lib, state, "GNGGA") == lib.GNSS_NMEA_GGA  # no fields at all
    assert parse(lib, state, "GNGGA,ab:cd,x,y,z,w,9,,,,") == lib.GNSS_NMEA_GGA
    assert not state.position_valid and not state.time_valid
    assert parse(lib, state, "") == lib.GNSS_NMEA_OTHER


# -- the real capture --------------------------------------------------------

def run_capture(ffi, lib, state, data: bytes) -> None:
    st = ffi.new("gnss_stream_t *")
    lib.gnss_stream_init(st)
    for b in data:
        if lib.gnss_stream_byte(st, b) == lib.GNSS_FRAME_NMEA:
            lib.gnss_nmea_parse(state, ffi.cast("char *", st.buf))


def reference(data: bytes):
    """What pynmeagps makes of the last complete epoch of the capture."""
    msgs = [m for _, m in NMEAReader(io.BytesIO(data), quitonerror=2)]
    last_gga = max(i for i, m in enumerate(msgs) if m.msgID == "GGA")
    first_of_epoch = max(i for i, m in enumerate(msgs[:last_gga]) if m.msgID == "RMC")
    epoch = msgs[first_of_epoch:]
    return msgs, epoch


def test_capture_end_state_matches_pynmeagps(ffi, lib, state):
    data = (FIXTURES / "max-m10s-nmea.bin").read_bytes()
    run_capture(ffi, lib, state, data)
    msgs, epoch = reference(data)
    gga = [m for m in msgs if m.msgID == "GGA"][-1]
    rmc = [m for m in msgs if m.msgID == "RMC"][-1]
    assert state.nmea_ok == len(msgs) == 684
    assert state.lat_e7 == round(gga.lat * 1e7)
    assert state.lon_e7 == round(gga.lon * 1e7)
    assert state.alt_msl_mm == round(gga.alt * 1000)
    assert state.sats_used_reported == gga.numSV
    assert state.quality == gga.quality
    assert (state.year, state.month, state.day) == (rmc.date.year, rmc.date.month, rmc.date.day)
    assert (state.hour, state.minute, state.second) == (gga.time.hour, gga.time.minute, gga.time.second)

    # Satellites: the GSV of the last epoch, per constellation.
    talker_letter = {"GP": "G", "GA": "E", "GB": "C", "GL": "R", "GQ": "J"}
    want = {}
    for m in epoch:
        if m.msgID != "GSV":
            continue
        for n in range(1, 5):
            prn = getattr(m, f"svid_{n:02d}", "")
            if prn in ("", None):
                continue
            key = (talker_letter[m.talker], int(prn))
            if m.talker == "GP" and 33 <= int(prn) <= 64:
                key = ("S", int(prn) + 87)
            cno = getattr(m, f"cno_{n:02d}", "")
            want[key] = max(want.get(key, 0), int(cno) if cno not in ("", None) else 0)
    got = sats(ffi, state)
    assert {k: v[2] for k, v in got.items() if k in want} == want
    assert set(want) <= set(got)

    used_want = set()
    sysid = {1: "G", 2: "R", 3: "E", 4: "C", 5: "J"}
    for m in epoch:
        if m.msgID == "GSA":
            for n in range(1, 13):
                prn = getattr(m, f"svid_{n:02d}", "")
                if prn not in ("", None):
                    used_want.add((sysid[int(m.systemId)], int(prn)))
    assert {k for k, v in got.items() if v[3]} == used_want
    assert len(used_want) > 4  # a real fix
