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
class Feature:
    """Something else on the board, drawn for reference: where it is
    relative to the header tells you which way up the board is."""

    kind: str  # chip, connector, led, cell, hole, pad, part, header, text
    x: float  # centre, mm from the board's top-left corner in the drawing
    y: float
    w: float  # size; a circle's diameter is w
    h: float = 0.0
    label: str = ""
    label_pos: str = "inside"  # inside, below, above, right


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
    heading: str  # above the board in the drawing
    layout: str  # where the drawn layout comes from, shown under the heading
    fill: str  # board colour in the drawing
    supply: str
    baud: int
    pads: tuple[Pad, ...]
    wires: tuple[Wire, ...]
    notes: tuple[str, ...]
    pitch: float = 2.54  # drawn pad spacing; the boards are not drawn to scale
    # Board outline in the drawing: width, the first row of pads from the top
    # edge, and the margin under the last row. The header is always on the
    # left, nearest the SuperMini, as on every board's own layout here.
    width: float = 24.0
    top: float = 3.5
    foot: float = 3.0
    features: tuple[Feature, ...] = field(default=())
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
    heading="u-blox 7 board (the \"GT-U7\" entry)",
    layout="Pad order as seen from above the pins. Other parts not drawn yet: no photo of this board.",
    fill="#1f7a4d",
    supply="3.3 V",
    baud=9600,
    # As seen from above the header pins, top to bottom.
    pads=(Pad("PPS", 0), Pad("TXD", 1), Pad("RXD", 2), Pad("GND", 3), Pad("VCC", 4)),
    wires=(Wire("3V3", "VCC"), Wire("G", "GND"), Wire("4", "RXD"), Wire("3", "TXD"), Wire("1", "PPS")),
    notes=(
        "Every pin is 3.3 V logic, so no level shifting is needed: the hook-up ten64 used.",
        "RXD is the board's input and TXD its output: GPIO4 (TX) goes to RXD, GPIO3 (RX) to TXD.",
        "Default UART speed is 9600 baud. Takes RTCM 2.3 corrections only.",
    ),
)

MAXM10S = Module(
    key="max-m10s",
    title="u-blox MAX-M10S breakout",
    heading="MAX-M10S breakout",
    layout="Pad names from the ten64 bench notes. Order and other parts not yet checked: no photo of this board.",
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
    heading="Quectel LC29H(AA) board",
    layout="Component side, header on the left, laid out from a photo of the board (2026-09-27). Not to scale.",
    fill="#3a3f4b",
    supply="5 V",
    baud=115200,
    pitch=3.81,
    width=34.0,
    top=7.2,
    foot=2.5,
    # Top to bottom as the silkscreen reads with the header on the left.
    pads=(
        Pad("P", 0),
        Pad("T2", 1, nc=DEBUG_UART),
        Pad("R2", 2, nc=DEBUG_UART),
        Pad("R1", 3),
        Pad("T1", 4),
        Pad("G", 5),
        Pad("V", 6),
    ),
    features=(
        Feature("hole", 2.6, 2.2, 2.3),
        Feature("hole", 31.5, 2.6, 2.3),
        Feature("hole", 32.0, 26.6, 2.3),
        Feature("pad", 23.3, 1.9, 1.8, label="ENT", label_pos="below"),
        Feature("pad", 25.4, 1.9, 1.8, label="R3", label_pos="below"),
        Feature("pad", 27.6, 1.9, 1.8, label="T3", label_pos="below"),
        Feature("led", 16.4, 3.1, 1.6, 0.9, label="PPS LED", label_pos="below"),
        Feature("chip", 25.6, 14.1, 12.9, 15.6, label="LC29H"),
        Feature("connector", 12.1, 21.3, 2.6, 2.6, label="U.FL antenna", label_pos="below"),
        Feature("part", 13.3, 28.6, 2.6, 1.6, label="LDO", label_pos="right"),
        Feature("led", 21.5, 27.6, 1.6, 0.9, label="POWER LED", label_pos="below"),
        Feature("cell", 27.8, 24.6, 5.5, label="backup"),
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
    heading="Huawei WD22UGRC card (LEA-M8T), connector J2",
    layout="Component side, J2 on the left, from photos and the reverse-engineered component layout. Not to scale.",
    fill="#4f7a2a",
    supply="3.3 V only",
    baud=9600,
    pitch=5.08,
    width=52.0,
    top=6.5,
    foot=5.3,
    # J2 is 2 x 4. The component layout marks pin 1; with J2 on the left it
    # is the top pin of the column at the board edge, and the odd pins run
    # down that column.
    pads=(
        Pad("VANT", 0, 0, "1"),
        Pad("V+", 0, 1, "2"),
        Pad("TxD", 1, 0, "3"),
        Pad("", 1, 1, "4", nc=NO_NET),
        Pad("RxD", 2, 0, "5"),
        Pad("1PPS", 2, 1, "6"),
        Pad("", 3, 0, "7", nc=NO_NET),
        Pad("GND", 3, 1, "8"),
    ),
    features=(
        Feature("hole", 3.0, 2.5, 3.0),
        Feature("hole", 49.0, 2.5, 3.0),
        Feature("hole", 3.0, 24.6, 3.0),
        Feature("hole", 49.0, 24.6, 3.0),
        Feature("header", 5.14, 14.12, 7.6, 19.4, label="J2", label_pos="above"),
        Feature("chip", 27.9, 9.6, 13.0, 15.0, label="LEA-M8T"),
        Feature("text", 27.9, 20.2, 0.0, label="WD22UGRC VER.C T"),
        Feature("connector", 47.5, 13.0, 5.5, 6.8, label="SMB", label_pos="above"),
        Feature("connector", 53.2, 13.0, 5.7, 2.6),
        Feature("part", 40.4, 21.6, 7.4, 4.6, label="6V8 TVS"),
        Feature("pad", 13.0, 24.8, 2.0, 1.4, label="−", label_pos="right"),
        Feature("pad", 19.0, 24.8, 2.0, 1.4, label="+", label_pos="right"),
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
