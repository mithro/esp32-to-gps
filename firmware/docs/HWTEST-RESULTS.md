# Bench results

Results of [the bench runbook](bench-runbook.md), newest first.

| Date | Receiver | Firmware (fork SHA) | Steps passed | Notes |
|---|---|---|---|---|
| 2026-10-08 (evening) | u-blox M10 (MAX-M10S), `esp32-gps-max-m10s`, 10.1.90.75 | `e43b15c`, no IPv6 | 0, 1, 2, 3, 8 | on ansells-iot, MQTT to ha.welland, 81 HA entities; corrections Connected on ADDE_RTCM3, 369125 bytes, 1054 frames, 0 bad CRC. No fix yet (0 satellites in view: antenna placement to check) |
| 2026-10-08 (evening) | u-blox 7 (GT-U7), `esp32-gps-gt-u7`, 10.1.90.76 | `e43b15c`, no IPv6 | 0, 1, 2, 3, 8 | as above; ADDE_RTCM23 streaming (21925 bytes; RTCM 2.3 is not framed, so 0 frames is expected). 32 satellites in view, no fix yet |
| 2026-10-08 (evening) | Quectel LC29H(AA), `esp32-gps-lc29h`, 10.1.90.77 | `e43b15c`, no IPv6 | 0, 2, 3, 8; **1 now fails** | as above; ADDE_RTCM3 streaming, 911 frames, message types 1077 1087 1097 1117 1127 1033 4094 1006 1230 1013 1042 1045 1046 1019 1020 1044. **Open:** after the first boot the LC29H no longer answers `$PQTMVERNO` (model and firmware null, `GpsReinit` gives "receiver not identified", with corrections on or off); running on `GpsModule lc29h` |

Bring-up on the network, 2026-10-08 evening (WiFi set over the USB console,
then `gdoc2netcfg tasmota configure`), found three firmware faults, each fixed
and measured on these nodes:

* **Every HTTP command took 2.0-2.3 s** (so gdoc2netcfg's 2 s scan never saw
  the nodes) and the main loop stalled for a minute at a time: with no host
  reading the USB console, arduino-esp32 3.3.12's `HWCDC::write()` waits up to
  2 s per write. Fork `4e5c0ac` sets its TX timeout to 0: 0.06-0.35 s after.
* **The LC29H set the clock to 2080-01-06**: its void RMCs carry a placeholder
  date that the NMEA parser took as valid. Fork `e43b15c` takes RMC's date only
  from a valid fix (host test added).
* **About half of all boots had no DNS server, so no MQTT**: the iot VLAN's
  router advertisements (RDNSS) replaced the DHCPv4 DNS server in lwIP's one DNS
  table, and Tasmota restored it only if it had seen it first (shown by
  instrumenting `WiFiHelper::scrubDNS`: `from(2404:e80:a137:190::1) to
  (0.0.0.0) save4 0.0.0.0` on a failing boot). The nodes get no global IPv6
  there, so the build drops IPv6 (`-UUSE_IPV6`): 12 of 12 restarts kept DNS,
  against 1 of 6, 3 of 10 and 2 of 4 before.

The nodes were then upgraded over the air (Tasmota `Upgrade`, served from
another host on the iot VLAN), which keeps their settings. Still to do: a fix
(steps 4-7), whether the receivers use the corrections (step 9), and PPS.

On 2026-10-17, after 8 days 20 hours up, all three were still on WiFi and MQTT
with corrections streaming (ADDE_RTCM3 1.87 GB and 5.6 million frames to each of
the M10 and LC29H, 0 and 1 bad CRC; ADDE_RTCM23 78 MB to the GT-U7), but none
had a fix: the M10 had 57 satellites and the GT-U7 46 in view, the LC29H none,
and no satellite on any of them had a signal strength (`CNo` null), so none was
being tracked. The in-view counts come from almanac predictions, so the antennas
most likely do not see the sky. Next: move them to a window or outside.
| 2026-10-08 | u-blox M10 (MAX-M10S breakout), ESP32 44:1B:F6:2E:A9:A4 | `8c8defb` | 0, 1, 3 | first flash; `GPS: identified u-blox M10 (m10) at 38400 baud`. SPG 5.10, hardware 000A0000, protocol 34.10. NMEA 720 -> 2064, UBX 3, 0 bad, between reads at uptime 00:01:03 and 00:02:55. No fix yet; no WiFi set, so corrections not tried |
| 2026-10-08 | u-blox 7 (GT-U7), ESP32 44:1B:F6:2F:18:78 | `8c8defb` | 0, 1, 3 | first flash; `GPS: identified u-blox 7 (ublox7) at 9600 baud`, then moved to 38400. Firmware 1.00 (59842), hardware 00070000, protocol 14.00. NMEA 185 -> 399, UBX 604 -> 1267, 0 bad. 16 GPS satellites in view, no fix yet; antenna OK. No WiFi set |
| 2026-10-08 | Quectel LC29H(AA), ESP32 E8:3D:C1:8C:5C:BC | `8c8defb` | 0, 1, 3 | first flash; `GPS: identified LC29H(AA) (lc29h) at 115200 baud`. Firmware LC29HAANR11A05S, hardware AG3335M. NMEA 1427 -> 3075, 0 bad. No fix yet; its clock read 2080-01-06 before a fix. No WiFi set |

All three on rpiz-gps, flashed over USB with the factory image built by
`firmware/build.py` at the pinned commit (build-info `built`
2026-10-08T14:30:35+10:30, `pinned` true, `fork_dirty` false), GPIO1 / 3 / 4
set to GPS PPS / GPS RX / GPS TX from the console. Each node found and
identified its receiver on its own at first boot (`GpsModule auto`), and
`GpsConfig` remembers it. The udev names they have on rpiz-gps are in
[hardware/udev/](../../hardware/udev/).
