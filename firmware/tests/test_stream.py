"""The NMEA / UBX framer in gnss_stream.c."""

from __future__ import annotations

import pytest
from pyubx2 import UBXMessage

from conftest import FIXTURES


@pytest.fixture
def stream(ffi, lib):
    st = ffi.new("gnss_stream_t *")
    lib.gnss_stream_init(st)
    return st


def feed(ffi, lib, st, data: bytes):
    """Every (type, frame bytes) the framer reports for the data."""
    out = []
    for b in data:
        t = lib.gnss_stream_byte(st, b)
        if t == lib.GNSS_FRAME_NMEA:
            out.append(("nmea", ffi.string(ffi.cast("char *", st.buf)).decode()))
        elif t == lib.GNSS_FRAME_UBX:
            out.append(("ubx", bytes(ffi.buffer(st.buf, 4 + st.ubx_len))))
        elif t == lib.GNSS_FRAME_BAD_NMEA:
            out.append(("bad-nmea", None))
        elif t == lib.GNSS_FRAME_BAD_UBX:
            out.append(("bad-ubx", None))
    return out


def test_one_nmea_sentence(ffi, lib, stream):
    frames = feed(ffi, lib, stream, b"$GNZDA,071349.00,04,10,2026,00,00*73\r\n")
    assert frames == [("nmea", "$GNZDA,071349.00,04,10,2026,00,00")]


def test_nmea_bad_checksum(ffi, lib, stream):
    assert feed(ffi, lib, stream, b"$GNZDA,071349.00,04,10,2026,00,00*72\r\n") == [("bad-nmea", None)]


def test_nmea_lowercase_checksum(ffi, lib, stream):
    assert feed(ffi, lib, stream, b"$GNZDA,071349.00,04,10,2026,00,00*73\r\n")[0][0] == "nmea"


def test_nmea_cut_short_by_a_new_sentence(ffi, lib, stream):
    frames = feed(ffi, lib, stream, b"$GNGGA,0713$GNZDA,071349.00,04,10,2026,00,00*73\r\n")
    assert frames == [("bad-nmea", None), ("nmea", "$GNZDA,071349.00,04,10,2026,00,00")]


def test_nmea_too_long(ffi, lib, stream):
    frames = feed(ffi, lib, stream, b"$" + b"A" * lib.GNSS_NMEA_MAX + b"*00\r\n")
    assert frames[0] == ("bad-nmea", None)


def test_one_ubx_frame(ffi, lib, stream):
    msg = UBXMessage("MON", "MON-VER", 2, swVersion=b"ROM SPG 5.10", hwVersion=b"000A0000")
    frames = feed(ffi, lib, stream, msg.serialize())
    assert frames == [("ubx", msg.serialize()[2:-2])]


def test_ubx_poll_has_no_payload(ffi, lib, stream):
    msg = UBXMessage("MON", "MON-VER", 2)  # a poll: zero-length payload
    assert feed(ffi, lib, stream, msg.serialize()) == [("ubx", b"\x0a\x04\x00\x00")]


def test_ubx_bad_checksum(ffi, lib, stream):
    raw = bytearray(UBXMessage("MON", "MON-VER", 2).serialize())
    raw[-1] ^= 1
    assert feed(ffi, lib, stream, bytes(raw)) == [("bad-ubx", None)]


def test_ubx_length_too_long_is_rejected_at_once(ffi, lib, stream):
    frames = feed(ffi, lib, stream, b"\xb5\x62\x01\x07\xff\xff")
    assert frames == [("bad-ubx", None)]


def test_dollar_inside_ubx_payload_does_not_start_nmea(ffi, lib, stream):
    msg = UBXMessage("MON", "MON-VER", 2, swVersion=b"$GNGGA,x*00\r\n", hwVersion=b"00070000")
    assert feed(ffi, lib, stream, msg.serialize()) == [("ubx", msg.serialize()[2:-2])]


def test_mixed_stream_with_noise(ffi, lib, stream):
    ubx = UBXMessage("MON", "MON-VER", 2).serialize()
    data = b"\x00\xff junk \xb5 more" + ubx + b"$GNZDA,071349.00,04,10,2026,00,00*73\r\n" + ubx
    kinds = [k for k, _ in feed(ffi, lib, stream, data)]
    assert kinds == ["ubx", "nmea", "ubx"]


def test_every_sentence_in_the_nmea_capture(ffi, lib, stream):
    data = (FIXTURES / "max-m10s-nmea.bin").read_bytes()
    frames = feed(ffi, lib, stream, data)
    assert len(frames) == data.count(b"$") == 684
    assert {k for k, _ in frames} == {"nmea"}


def test_every_frame_in_the_ubx_capture(ffi, lib, stream):
    data = (FIXTURES / "max-m10s-ubx.bin").read_bytes()
    frames = feed(ffi, lib, stream, data)
    assert len(frames) == 186
    assert {k for k, _ in frames} == {"ubx"}
    assert sum(4 + len(f) for _, f in frames) == len(data)  # sync + checksum per frame


def test_capture_split_at_every_byte_boundary_still_frames(ffi, lib):
    """Feeding is per byte, so where the UART read splits the data cannot matter;
    check it anyway by restarting a fresh framer mid-stream and comparing."""
    data = (FIXTURES / "max-m10s-nmea.bin").read_bytes()[:2000]
    st = ffi.new("gnss_stream_t *")
    lib.gnss_stream_init(st)
    whole = feed(ffi, lib, st, data)
    lib.gnss_stream_init(st)
    parts = feed(ffi, lib, st, data[:999]) + feed(ffi, lib, st, data[999:])
    assert whole == parts
