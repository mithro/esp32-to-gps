# Firmware design: Tasmota GPS driver for esp32-to-gps

Date: 2026-10-04. Status: agreed in conversation, written down here.

## Goal

Tasmota firmware for an ESP32-C3 SuperMini wired to one GPS receiver (see
[docs/wiring.md](../../wiring.md)) that:

1. works with all four supported receivers: the u-blox 7 board ("GT-U7"),
   the MAX-M10S, the Quectel LC29H(AA) and the LEA-M8T;
2. publishes **all** receiver state to Home Assistant over MQTT, with
   discovery;
3. pulls RTCM corrections from the NTRIP proxy on ten64 and feeds them to
   the receiver.

## Decisions already made

| Decision | Choice |
|---|---|
| ESP32 board | ESP32-C3 SuperMini, native USB console |
| GPS UART pins | GPIO4 TX, GPIO3 RX, GPIO1 PPS ([wiring](../../wiring.md)) |
| Approach | Extend Tasmota's own GPS driver, `xsns_60_GPS.ino` |
| Where the changes live | A fork, `mithro/Tasmota`, branch `esp32-to-gps`. Not sent upstream. |
| Fork base | Upstream `development` (`b5a73b8a7`, 2026-09-30, 15.6.0.2), kept current by merging upstream `development` in. Never rebased. |
| Satellites in Home Assistant | Summary sensors plus the full table as attributes; one entity per satellite behind a switch, off by default |

## Two repositories

**`mithro/Tasmota`, branch `esp32-to-gps`:**

* `tasmota/tasmota_xsns_sensor/xsns_60_GPS.ino` is extended in place. It
  keeps its existing features (NTP server, flash log, TCP serial bridge) and
  its existing `GPS` JSON in `tele/<topic>/SENSOR`.
* New pure C99 files in `tasmota/tasmota_xsns_sensor/gnss/`, with no Tasmota
  or Arduino dependency, hold all the protocol logic. PlatformIO compiles
  every source under `tasmota/`, which esp32-to-433mhz relied on for its own
  pure-C directory.

**`mithro/esp32-to-gps` (this repository), `firmware/`:**

* `build.py` clones the fork at a pinned commit SHA, adds
  `platformio_override.ini` and `user_config_override.h`, and builds
  `env:tasmota32c3-gps`. It refuses to build if the checkout is not at the
  pinned SHA.
* `tests/` compiles the fork's `gnss/*.c` on the host and tests it with
  pytest through ctypes, so the tests run exactly the code the device runs.
* `fixtures/` holds serial captures from the real receivers, with every
  position moved to a public reference point (see Fixtures below).
* `docs/mqtt-home-assistant.md` lists every topic and entity.

## Pure-C core (`gnss/`)

| File | Responsibility |
|---|---|
| `gnss_state.h` | One `gnss_state_t` struct holding everything known about the receiver: time, fix, position, velocity, accuracy, DOPs, satellite table, module identity, antenna, corrections and error counters. |
| `gnss_stream.c` | Byte-at-a-time demultiplexer: splits the receiver's output into NMEA sentences and UBX frames, checks checksums, counts good and bad frames. |
| `gnss_nmea.c` | GGA, RMC, GSA, GSV, VTG, GLL, ZDA, GST and TXT, any talker (GP, GL, GA, GB, BD, GQ, GI, GN), NMEA 4.10/4.11 system and signal IDs. Quectel `$PQTMVERNO` and `$PAIR` replies. |
| `gnss_ubx.c` | UBX decode: NAV-PVT, NAV-DOP, NAV-SAT, NAV-SVINFO (u-blox 7 has no NAV-SAT), MON-VER, MON-HW, MON-RF, RXM-RTCM, TIM-TP, ACK. UBX encode: polls, CFG-MSG, CFG-VALSET. |
| `gnss_module.c` | Receiver identification from MON-VER or `$PQTMVERNO`, and the configuration command list for each receiver. |
| `gnss_rtcm.c` | RTCM 3 framing with CRC-24Q and per-message-type counts; byte counting for RTCM 2.3, which is passed through unparsed. |
| `gnss_ntrip.c` | NTRIP request builder and response-header parser (v1 `ICY 200 OK` and v2 `HTTP/1.1 200 OK`). The socket itself stays in the `.ino`. |
| `gnss_json.c` | The state JSON, the satellite JSON and the Home Assistant discovery JSON, written into caller-supplied buffers. |

No heap allocation; fixed-size tables (64 satellites). Every function is
callable from the host tests.

## Receivers

Identification runs at boot and whenever the receiver goes quiet:

1. Listen at 9600, 38400 and 115200 baud in turn until valid NMEA or UBX
   arrives. A configured speed (`GpsBaud`) skips the search.
2. Send a UBX MON-VER poll. A reply identifies a u-blox receiver by its
   hardware version (`00070000` u-blox 7, `00080000` M8, `000A0000` M10) and
   its extension strings (`MOD=`, `FWVER=`, `PROTVER=`).
3. Otherwise send `$PQTMVERNO`. A reply identifies a Quectel LC29H.

Configuration is written to RAM only and re-sent after every
identification. The MAX-M10S has no flash, so this is required there; doing
it the same way for every receiver means none depends on saved settings.

