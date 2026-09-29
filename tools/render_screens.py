"""Render the game's screens to PNGs on the PC, for the README.

Runs the real game code under CPython with stand-ins for the MicroPython-only
parts: a fake SPI bus decodes the ILI9341 commands into a pixel buffer, a clock
advances only when the code sleeps or reads a button, and a simulated player
presses whatever the games light up. Names and scores come from sample data
below, not from the board or players.txt.

    py tools/render_screens.py        writes docs/images/*.png
"""

import builtins
import contextlib
import io
import os
import random
import struct
import sys
import tempfile
import time
import types
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images")
W, H = 240, 320
PNG_SCALE = 2  # each LCD pixel becomes a 2x2 block, so the images stay crisp on GitHub

PLAYERS = ["Maja", "Luka", "Ana", "Žan", "Eva", "Tim", "Nika", "Jure"]
SETTINGS = {
    "global": {"player": "Maja", "recent": ["Maja", "Luka", "Ana"]},
    "reflex": {"difficulty": "Normal", "mode": "classic", "wait_level": 2},
    "memory": {"difficulty": "Easy", "mode": "classic"},
    "touch": {"cal": [False, 1, 0, 1, 0]},  # skips the calibration screen
}
SCORES = {
    "reflex/classic": {"Normal": [
        ["Luka", 3120], ["Ana", 3395], ["Maja", 3890], ["Žan", 3980],
        ["Eva", 4210], ["Tim", 4675], ["Nika", 5020], ["Jure", 5480],
    ]},
    "memory/classic": {"Easy": [
        ["Eva", 14], ["Maja", 11], ["Jure", 9], ["Ana", 8], ["Luka", 6],
    ]},
}

# MicroPython's built-in 8x8 font (extmod/font_petme128_8x8.h, MIT licence,
# (c) 2013-2014 Damien P. George): characters 32-127, one byte per column, LSB on top.
FONT = bytes.fromhex(
    "00000000000000000000004f4f0000000007070000070700147f7f14147f7f14"
    "00242e6b6b3a1200006333180c66630000327f4d4d7772500000000406030100"
    "00001c3e63410000000041633e1c0000082a3e1c1c3e2a080008083e3e080800"
    "000080e0600000000008080808080800000000606000000000406030180c0602"
    "003e7f49457f3e000040447f7f40400000627351494f460000226349497f3600"
    "00181814167f7f1000276745457d3900003e7f49497b3200000303797d070300"
    "00367f49497f360000266f49497f3e000000002424000000000080e464000000"
    "00081c3663414100001414141414140000414163361c080000020351590f0600"
    "003e7f414d4f2e00007c7e0b0b7e7c00007f7f49497f3600003e7f4141632200"
    "007f7f41633e1c00007f7f4949414100007f7f0909010100003e7f41497b3a00"
    "007f7f08087f7f000000417f7f410000002060417f3f0100007f7f1c36634100"
    "007f7f4040404000007f7f060c067f7f007f7f0e1c7f7f00003e7f41417f3e00"
    "007f7f09090f0600001e3f21617f5e00007f7f19396f460000266f49497b3200"
    "0001017f7f010100003f7f40407f3f00001f3f60603f1f00007f7f3018307f7f"
    "0063771c1c77630000070f78780f0700006171594d47430000007f7f41410000"
    "0002060c18306040000041417f7f000000080c06060c0800c0c0c0c0c0c0c0c0"
    "000001030604000000207454547c7800007f7f44447c380000387c44446c2800"
    "00387c44447f7f0000387c54545c580000087e7f090302000098bca4a4fc7c00"
    "007f7f04047c78000000007d7d0000000040c08080fd7d00007f7f30386c4400"
    "0000417f7f400000007c7c1830187c7c007c7c04047c780000387c44447c3800"
    "00fcfc24243c180000183c2424fcfc00007c7c04040c080000485c5454742000"
    "04043f7f44642000003c7c40407c3c00001c3c60603c1c00001c7c3018307c1c"
    "00446c38386c4400009cbca0a0fc7c00004464745c4c44000008083e77414100"
    "000000ffff000000004141773e0808000002030103020301aa55aa55aa55aa55"
)


