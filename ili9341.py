import struct
import framebuf
from time import sleep_ms


# 8x8 glyphs (one byte per row, MSB = leftmost pixel) for letters the built-in
# ASCII font lacks, drawn in the same style. Lowercase keeps the font's x-height
# with the accent in the two free rows above; capitals shrink to fit their accent.
EXTRA_GLYPHS = {
    "č": b"\x24\x18\x3c\x66\x60\x66\x3c\x00",
    "š": b"\x24\x18\x3c\x60\x3c\x06\x7c\x00",
    "ž": b"\x24\x18\x7e\x0c\x18\x30\x7e\x00",
    "ć": b"\x0c\x18\x3c\x66\x60\x66\x3c\x00",
    "đ": b"\x06\x1f\x3e\x66\x66\x66\x3e\x00",
    "Č": b"\x24\x18\x3e\x60\x60\x60\x3e\x00",
    "Š": b"\x24\x18\x3e\x60\x3c\x06\x7c\x00",
    "Ž": b"\x24\x18\x7e\x0c\x18\x30\x7e\x00",
    "Ć": b"\x0c\x18\x3e\x60\x60\x60\x3e\x00",
    "Đ": b"\x78\x6c\x66\xf6\x66\x6c\x78\x00",
}


def color565(r, g, b):
    return (r & 0xF8) << 8 | (g & 0xFC) << 3 | b >> 3


class ILI9341:
    # madctl picks rotation (BGR panel order): 0x48 portrait, 0x28 landscape,
    # 0x88 portrait flipped, 0xE8 landscape flipped. Swap width/height to match.
    def __init__(self, spi, cs, dc, rst, width, height, madctl):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = width
        self.height = height

        self.rst(0)
        sleep_ms(50)
        self.rst(1)
        sleep_ms(150)

        self._cmd(0x01)  # software reset
        sleep_ms(150)
        self._cmd(0x11)  # sleep out
        sleep_ms(120)
        self._cmd(0x3A, b"\x55")  # 16-bit color
        self._cmd(0x36, bytes([madctl]))
        self._cmd(0x29)  # display on
        sleep_ms(20)

    def _cmd(self, cmd, data=None):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([cmd]))
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _begin_write(self, x, y, w, h):
        self._cmd(0x2A, struct.pack(">HH", x, x + w - 1))
        self._cmd(0x2B, struct.pack(">HH", y, y + h - 1))
        self.cs(0)
        self.dc(0)
        self.spi.write(b"\x2C")
        self.dc(1)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        pixels = w * h
        chunk = min(pixels, 512)
        buf = struct.pack(">H", color) * chunk
        self._begin_write(x, y, w, h)
        full, rest = divmod(pixels, chunk)
        for _ in range(full):
            self.spi.write(buf)
        if rest:
            self.spi.write(memoryview(buf)[: rest * 2])
        self.cs(1)

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def text(self, s, x, y, fg, bg, scale=1):
        """Draw `s` at (x, y). `scale` may be fractional (e.g. 1.5): each font pixel
        then becomes 1 or 2 screen pixels, alternating, so a character is int(8 * scale) wide.
        """
        # Screen pixels covered by each of a glyph's 8 columns (and rows).
        sizes = [int((i + 1) * scale) - int(i * scale) for i in range(8)]
        cell = sum(sizes)
        s = s[: max(0, (self.width - x) // cell)]
        if not s:
            return

        # Render with the built-in 8x8 font into a 1-bit buffer, then expand to RGB565.
        # framebuf walks the UTF-8 bytes, so non-ASCII characters are drawn as a space
        # (one cell each) and then patched from EXTRA_GLYPHS. Row r of character k is
        # byte r * len(s) + k.
        n = len(s)
        w = n * 8
        mono = bytearray(n * 8)
        ascii_s = "".join(c if c < "\x80" else " " for c in s)
        framebuf.FrameBuffer(mono, w, 8, framebuf.MONO_HLSB).text(ascii_s, 0, 0, 1)
        if ascii_s != s:
            for k, c in enumerate(s):
                glyph = EXTRA_GLYPHS.get(c)
                if glyph:
                    for r in range(8):
                        mono[r * n + k] = glyph[r]

        fg_hi, fg_lo = fg >> 8, fg & 0xFF
        bg_hi, bg_lo = bg >> 8, bg & 0xFF
        line = bytearray(n * cell * 2)

        self._begin_write(x, y, n * cell, cell)
        for row in range(8):
            base = row * n
            i = 0
            for col in range(w):
                if mono[base + (col >> 3)] & (0x80 >> (col & 7)):
                    hi, lo = fg_hi, fg_lo
                else:
                    hi, lo = bg_hi, bg_lo
                for _ in range(sizes[col & 7]):
                    line[i] = hi
                    line[i + 1] = lo
                    i += 2
            for _ in range(sizes[row]):
                self.spi.write(line)
        self.cs(1)
