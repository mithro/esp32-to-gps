# Bench runbook

How to confirm the wiring and the firmware on real hardware, one receiver at
a time. This is step 3 of the project: carrier-board work starts only after
every receiver below has passed, or its failure has been explained.

Record each run in [HWTEST-RESULTS.md](HWTEST-RESULTS.md): the date, the
firmware's `build-info-tasmota32c3-gps.json`, and the outcome of every step.

## Before powering anything

1. Wire the receiver as [docs/wiring.md](../../docs/wiring.md) shows, and
   compare every pad name on the board with the diagram.
2. **LC29H:** check that the board's V pad really goes to a regulator (5 V)
   and fit the 1 kΩ / 5.6 kΩ divider on GPIO4 → R1.
3. **LEA-M8T:** find J2 pin 1 with a meter (GND, pin 8, buzzes to the corner
   mounting pads; VANT, pin 1, reads a few ohms to the SMB centre pin), and
   check V+ is fed from 3V3, never 5V.
4. Put the antenna where it sees the sky.

## Flash and set up the ESP32

```
uv run firmware/build.py
esptool.py --chip esp32c3 write_flash 0x0 firmware/dist/tasmota32c3-gps.factory.bin
```

Join the ESP32's WiFi access point, set WiFi, then on **Configuration →
Configure Module** set:

| GPIO | Function |
|---|---|
| GPIO1 | GPS PPS |
| GPIO3 | GPS RX (the plain one, not GPS RX 2 or 3: the driver finds the speed itself) |
| GPIO4 | GPS TX |

Then set MQTT (`MqttHost ha.welland.mithis.com`, the device's `tas-` login)
and `DeviceName`. Once one board is set up, its `Template` command output can
be pasted into the others.

## Per receiver

For each step write down what happened, with the console line or MQTT
message that shows it.

| # | Check | How | Pass when |
|---|---|---|---|
| 0 | Start clean | `GpsModule auto`, then `GpsReinit` | `GpsConfig` shows `"Remembered":{"Module":"none"...}` |
| 1 | The receiver is found and identified | console, `GpsConfig` | log `GPS: identified <model> (<type>) at <baud> baud`; `GpsConfig` now remembers that type and speed |
| 2 | It is configured | console | `GPS: <type> configured`; no `ACK-NAK` piling up (`Health` counters move, `UBXBad` / `NMEABad` stay near 0) |
| 3 | Data flows | `GpsStatus` twice, 10 s apart | `Health.NMEA` or `Health.UBX` rising; `LastData` 0 or 1 |
| 4 | Satellites | `tele/<topic>/GNSS_SATS` | satellites listed with elevation, azimuth and C/N0; per-constellation counts plausible for the receiver |
| 5 | Fix | `GpsStatus` | `Fix` 3D, `Lat` / `Lon` / `AltMSL` right for the bench, `HAcc` reasonable |
| 6 | Time | `Time` in the console, `GpsStatus` | ESP32 clock matches `Time` |
| 7 | PPS | `GpsStatus` | `PPS.Present` true and `PPS.Count` rising once a second (needs a fix on the MAX-M10S) |
| 8 | Corrections arrive | `GpsStatus` | `Corrections.State` Connected, `Frames` (RTCM 3) or `Bytes` (RTCM 2.3) rising, `Age` small, `BadCRC` 0 |
| 9 | Corrections used | `GpsStatus` | the receiver says so: `Quality` DGNSS, `DiffAge` set, or `Corrections.Used` rising. **Record it either way**: on these receivers this is the open question |
| 10 | Home Assistant | the device page in Home Assistant | every entity in [mqtt-home-assistant.md](mqtt-home-assistant.md) present; the values above shown; nothing "unavailable" while the ESP32 is online |
| 11 | Per-satellite entities | `GpsSatEntities 1`, wait a minute, then `GpsSatEntities 0` | entities appear for each satellite, then go away |
| 12 | Recovery | unplug the receiver's supply for 10 s, plug it back | log `receiver silent, looking for it again`, then `<type> receiver at <baud> baud, as last time` and steps 2-3 pass again on their own |
| 13 | Reboot, no detection | `Restart 1` | log `<type> receiver at <baud> baud, as last time` within a few seconds of start, **no** `identified` line; steps 2-8 pass |
| 14 | Power cycle, no detection | cut the power to the ESP32 and the receiver together | as step 13. For the u-blox 7 and LEA-M8T this tests the fall back from 38400 to the 9600 they start at |
| 15 | Swapped receiver | with `GpsModule auto`, wire in a different receiver and restart | it is found and configured as the new type, and `GpsConfig` remembers the new one |

## What to expect from each receiver

| Receiver | Found at | Then runs at | Satellites from | Corrections |
|---|---|---|---|---|
| u-blox 7 board | 9600 (first time) or 38400 (after a configuration, until it loses power) | 38400 | NAV-SVINFO: GPS, SBAS, QZSS, and GLONASS if enabled | `ADDE_RTCM23`. The only one proven to apply DGPS corrections (on ten64, 2026-09-05). |
| MAX-M10S | 38400 | 38400 | NAV-SAT: GPS, Galileo, BeiDou, QZSS | `ADDE_RTCM3`; never seen applied on ten64 |
| LC29H(AA) | 115200 | 115200 | NMEA GSV: GPS, GLONASS, Galileo, BeiDou, QZSS, both bands | `ADDE_RTCM3`; the AA has no RTK engine, so it may ignore them |
| LEA-M8T | 9600 (first time) or 38400 | 38400 | NAV-SAT | `ADDE_RTCM3`; untested. Also check `Receiver.QErr` moves (TIM-TP) |

## Capture fixtures while you are there

Each receiver's real output makes the host tests better. With the receiver
on the ESP32, enable the virtual serial port (`Sensor60 14`), then from a
PC on the same network:

```
timeout 32 nc <esp32-ip> 1234 > tmp/<receiver>.raw
uv run firmware/fixtures/anonymise.py tmp/<receiver>.raw firmware/fixtures/<receiver>.bin
```

and check the result holds no real position before committing it.
