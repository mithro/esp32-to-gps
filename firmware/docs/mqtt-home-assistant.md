# MQTT and Home Assistant

What the firmware publishes, and the Home Assistant entities it creates.
`<topic>` is the device's Tasmota topic (`Topic` command).

## Topics

| Topic | When | Retained | Contents |
|---|---|---|---|
| `tele/<topic>/GNSS` | every `GpsPeriod` seconds (default 10) | no | the full receiver state, below |
| `tele/<topic>/GNSS_SATS` | every 30 s | no | the satellite table |
| `tele/<topic>/SENSOR` | every `TelePeriod` | no | Tasmota's own `GPS` object (`Lat`, `Lon`, `Alt`, `hAcc`, `vAcc`, `Fix`, `Sats`, `Spd`, `Hdng`, `sAcc`), kept for existing rules |
| `tele/<topic>/LWT` | Tasmota's | yes | `Online` / `Offline`: every entity's availability |
| `homeassistant/<component>/gps_<mac>/<entity>/config` | after connecting, and again once the receiver is identified | yes | discovery, one per entity |

Unknown values are JSON `null`, so Home Assistant shows them as unknown
rather than as zero: there is no position without a fix, no GDOP from a
receiver that only speaks NMEA, no antenna status from one that does not
report it.

## `tele/<topic>/GNSS`

```json
{
  "Time": "2026-10-04T07:13:49Z", "Fix": "3D", "FixType": 3, "Quality": "GNSS", "QualityId": 1,
  "Lat": -34.9284653, "Lon": 138.6007062, "AltMSL": 25.700, "AltEllipsoid": 24.500, "GeoidSep": -1.200,
  "HAcc": 1.500, "VAcc": 2.300, "SAcc": 0.410, "TAcc": 25, "Speed": 0.036, "Course": 123.45000,
  "HDOP": 0.91, "VDOP": 1.34, "PDOP": 1.62, "GDOP": 1.91, "TDOP": 1.01,
  "SatsUsed": 16, "SatsInView": 36,
  "Constellations": {"GPS": {"InView": 11, "Used": 7}, "GLONASS": {"InView": 0, "Used": 0},
                     "Galileo": {"InView": 12, "Used": 5}, "BeiDou": {"InView": 12, "Used": 3},
                     "QZSS": {"InView": 1, "Used": 1}, "SBAS": {"InView": 0, "Used": 0}},
  "CNo": {"Min": 21, "Avg": 34, "Max": 45},
  "DiffAge": null, "DiffStation": null,
  "Corrections": {"State": "Connected", "Mount": "ADDE_RTCM3", "Error": null, "Bytes": 27869,
                  "Frames": 77, "BadCRC": 0, "Age": 1, "Types": "1006,1077,1087,1097,1117,1127,1013,1033,1230,4094",
                  "Station": 200, "Used": 40, "Failed": 0},
  "Receiver": {"Model": "MAX-M10S", "Firmware": "SPG 5.10", "Hardware": "000A0000", "Protocol": "34.10",
               "Baud": 38400, "Antenna": "OK", "Jamming": 17, "Noise": 82, "QErr": null},
  "PPS": {"Present": true, "Count": 1234},
  "Health": {"NMEA": 684, "NMEABad": 0, "UBX": 186, "UBXBad": 0, "LastData": 0}
}
```