| Receiver | Configure with | Output used | Corrections mountpoint (default) |
|---|---|---|---|
| u-blox 7 | legacy CFG-MSG | UBX NAV-PVT, NAV-DOP, NAV-SVINFO, MON-HW; NMEA GGA, RMC | `ADDE_RTCM23` (RTCM 2.3, the only kind it takes) |
| MAX-M10S | CFG-VALSET, RAM layer, key IDs as already used on ten64 | UBX NAV-PVT, NAV-DOP, NAV-SAT, MON-RF, RXM-RTCM; NMEA GGA, RMC | `ADDE_RTCM3` |
| LEA-M8T | legacy CFG-MSG | as the u-blox 7, with NAV-SAT instead of NAV-SVINFO, plus RXM-RTCM and TIM-TP | `ADDE_RTCM3` (untested) |
| LC29H(AA) | its defaults; queries only | NMEA GGA, RMC, GSA, GSV, VTG, GST, ZDA | `ADDE_RTCM3` (untested) |

NMEA GSA, GSV, GLL and VTG are turned off on the u-blox receivers because
UBX carries the same information more completely, and 9600 baud on the
u-blox 7 has no room for both. GGA stays on for the age and station of
the differential corrections, which UBX NAV-PVT does not report.

The corrections mountpoint can be overridden, or corrections switched off,
with a command.

## Corrections (NTRIP)

* Default caster `10.1.10.1:2101`, the proxy's address on the network the
  IoT VLAN is allowed to reach. The proxy needs no login.
* NTRIP v2 request; a v1 `ICY 200 OK` reply is also accepted.
* Bytes go straight to the receiver's UART. RTCM 3 frames are checked
  (CRC-24Q) and counted by message type for Home Assistant; RTCM 2.3 is only
  counted.
* Reconnect with backoff (5 s doubling to 5 min) after a failure.
* The receiver's own view of the corrections (NMEA GGA differential age and
  station, UBX RXM-RTCM used/failed counts, NAV-PVT `diffSoln`) is published
  alongside, so Home Assistant shows both "corrections are arriving" and
  "the receiver is using them".

## MQTT and Home Assistant

* `tele/<topic>/SENSOR` keeps Tasmota's existing `GPS` object (latitude,
  longitude, altitude, accuracy, fix) so existing Tasmota rules still work.
* `tele/<topic>/GNSS`: the full state as JSON, every `GpsPeriod` seconds
  (default 10).
* `tele/<topic>/GNSS_SATS`: the satellite table as JSON, every 30 s.
* Discovery: retained `homeassistant/<component>/<device-id>/<field>/config`
  messages published by the driver itself, because Tasmota's own discovery
  only knows a fixed list of sensor keys, and none of them are GPS ones.
  Availability is Tasmota's `tele/<topic>/LWT`.

Entities, all on one Home Assistant device per ESP32:

| Group | Entities |
|---|---|
| Position | device tracker (latitude, longitude, accuracy); latitude; longitude; altitude above mean sea level; height above the ellipsoid; geoid separation |
| Fix | fix type (none, 2D, 3D, time only, ...); fix quality (GPS, DGPS, RTK float, RTK fixed, ...); time to first fix |
| Accuracy | horizontal, vertical, speed and time accuracy; HDOP, VDOP, PDOP, GDOP, TDOP |
| Motion | ground speed; course |
| Time | GNSS UTC time; PPS present and pulse count |
| Satellites | in view and used, in total and for each of GPS, GLONASS, Galileo, BeiDou, QZSS, SBAS; C/N0 average, maximum and minimum of the used satellites; a "Satellites" sensor carrying the full table (constellation, ID, elevation, azimuth, C/N0, used) as attributes |
| Per satellite (switch, off by default) | one C/N0 sensor per satellite, created when it is first seen and unavailable after 2 minutes out of view |
| Corrections | connection state; mountpoint; bytes and RTCM frames received; age of the last frame; RTCM 3 message types seen; CRC errors; receiver's differential age and station; RTCM messages used and failed (u-blox M8/M10) |
| Receiver | model; firmware version; protocol version; UART speed; antenna status; jamming indicator; noise level; TIM-TP quantization error (LEA-M8T) |
| Health | NMEA and UBX frames good and bad; seconds since the last valid data |

## Commands

| Command | Meaning |
|---|---|
| `GpsBaud <n>` | Fix the UART speed; 0 searches (default) |
| `GpsNtrip <host>:<port>/<mount>` | Caster and mountpoint; `0` disables corrections; `1` restores the per-receiver default |
| `GpsPeriod <s>` | How often `GNSS` is published |
| `GpsSatEntities 0|1` | Per-satellite Home Assistant entities |
| `GpsHass 0|1` | Home Assistant discovery on or off |
| `GpsReinit` | Identify and configure the receiver again |

The existing `Sensor60` commands are unchanged.

## UART throughput

The current driver reads the UART every 100 ms into a 256-byte buffer, which
an LC29H at 115200 baud overruns in about 22 ms. The extended driver reads
from `FUNC_LOOP` into a 2 KB buffer and parses as it goes.

## Fixtures and privacy

Captures from the real receivers contain the exact position of the antenna
at the user's house. This repository is public, so before a capture is
committed every position in it (NMEA and UBX) is moved by a fixed offset to
Victoria Square, Adelaide, and the checksums are recomputed. The script that
does this is committed beside the fixtures; the raw captures are not.

## Testing

* **Host (CI):** pytest against the compiled pure-C core. Fixtures are real
  captures, plus frames built with the open-source `pyubx2`, `pynmeagps` and
  `pyrtcm` libraries, which also check every UBX message and configuration
  key the firmware encodes.
* **Build (CI):** the firmware compiles for `tasmota32c3-gps`.
* **Bench:** a runbook per receiver, run on the user's test hardware: it is
  identified, it gets a fix, every Home Assistant entity appears and
  updates, and corrections arrive (and, where the receiver reports it, are
  used). Results go in `firmware/docs/HWTEST-RESULTS.md`.

## Out of scope for now

RTK on the LC29H(AA) (it has no RTK engine), writing configuration to
receiver flash, firmware updates of the receivers, and the carrier PCB.
