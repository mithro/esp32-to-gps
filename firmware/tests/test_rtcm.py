"""RTCM framing, chunk stripping and NTRIP handling in gnss_rtcm.c.

The fixtures are 12 s of each mountpoint of the ten64 proxy, reply header
included; frames are checked against pyrtcm.
"""

from __future__ import annotations

import io

import pytest
from pyrtcm import RTCMReader

from conftest import FIXTURES

RTCM3 = (FIXTURES / "ntrip-adde-rtcm3.bin").read_bytes()
RTCM23 = (FIXTURES / "ntrip-adde-rtcm23.bin").read_bytes()


def body(data: bytes) -> bytes:
    return data[data.index(b"\r\n\r\n") + 4:]


def dechunk_http(data: bytes) -> bytes:
    """Reference de-chunker, in Python."""
    out, i = bytearray(), 0
    while i < len(data):
        eol = data.index(b"\r\n", i)
        n = int(data[i:eol].split(b";")[0], 16)
        out += data[eol + 2:eol + 2 + n]
        i = eol + 2 + n + 2
        if n == 0:
            break
    return bytes(out)


@pytest.fixture
def rtcm(ffi, lib):
    r = ffi.new("gnss_rtcm_t *")
    lib.gnss_rtcm_init(r)
    return r


def feed(ffi, lib, r, data: bytes, block: int = 512) -> int:
    done = 0
    for i in range(0, len(data), block):
        part = data[i:i + block]
        done += lib.gnss_rtcm_feed(r, part, len(part))
    return done


def dechunk(ffi, lib, data: bytes, declared: bool = False, block: int = 512) -> bytes:
    d = ffi.new("gnss_dechunk_t *")
    lib.gnss_dechunk_init(d, declared)
    out, pending = bytearray(), b""
    for i in range(0, len(data), block):
        part = pending + data[i:i + block]
        buf = ffi.new("uint8_t[]", len(part))  # exact size: initialising from bytes would add a NUL
        ffi.memmove(buf, part, len(part))
        n = lib.gnss_dechunk(d, buf, len(part))
        if n == 0 and not d.decided:
            pending = part
            continue
        pending = b""
        out += ffi.buffer(buf, n)
    return bytes(out)


# -- CRC-24Q -------------------------------------------------------------------

def test_crc24q_matches_pyrtcm(lib):
    from pyrtcm import calc_crc24q
    for sample in (b"", b"\xd3\x00\x13", body(RTCM3)[5:400]):
        assert lib.gnss_crc24q(sample, len(sample)) == calc_crc24q(sample)


# -- RTCM 3 framing --------------------------------------------------------------

def test_real_rtcm3_stream(ffi, lib, rtcm):
    stream = dechunk_http(body(RTCM3))
    want = [m for _, m in RTCMReader(io.BytesIO(stream), quitonerror=2)]
    assert feed(ffi, lib, rtcm, stream) == len(want) == 77
    assert rtcm.frames == 77 and rtcm.bad_crc == 0 and rtcm.bytes == len(stream)
    types = {rtcm.types[i]: rtcm.counts[i] for i in range(rtcm.n_types)}
    pyrtcm_types = {}
    for m in want:
        pyrtcm_types[int(m.identity)] = pyrtcm_types.get(int(m.identity), 0) + 1
    assert types == pyrtcm_types
    assert {1006, 1077, 1087, 1097, 1127} <= set(types)  # station, GPS/GLONASS/Galileo/BeiDou MSM7
    station = next(m for m in want if m.identity == "1006").DF003
    assert rtcm.station_valid and rtcm.station == station


def test_junk_between_frames_is_skipped(ffi, lib, rtcm):
    """The proxy's undeclared chunk framing, left in: frames still count."""
    assert feed(ffi, lib, rtcm, body(RTCM3)) == 77
    assert rtcm.bad_crc == 0


@pytest.mark.parametrize("block", [1, 7, 64, 1000])
def test_any_split_point(ffi, lib, rtcm, block):
    stream = dechunk_http(body(RTCM3))
    whole = ffi.new("gnss_rtcm_t *")
    lib.gnss_rtcm_init(whole)
    assert feed(ffi, lib, rtcm, stream, block) == feed(ffi, lib, whole, stream, len(stream)) == 77


def test_bad_crc_counted(ffi, lib, rtcm):
    stream = bytearray(dechunk_http(body(RTCM3)))
    stream[10] ^= 0xFF  # inside the first frame
    feed(ffi, lib, rtcm, bytes(stream))
    assert rtcm.bad_crc == 1 and rtcm.frames == 76


def test_rtcm2_is_counted_not_framed(ffi, lib, rtcm):
    stream = body(RTCM23)
    assert feed(ffi, lib, rtcm, stream) == 0
    assert rtcm.bytes == len(stream) and rtcm.frames == 0 and rtcm.bad_crc == 0


