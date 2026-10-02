#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Draw the jumper-wire hook-up of an ESP32-C3 SuperMini to each supported GPS
receiver board, as docs/images/wiring-<module>.svg.

The SuperMini is drawn to scale from the component side, USB-C up.  We have no
measured outlines for the GPS boards, so each is a schematic block: its pads
are in the order they have on the board and carry the names printed there,
but the block is not to scale.  A pad that must be left disconnected is
crossed out in red, and each diagram lists those pads with the reason.

Every wire leaves its SuperMini pin to the right, turns down (or up) a lane
of its own in the gap, and runs right again into its pad.  A pad in the far
column of a two-row header is reached along the channel between two rows of
pads.  Which lane each wire takes, and how high the GPS board sits beside the
SuperMini, are chosen by exhaustive search: every lane order at every board
height, ranked by wires running on top of each other (never allowed if it
can be avoided), then by crossings, then by steps too short to draw cleanly,
then by total wire length.  The search
is deterministic, so the drawings regenerate byte-identically.
"""

from __future__ import annotations

import itertools
import pathlib
import sys
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import supermini as sm  # noqa: E402
from gps_modules import MODULES, Module  # noqa: E402
from svgdraw import FONT, INK, MUTED, S, View, page  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "images"

PAGE_W = 92.0  # every diagram the same width
LANE = 2.2  # mm between parallel wires in the gap (the wires are 1.3 mm wide)
LANE_X0 = sm.BOARD_W + 3.0  # first lane, in the SuperMini's frame
MOD_W = 31.0  # width of a GPS board block
HEAD_H = 8.5  # from the top of a block to its first row of pads
FOOT_H = 3.0  # below its last row
PAD_X = 2.6  # from the block's left edge to its near column of pads
DIVIDER_W = 13.0  # extra gap for the resistors, where a wire has a divider
MIN_GAP = 2.0  # parallel wires closer than this, side by side, are a clash
STEP = sm.PITCH / 4  # board heights tried by the search
NC = "#d81e1e"  # the cross on a pad that is left disconnected
MIN_STEP = 3.2  # a vertical run shorter than this cannot fit its two rounded corners

Pt = tuple[float, float]


def simplify(pts: list[Pt]) -> list[Pt]:
    """Drop repeated points and the middle one of three in a line."""
    out: list[Pt] = []
    for p in pts:
        if out and abs(p[0] - out[-1][0]) < 1e-6 and abs(p[1] - out[-1][1]) < 1e-6:
            continue
        if len(out) >= 2:
            (x0, y0), (x1, y1) = out[-2], out[-1]
            if (abs(x0 - x1) < 1e-6 and abs(x1 - p[0]) < 1e-6) or (abs(y0 - y1) < 1e-6 and abs(y1 - p[1]) < 1e-6):
                out[-1] = p
                continue
        out.append(p)
    return out


class Layout:
    """Where one module's block sits and how its wires run, in the SuperMini's
    frame (mm from the SuperMini's top-left corner)."""

    def __init__(self, mod: Module, my: float, order: tuple[int, ...], flip: bool = False):
        self.mod, self.my = mod, my
        self.cols = max(p.col for p in mod.pads) + 1
        self.flip = flip  # a two-row header drawn with its rows the other way round
        n = len(mod.wires)
        self.mx = LANE_X0 + (n - 1) * LANE + 3.0 + (DIVIDER_W if mod.divider else 0.0)
        rows = max(p.row for p in mod.pads) + 1
        self.h = HEAD_H + (rows - 1) * mod.pitch + FOOT_H
        self.routes: dict[str, list[Pt]] = {}
        for w, lane in zip(mod.wires, order):
            lx = LANE_X0 + lane * LANE
            xs, ys = sm.pin_xy(w.pin)
            px, py = self.pad_xy(w.pad)
            if self.col(mod.pad(w.pad)) == 0:
                pts = [(xs, ys), (lx, ys), (lx, py), (px, py)]
            else:  # along the channel below its row, then up into the pad
                ye = py + mod.pitch / 2
                pts = [(xs, ys), (lx, ys), (lx, ye), (px, ye), (px, py)]
            self.routes[w.pad] = simplify(pts)

    def col(self, pad) -> int:
        """The column the pad is drawn in: 0 is nearest the SuperMini."""
        return self.cols - 1 - pad.col if self.flip else pad.col

    def pad_xy(self, name: str) -> Pt:
        p = self.mod.pad(name)
        return self.xy(p.row, self.col(p))

    def xy(self, row: int, col: int) -> Pt:
        return self.mx + PAD_X + col * self.mod.pitch, self.my + HEAD_H + row * self.mod.pitch

    def cost(self) -> tuple[int, int, int, float]:
        """(clashes, crossings, kinks, total length)."""
        segs = {k: list(zip(v, v[1:])) for k, v in self.routes.items()}
        clash = cross = 0
        for a, b in itertools.combinations(segs, 2):
            for (ax0, ay0), (ax1, ay1) in segs[a]:
                for (bx0, by0), (bx1, by1) in segs[b]:
                    ah, bh = abs(ay0 - ay1) < 1e-6, abs(by0 - by1) < 1e-6
                    if ah == bh:  # parallel: too close and side by side?
                        if ah:
                            sep, lo, hi = abs(ay0 - by0), max(min(ax0, ax1), min(bx0, bx1)), min(max(ax0, ax1), max(bx0, bx1))
                        else:
                            sep, lo, hi = abs(ax0 - bx0), max(min(ay0, ay1), min(by0, by1)), min(max(ay0, ay1), max(by0, by1))
                        if sep < MIN_GAP and hi - lo > 0.3:
                            clash += 1
                        continue
                    # one of each: h is the horizontal one, v the vertical one
                    (hx0, hy, hx1, _), (vx, vy0, _, vy1) = ((ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1)) if ah else ((bx0, by0, bx1, by1), (ax0, ay0, ax1, ay1))
                    if min(hx0, hx1) - 1e-6 <= vx <= max(hx0, hx1) + 1e-6 and min(vy0, vy1) - 1e-6 <= hy <= max(vy0, vy1) + 1e-6:
                        cross += 1
        # A step too short for two rounded corners draws as a kink.
        kinks = sum(1 for s in segs.values() for (x0, y0), (x1, y1) in s if abs(x0 - x1) < 1e-6 and abs(y0 - y1) < MIN_STEP and (x1, y1) != s[-1][1])
        length = sum(abs(x1 - x0) + abs(y1 - y0) for s in segs.values() for (x0, y0), (x1, y1) in s)
        return clash, cross, kinks, round(length, 3)


def best_layout(mod: Module) -> Layout:
    n = len(mod.wires)
    best = None
    two_rows = any(p.col for p in mod.pads)
    for flip in (False, True) if two_rows else (False,):
        for k in range(-16, 33):
            for order in itertools.permutations(range(n)):
                lay = Layout(mod, k * STEP, order, flip)
                key = (*lay.cost(), abs(k), k, order, flip)
                if best is None or key < best[0]:
                    best = (key, lay)
    return best[1]


def draw_supermini(v: View, used: set[str]) -> None:
    W, H = sm.BOARD_W, sm.BOARD_H
    v.rect(0, 0, W, H, fill="#1f2430", stroke="#0b0d12", width=0.25, rx=0.6)
    v.rect((W - sm.USB_W) / 2, sm.USB_TOP, (W + sm.USB_W) / 2, sm.USB_BOTTOM, fill="#b9bdc5", stroke=INK, width=0.12, rx=1.0)
    v.text(W / 2, 2.2, "USB-C", size=0.9, weight="bold")
    for dx, name in ((-sm.BUTTON_DX, "BOOT"), (sm.BUTTON_DX, "RST")):
        v.circle(W / 2 + dx, sm.BUTTON_Y, 1.2, fill="#3a4050", stroke="#0b0d12", width=0.1)
        v.text(W / 2 + dx, sm.BUTTON_Y + 2.0, name, size=0.6, fill="#c9ced6")
    v.rect(sm.ANT_X0, H - sm.ANT_H, sm.ANT_X1, H - 0.3, fill="none", stroke="#c9ced6", width=0.08, dash="3 3")
    v.text(W / 2, H - sm.ANT_H / 2 - 0.15, "antenna", size=0.6, fill="#c9ced6")
    v.text(W / 2, 14.2, "ESP32-C3", size=1.05, fill="#ffffff", weight="bold")
    v.text(W / 2, 15.9, "SuperMini", size=1.05, fill="#ffffff", weight="bold")
    for name in sm.LEFT + sm.RIGHT:
        x, y = sm.pin_xy(name)
        left = name in sm.LEFT
        v.pad(x, y, used=name in used)
        v.text(2.6 if left else W - 2.6, y, name, size=0.95, anchor="start" if left else "end", fill="#ffffff" if name in used else "#9aa0a6", weight="bold")


def draw_module(v: View, lay: Layout) -> None:
    mod, mx, my = lay.mod, lay.mx, lay.my
    v.rect(mx, my, mx + MOD_W, my + lay.h, fill=mod.fill, stroke=INK, width=0.25, rx=0.8)
    v.text(mx + MOD_W / 2, my + 2.3, mod.heading, size=1.4, fill="#ffffff", weight="bold")
    for i, line in enumerate(mod.sub):
        v.text(mx + MOD_W / 2, my + 4.3 + i * 1.4, line, size=0.85, fill="#ffffff")


def draw_pads(v: View, lay: Layout) -> None:
    """Pads and their names, on top of the wires."""
    mod = lay.mod
    wired = {w.pad for w in mod.wires} | {name for a, b, _ in mod.links for name in (a, b)}
    cols = lay.cols
    for p in mod.pads:
        x, y = lay.xy(p.row, lay.col(p))
        if p.nc:  # left disconnected: crossed out, its number moves to the label
            v.pad(x, y, used=False)
            strike(v, x, y)
        else:
            v.pad(x, y, label=p.number, used=True)
    link_note = {b: label for _, b, label in mod.links}
    for row in sorted({p.row for p in mod.pads}):
        pads = sorted((p for p in mod.pads if p.row == row), key=lay.col)
        x, y = lay.xy(row, cols - 1)
        names = " · ".join(p.name or f"{p.number} n/c" for p in pads)
        live = any(not p.nc for p in pads)
        v.text(x + 1.7, y, names, size=1.1, anchor="start", fill="#ffffff" if live else "#c9ced6", weight="bold")
        note = next((link_note[p.name] for p in pads if p.name in link_note), "")
        if not note and cols == 1 and pads[0].nc:
            note = "leave disconnected"
        if note:
            v.text(x + (10.4 if cols > 1 else 5.6), y, note, size=0.8, anchor="start", fill="#e6e8ec")


def strike(v: View, x: float, y: float, r: float = 1.0) -> None:
    """A red cross over a pad that is left disconnected."""
    for width, stroke in ((0.55, "#ffffff"), (0.3, NC)):
        v.line(x - r, y - r, x + r, y + r, stroke=stroke, width=width)
        v.line(x - r, y + r, x + r, y - r, stroke=stroke, width=width)


def draw_divider(v: View, lay: Layout) -> None:
    """The series resistor on the wire's last run and the shunt resistor from
    there up to the ground wire, between the lanes and the board."""
    d = lay.mod.divider
    _, y = lay.pad_xy(d.pad)
    _, yg = lay.pad_xy(d.ground_pad)
    xr, xj = lay.mx - 9.5, lay.mx - 5.2
    v.wire([(xj, y), (xj, yg)], sm.WIRES["G"][1], width=0.9, crimps=False)
    yb = yg + lay.mod.pitch / 2  # midway between the ground wire and the next one
    v.rect(xj - 0.65, yb - 0.95, xj + 0.65, yb + 0.95, fill="#ffffff", stroke=INK, width=0.14, rx=0.15)
    v.text(xj + 1.2, yb, d.shunt, size=0.85, anchor="start", weight="bold", halo=True)
    v.rect(xr - 1.6, y - 0.65, xr + 1.6, y + 0.65, fill="#ffffff", stroke=INK, width=0.14, rx=0.15)
    v.text(xr, y + 1.6, d.series, size=0.85, weight="bold", halo=True)
    for jy in (y, yg):
        v.circle(xj, jy, 0.5, fill=INK, stroke=INK, width=0.05)


def legend_rows(mod: Module) -> list[tuple[str, str, str, str]]:
    """(fill, colour name, what it joins, purpose) per wire."""
    rows = []
    for w in mod.wires:
        colour, fill = sm.WIRES[w.pin]
        pin = w.pin if w.pin in ("5V", "G", "3V3") else f"GPIO{w.pin}"
        purpose = sm.ROLE[w.pin].split(": ", 1)[-1].split(" (")[0] if w.pin in ("5V", "3V3") else sm.ROLE[w.pin].split(": ", 1)[-1]
        if mod.divider and mod.divider.pad == w.pad:
            purpose += f", through {mod.divider.series} with {mod.divider.shunt} to ground"
        rows.append((fill, colour, f"{pin} → {w.pad}", purpose))
    for a, b, label in mod.links:
        rows.append((sm.WIRES["3V3"][1], "red link", f"{a} → {b}", label))
    return rows


def draw(mod: Module) -> None:
    lay = best_layout(mod)
    used = {w.pin for w in mod.wires}
    v = View(0, 0)
    draw_module(v, lay)
    draw_supermini(v, used)
    for w in mod.wires:
        v.wire(lay.routes[w.pad], sm.WIRES[w.pin][1])
    for a, b, _ in mod.links:
        v.wire([lay.pad_xy(a), lay.pad_xy(b)], sm.WIRES["3V3"][1], width=1.0, crimps=False, dash="4 4")
    if mod.divider:
        draw_divider(v, lay)
    draw_pads(v, lay)

    ox = (PAGE_W - (lay.mx + MOD_W)) / 2
    oy = 12.0 + max(0.0, -lay.my)
    bottom = oy + max(sm.BOARD_H, lay.my + lay.h)

    def text(x, y, s, size, weight="normal", fill=INK, anchor="start"):
        t = s.replace("&", "&amp;").replace("<", "&lt;")
        return f'<text x="{x * S:.1f}" y="{y * S:.1f}" font-size="{size * S:.1f}" font-family="{FONT}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" dy="0.36em">{t}</text>'

    parts = [
        text(PAGE_W / 2, 3.0, f"ESP32-C3 SuperMini to the {mod.title}", 1.7, "bold", anchor="middle"),
        text(PAGE_W / 2, 5.6, "SuperMini seen from the component side, USB-C up. The GPS board is a schematic: pads in board order, not to scale.", 1.0, anchor="middle"),
        text(PAGE_W / 2, 7.5, f"Supply: {mod.supply}.  Default UART speed: {mod.baud} baud.", 1.0, "bold", anchor="middle"),
        v.svg_group(ox, oy),
    ]
    lx, y = 5.0, bottom + 4.0
    parts.append(text(lx, y, "Wires", 1.05, "bold"))
    for fill, colour, joins, purpose in legend_rows(mod):
        y += 2.2
        parts.append(f'<rect x="{lx * S:.1f}" y="{(y - 0.55) * S:.1f}" width="{3.6 * S:.1f}" height="{1.1 * S:.1f}" fill="{fill}" stroke="{INK}" stroke-width="{0.1 * S:.1f}" rx="{0.45 * S:.1f}"/>')
        parts.append(text(lx + 4.6, y, colour, 0.95, "bold"))
        parts.append(text(lx + 13.0, y, joins, 0.95))
        parts.append(text(lx + 28.0, y, purpose, 0.85, fill=MUTED))
    # Everything on the GPS side that is left disconnected, with the reason.
    y += 3.2
    parts.append(text(lx, y, "Leave disconnected on the GPS board", 1.05, "bold"))
    gone = mod.disconnected()
    if not gone:
        y += 2.2
        parts.append(text(lx + 4.6, y, f"Nothing: all {len(mod.pads)} pads on the header are wired.", 0.95))
    for pads, why in gone:
        y += 2.2
        k = View(0, 0)
        k.circle(lx + 1.8, y, 0.6, fill="#9aa0a6", stroke=INK, width=0.1)
        strike(k, lx + 1.8, y, 0.75)
        parts.append(k.svg_group(0, 0))
        parts.append(text(lx + 4.6, y, pads, 0.95, "bold"))
        parts.append(text(lx + 28.0, y, why, 0.85, fill=MUTED))
    y += 3.2
    parts.append(text(lx, y, "Notes", 1.05, "bold"))
    for note in mod.notes:
        for i, line in enumerate(textwrap.wrap(note, 112)):
            y += 1.9 if i == 0 else 1.5
            if i == 0:
                parts.append(f'<circle cx="{(lx + 0.6) * S:.1f}" cy="{y * S:.1f}" r="{0.3 * S:.1f}" fill="{INK}"/>')
            parts.append(text(lx + 2.0, y, line, 0.9))
    path = OUT / f"wiring-{mod.key}.svg"
    path.write_text(page(PAGE_W, y + 2.5, parts))
    clash, cross, kinks, _ = lay.cost()
    print(f"wrote {path.relative_to(path.parents[2])} ({cross} crossings, {clash} clashes, {kinks} kinks)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for mod in MODULES:
        draw(mod)


if __name__ == "__main__":
    main()
