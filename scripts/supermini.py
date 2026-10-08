"""ESP32-C3 SuperMini geometry and the GPIO assignment this project uses.

Dimensions (mm) are the ones mithro/esp32-to-433mhz measured for its
scripts/generate_supermini.py (GrabCAD STEP model "ESP32C3-SuperMini" by Ulf
Hille, checked against the mischianti.org dimension drawing): an 18.00 x 22.52
board, two rows of eight pins 15.24 apart on a 2.54 pitch, the first pin
1.74 from the USB-C edge.
"""

from __future__ import annotations

BOARD_W = 18.00
BOARD_H = 22.52
PITCH = 2.54
ROW_SPACING = 15.24
PIN_EDGE_X = (BOARD_W - ROW_SPACING) / 2  # 1.38 from the long edge to a pin centre
PIN_TOP_Y = 1.74  # first pin centre from the USB-C edge

# Pin names as printed on the board, top (USB-C end) to bottom, seen from the
# component side.
LEFT = ["5", "6", "7", "8", "9", "10", "20", "21"]
RIGHT = ["5V", "G", "3V3", "4", "3", "2", "1", "0"]

# Component-side features, for the drawings only.
USB_W, USB_TOP, USB_BOTTOM = 9.0, -1.5, 5.85
BUTTON_DX, BUTTON_Y, BUTTON_R = 2.95, 8.84, 1.5
ANT_X0, ANT_X1, ANT_H = 5.5, 12.5, 2.6

# Wire colour for each SuperMini pin a GPS module uses: (colour name, fill).
# The colour follows the signal, named from the GPS board's side: red is the
# supply (3V3, or 5V for the LC29H's VCC), black ground, yellow the board's
# RXD (driven by GPIO4), blue its TXD (read on GPIO3) and green PPS.
WIRES = {
    "G": ("black", "#26262e"),
    "3V3": ("red", "#d81e1e"),
    "5V": ("red", "#d81e1e"),
    "4": ("yellow", "#f2d21e"),
    "3": ("blue", "#2464c8"),
    "1": ("green", "#2e9e4f"),
}

# What each pin is for.  The GPS signals all sit on the right-hand header,
# next to the supplies, so one 8-way connector carries everything.
ROLE = {
    "5V": "5 V supply (LC29H board only)",
    "G": "ground",
    "3V3": "3.3 V supply (u-blox boards)",
    "4": "GPIO4: ESP32 TX to GPS RX (commands, RTCM corrections)",
    "3": "GPIO3: ESP32 RX from GPS TX (NMEA / UBX)",
    "2": "GPIO2: boot strap, keep free",
    "1": "GPIO1: PPS input",
    "0": "GPIO0: spare",
    "5": "GPIO5: free",
    "6": "GPIO6: free",
    "7": "GPIO7: free",
    "8": "GPIO8: boot strap, keep free",
    "9": "GPIO9: boot strap (BOOT button), keep free",
    "10": "GPIO10: free",
    "20": "GPIO20: UART0 RX, keep free",
    "21": "GPIO21: UART0 TX (ROM boot log), keep free",
}
STRAPS = {"2", "8", "9"}


def pin_xy(name: str) -> tuple[float, float]:
    """Pin centre in mm from the board's top-left corner, component side up."""
    if name in LEFT:
        return PIN_EDGE_X, PIN_TOP_Y + LEFT.index(name) * PITCH
    return BOARD_W - PIN_EDGE_X, PIN_TOP_Y + RIGHT.index(name) * PITCH
