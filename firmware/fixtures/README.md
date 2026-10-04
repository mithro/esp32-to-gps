# Receiver captures

Real serial output from the receivers, used by the host tests. Every
position has been moved to Victoria Square, Adelaide by
[anonymise.py](anonymise.py) before being committed, because the receivers
sit at a private address. The raw captures are not committed.

| File | Receiver | Captured | How | Contents |
|---|---|---|---|---|
| `max-m10s-nmea.bin` | u-blox MAX-M10S on ten64 (ROM SPG 5.10, PROTVER 34.10), 38400 baud | 2026-10-04, 30 s | `gpspipe -R` from ten64's read-only gpsd | NMEA only: GGA, RMC, GLL, VTG, ZDA, GSA and GSV for GPS, Galileo and BeiDou. 684 sentences. 3D fix. |
| `max-m10s-ubx.bin` | u-blox MAX-M10S on rpi-sdr-pluto, 38400 baud | 2026-10-04, 30 s | `gpspipe -R` from rpi-sdr-pluto's gpsd, which had put the receiver in binary mode | UBX only: NAV-PVT, NAV-SAT, NAV-SIG, NAV-DOP, NAV-TIMEGPS, NAV-EOE. 186 frames. **No fix**: the antenna there gets a poor view of the sky, so latitude and longitude are 0. NAV-POSECEF and NAV-VELECEF were dropped by the anonymiser. |

No captures yet from the u-blox 7 board, the LC29H(AA) or the LEA-M8T.
They will be taken from the test hardware.

To add one:

```
ssh <host> timeout 32 gpspipe -R > tmp/<name>.raw     # tmp/ is gitignored
uv run firmware/fixtures/anonymise.py tmp/<name>.raw firmware/fixtures/<name>.bin
```

Then check that the result holds no original position before committing it.
