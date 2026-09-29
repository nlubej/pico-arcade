from machine import Pin, SPI
from ili9341 import ILI9341, color565

# MISO is never read, but SPI0 would otherwise claim its default MISO pin (GPIO16,
# a game button). Point it at GPIO4 instead; creating the DC Pin afterwards takes GPIO4 back.
_spi = SPI(0, baudrate=40_000_000, sck=Pin(2), mosi=Pin(3), miso=Pin(4))
lcd = ILI9341(
    _spi,
    cs=Pin(0, Pin.OUT, value=1),
    dc=Pin(4, Pin.OUT, value=0),
    rst=Pin(1, Pin.OUT, value=1),
    width=240,
    height=320,
    madctl=0x88,
)

BLACK = 0x0000
WHITE = 0xFFFF
TITLE_BG = color565(0, 70, 160)
HIGHLIGHT_BG = color565(255, 200, 0)
CARD_BG = color565(36, 40, 52)
CARD_SUB_FG = color565(170, 175, 190)

SCALE = 1.8  # 14x14 px characters -> 16 fit on one line
LEFT = 8
TITLE_H = 32
TOP = 40
ROW_H = 24
ROWS = (lcd.height - TOP) // ROW_H  # rows that fit below the title bar (11)


def _row_y(row):
    return TOP + row * ROW_H


def draw_title(text, bg=TITLE_BG):
    lcd.fill_rect(0, 0, lcd.width, TITLE_H, bg)
    lcd.text(text, LEFT, (TITLE_H - int(8 * SCALE)) // 2, WHITE, bg, SCALE)


def draw_row(row, text, selected=False, scale=SCALE):
    y = _row_y(row)
    bg = HIGHLIGHT_BG if selected else BLACK
    fg = BLACK if selected else WHITE
    lcd.fill_rect(0, y, lcd.width, ROW_H, bg)
    if text:
        lcd.text(text, LEFT, y + (ROW_H - int(8 * scale)) // 2, fg, bg, scale)


def screen(title, lines, selected_row=None, scales=None):
    """Draw a full screen; `scales` optionally gives a text size per row (default SCALE)."""
    lcd.fill(BLACK)
    draw_title(title)
    for row, text in enumerate(lines):
        if text or row == selected_row:
            scale = scales[row] if scales and row < len(scales) else SCALE
            draw_row(row, text, row == selected_row, scale)


CARD_X = 12
CARD_W = lcd.width - 2 * CARD_X
CARD_H = 76
CARD_GAP = 12
CARD_TOP = TITLE_H + 12
CARD_STRIPE = 6
CARD_TEXT_X = CARD_X + CARD_STRIPE + 12
CARD_SUB_SCALE = 1.3
FOOTER_H = ROW_H  # height of each slim row pinned below a card list

EXIT_W = 84
EXIT_H = 36
EXIT_X = (lcd.width - EXIT_W) // 2
EXIT_Y = lcd.height - EXIT_H - 40
EXIT_BG = color565(210, 30, 30)


def card_y(slot, h=CARD_H):
    return CARD_TOP + slot * (h + CARD_GAP)


def footer_top(count):
    """Top of the first of `count` slim rows pinned to the bottom of the screen."""
    return lcd.height - count * FOOTER_H - 4 if count else lcd.height


def draw_card(slot, title, accent, tag, subtitle, selected=False, h=CARD_H):
    """Draw a card in position `slot` of a vertical card list: accent stripe, title,
    small `tag` in the top-right corner and `subtitle` underneath, spaced to fit `h`.

    `subtitle` is a string or a list of lines. Text that would run into the tag or
    off the card is cut short.
    """
    x, y, w = CARD_X, card_y(slot, h), CARD_W
    bg = HIGHLIGHT_BG if selected else CARD_BG
    fg = BLACK if selected else WHITE
    sub_fg = BLACK if selected else CARD_SUB_FG
    lines = [subtitle] if isinstance(subtitle, str) else subtitle
    lines = [line for line in lines if line]
    lcd.fill_rect(x, y, w, h, bg)
    lcd.fill_rect(x, y, CARD_STRIPE, h, accent)
    # Round the corners by knocking out a 2x2 block at each one.
    for cx, cy in ((x, y), (x + w - 2, y), (x, y + h - 2), (x + w - 2, y + h - 2)):
        lcd.fill_rect(cx, cy, 2, 2, BLACK)

    title_h = int(8 * SCALE)
    sub_h = int(8 * CARD_SUB_SCALE)
    # Equal space above the title, between lines and below the last one.
    pad = (h - title_h - len(lines) * sub_h) // (len(lines) + 2 if lines else 2)
    right = x + w - 10  # text stops here
    tag_x = right - len(tag) * 8
    title_right = tag_x - 8 if tag else right
    lcd.text(title[: (title_right - CARD_TEXT_X) // title_h], CARD_TEXT_X, y + pad, fg, bg, SCALE)
    if tag:
        lcd.text(tag, tag_x, y + pad + (title_h - 8) // 2, sub_fg, bg, 1)
    line_y = y + 2 * pad + title_h
    for line in lines:
        lcd.text(line[: (right - CARD_TEXT_X) // sub_h], CARD_TEXT_X, line_y, sub_fg, bg, CARD_SUB_SCALE)
        line_y += sub_h + pad


def draw_footer(i, count, text, selected=False):
    """Draw slim row `i` of `count` pinned below a card list, aligned with the card text."""
    y = footer_top(count) + i * FOOTER_H
    bg = HIGHLIGHT_BG if selected else BLACK
    fg = BLACK if selected else WHITE
    lcd.fill_rect(CARD_X, y, CARD_W, FOOTER_H, bg)
    cell = int(8 * SCALE)
    text = text[: (CARD_X + CARD_W - 10 - CARD_TEXT_X) // cell]  # keep inside the row
    lcd.text(text, CARD_TEXT_X, y + (FOOTER_H - cell) // 2, fg, bg, SCALE)


def draw_exit_button():
    """Red Exit button centred near the bottom, shown while a game is running."""
    lcd.fill_rect(EXIT_X, EXIT_Y, EXIT_W, EXIT_H, EXIT_BG)
    cell = int(8 * SCALE)
    lcd.text("EXIT", EXIT_X + (EXIT_W - 4 * cell) // 2, EXIT_Y + (EXIT_H - cell) // 2, WHITE, EXIT_BG, SCALE)