| Field | Meaning |
|---|---|
| `Time` | UTC from the receiver, ISO 8601; null until it has both time and date |
| `Fix`, `FixType` | none, dead reckoning, 2D, 3D, GNSS + dead reckoning, time only (UBX NAV-PVT `fixType`, or NMEA GSA) |
| `Quality`, `QualityId` | the NMEA GGA quality: GNSS, DGNSS, RTK float, RTK fixed, ... |
| `Lat`, `Lon` | degrees, 7 decimal places |
| `AltMSL`, `AltEllipsoid`, `GeoidSep` | metres above mean sea level, above the WGS84 ellipsoid, and the difference |
| `HAcc`, `VAcc`, `SAcc`, `TAcc` | the receiver's own accuracy estimates: metres, metres, m/s, ns (UBX NAV-PVT, or NMEA GST) |
| `Speed`, `Course` | m/s over ground, degrees true |
| `HDOP` ... `TDOP` | dilution of precision |
| `SatsUsed`, `SatsInView`, `Constellations` | counts, in total and per constellation |
| `CNo` | carrier-to-noise density of the satellites used in the fix, dB-Hz |
| `DiffAge`, `DiffStation` | the receiver's report (NMEA GGA) of the corrections it applied |
| `Corrections` | the NTRIP side: connection `State`, `Mount`, the last `Error`, bytes and RTCM 3 `Frames` received, `BadCRC`, seconds since the last good frame (`Age`), RTCM message `Types` seen, base `Station` (RTCM 1005/1006); and the receiver's RXM-RTCM count of messages it `Used` and `Failed` (u-blox M8 and M10) |
| `Receiver` | identity, UART speed, antenna status, jamming indicator (0-255), noise level, TIM-TP quantization error in ps (LEA-M8T) |
| `PPS` | a pulse in the last 2 s, and the count since boot (needs a GPIO set to "GPS PPS") |
| `Health` | frames decoded and rejected since boot; seconds since the last good frame |

## `tele/<topic>/GNSS_SATS`

```json
{"InView": 36, "Used": 16,
 "Sats": [["G05", "GPS", 45, 123, 40, true], ["E07", "Galileo", 12, 300, 33, false], ...],
 "CNo": {"G05": 40, "E07": 33, ...}}
```

Each satellite is `[id, constellation, elevation, azimuth, C/N0, used]`;
an unknown elevation, azimuth or C/N0 is null. IDs are a RINEX-style letter
(G GPS, R GLONASS, E Galileo, C BeiDou, J QZSS, S SBAS, I NavIC) and the
satellite number.

## Home Assistant entities

All on one device per ESP32, named after its Tasmota `DeviceName`, with the
receiver model as the device model. "Diagnostic" entities are in the
device's diagnostic section.

