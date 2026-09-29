from time import ticks_ms, ticks_diff
from hardware import stages, shuffled, all_leds_off, light_all
from ili9341 import color565
from ui import menu as show_menu, Mode, check_exit, wait_ms
import display
import players
import settings

NAME = "reflex"
TITLE = "Reflex"
COLOR = color565(255, 90, 60)

DIFFICULTY_N = {"Easy": 1, "Normal": 2, "Hard": 3}
WAIT_SECONDS = {1: 0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1.0}

# Restored from flash; changed via the Settings menu.
difficulty = settings.get("reflex", "difficulty", "Easy", DIFFICULTY_N)  # Easy=1 button/round, Normal=2, Hard=3
wait_level = settings.get("reflex", "wait_level", 1, WAIT_SECONDS)  # 1-5 -> 0s/0.25s/0.5s/0.75s/1.0s

TOTAL_ROUNDS = 10


def _pick_difficulty(encoder):
    global difficulty
    options = ["Easy", "Normal", "Hard"]
    idx = show_menu(encoder, "DIFFICULTY", options, options.index(difficulty))
    difficulty = options[idx]
    settings.set("reflex", "difficulty", difficulty)


def _pick_wait_level(encoder):
    global wait_level
    options = [f"{lvl} ({WAIT_SECONDS[lvl]}s)" for lvl in range(1, 6)]
    idx = show_menu(encoder, "WAIT TIME", options, wait_level - 1)
    wait_level = idx + 1
    settings.set("reflex", "wait_level", wait_level)


def run_settings(encoder):
    options = ["Difficulty", "Wait time", "Back"]
    selected = 0
    while True:
        choice = show_menu(encoder, "SETTINGS", options, selected)
        selected = len(options) - 1  # after changing a setting, land on Back
        if choice == 0:
            _pick_difficulty(encoder)
        elif choice == 1:
            _pick_wait_level(encoder)
        else:
            return


def run_classic(encoder):
    """Light n buttons per round for TOTAL_ROUNDS rounds; score = total reaction time."""
    n = DIFFICULTY_N[difficulty]
    wait_seconds = WAIT_SECONDS[wait_level]

    try:
        all_leds_off()
        player = players.current()
        display.screen("REFLEX", ["", "", f"{difficulty} mode", player])
        display.draw_exit_button()
        reactions_ms = []
        previous = set()

        for round_num in range(1, TOTAL_ROUNDS + 1):
            display.draw_row(0, f"Round {round_num}/{TOTAL_ROUNDS}")

            available = [s for s in stages if s not in previous]
            if len(available) < n:
                available = list(stages)
            picks = shuffled(available)[:n]
            previous = set(picks)

            wait_ms(int(wait_seconds * 1000))

            for led, _ in picks:
                led.on()
            start = ticks_ms()

            pending = {btn for _, btn in picks}
            while pending:
                check_exit()
                for _, btn in picks:
                    if btn in pending and btn.value() == 0:
                        pending.discard(btn)

            reaction_ms = ticks_diff(ticks_ms(), start)
            for led, _ in picks:
                led.off()

            reactions_ms.append(reaction_ms)
            print(f"Round {round_num} reaction:", reaction_ms, "ms")
            display.draw_row(1, f"Last: {reaction_ms}ms")

        light_all(2, wait_ms)
        total = sum(reactions_ms)
        print("Total reaction time:", total, "ms")
        return total, "RESULT", [
            f"Total: {total}ms",
            f"Avg: {total // TOTAL_ROUNDS}ms",
            f"Best: {min(reactions_ms)}ms",
        ]
    finally:
        all_leds_off()


def run_dummy(encoder):
    """TEMPORARY: placeholder mode to try out multi-mode menus. Scores a random number."""
    import random
    hits = random.randint(10, 60)
    return hits, "RESULT", ["Dummy mode", f"Hits: {hits}"]


MODES = [
    Mode("classic", "Classic", run_classic, lambda ms: f"{ms}ms", higher_is_better=False),
    Mode("dummy", "Time trial", run_dummy, lambda n: f"{n} hits", higher_is_better=True),  # TEMPORARY
]
