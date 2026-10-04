# Firmware

Tasmota for an ESP32-C3 SuperMini wired to a GPS receiver, as in
[docs/wiring.md](../docs/wiring.md).

> [!WARNING]
> Not yet run on hardware. The host tests pass against real captures from
> the receivers on ten64; the [bench runbook](docs/bench-runbook.md) is what
> confirms it on the ESP32.

## Where the code is

The driver is Tasmota's own GPS driver, `xsns_60_GPS.ino`, extended in the
fork [mithro/Tasmota](https://github.com/mithro/Tasmota/tree/esp32-to-gps),
branch `esp32-to-gps`, which is based on upstream `development` and kept up
to date by merging it in. All the protocol work is pure C in
`tasmota/tasmota_xsns_sensor/gnss/` in the fork:

| File | Does |
|---|---|
| `gnss_state` | everything known about the receiver, and the satellite table |
| `gnss_stream` | splits the serial stream into NMEA sentences and UBX frames |
| `gnss_nmea` | NMEA, including the Quectel replies |
| `gnss_ubx` | UBX decoding, and the commands sent to u-blox receivers |
| `gnss_module` | identifies the receiver and lists its configuration |
| `gnss_rtcm` | watches the corrections, strips HTTP chunking, speaks NTRIP |
| `gnss_json` | the MQTT JSON and the Home Assistant discovery |

This repository holds the build settings, the host tests and the docs.

## What it does

* Finds the receiver's speed (9600, 38400, 115200), identifies it (UBX
  MON-VER, then Quectel `$PQTMVERNO`) and configures it in RAM.
* Reads everything the receiver reports: position, time, motion, accuracy,
  DOPs, every satellite with its signal, antenna and jamming status.
* Fetches RTCM corrections from the NTRIP proxy on ten64 and passes them to
  the receiver: `ADDE_RTCM23` for the u-blox 7, `ADDE_RTCM3` for the others.
* Counts PPS pulses on the GPIO set to "GPS PPS".
* Publishes it all over MQTT with Home Assistant discovery: 66 entities.
  See [docs/mqtt-home-assistant.md](docs/mqtt-home-assistant.md).
* Keeps the driver's earlier features: NTP server, flash track log and GPX
  download, the TCP serial bridge, `Sensor60` commands.

## Build

```
uv run firmware/build.py
```

This clones the fork at the commit pinned in `build.py` into
`firmware/build/Tasmota`, copies in `overlay/`, builds `tasmota32c3-gps` with
pioarduino (the PlatformIO fork upstream Tasmota uses) and puts the images
in `firmware/dist/`. To build a local checkout of the fork instead:

```
TASMOTA_DIR=~/github/mithro/Tasmota/.worktrees/esp32-to-gps uv run firmware/build.py
```

## Test

```
uv run firmware/build.py --fetch-only     # or set TASMOTA_DIR
uv run --with pytest --with cffi --with pyubx2 --with pynmeagps --with pyrtcm --with jinja2 pytest firmware/tests
```

The tests compile the fork's `gnss/*.c` with `-Wall -Wextra -Wconversion
-Werror` and drive it through cffi. They check it against:

* real serial captures from the MAX-M10S receivers on ten64 and
  rpi-sdr-pluto, and the ten64 NTRIP proxy (see [fixtures/](fixtures/));
* pyubx2, pynmeagps and pyrtcm decoding the same data, and decoding every
  command the firmware sends;
* Jinja2 rendering every Home Assistant template against the firmware's JSON.

## Updating the fork

1. In the fork, merge upstream `development` into `esp32-to-gps` (never
   rebase: the branch is published).
2. Push it, and set `TASMOTA_SHA` in `build.py` to the new commit in its own
   commit here.
