"""The GPS receiver boards this project supports, and how each one is wired
to the ESP32-C3 SuperMini.

This is the single source for the wiring diagrams and the wiring tables in
the docs.  Pad names are the ones printed on each board, in board order.
Where each fact comes from is recorded in docs/wiring.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pad:
    name: str  # as printed on the board
    row: int  # position along the header, 0 at the top of the drawing
    col: int = 0  # 0 = the column nearer the SuperMini, 1 = the far column
    number: str = ""  # pin number, for headers that are numbered
    nc: str = ""  # set when the pad must be left disconnected: the reason why


@dataclass(frozen=True)
class Wire:
    pin: str  # SuperMini pin, as printed: "3V3", "G", "4" ...
    pad: str  # module pad name


@dataclass(frozen=True)
class Divider:
    """A resistor divider on one wire: `series` in line, `shunt` from the
    module side of it to the ground pad."""

    pad: str
    series: str
    shunt: str
    ground_pad: str


@dataclass(frozen=True)
class Module:
    key: str  # file name suffix: docs/images/wiring-<key>.svg
    title: str  # in the diagram title and the docs
    heading: str  # on the board in the drawing
    sub: tuple[str, ...]  # smaller lines under the heading
    fill: str  # board colour in the drawing
    supply: str
    baud: int
    pads: tuple[Pad, ...]
    wires: tuple[Wire, ...]
    notes: tuple[str, ...]
    pitch: float = 2.54  # drawn pad spacing; the boards are not drawn to scale
    divider: Divider | None = None
    links: tuple[tuple[str, str, str], ...] = field(default=())  # (pad, pad, label)
    # Points off the header that must also be left disconnected: (names, reason).
    off_header: tuple[tuple[str, str], ...] = field(default=())

    def __post_init__(self) -> None:
        """Every pad is accounted for: wired, linked, or recorded as left
        disconnected, and never more than one of those."""
        wired = [w.pad for w in self.wires] + [b for _, b, _ in self.links]
        assert len(wired) == len(set(wired)), f"{self.key}: a pad is wired twice"
        for p in self.pads:
            label = p.name or f"pin {p.number}"
            assert (p.name in wired) != bool(p.nc), f"{self.key}: {label} must be either wired or recorded as disconnected"

    def pad(self, name: str) -> Pad:
        return next(p for p in self.pads if p.name == name)

    def disconnected(self) -> list[tuple[str, str]]:
        """(pads, reason) for everything on the GPS side that is left
        disconnected, pads with the same reason grouped together."""
        groups: dict[str, list[Pad]] = {}
        for p in self.pads:
            if p.nc:
                groups.setdefault(p.nc, []).append(p)
        out = []
        for why, pads in groups.items():
            if all(p.name for p in pads):
                out.append((", ".join(p.name for p in pads), why))
            else:  # unnamed pins of a numbered header, in pin order
                out.append(("pins " + ", ".join(sorted((p.number for p in pads), key=int)), why))
        return out + list(self.off_header)


UBLOX7 = Module(
    key="ublox7",
    title="u-blox 7 board",
    heading="u-blox 7",
    sub=("GPS receiver board", "the \"GT-U7\" entry"),
    fill="#1f7a4d",
    supply="3.3 V",
    baud=9600,
    pads=(Pad("VCC", 0), Pad("GND", 1), Pad("RXD", 2), Pad("TXD", 3), Pad("PPS", 4)),
    wires=(Wire("3V3", "VCC"), Wire("G", "GND"), Wire("4", "RXD"), Wire("3", "TXD"), Wire("1", "PPS")),
    notes=(
        "Every pin is 3.3 V logic, so the wires go straight across: the hook-up ten64 used.",
        "RXD is the board's input and TXD its output: GPIO4 (TX) goes to RXD, GPIO3 (RX) to TXD.",
        "Default UART speed is 9600 baud. Takes RTCM 2.3 corrections only.",
    ),
)

MAXM10S = Module(
    key="max-m10s",
    title="u-blox MAX-M10S breakout",
    heading="MAX-M10S",
    sub=("u-blox M10 breakout",),
    fill="#1c6b9c",
    supply="3.3 V",
    baud=38400,
    pads=(Pad("V", 0), Pad("G", 1), Pad("T", 2), Pad("R", 3), Pad("P", 4)),
    wires=(Wire("3V3", "V"), Wire("G", "G"), Wire("3", "T"), Wire("4", "R"), Wire("1", "P")),
    notes=(
        "Supply is 3.3 V (2.7 to 3.6 V). Never use the 5V pin.",
        "T is the module's output and R its input. If the module is silent, check these two first.",
        "Default UART speed is 38400 baud. The module has no flash, so the firmware configures it at every boot.",
    ),
)

DEBUG_UART = "1.8 V debug UART: 3.3 V exceeds its rating"

LC29H = Module(
    key="lc29h",
    title="Quectel LC29H(AA) board",
    heading="LC29H(AA)",
    sub=("Quectel dual-band L1+L5", "V is beside the POWER LED"),
    fill="#3a3f4b",
    supply="5 V",
    baud=115200,
    pitch=3.81,
    pads=(
        Pad("V", 0),
        Pad("G", 1),
        Pad("T1", 2),
        Pad("R1", 3),
        Pad("R2", 4, nc=DEBUG_UART),
        Pad("T2", 5, nc=DEBUG_UART),
        Pad("P", 6),
    ),
    wires=(Wire("5V", "V"), Wire("G", "G"), Wire("3", "T1"), Wire("4", "R1"), Wire("1", "P")),
    divider=Divider(pad="R1", series="1 kΩ", shunt="5.6 kΩ", ground_pad="G"),
    off_header=(("ENT, R3, T3", "test points beside the header: probe pads, not connections"),),
    notes=(
        "V takes 5 V: the board has its own regulator. (Inferred from the regulator on the board; check the listing.)",
        "R1 is a 2.8 V input, 3.08 V absolute maximum. 1 kΩ in series and 5.6 kΩ to ground give 2.8 V from GPIO4.",
        "Never connect T2 or R2. They are a 1.8 V debug port and 3.3 V exceeds their rating.",
        "Default UART speed is 115200 baud.",
    ),
)

NO_NET = "no net in the reverse-engineered schematic"

LEAM8T = Module(
    key="lea-m8t",
    title="u-blox LEA-M8T (Huawei WD22UGRC card, J2)",
    heading="LEA-M8T",
    sub=("Huawei WD22UGRC", "connector J2 (2 x 5)"),
    fill="#5b6b2a",
    supply="3.3 V only",
    baud=9600,
    pitch=5.08,
    pads=(
        Pad("V+", 0, 0, "2"),
        Pad("VANT", 0, 1, "1"),
        Pad("", 1, 0, "4", nc=NO_NET),
        Pad("TxD", 1, 1, "3"),
        Pad("1PPS", 2, 0, "6"),
        Pad("RxD", 2, 1, "5"),
        Pad("GND", 3, 0, "8"),
        Pad("", 3, 1, "7", nc=NO_NET),
        Pad("", 4, 0, "10", nc=NO_NET),
        Pad("", 4, 1, "9", nc=NO_NET),
    ),
    wires=(Wire("3V3", "V+"), Wire("G", "GND"), Wire("3", "TxD"), Wire("4", "RxD"), Wire("1", "1PPS")),
    links=(("V+", "VANT", "link for an active antenna"),),
    notes=(
        "3.3 V ONLY. The card has no regulator: 5 V destroys the module.",
        "Find pin 1 with a meter before powering anything. GND (8) buzzes to the corner mounting pads; VANT (1) reads a few ohms to the SMB centre pin.",
        "VANT is the antenna bias input. Link it to V+ for a 3.3 V active antenna; leave it open for a passive one.",
        "Default UART speed is 9600 baud. The J2 pinout is reverse-engineered and has not been powered yet.",
    ),
)

MODULES = (UBLOX7, MAXM10S, LC29H, LEAM8T)