# --- Clock: advances only when the game sleeps or polls a button ---------------

_now = 0


def _sleep_ms(ms):
    global _now
    _now += ms


time.sleep_ms = _sleep_ms
time.ticks_ms = lambda: _now
time.ticks_add = lambda a, b: a + b
time.ticks_diff = lambda a, b: a - b
os.rename = os.replace  # littlefs rename overwrites the target; Windows rename doesn't
_open = builtins.open


def _open_utf8(file, mode="r", *args, **kwargs):
    # MicroPython always reads text as UTF-8; Windows Python defaults to the ANSI code page.
    if "b" not in mode:
        kwargs.setdefault("encoding", "utf-8")
    return _open(file, mode, *args, **kwargs)


builtins.open = _open_utf8


# --- LCD: decodes the ILI9341 command stream into `pixels` (RGB565) -------------

pixels = bytearray(W * H * 2)
_lcd = {"cmd": None, "x0": 0, "x1": 0, "y0": 0, "y1": 0, "x": 0, "y": 0}


def _lcd_write(data):
    s = _lcd
    if Pin.pins[4]._v == 0:  # DC low: a command byte
        s["cmd"] = data[0]
        if s["cmd"] == 0x2C:
            s["x"], s["y"] = s["x0"], s["y0"]
        return
    if s["cmd"] == 0x2A:
        s["x0"], s["x1"] = struct.unpack(">HH", data)
    elif s["cmd"] == 0x2B:
        s["y0"], s["y1"] = struct.unpack(">HH", data)
    elif s["cmd"] == 0x2C:
        i = 0
        while i < len(data):
            n = min((len(data) - i) // 2, s["x1"] + 1 - s["x"])
            at = (s["y"] * W + s["x"]) * 2
            pixels[at:at + n * 2] = data[i:i + n * 2]
            i += n * 2
            s["x"] += n
            if s["x"] > s["x1"]:
                s["x"], s["y"] = s["x0"], s["y"] + 1


# --- Simulated player -----------------------------------------------------------

BUTTONS = (12, 14, 16, 18, 20)  # each button's LED is on the next GPIO
bot = {"phase": None, "watched": [], "queue": [], "press_at": None}


def _button_down(pin):
    """Whether the simulated player is holding button `pin` right now."""
    if bot["phase"] == "answer":
        # Memory: repeat the watched sequence, pausing between presses.
        if not bot["queue"]:
            return False
        if bot["press_at"] is None:
            bot["press_at"] = _now + random.randint(150, 350)
        held = _now - bot["press_at"]
        if held >= 120:
            bot["queue"].pop(0)
            bot["press_at"] = None
            return False
        return held >= 0 and BUTTONS[bot["queue"][0]] == pin
    # Reflex: press each lit button after a human-ish reaction time.
    led = Pin.pins[pin + 1]
    return led._v and _now >= led.press_at


# --- Stand-ins for MicroPython modules ------------------------------------------

class Pin:
    IN, OUT, PULL_UP, IRQ_FALLING, IRQ_RISING = 0, 1, 2, 4, 8
    pins = {}

    def __init__(self, id, mode=None, pull=None, value=None):
        self.id = id
        self._v = value if value is not None else (1 if pull == Pin.PULL_UP else 0)
        self.press_at = 0
        Pin.pins[id] = self

    def value(self, v=None):
        if v is None:
            if self.id in BUTTONS:
                _sleep_ms(1)
                return 0 if _button_down(self.id) else 1
            return self._v
        if v and not self._v and self.id - 1 in BUTTONS:
            self.press_at = _now + random.randint(240, 420)
            if bot["phase"] == "watch":
                bot["watched"].append(BUTTONS.index(self.id - 1))
        self._v = 1 if v else 0

    __call__ = value

    def on(self):
        self.value(1)

    def off(self):
        self.value(0)

    def irq(self, trigger=None, handler=None):
        pass


class SPI:
    def __init__(self, id, **kwargs):
        self.id = id

    def write(self, data):
        if self.id == 0:
            _lcd_write(bytes(data))

    def write_readinto(self, tx, rx):
        rx[:] = bytes(len(rx))


class FrameBuffer:
    """Just enough of framebuf.FrameBuffer for ili9341.text(): MONO_HLSB text."""

    def __init__(self, buf, width, height, fmt):
        self.buf, self.width = buf, width

    def text(self, s, x, y, c):
        for k, ch in enumerate(s):
            code = ord(ch) if 32 <= ord(ch) <= 127 else 127
            for col, bits in enumerate(FONT[(code - 32) * 8:(code - 32) * 8 + 8]):
                for row in range(8):
                    if bits >> row & 1:
                        px, py = x + k * 8 + col, y + row
                        self.buf[(py * self.width + px) >> 3] |= 0x80 >> (px & 7)


sys.modules["machine"] = types.SimpleNamespace(Pin=Pin, SPI=SPI)
sys.modules["framebuf"] = types.SimpleNamespace(FrameBuffer=FrameBuffer, MONO_HLSB=0)


class Shot(Exception):
    """Raised when a screen is complete and waiting for input: time to save it."""


class Encoder:
    sw = types.SimpleNamespace(value=lambda: 1)

    def take_delta(self):
        return 0

    def pressed(self):
        raise Shot


def save_png(name):
    rows = []
    for y in range(H):
        line = bytearray()
        for x in range(W):
            v = pixels[(y * W + x) * 2] << 8 | pixels[(y * W + x) * 2 + 1]
            rgb = bytes(((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31))
            line += rgb * PNG_SCALE
        rows += [b"\x00" + bytes(line)] * PNG_SCALE

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", W * PNG_SCALE, H * PNG_SCALE, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
    with open(os.path.join(OUT, name + ".png"), "wb") as f:
        f.write(png)


def shoot(name, action, save=True):
    """Run `action` until it waits for input, then save the screen as `name`."""
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            action()
        except Shot:
            pass
        else:
            raise RuntimeError(f"{name}: never waited for input")
    if save:
        save_png(name)


def main():
    import json

    random.seed(3)
    os.makedirs(OUT, exist_ok=True)
    # The game reads and writes its files in the current directory, so give it a scratch one.
    work = tempfile.mkdtemp()
    os.chdir(work)
    with open("players.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(PLAYERS) + "\n")
    for path, data in (("settings.json", SETTINGS), ("scores.json", SCORES)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    sys.path.insert(0, ROOT)

    import display
    import hardware
    import ui
    import reflex
    import memory

    draw_row = display.draw_row
    game = {"round": 0}

    def watching_draw_row(row, text, *args, **kwargs):
        # Steers the simulated player and saves the mid-game shots as the rows change.
        draw_row(row, text, *args, **kwargs)
        if text.startswith("Round "):
            game["round"] = int(text.split()[1].split("/")[0])
        elif text == "Watch...":
            bot.update(phase="watch", watched=[])
        elif text == "Your turn!":
            bot.update(phase="answer", queue=list(bot["watched"]), press_at=None)
            if game["round"] == 5:
                save_png("memory-game")
                raise Shot  # the memory result isn't needed
        elif text == "Correct!":
            bot["phase"] = None
        elif text.startswith("Last:") and game["round"] == 7:
            save_png("reflex-game")

    display.draw_row = watching_draw_row

    # Play first, so the menus and leaderboard below include the new best.
    shoot("reflex-result", lambda: ui._play(Encoder(), reflex, reflex.MODES[0]))
    hardware.RotaryEncoder = Encoder
    shoot("main-menu", lambda: __import__("main"))
    shoot("reflex-menu", lambda: ui.game_menu(Encoder(), reflex))
    shoot("leaderboard", lambda: ui.leaderboard(Encoder(), reflex, 0))
    shoot("players", lambda: ui.pick_player(Encoder()))
    shoot("memory-game", lambda: ui._play(Encoder(), memory, memory.MODES[0]), save=False)
    for name in sorted(os.listdir(OUT)):
        print("wrote", os.path.join("docs", "images", name))

if __name__ == "__main__":
    main()
