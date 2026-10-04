#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Make a raw receiver capture safe to publish: move every position in it to
a public reference point.

    uv run firmware/fixtures/anonymise.py <capture.raw> <fixture.bin>

The captures come from receivers at a private address.  Every position is
moved by one fixed offset, chosen so that the first fix in the capture lands
exactly on Victoria Square, Adelaide; positions keep their scatter relative
to each other, so the data still looks like a real stationary receiver.
Satellite elevations and azimuths are left alone: they only narrow the
position to a few hundred kilometres.

* NMEA GGA, RMC, GLL and GNS: latitude and longitude are moved.
* UBX NAV-PVT and NAV-POSLLH: latitude and longitude are moved.
* Every other UBX message that carries a position (NAV-POSECEF,
  NAV-HPPOSECEF, NAV-HPPOSLLH, NAV-VELECEF, ...) is dropped, as is any UBX
  message this script does not know to be position-free.
* gpsd's JSON lines at the start of a gpspipe -R capture are dropped.
* Checksums are recomputed; a frame whose checksum was already wrong is
  dropped rather than published with a corrected one.
"""

from __future__ import annotations

import sys

TARGET_LAT, TARGET_LON = -34.92850, 138.60070  # Victoria Square, Adelaide

# UBX (class, id) known to carry no position, kept unchanged.
UBX_KEEP = {
    (0x01, 0x04),  # NAV-DOP
    (0x01, 0x21),  # NAV-TIMEUTC
    (0x01, 0x20),  # NAV-TIMEGPS
    (0x01, 0x22),  # NAV-CLOCK
    (0x01, 0x03),  # NAV-STATUS
    (0x01, 0x30),  # NAV-SVINFO
    (0x01, 0x35),  # NAV-SAT
    (0x01, 0x43),  # NAV-SIG
    (0x01, 0x61),  # NAV-EOE
    (0x01, 0x26),  # NAV-TIMELS
    (0x01, 0x12),  # NAV-VELNED (velocity only)
    (0x02, 0x32),  # RXM-RTCM
    (0x05, 0x00), (0x05, 0x01),  # ACK
    (0x0A, 0x04),  # MON-VER
    (0x0A, 0x09),  # MON-HW
    (0x0A, 0x38),  # MON-RF
    (0x0D, 0x01),  # TIM-TP
}
UBX_MOVE = {(0x01, 0x07): (28, 24), (0x01, 0x02): (8, 4)}  # NAV-PVT, NAV-POSLLH: (lat, lon) offsets
NMEA_MOVE = {"GGA": 2, "RMC": 3, "GLL": 1, "GNS": 2}  # index of the latitude field


def ubx_ck(body: bytes) -> bytes:
    a = b = 0
    for x in body:
        a = (a + x) & 0xFF
        b = (b + a) & 0xFF
    return bytes([a, b])


def nmea_ck(body: str) -> str:
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def dm_to_deg(v: str, hemi: str) -> float:
    dot = v.index(".")
    deg = int(v[: dot - 2]) + float(v[dot - 2:]) / 60
    return -deg if hemi in "SW" else deg


def deg_to_dm(deg: float, width: int, decimals: int) -> tuple[str, str]:
    a = abs(deg)
    d = int(a)
    m = round((a - d) * 60, decimals)
    if m >= 60:
        d, m = d + 1, 0.0
    return f"{d:0{width}d}{m:0{decimals + 3}.{decimals}f}", ""


class Mover:
    def __init__(self) -> None:
        self.dlat: float | None = None
        self.dlon = 0.0

    def move(self, lat: float, lon: float) -> tuple[float, float]:
        if self.dlat is None:
            self.dlat, self.dlon = TARGET_LAT - lat, TARGET_LON - lon
        return lat + self.dlat, lon + self.dlon


def nmea(line: str, mv: Mover) -> str | None:
    if "*" not in line:
        return None
    body, ck = line[1:].split("*", 1)
    if nmea_ck(body) != ck[:2].upper():
        return None
    f = body.split(",")
    kind = f[0][2:] if f[0][0] != "P" else f[0]
    if kind in NMEA_MOVE:
        i = NMEA_MOVE[kind]
        if f[i] and f[i + 2]:
            lat, lon = mv.move(dm_to_deg(f[i], f[i + 1]), dm_to_deg(f[i + 2], f[i + 3]))
            ld = len(f[i].split(".")[1])
            f[i], f[i + 1] = deg_to_dm(lat, 2, ld)[0], "S" if lat < 0 else "N"
            f[i + 2], f[i + 3] = deg_to_dm(lon, 3, len(f[i + 2].split(".")[1]))[0], "W" if lon < 0 else "E"
        body = ",".join(f)
    elif kind not in {"GSV", "GSA", "VTG", "ZDA", "TXT", "GST", "GBS", "GRS", "DTM"} and not kind.startswith(("PQTM", "PAIR")):
        return None  # not known to be position-free
    return f"${body}*{nmea_ck(body)}\r\n"


def ubx(frame: bytes, mv: Mover) -> bytes | None:
    cls, mid = frame[2], frame[3]
    body = bytearray(frame[2:-2])
    if ubx_ck(bytes(body)) != frame[-2:]:
        return None
    if (cls, mid) in UBX_MOVE:
        lat_o, lon_o = (4 + o for o in UBX_MOVE[(cls, mid)])
        lat = int.from_bytes(body[lat_o:lat_o + 4], "little", signed=True)
        lon = int.from_bytes(body[lon_o:lon_o + 4], "little", signed=True)
        if lat or lon:
            nlat, nlon = mv.move(lat / 1e7, lon / 1e7)
            body[lat_o:lat_o + 4] = round(nlat * 1e7).to_bytes(4, "little", signed=True)
            body[lon_o:lon_o + 4] = round(nlon * 1e7).to_bytes(4, "little", signed=True)
    elif (cls, mid) not in UBX_KEEP:
        return None
    return b"\xb5\x62" + bytes(body) + ubx_ck(bytes(body))


def anonymise(data: bytes) -> bytes:
    mv, out, i = Mover(), bytearray(), 0
    while i < len(data):
        if data[i:i + 2] == b"\xb5\x62" and i + 6 <= len(data):
            n = 8 + int.from_bytes(data[i + 4:i + 6], "little")
            if i + n > len(data):
                break
            frame = ubx(data[i:i + n], mv)
            if frame:
                out += frame
            i += n
        elif data[i:i + 1] == b"$":
            end = data.find(b"\n", i)
            if end < 0:
                break
            line = nmea(data[i:end].decode("ascii", "replace").rstrip("\r"), mv)
            if line:
                out += line.encode()
            i = end + 1
        else:
            i += 1  # gpsd JSON, line ends, partial frames
    return bytes(out)


def main() -> None:
    src, dst = sys.argv[1:3]
    data = open(src, "rb").read()
    out = anonymise(data)
    open(dst, "wb").write(out)
    print(f"{src}: {len(data)} bytes -> {dst}: {len(out)} bytes")


if __name__ == "__main__":
    main()
