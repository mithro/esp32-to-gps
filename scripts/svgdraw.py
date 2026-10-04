"""Small SVG drawing helpers shared by the diagram scripts.

Adapted from scripts/draw_pinouts.py and scripts/draw_wiring.py in
mithro/esp32-to-433mhz.  Everything is plain text output with fixed number
formatting, so the drawings regenerate byte-identically.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

S = 11.0  # px per mm
INK = "#1a1a2e"
MUTED = "#555c66"
PIN = "#f2c94c"
PIN_UNUSED = "#9aa0a6"
FONT = "Helvetica, Arial, sans-serif"


class View:
    """A group of shapes; x/y in mm from the group's top-left corner."""

    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.items: list[str] = []

    def rect(self, x0, y0, x1, y1, fill="none", stroke=INK, width=0.15, dash=None, rx=0.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(f'<rect x="{x0 * S:.1f}" y="{y0 * S:.1f}" width="{(x1 - x0) * S:.1f}" height="{(y1 - y0) * S:.1f}" rx="{rx * S:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{width * S:.2f}"{d}/>')

    def line(self, x0, y0, x1, y1, stroke=INK, width=0.15, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(f'<line x1="{x0 * S:.1f}" y1="{y0 * S:.1f}" x2="{x1 * S:.1f}" y2="{y1 * S:.1f}" stroke="{stroke}" stroke-width="{width * S:.2f}" stroke-linecap="round"{d}/>')

    def circle(self, x, y, r, fill="none", stroke=INK, width=0.15):
        self.items.append(f'<circle cx="{x * S:.1f}" cy="{y * S:.1f}" r="{r * S:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{width * S:.2f}"/>')

    def text(self, x, y, s, size=1.4, anchor="middle", weight="normal", fill=INK, halo=False):
        h = f' stroke="#ffffff" stroke-width="{0.35 * S:.1f}" paint-order="stroke" stroke-linejoin="round"' if halo else ""
        self.items.append(f'<text x="{x * S:.1f}" y="{y * S:.1f}" font-size="{size * S:.1f}" font-family="{FONT}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" dy="0.36em"{h}>{escape(s)}</text>')

    def pad(self, x, y, label="", used=True, square=False):
        """Header pad: a ring, with an optional number inside."""
        fill = PIN if used else PIN_UNUSED
        if square:
            self.rect(x - 0.8, y - 0.8, x + 0.8, y + 0.8, fill=fill, stroke=INK, width=0.12)
        else:
            self.circle(x, y, 0.8, fill=fill, stroke=INK, width=0.12)
        self.circle(x, y, 0.45, fill="#ffffff", stroke=INK, width=0.08)
        if label:
            self.text(x, y, label, size=0.7, weight="bold")

    def wire(self, pts: list[tuple[float, float]], fill: str, width: float = 1.3, crimps: bool = True, dash=None):
        """A jumper wire through the points (mm), corners rounded, with an ink
        outline so that light colours show on white."""
        d = rounded_path([(x * S, y * S) for x, y in pts], 1.6 * S)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{width * S:.1f}" stroke-linecap="round"{da}/>')
        self.items.append(f'<path d="{d}" fill="none" stroke="{fill}" stroke-width="{(width - 0.45) * S:.1f}" stroke-linecap="round"{da}/>')
        if crimps:
            for x, y in (pts[0], pts[-1]):
                self.circle(x, y, 0.8, fill=fill, stroke=INK, width=0.15)

    def svg_group(self, ox: float, oy: float) -> str:
        return f'<g transform="translate({ox * S:.1f} {oy * S:.1f})">\n' + "\n".join(self.items) + "\n</g>"


def rounded_path(pts: list[tuple[float, float]], r: float) -> str:
    """SVG path through the points (px) with corners rounded by r (px)."""
    d = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        l1 = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1e-6)
        l2 = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1e-6)
        rr = min(r, l1 / 2, l2 / 2)
        ax, ay = x1 - (x1 - x0) / l1 * rr, y1 - (y1 - y0) / l1 * rr
        bx, by = x1 + (x2 - x1) / l2 * rr, y1 + (y2 - y1) / l2 * rr
        d.append(f"L {ax:.1f} {ay:.1f} Q {x1:.1f} {y1:.1f} {bx:.1f} {by:.1f}")
    d.append(f"L {pts[-1][0]:.1f} {pts[-1][1]:.1f}")
    return " ".join(d)


def page(w: float, h: float, groups: list[str]) -> str:
    """A whole SVG document, w x h mm, white background."""
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * S:.0f}" height="{h * S:.0f}" viewBox="0 0 {w * S:.0f} {h * S:.0f}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        *groups,
        "</svg>",
    ]) + "\n"
