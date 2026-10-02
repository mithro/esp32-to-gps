#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Draw the ESP32-C3 SuperMini with every pin's role in this project, as
docs/images/pinout-supermini-gps.svg.

The board is seen from the component side, USB-C up.  Pins a GPS board is
wired to carry the colour of their jumper wire; the three boot-strap pins and
the two UART0 pins are marked as kept free.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import supermini as sm  # noqa: E402
from draw_wiring import draw_supermini  # noqa: E402
from svgdraw import INK, MUTED, View, page  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "images"
PAGE_W = 92.0
WARN = "#b3261e"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v = View(0, 0)
    draw_supermini(v, set(sm.WIRES))
    for name in sm.LEFT + sm.RIGHT:
        x, y = sm.pin_xy(name)
        left = name in sm.LEFT
        edge = 0.0 if left else sm.BOARD_W
        out = -1 if left else 1
        role = sm.ROLE[name]
        keep_free = "keep free" in role
        colour = WARN if keep_free else (INK if name in sm.WIRES else MUTED)
        v.line(edge, y, edge + out * 2.2, y, stroke=colour, width=0.12)
        tx = edge + out * 3.0
        if name in sm.WIRES:  # a stub of the jumper wire's colour
            v.rect(min(tx, tx + out * 3.6), y - 0.55, max(tx, tx + out * 3.6), y + 0.55, fill=sm.WIRES[name][1], stroke=INK, width=0.1, rx=0.45)
            tx += out * 4.6
        v.text(tx, y, role, size=0.9, anchor="end" if left else "start", fill=colour, weight="bold" if name in sm.WIRES else "normal")

    title = View(0, 0)
    title.text(PAGE_W / 2, 3.0, "ESP32-C3 SuperMini pin assignment for a GPS receiver", size=1.7, weight="bold")
    title.text(PAGE_W / 2, 5.6, "Seen from the component side, USB-C up. All GPS wires are on the right-hand header.", size=1.0)
    ox, oy = 26.0, 10.5
    path = OUT / "pinout-supermini-gps.svg"
    path.write_text(page(PAGE_W, oy + sm.BOARD_H + 3.0, [title.svg_group(0, 0), v.svg_group(ox, oy)]))
    print(f"wrote {path.relative_to(path.parents[2])}")


if __name__ == "__main__":
    main()
