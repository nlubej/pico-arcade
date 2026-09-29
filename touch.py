from machine import Pin, SPI
from time import sleep_ms
import display
import settings

# XPT2046 commands: 12-bit differential read of X (0xD0) or Y (0x90). The low "power
# down" bits stay 00 so the chip keeps T_IRQ enabled between reads.
_READ_X = 0xD0
_READ_Y = 0x90
SAMPLES = 5  # reads per position; the median rejects the panel's spikes
TAP_SLOP = 12  # a press that moves further than this (px) is a drag, not a tap
RELEASE_POLLS = 3  # polls without contact before a press counts as over (debounce)


class XPT2046:
    def __init__(self, spi, cs, irq, width, height):
        self.spi = spi
        self.cs = cs
        self.irq = irq  # low while the screen is pressed
        self.width = width
        self.height = height
        self.cal = None  # (swap, ax, bx, ay, by): screen = a * raw + b per axis
        self._tx = bytearray(3)
        self._rx = bytearray(3)
        self._start = None  # screen point where the current press began
        self._last = None
        self._anchor_y = 0  # y that drags are measured from; moves one row at a time
        self._moved = False
        self._up = 0  # consecutive polls without contact
        self._ignore = False  # skip the current press (it began before flush())

    def _read(self, cmd):
        self._tx[0] = cmd
        self.cs(0)
        self.spi.write_readinto(self._tx, self._rx)
        self.cs(1)
        return ((self._rx[1] << 8) | self._rx[2]) >> 3

    def raw(self):
        """Median raw (x, y) of the current press, or None when not pressed."""
        if self.irq.value():
            return None
        xs = sorted(self._read(_READ_X) for _ in range(SAMPLES))
        ys = sorted(self._read(_READ_Y) for _ in range(SAMPLES))
        # Lifted mid-read, or a reading of 0 (no contact): the samples are unreliable.
        if self.irq.value() or not xs[0] or not ys[0]:
            return None
        return xs[SAMPLES // 2], ys[SAMPLES // 2]

    def point(self):
        """Screen (x, y) of the current press, or None when not pressed or uncalibrated."""
        r = self.raw()
        if r is None or self.cal is None:
            return None
        swap, ax, bx, ay, by = self.cal
        rx, ry = (r[1], r[0]) if swap else r
        x = min(self.width - 1, max(0, int(ax * rx + bx)))
        y = min(self.height - 1, max(0, int(ay * ry + by)))
        return x, y

    def flush(self):
        """Forget any press in progress, so a finger already down when a screen
        appears (or taps made during a game) can't select anything on it."""
        self._start = None
        self._ignore = not self.irq.value()

    def poll(self):
        """Call every loop. Returns (tap, rows): `tap` is the (x, y) of a press that
        just ended without moving, else None; `rows` is how many whole rows the finger
        was dragged since the last call, positive downwards (moving the selection
        down the list, like turning the encoder)."""
        p = self.point()
        if p is None:
            self._up += 1
            if self._up < RELEASE_POLLS:
                return None, 0
            self._ignore = False
            tap = self._last if self._start is not None and not self._moved else None
            self._start = None
            return tap, 0

        self._up = 0
        if self._ignore:
            return None, 0
        if self._start is None:
            self._start = self._last = p
            self._anchor_y = p[1]
            self._moved = False
            return None, 0

        self._last = p
        if abs(p[0] - self._start[0]) > TAP_SLOP or abs(p[1] - self._start[1]) > TAP_SLOP:
            self._moved = True
        if not self._moved:
            return None, 0
        rows = int((p[1] - self._anchor_y) / display.ROW_H)  # rounds toward zero
        self._anchor_y += rows * display.ROW_H
        return None, rows


panel = XPT2046(
    SPI(1, baudrate=1_000_000, sck=Pin(10), mosi=Pin(11), miso=Pin(8)),
    cs=Pin(9, Pin.OUT, value=1),
    irq=Pin(22, Pin.IN, Pin.PULL_UP),
    width=display.lcd.width,
    height=display.lcd.height,
)

_saved = settings.get("touch", "cal", None)
if isinstance(_saved, list) and len(_saved) == 5:
    panel.cal = tuple(_saved)


def needs_calibration():
    return panel.cal is None


# Crosshair positions: two share a y (to find the screen x axis), two share an x.
TARGETS = ((20, 20), (display.lcd.width - 20, 20), (20, display.lcd.height - 20))
CROSS = 10  # crosshair arm length (px)
MIN_SPAN = 300  # raw units two targets must differ by, else the taps were misplaced


def _cross(x, y, color):
    display.lcd.fill_rect(x - CROSS, y, 2 * CROSS + 1, 1, color)
    display.lcd.fill_rect(x, y - CROSS, 1, 2 * CROSS + 1, color)


def _press_raw():
    """Wait for a press and its release; return its median raw (x, y)."""
    while True:
        samples = []
        while True:
            r = panel.raw()
            if r:
                samples.append(r)
            elif samples:
                break
            sleep_ms(10)
        if len(samples) >= 5:  # shorter is a bounce, not a deliberate tap
            xs = sorted(s[0] for s in samples)
            ys = sorted(s[1] for s in samples)
            return xs[len(xs) // 2], ys[len(ys) // 2]


def calibrate():
    """Have the user tap three crosshairs, then store how raw readings map to pixels."""
    lcd = display.lcd
    print()
    print("=== TOUCH SETUP ===")
    while True:
        lcd.fill(display.BLACK)
        lcd.text("Tap each cross", display.LEFT, lcd.height // 2 - 24, display.WHITE, display.BLACK, display.SCALE)
        lcd.text("with a fingernail", display.LEFT, lcd.height // 2, display.WHITE, display.BLACK, display.SCALE)
        raw = []
        for x, y in TARGETS:
            _cross(x, y, display.HIGHLIGHT_BG)
            print(f"Tap the cross at ({x}, {y})")
            raw.append(_press_raw())
            _cross(x, y, display.BLACK)

        (x0, y0), (x1, _), (_, y2) = TARGETS
        p0, p1, p2 = raw
        # If moving along the screen's x changed the panel's Y channel more, the axes are swapped.
        swap = abs(p1[1] - p0[1]) > abs(p1[0] - p0[0])
        i, j = (1, 0) if swap else (0, 1)  # raw channel for screen x, and for screen y
        if abs(p1[i] - p0[i]) >= MIN_SPAN and abs(p2[j] - p0[j]) >= MIN_SPAN:
            break
        print("Taps too close together, try again")
        display.screen("TOUCH SETUP", ["", "Missed a cross,", "try again"])
        sleep_ms(1500)

    ax = (x1 - x0) / (p1[i] - p0[i])
    ay = (y2 - y0) / (p2[j] - p0[j])
    panel.cal = (swap, ax, x0 - ax * p0[i], ay, y0 - ay * p0[j])
    settings.set("touch", "cal", list(panel.cal))
    print(f"Touch calibrated: {panel.cal}")
    display.screen("TOUCH SETUP", ["", "Touch calibrated"])
    sleep_ms(1000)