| ID | Name | Component | Source | Unit | Category |
|---|---|---|---|---|---|
| `location` | Location | device_tracker | `GNSS`: `Lat, Lon, HAcc` |  |  |
| `lat` | Latitude | sensor | `GNSS`: `Lat` | ° |  |
| `lon` | Longitude | sensor | `GNSS`: `Lon` | ° |  |
| `alt` | Altitude | sensor | `GNSS`: `AltMSL` | m |  |
| `alt_ellipsoid` | Height above ellipsoid | sensor | `GNSS`: `AltEllipsoid` | m | diagnostic |
| `geoid_sep` | Geoid separation | sensor | `GNSS`: `GeoidSep` | m | diagnostic |
| `fix` | Fix | sensor | `GNSS`: `Fix` |  |  |
| `quality` | Fix quality | sensor | `GNSS`: `Quality` |  |  |
| `h_acc` | Horizontal accuracy | sensor | `GNSS`: `HAcc` | m |  |
| `v_acc` | Vertical accuracy | sensor | `GNSS`: `VAcc` | m |  |
| `s_acc` | Speed accuracy | sensor | `GNSS`: `SAcc` | m/s | diagnostic |
| `t_acc` | Time accuracy | sensor | `GNSS`: `TAcc` | ns | diagnostic |
| `hdop` | HDOP | sensor | `GNSS`: `HDOP` |  |  |
| `vdop` | VDOP | sensor | `GNSS`: `VDOP` |  | diagnostic |
| `pdop` | PDOP | sensor | `GNSS`: `PDOP` |  | diagnostic |
| `gdop` | GDOP | sensor | `GNSS`: `GDOP` |  | diagnostic |
| `tdop` | TDOP | sensor | `GNSS`: `TDOP` |  | diagnostic |
| `speed` | Speed | sensor | `GNSS`: `Speed` | m/s |  |
| `course` | Course | sensor | `GNSS`: `Course` | ° |  |
| `time` | GNSS time | sensor | `GNSS`: `Time` |  |  |
| `pps` | PPS | binary_sensor | `GNSS`: `PPS.Present` |  | diagnostic |
| `pps_count` | PPS pulses | sensor | `GNSS`: `PPS.Count` |  | diagnostic |
| `sats_used` | Satellites used | sensor | `GNSS`: `SatsUsed` |  |  |
| `sats_in_view` | Satellites in view | sensor | `GNSS`: `SatsInView` |  |  |
| `gps_in_view` | GPS satellites in view | sensor | `GNSS`: `Constellations.GPS.InView` |  |  |
| `gps_used` | GPS satellites used | sensor | `GNSS`: `Constellations.GPS.Used` |  |  |
| `glonass_in_view` | GLONASS satellites in view | sensor | `GNSS`: `Constellations.GLONASS.InView` |  |  |
| `glonass_used` | GLONASS satellites used | sensor | `GNSS`: `Constellations.GLONASS.Used` |  |  |
| `galileo_in_view` | Galileo satellites in view | sensor | `GNSS`: `Constellations.Galileo.InView` |  |  |
| `galileo_used` | Galileo satellites used | sensor | `GNSS`: `Constellations.Galileo.Used` |  |  |
| `beidou_in_view` | BeiDou satellites in view | sensor | `GNSS`: `Constellations.BeiDou.InView` |  |  |
| `beidou_used` | BeiDou satellites used | sensor | `GNSS`: `Constellations.BeiDou.Used` |  |  |
| `qzss_in_view` | QZSS satellites in view | sensor | `GNSS`: `Constellations.QZSS.InView` |  |  |
| `qzss_used` | QZSS satellites used | sensor | `GNSS`: `Constellations.QZSS.Used` |  |  |
| `sbas_in_view` | SBAS satellites in view | sensor | `GNSS`: `Constellations.SBAS.InView` |  |  |
| `sbas_used` | SBAS satellites used | sensor | `GNSS`: `Constellations.SBAS.Used` |  |  |
| `cno_min` | Signal C/N0 minimum | sensor | `GNSS`: `CNo.Min` | dB-Hz |  |
| `cno_avg` | Signal C/N0 average | sensor | `GNSS`: `CNo.Avg` | dB-Hz |  |
| `cno_max` | Signal C/N0 maximum | sensor | `GNSS`: `CNo.Max` | dB-Hz |  |
| `satellites` | Satellites | sensor | `GNSS_SATS`: `InView` |  |  |
| `corr_state` | Corrections | sensor | `GNSS`: `Corrections.State` |  |  |
| `corr_mount` | Corrections mountpoint | sensor | `GNSS`: `Corrections.Mount` |  | diagnostic |
| `corr_error` | Corrections error | sensor | `GNSS`: `Corrections.Error` |  | diagnostic |
| `corr_bytes` | Corrections received | sensor | `GNSS`: `Corrections.Bytes` | B | diagnostic |
| `corr_frames` | RTCM frames received | sensor | `GNSS`: `Corrections.Frames` |  | diagnostic |
| `corr_bad_crc` | RTCM CRC errors | sensor | `GNSS`: `Corrections.BadCRC` |  | diagnostic |
| `corr_age` | Corrections age | sensor | `GNSS`: `Corrections.Age` | s |  |
| `corr_types` | RTCM message types | sensor | `GNSS`: `Corrections.Types` |  | diagnostic |
| `corr_station` | Corrections base station | sensor | `GNSS`: `Corrections.Station` |  | diagnostic |
| `diff_age` | Differential age | sensor | `GNSS`: `DiffAge` | s |  |
| `diff_station` | Differential station | sensor | `GNSS`: `DiffStation` |  | diagnostic |
| `rtcm_used` | RTCM messages used | sensor | `GNSS`: `Corrections.Used` |  | diagnostic |
| `rtcm_failed` | RTCM messages rejected | sensor | `GNSS`: `Corrections.Failed` |  | diagnostic |
| `model` | Receiver model | sensor | `GNSS`: `Receiver.Model` |  | diagnostic |
| `firmware` | Receiver firmware | sensor | `GNSS`: `Receiver.Firmware` |  | diagnostic |
| `protocol` | Receiver protocol version | sensor | `GNSS`: `Receiver.Protocol` |  | diagnostic |
| `baud` | Receiver UART speed | sensor | `GNSS`: `Receiver.Baud` | Bd | diagnostic |
| `antenna` | Antenna | sensor | `GNSS`: `Receiver.Antenna` |  |  |
| `jamming` | Jamming indicator | sensor | `GNSS`: `Receiver.Jamming` |  | diagnostic |
| `noise` | Noise level | sensor | `GNSS`: `Receiver.Noise` |  | diagnostic |
| `qerr` | Timepulse quantization error | sensor | `GNSS`: `Receiver.QErr` | ps | diagnostic |
| `nmea` | NMEA sentences | sensor | `GNSS`: `Health.NMEA` |  | diagnostic |
| `nmea_bad` | NMEA sentences bad | sensor | `GNSS`: `Health.NMEABad` |  | diagnostic |
| `ubx` | UBX messages | sensor | `GNSS`: `Health.UBX` |  | diagnostic |
| `ubx_bad` | UBX messages bad | sensor | `GNSS`: `Health.UBXBad` |  | diagnostic |
| `last_data` | Since last receiver data | sensor | `GNSS`: `Health.LastData` | s | diagnostic |