# -- chunk stripping ------------------------------------------------------------

def test_undeclared_chunking_is_detected_and_stripped(ffi, lib):
    """The ten64 proxy's RTCM 3 mountpoint: chunked, but not declared."""
    assert dechunk(ffi, lib, body(RTCM3)) == dechunk_http(body(RTCM3))


@pytest.mark.parametrize("block", [1, 3, 9, 10, 100, 4096])
def test_stripping_does_not_depend_on_read_size(ffi, lib, block):
    assert dechunk(ffi, lib, body(RTCM3), block=block) == dechunk_http(body(RTCM3))


def test_plain_streams_pass_through(ffi, lib):
    assert dechunk(ffi, lib, body(RTCM23)) == body(RTCM23)  # RTCM 2.3 starts with letters, not CR LF
    plain = dechunk_http(body(RTCM3))
    assert dechunk(ffi, lib, plain) == plain  # RTCM 3 starts with 0xD3


def test_declared_chunking(ffi, lib):
    chunked = b"5\r\nhello\r\n3;ext=1\r\nabc\r\n0\r\n\r\n"
    assert dechunk(ffi, lib, chunked, declared=True) == b"helloabc"


# -- NTRIP -----------------------------------------------------------------------

def request(ffi, lib, *args) -> bytes:
    out = ffi.new("char[512]")
    n = lib.gnss_ntrip_request(out, 512, *[a if not isinstance(a, str) else a.encode() for a in args])
    return bytes(ffi.buffer(out, n))


def test_request_without_login(ffi, lib):
    req = request(ffi, lib, "10.1.10.1", 2101, "ADDE_RTCM3", ffi.NULL, ffi.NULL)
    assert req == (b"GET /ADDE_RTCM3 HTTP/1.1\r\nHost: 10.1.10.1:2101\r\nNtrip-Version: Ntrip/2.0\r\n"
                   b"User-Agent: NTRIP esp32-to-gps/1.0\r\nConnection: close\r\n\r\n")


def test_request_with_login(ffi, lib):
    req = request(ffi, lib, "caster.example", 2101, "MOUNT", "user", "pass word")
    assert b"Authorization: Basic dXNlcjpwYXNzIHdvcmQ=\r\n" in req  # base64("user:pass word")


def test_request_too_long_for_buffer(ffi, lib):
    out = ffi.new("char[20]")
    assert lib.gnss_ntrip_request(out, 20, b"10.1.10.1", 2101, b"ADDE_RTCM3", ffi.NULL, ffi.NULL) == 0


def reply(ffi, lib, data: bytes):
    hl, ch = ffi.new("size_t *"), ffi.new("bool *")
    r = lib.gnss_ntrip_reply(data, len(data), hl, ch)
    return r, hl[0], bool(ch[0])


def test_reply_from_the_proxy(ffi, lib):
    r, hl, chunked = reply(ffi, lib, RTCM3[:600])
    assert r == lib.GNSS_NTRIP_OK and not chunked
    assert RTCM3[hl:hl + 5] == b"1b7\r\n"  # the undeclared chunk framing starts right after


def test_reply_ntrip1(ffi, lib):
    r, hl, _ = reply(ffi, lib, b"ICY 200 OK\r\n\xd3\x00\x13")
    assert r == lib.GNSS_NTRIP_OK and hl == 12
    r, hl, _ = reply(ffi, lib, b"ICY 200 OK\r\n\r\n\xd3\x00")
    assert r == lib.GNSS_NTRIP_OK and hl == 14


def test_reply_declared_chunked(ffi, lib):
    r, _, chunked = reply(ffi, lib, b"HTTP/1.1 200 OK\r\nTransfer-Encoding: Chunked\r\n\r\n")
    assert r == lib.GNSS_NTRIP_OK and chunked


@pytest.mark.parametrize("data,expected", [
    (b"HTTP/1.1 200 OK\r\nContent-Type: gnss/sourcetable\r\n\r\nSTR;...", "SOURCETABLE"),
    (b"SOURCETABLE 200 OK\r\n", "SOURCETABLE"),
    (b"HTTP/1.1 401 Unauthorized\r\n\r\n", "UNAUTHORIZED"),
    (b"HTTP/1.1 404 Not Found\r\n\r\n", "ERROR"),
    (b"HTTP/1.1 200 OK\r\nServer: x\r\n", "INCOMPLETE"),
    (b"HTTP/1.1", "INCOMPLETE"),
    (b"ICY 200 O", "INCOMPLETE"),
    (b"garbage that is long enough", "ERROR"),
])
def test_reply_kinds(ffi, lib, data, expected):
    assert reply(ffi, lib, data)[0] == getattr(lib, f"GNSS_NTRIP_{expected}")
