from time import sleep_ms, ticks_ms, ticks_add, ticks_diff
import display
import players
import scores
import settings
import touch

TAP_FLASH_MS = 150  # how long a tapped item shows highlighted before it opens
EXIT_SLOP = 16  # presses this close outside the Exit button still count
EXIT_HITS = 2  # consecutive readings on the button needed, so one stray reading can't exit
_exit_hits = 0


class GameExit(Exception):
    """Raised mid-game when the player taps Exit; the game ends without recording anything."""


def check_exit():
    """Call often while a game runs; raises GameExit once the Exit button is pressed.

    Reacts to the press itself rather than waiting for a clean tap and release:
    resistive readings jump around as a press starts and ends, which made taps miss.
    """
    global _exit_hits
    p = touch.panel.point()
    if p and (display.EXIT_X - EXIT_SLOP <= p[0] < display.EXIT_X + display.EXIT_W + EXIT_SLOP
              and display.EXIT_Y - EXIT_SLOP <= p[1] < display.EXIT_Y + display.EXIT_H + EXIT_SLOP):
        _exit_hits += 1
        if _exit_hits >= EXIT_HITS:
            raise GameExit
    else:
        _exit_hits = 0


def wait_ms(ms):
    """sleep_ms() that keeps watching the Exit button."""
    deadline = ticks_add(ticks_ms(), ms)
    while True:
        check_exit()
        left = ticks_diff(deadline, ticks_ms())
        if left <= 0:
            return
        sleep_ms(min(left, 10))


def _print_menu(title, options, selected):
    print()
    print(f"=== {title} ===")
    for i, opt in enumerate(options):
        if opt == "":
            print()
        else:
            print(f"{'>' if i == selected else ' '} {opt}")


def menu(encoder, title, options, selected=0):
    """Show `title` + `options`, navigate with the encoder or by touch, return the
    selected index.

    Lists longer than the screen scroll so the selection stays visible; dragging
    moves the selection like turning the encoder.
    """
    selectable = [i for i, opt in enumerate(options) if opt != ""]
    idx = selectable.index(selected) if selected in selectable else 0
    encoder.take_delta()  # drop rotation that happened before this menu appeared
    touch.panel.flush()

    rows = display.ROWS
    first = max(0, selectable[idx] - rows + 1)  # index of the option on the top row
    display.screen(title, options[first:first + rows], selectable[idx] - first)
    _print_menu(title, options, selectable[idx])

    while True:
        tap, drag = touch.panel.poll()
        delta = encoder.take_delta() + drag
        if delta != 0:
            old = selectable[idx]
            idx = (idx + delta) % len(selectable)
            new = selectable[idx]
            if new < first or new >= first + rows:
                # Scrolled past the edge: shift the window and redraw every row.
                first = new if new < first else new - rows + 1
                for row in range(rows):
                    i = first + row
                    display.draw_row(row, options[i] if i < len(options) else "", i == new)
            else:
                display.draw_row(old - first, options[old])
                display.draw_row(new - first, options[new], selected=True)
            _print_menu(title, options, new)

        if tap and tap[1] >= display.TOP:
            row = (tap[1] - display.TOP) // display.ROW_H
            i = first + row
            if row < rows and i < len(options) and options[i] != "":
                display.draw_row(selectable[idx] - first, options[selectable[idx]])
                display.draw_row(row, options[i], selected=True)
                sleep_ms(TAP_FLASH_MS)
                return i

        if encoder.pressed():
            return selectable[idx]

        sleep_ms(10)