The **Satellites** sensor carries the whole `GNSS_SATS` message as its
attributes.

### Per-satellite entities

`GpsSatEntities 1` adds one sensor per satellite, `<Constellation> <number>
C/N0`, created when the satellite is first seen and unavailable two minutes
after it leaves view. `GpsSatEntities 0` (the default) removes them again.
There can be 60 or more at once on a multi-constellation receiver.

## Commands

| Command | Meaning |
|---|---|
| `GpsModule auto\|ublox7\|m8\|m10\|lc29h` | the receiver type. `auto` (the default) identifies it once and remembers it; a type set here is used without identifying |
| `GpsBaud <speed>` | fix the receiver's UART speed; `0` finds it (default) |
| `GpsConfig` | every setting, including the remembered receiver and its speed (the NTRIP password shows as `****`) |
| `GpsNtrip 0` | corrections off |
| `GpsNtrip 1` | corrections from the ten64 proxy, `10.1.10.1:2101`, mountpoint by receiver (default) |
| `GpsNtrip <host>:<port>/<mount>[ <user> <password>]` | corrections from another caster |
| `GpsPeriod <seconds>` | how often `GNSS` is published, 1-3600 |
| `GpsSatEntities 0\|1` | per-satellite entities |
| `GpsHass 0\|1` | Home Assistant discovery |
| `GpsReinit` | forget the remembered receiver and identify it again; with `GpsModule` set, configure it again |
| `GpsStatus` | reply with the full state, as on `GNSS` |

Settings are kept in `/gnss.cfg` on the ESP32's file system. The older
`Sensor60` commands work as before.

### Start-up

The first time, the firmware searches 9600, 38400 and 115200 baud for the
receiver, identifies it (UBX MON-VER, then Quectel `$PQTMVERNO`) and saves
the type and the speed it was found at. After that it opens the UART at that
speed (or the speed it runs the receiver at, or the receiver's power-up
default) and configures the receiver as soon as data arrives: no search, no
identification. It falls back to a full search only if the receiver stays
silent at those speeds.

The configuration itself is sent at every start, because it goes to the
receiver's RAM: the MAX-M10S has no flash, and none of the receivers keeps
it through a power cut. Each configuration ends with an identity query. If
the reply shows a different receiver from the remembered one, the new one is
saved and configured. A receiver set with `GpsModule` is kept, and the
mismatch is logged.

| Receiver | Corrections mountpoint |
|---|---|
| u-blox 7 | `ADDE_RTCM23` (RTCM 2.3, the only kind it takes) |
| u-blox M8 (LEA-M8T), M10 (MAX-M10S), Quectel LC29H | `ADDE_RTCM3` |
