"""Bringing the receiver link up (gnss_link.c), against a simulated receiver.

The simulated receiver sends data once a second, but only when the ESP32's
UART is at its speed; answers a UBX MON-VER poll if it is a u-blox and
$PQTMVERNO if it is a Quectel, with replies decoded by the real parsers; and
changes speed when it is sent a CFG-PRT.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pyubx2 import SET, UBXMessage, UBXReader

MON_VER = b"\xb5\x62\x0a\x04\x00\x00\x0e\x34"
HW = {"UBLOX7": b"00070000", "UBLOX_M8": b"00080000", "UBLOX_M10": b"000A0000"}


@dataclass
class Receiver:
    kind: str                # UBLOX7, UBLOX_M8, UBLOX_M10, QUECTEL_LC29H
    baud: int
    silent_from: float = 1e12   # seconds
    received: list = field(default_factory=list)


class Sim:
    def __init__(self, ffi, lib, rx: Receiver, **cfg):
        self.ffi, self.lib, self.rx = ffi, lib, rx
        self.link = ffi.new("gnss_link_t *")
        self.state = ffi.new("gnss_state_t *")
        self.action = ffi.new("gnss_link_action_t *")
        lib.gnss_state_init(self.state)
        c = ffi.new("gnss_link_cfg_t *")
        for k, v in cfg.items():
            setattr(c, k, getattr(lib, f"GNSS_MODULE_{v}") if k.endswith("module") else v)
        self.uart = 0
        self.t = 0.0
        self.next_data = 0.0
        self.saves = []
        self.logs = []
        self.sent = []       # (time, bytes) the ESP32 sent while the receiver could hear it
        lib.gnss_link_start(self.link, c, self.state, 0)

    def reply(self, data: bytes) -> None:
        lib, ffi, rx = self.lib, self.ffi, self.rx
        if data == MON_VER and rx.kind in HW:
            payload = b"ROM SPG".ljust(30, b"\0") + HW[rx.kind].ljust(10, b"\0")
            lib.gnss_ubx_parse(self.state, 0x0A, 0x04, payload, len(payload))
        elif data.startswith(b"$PQTMVERNO") and rx.kind == "QUECTEL_LC29H":
            lib.gnss_nmea_parse(self.state, b"$PQTMVERNO,LC29HAANR11A05S,2025/09/12,10:21:16")
        elif data.startswith(b"\xb5\x62\x06\x00") and rx.kind in HW:  # CFG-PRT
            rx.baud = UBXReader.parse(data, msgmode=SET).baudRate

    def run(self, seconds: float) -> None:
        lib, ffi = self.lib, self.ffi
        end = self.t + seconds
        while self.t < end:
            ms = int(self.t * 1000)
            if self.uart == self.rx.baud and self.t >= self.next_data and self.t < self.rx.silent_from:
                lib.gnss_link_frame(self.link, ms)
                self.next_data = self.t + 1.0
            while lib.gnss_link_step(self.link, self.state, ms, self.action):
                a = self.action
                if a.baud:
                    self.uart = a.baud
                if a.send_len:
                    data = bytes(ffi.buffer(a.send, a.send_len))
                    if self.uart == self.rx.baud:
                        self.sent.append((self.t, data))
                        self.reply(data)
                if a.baud_after:
                    self.uart = a.baud_after
                if a.save:
                    self.saves.append((self.link.cfg.known_module, self.link.cfg.known_baud))
                if a.log[0]:
                    self.logs.append(ffi.string(a.log).decode())
            self.t += 0.05

    @property
    def phase(self) -> int:
        return self.link.phase

    def probes(self) -> list[bytes]:
        return [d for _, d in self.sent if d == MON_VER or d.startswith(b"$PQTMVERNO")]

    def first_config_time(self) -> float:
        return next(t for t, d in self.sent if d != MON_VER and not d.startswith(b"$PQTMVERNO"))


def m(lib, name):
    return getattr(lib, f"GNSS_MODULE_{name}")


# -- first boot: nothing known ------------------------------------------------------

def test_unknown_receiver_is_searched_for_identified_and_remembered(ffi, lib):
    s = Sim(ffi, lib, Receiver("UBLOX_M10", 38400))
    s.run(10)
    assert s.phase == lib.GNSS_LINK_RUNNING and s.link.module == m(lib, "UBLOX_M10")
    assert s.saves == [(m(lib, "UBLOX_M10"), 38400)]
    assert s.probes()[0] == MON_VER  # it had to ask
    assert any("identified" in line for line in s.logs)


def test_unknown_quectel_is_identified_by_the_second_probe(ffi, lib):
    s = Sim(ffi, lib, Receiver("QUECTEL_LC29H", 115200))
    s.run(15)
    assert s.link.module == m(lib, "QUECTEL_LC29H") and s.phase == lib.GNSS_LINK_RUNNING
    assert s.saves == [(m(lib, "QUECTEL_LC29H"), 115200)]


def test_unknown_ublox7_is_moved_to_38400(ffi, lib):
    rx = Receiver("UBLOX7", 9600)
    s = Sim(ffi, lib, rx)
    s.run(15)
    assert rx.baud == 38400 and s.uart == 38400 and s.phase == lib.GNSS_LINK_RUNNING
    assert s.saves == [(m(lib, "UBLOX7"), 9600)]  # remembered where it was found


# -- later boots: known receiver -------------------------------------------------------

def test_known_receiver_is_configured_without_searching_or_probing(ffi, lib):
    s = Sim(ffi, lib, Receiver("UBLOX_M10", 38400), known_module="UBLOX_M10", known_baud=38400)
    s.run(10)
    assert s.phase == lib.GNSS_LINK_RUNNING
    assert s.first_config_time() < 1.5    # the first data arrives at once; no 2.5 s search, no probe wait
    assert s.sent[0][1][2:4] == b"\x06\x8a"  # CFG-VALSET is the first thing sent
    assert s.saves == []                  # nothing changed: no flash write
    assert any("as last time" in line for line in s.logs)


def test_known_ublox7_after_an_esp32_only_reset(ffi, lib):
    """The receiver stayed powered, so it is still at 38400, not the 9600 it was found at."""
    rx = Receiver("UBLOX7", 38400)
    s = Sim(ffi, lib, rx, known_module="UBLOX7", known_baud=9600)
    s.run(10)
    assert s.phase == lib.GNSS_LINK_RUNNING and rx.baud == 38400
    assert s.probes() == [MON_VER]  # only the MON-VER at the end of the configuration
    assert s.saves == [(m(lib, "UBLOX7"), 38400)]


def test_known_ublox7_after_a_power_cut(ffi, lib):
    rx = Receiver("UBLOX7", 9600)
    s = Sim(ffi, lib, rx, known_module="UBLOX7", known_baud=9600)
    s.run(10)
    assert s.phase == lib.GNSS_LINK_RUNNING and rx.baud == 38400 and s.uart == 38400
    assert s.first_config_time() < 1.5 and s.saves == []


def test_identity_reply_fills_in_the_model(ffi, lib):
    s = Sim(ffi, lib, Receiver("QUECTEL_LC29H", 115200), known_module="QUECTEL_LC29H", known_baud=115200)
    s.run(5)
    assert ffi.string(s.state.model) == b"LC29H(AA)"


# -- the receiver was changed ---------------------------------------------------------

def test_remembered_receiver_not_found_falls_back_to_a_search(ffi, lib):
    s = Sim(ffi, lib, Receiver("QUECTEL_LC29H", 115200), known_module="UBLOX_M10", known_baud=38400)
    s.run(20)
    assert s.link.module == m(lib, "QUECTEL_LC29H") and s.phase == lib.GNSS_LINK_RUNNING
    assert s.saves[-1] == (m(lib, "QUECTEL_LC29H"), 115200)
    assert any("searching" in line for line in s.logs)


def test_a_different_receiver_at_the_same_speed_is_noticed_and_remembered(ffi, lib):
    """An M10 remembered, a configured u-blox 7 (also at 38400) connected: its
    MON-VER reply gives it away, and it is configured as what it is."""
    rx = Receiver("UBLOX7", 38400)
    s = Sim(ffi, lib, rx, known_module="UBLOX_M10", known_baud=38400)
    s.run(15)
    assert s.link.module == m(lib, "UBLOX7") and s.phase == lib.GNSS_LINK_RUNNING
    assert s.saves[-1] == (m(lib, "UBLOX7"), 38400)
    assert any("not m10" in line for line in s.logs)
    assert any(d.startswith(b"\xb5\x62\x06\x00") for _, d in s.sent)  # the u-blox 7's CFG-PRT went out


def test_fixed_module_is_kept_and_the_mismatch_logged_once(ffi, lib):
    s = Sim(ffi, lib, Receiver("UBLOX_M10", 38400), fixed_module="UBLOX_M8")
    s.run(30)
    assert s.link.module == m(lib, "UBLOX_M8") and s.phase == lib.GNSS_LINK_RUNNING
    assert sum("GpsModule says m8" in line for line in s.logs) == 1
    assert s.probes() == [MON_VER]  # no identification probe: only the configuration's MON-VER


def test_fixed_module_skips_probing_even_on_first_boot(ffi, lib):
    s = Sim(ffi, lib, Receiver("QUECTEL_LC29H", 115200), fixed_module="QUECTEL_LC29H")
    s.run(10)
    assert s.sent[0][1] == b"$PQTMVERNO*58\r\n"  # the configuration's own first command
    assert s.first_config_time() < 1.5
    assert s.saves == [(0, 115200)]  # only the speed is remembered


def test_fixed_baud_is_the_only_speed_tried(ffi, lib):
    s = Sim(ffi, lib, Receiver("UBLOX_M10", 38400), fixed_baud=115200)
    s.run(20)
    assert s.phase != lib.GNSS_LINK_RUNNING and s.uart == 115200


# -- while running -------------------------------------------------------------------

def test_silent_receiver_is_looked_for_again(ffi, lib):
    rx = Receiver("UBLOX_M10", 38400, silent_from=8)
    s = Sim(ffi, lib, rx, known_module="UBLOX_M10", known_baud=38400)
    s.run(8)
    assert s.phase == lib.GNSS_LINK_RUNNING
    s.run(11)
    assert any("silent" in line for line in s.logs)
    assert s.phase == lib.GNSS_LINK_LISTEN  # looked for as the known receiver
    rx.silent_from = 1e12
    s.run(5)
    assert s.phase == lib.GNSS_LINK_RUNNING


def test_forget_identifies_from_scratch(ffi, lib):
    s = Sim(ffi, lib, Receiver("UBLOX_M10", 38400), known_module="UBLOX_M10", known_baud=38400)
    s.run(5)
    lib.gnss_link_forget(s.link, s.state, int(s.t * 1000), s.action)
    assert s.action.save and s.link.cfg.known_module == 0 and s.link.phase == lib.GNSS_LINK_SEARCH
    s.run(10)
    assert s.link.module == m(lib, "UBLOX_M10") and MON_VER in s.probes()


# -- the helpers ----------------------------------------------------------------------

@pytest.mark.parametrize("module,last,expected", [
    ("UBLOX7", 9600, [9600, 38400]),
    ("UBLOX7", 38400, [38400, 9600]),
    ("UBLOX7", 0, [38400, 9600]),
    ("UBLOX_M10", 38400, [38400]),
    ("QUECTEL_LC29H", 115200, [115200]),
    ("QUECTEL_LC29H", 9600, [9600, 115200]),
])
def test_boot_bauds(ffi, lib, module, last, expected):
    out = ffi.new("uint32_t[4]")
    n = lib.gnss_module_boot_bauds(m(lib, module), last, out, 4)
    assert list(out[0:n]) == expected


@pytest.mark.parametrize("key,module", [
    ("auto", "UNKNOWN"), ("ublox7", "UBLOX7"), ("M8", "UBLOX_M8"), ("m10", "UBLOX_M10"), ("LC29H", "QUECTEL_LC29H"),
])
def test_module_keys(ffi, lib, key, module):
    out = ffi.new("uint8_t *")
    assert lib.gnss_module_from_key(key.encode(), out) and out[0] == m(lib, module)
    assert ffi.string(lib.gnss_module_key(out[0])).decode() == key.lower()


def test_unknown_key(ffi, lib):
    out = ffi.new("uint8_t *")
    assert not lib.gnss_module_from_key(b"m9", out)
    assert not lib.gnss_module_from_key(b"m1", out)
    assert not lib.gnss_module_from_key(b"", out)