def card_menu(encoder, title, cards, selected=0, footer=(), title_bg=display.TITLE_BG,
              card_h=display.CARD_H):
    """Like menu(), but shows `cards` as a vertical card list.

    Each card is (title, accent_color, tag, subtitle). `footer` items are slim rows
    pinned to the bottom of the screen; cards that don't fit above them scroll.
    Returns the selected index, counting cards first and then footer items.
    """
    n_cards = len(cards)
    total = n_cards + len(footer)
    area = display.footer_top(len(footer)) - display.CARD_TOP
    fit = max(1, (area + display.CARD_GAP) // (card_h + display.CARD_GAP))
    idx = selected if 0 <= selected < total else 0
    first = 0  # card shown in the top slot
    names = [c[0] for c in cards] + list(footer)

    def scroll():
        nonlocal first
        if idx < n_cards:
            if idx < first:
                first = idx
            elif idx >= first + fit:
                first = idx - fit + 1

    def draw(i, selected):
        if i >= n_cards:
            display.draw_footer(i - n_cards, len(footer), footer[i - n_cards], selected)
        elif first <= i < first + fit:
            display.draw_card(i - first, *cards[i], selected=selected, h=card_h)

    def hit(y):
        """Index of the card or footer row at height `y`, or None."""
        top = display.footer_top(len(footer))
        if y >= top:
            i = (y - top) // display.FOOTER_H
            return n_cards + i if i < len(footer) else None
        if y < display.CARD_TOP:
            return None
        slot, offset = divmod(y - display.CARD_TOP, card_h + display.CARD_GAP)
        if offset < card_h and slot < fit and first + slot < n_cards:
            return first + slot
        return None  # the gap between cards

    encoder.take_delta()
    touch.panel.flush()
    scroll()
    display.lcd.fill(display.BLACK)
    display.draw_title(title, title_bg)
    for i in range(total):
        draw(i, i == idx)
    _print_menu(title, names, idx)

    while True:
        tap, drag = touch.panel.poll()
        delta = encoder.take_delta() + drag
        if delta != 0:
            old, old_first = idx, first
            idx = (idx + delta) % total
            scroll()
            if first != old_first:
                # Scrolled: every visible card moved up or down a slot.
                for i in range(first, min(first + fit, n_cards)):
                    draw(i, i == idx)
            if old >= n_cards or first == old_first:
                draw(old, False)
            draw(idx, True)
            _print_menu(title, names, idx)

        i = hit(tap[1]) if tap else None
        if i is not None:
            draw(idx, False)
            draw(i, True)
            sleep_ms(TAP_FLASH_MS)
            return i

        if encoder.pressed():
            return idx

        sleep_ms(10)


def notice(encoder, title, lines):
    """Show a message screen and wait for an encoder click or a tap."""
    display.screen(title, lines + ["", "Click or tap"])
    print()
    print(f"=== {title} ===")
    for line in lines:
        print(line)
    print("(click to continue)")
    touch.panel.flush()
    while not encoder.pressed():
        tap, _ = touch.panel.poll()
        if tap:
            return
        sleep_ms(10)


LEVELS = ["Easy", "Normal", "Hard"]


class Mode:
    """One way to play a game, with its own leaderboards.

    `run(encoder)` plays one game and returns (score, result_title, result_lines),
    or None if nothing should be recorded. `format_score` renders a score with its
    unit in at most SCORE_W characters, e.g. "2345ms".
    """

    def __init__(self, key, name, run, format_score, higher_is_better):
        self.key = key
        self.name = name
        self.run = run
        self.format_score = format_score
        self.higher_is_better = higher_is_better


def _scores_key(game, mode):
    return f"{game.NAME}/{mode.key}"


def last_mode(game):
    """Index of the mode of `game` played most recently (the first one if none)."""
    keys = [m.key for m in game.MODES]
    return keys.index(settings.get(game.NAME, "mode", keys[0], keys))


def best_line(game, mode, player):
    """Card subtitle: `player`'s rank and best in `mode` at the game's current difficulty."""
    best = scores.best(_scores_key(game, mode), game.difficulty, player)
    if best is None:
        return "No score yet"
    rank, score = best
    return f"#{rank}  {mode.format_score(score)}"


PLAYER_W = 8  # characters of the player's name on the game screen's "You: ..." row
GAME_CARD_H = 56


def _play(encoder, game, mode):
    global _exit_hits
    _exit_hits = 0
    try:
        result = mode.run(encoder)
    except GameExit:
        # Leave everything as it was, including which mode was played last.
        print("Game exited, nothing recorded")
        return
    settings.set(game.NAME, "mode", mode.key)
    if result is None:
        return
    score, title, lines = result
    rank, is_best = scores.add(
        _scores_key(game, mode), game.difficulty, players.current(), score, mode.higher_is_better
    )
    notice(encoder, title, lines + ["", f"New best! #{rank}" if is_best else "Not your best"])


def pick_player(encoder):
    """Let the user choose the current player, most recently picked first."""
    names = players.by_recent()  # the current player is first, so the cursor starts there
    idx = menu(encoder, "PLAYER", names)
    players.set_current(names[idx])


def game_menu(encoder, game):
    """A game's screen: one card per mode, then You (the current player, click to
    change) / Leaderboard / Settings / Back.

    `game` is a module with NAME, TITLE, COLOR, MODES, `difficulty` and run_settings().
    """
    choice = last_mode(game)
    while True:
        player = players.current()
        # Built fresh each time so the bests reflect settings and the latest games.
        # Every mode shares the difficulty, so it goes in the title bar rather than on
        # each card, leaving the full card width for the mode name.
        cards = [(m.name, game.COLOR, "", best_line(game, m, player)) for m in game.MODES]
        title = f"{game.TITLE.upper()}  {game.difficulty.upper()}"
        footer = [f"Player: {player[:PLAYER_W]}", "Leaderboard", "Settings", "Back"]
        choice = card_menu(encoder, title, cards, choice, footer, game.COLOR, GAME_CARD_H)
        n = len(game.MODES)
        if choice < n:
            _play(encoder, game, game.MODES[choice])
        elif choice == n:
            pick_player(encoder)
        elif choice == n + 1:
            leaderboard(encoder, game, last_mode(game))
        elif choice == n + 2:
            game.run_settings(encoder)
        else:
            return


# Score rows use 1.5x text (12 px characters, 19 per line): rank + name + score.
ENTRY_SCALE = 1.5
NAME_W = 8  # characters of a player's name shown on the leaderboard
SCORE_W = 7  # e.g. "12345ms", right-aligned
BACK_ROW = display.ROWS - 1

# What the encoder is working on in the leaderboard; clicking moves down one step.
_MODE, _LEVEL, _LIST = 0, 1, 2


def _last_shown(board, first, visible):
    """Index of the last entry shown when `first` is on top; the bottom row
    becomes "..." when more entries follow."""
    if len(board) > first + visible:
        return first + visible - 2
    return first + visible - 1


def _entry_text(board, i, format_score):
    name, score = board[i]
    return f"{i + 1:>2} {name[:NAME_W]:<{NAME_W}} {format_score(score):>{SCORE_W}}"


def leaderboard(encoder, game, mode_idx):
    """Show each player's best for one mode and difficulty of `game`.

    Turning changes whatever is highlighted and clicking moves down one step:
    mode (and Back) -> difficulty -> the list, where turning scrolls starting at the
    current player's entry -> back to the mode. With a single mode the mode row is
    hidden and Back is part of the difficulty row instead.

    By touch: tap the left or right half of the mode/difficulty row to step it,
    drag to scroll the list, and tap Back to leave.
    """
    modes = game.MODES
    has_modes = len(modes) > 1
    top = _MODE if has_modes else _LEVEL  # the selector that also offers Back
    level_row = 1 if has_modes else 0
    first_row = level_row + 1
    visible = BACK_ROW - first_row  # score rows on screen; longer boards scroll

    mode = mode_idx
    level = LEVELS.index(game.difficulty)
    focus = top
    back = False  # Back is highlighted in place of the top selector's value
    cursor = None  # highlighted entry while scrolling the list
    first = 0  # entry shown on the top score row

    def load():
        return scores.board(_scores_key(game, modes[mode]), LEVELS[level])

    board = load()

    # Last (text, selected) drawn on each row, so only rows that change are redrawn.
    shown = {row: ("", False) for row in range(display.ROWS)}

    def show(row, text, selected=False, scale=display.SCALE):
        if shown[row] != (text, selected):
            display.draw_row(row, text, selected, scale)
            shown[row] = (text, selected)

    def redraw():
        nonlocal first
        if cursor is not None:
            # Scroll down until the cursor is above any "..." row.
            while cursor > _last_shown(board, first, visible):
                first += 1
        fmt = modes[mode].format_score
        if has_modes:
            show(0, f"< {modes[mode].name} >", focus == _MODE and not back)
        show(level_row, f"< {LEVELS[level]} >", focus == _LEVEL and not back)
        print()
        print(f"=== LEADERBOARD: {modes[mode].name} / {LEVELS[level]} ===")
        last = _last_shown(board, first, visible)
        for r in range(visible):
            i = first + r
            if i > last:
                text = "..." if i < len(board) else ""
                if text:
                    print("  ...")
            elif i < len(board):
                text = _entry_text(board, i, fmt)
                print(f"{'>' if i == cursor else ' '} {text}")
            else:
                text = "No scores yet" if i == 0 else ""
            show(first_row + r, text, i == cursor, ENTRY_SCALE)
        if not board:
            print("No scores yet")
        show(BACK_ROW, "Back", back)
        if back:
            print("> Back")

    encoder.take_delta()
    touch.panel.flush()
    display.lcd.fill(display.BLACK)
    display.draw_title("LEADERBOARD", game.COLOR)
    redraw()

    while True:
        tap, drag = touch.panel.poll()
        if drag and board and focus != _LIST:
            focus, back, cursor = _LIST, False, first
        delta = encoder.take_delta() + (drag if focus == _LIST else 0)
        if delta != 0:
            if focus == _LIST:
                cursor = max(0, min(len(board) - 1, cursor + delta))
                if cursor < first:
                    first = cursor
            else:
                count = len(modes) if focus == _MODE else len(LEVELS)
                current = mode if focus == _MODE else level
                # The top selector has one extra stop after its last value: Back.
                stops = count + 1 if focus == top else count
                pos = ((count if back else current) + delta) % stops
                back = pos == count
                if not back and pos != current:
                    if focus == _MODE:
                        mode = pos
                    else:
                        level = pos
                    board = load()
                    first = 0
            redraw()

        row = (tap[1] - display.TOP) // display.ROW_H if tap and tap[1] >= display.TOP else None
        if row == BACK_ROW:
            back = True
            redraw()
            sleep_ms(TAP_FLASH_MS)
            return
        if row is not None and (row == level_row or (has_modes and row == 0)):
            step = 1 if tap[0] >= display.lcd.width // 2 else -1
            if row == level_row:
                focus, level = _LEVEL, (level + step) % len(LEVELS)
            else:
                focus, mode = _MODE, (mode + step) % len(modes)
            back, cursor, first = False, None, 0
            board = load()
            redraw()

        if encoder.pressed():
            if back:
                return
            if focus == _MODE:
                focus = _LEVEL
            elif focus == _LEVEL and board:
                focus = _LIST
                me = players.current()
                names = [name for name, _ in board]
                cursor = names.index(me) if me in names else 0
            else:
                # From the list, or a level with no scores to scroll: back to the top.
                focus = top
                cursor = None
                first = 0
            redraw()

        sleep_ms(10)
