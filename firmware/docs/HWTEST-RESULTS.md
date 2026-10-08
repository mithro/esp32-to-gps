# Bench results

Results of [the bench runbook](bench-runbook.md), newest first.

| Date | Receiver | Firmware (fork SHA) | Steps passed | Notes |
|---|---|---|---|---|
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
