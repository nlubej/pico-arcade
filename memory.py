from time import sleep_ms
import random
from hardware import stages, all_leds_off, light_all, flash_all
from ili9341 import color565
from ui import menu as show_menu, Mode, check_exit, wait_ms
import display
import players
import settings

NAME = "memory"
TITLE = "Memory"
COLOR = color565(70, 200, 120)

START_LENGTH = 2
RAMP_ROUNDS = 10  # speed/gap ramp reaches its end value by this round, then holds
DEBOUNCE_MS = 20  # a button must read steady this long before a press/release counts

# (start_ms, end_ms) interpolated linearly across the first RAMP_ROUNDS rounds,
# then held at the end value for as long as the game continues.
ON_MS = {
    "Easy": (500, 500),
    "Normal": (500, 200),
    "Hard": (500, 150),
}
GAP_MS = {
    "Easy": (300, 300),
    "Normal": (300, 300),
    "Hard": (300, 100),
}

# Restored from flash; changed via the Settings menu. Selects the timing curve above.
difficulty = settings.get("memory", "difficulty", "Easy", ON_MS)


def _pick_difficulty(encoder):
    global difficulty
    options = ["Easy", "Normal", "Hard"]
    idx = show_menu(encoder, "DIFFICULTY", options, options.index(difficulty))
    difficulty = options[idx]
    settings.set("memory", "difficulty", difficulty)


def run_settings(encoder):
    options = ["Difficulty", "Back"]
    selected = 0
    while True:
        choice = show_menu(encoder, "SETTINGS", options, selected)
        selected = len(options) - 1  # after changing a setting, land on Back
        if choice == 0:
            _pick_difficulty(encoder)
        else:
            return


def _is_steady(btn, value):
    """True if `btn` reads `value` continuously for DEBOUNCE_MS (filters contact bounce)."""
    for _ in range(DEBOUNCE_MS):
        if btn.value() != value:
            return False
        sleep_ms(1)
    return True


def _wait_for_any_press():
    while True:
        check_exit()
        for idx, (led, btn) in enumerate(stages):
            if btn.value() == 0 and _is_steady(btn, 0):
                led.on()  # show which button registered while it's held
                while not _is_steady(btn, 1):
                    pass
                led.off()
                return idx


def _add_step(sequence):
    """Append a random LED index, never the same as the previous one: a back-to-back
    repeat is just the same LED blinking twice, which is hard to see."""
    if not sequence:
        sequence.append(random.randint(0, len(stages) - 1))
        return
    # Pick uniformly from the other len(stages) - 1 LEDs by skipping over the last one.
    idx = random.randint(0, len(stages) - 2)
    if idx >= sequence[-1]:
        idx += 1
    sequence.append(idx)


def run_classic(encoder):
    """Repeat a sequence that grows by one each round; score = rounds survived."""
    on_start, on_end = ON_MS[difficulty]
    gap_start, gap_end = GAP_MS[difficulty]

    try:
        all_leds_off()
        player = players.current()
        display.screen("MEMORY", ["", "", f"{difficulty} mode", player])
        display.draw_exit_button()
        sequence = []
        for _ in range(START_LENGTH):
            _add_step(sequence)

        round_num = 1
        while True:
            _add_step(sequence)

            t = min(1.0, (round_num - 1) / (RAMP_ROUNDS - 1))
            on_ms = int(on_start + (on_end - on_start) * t)
            gap_ms = int(gap_start + (gap_end - gap_start) * t)

            display.draw_row(0, f"Round {round_num}")
            display.draw_row(1, "Watch...")

            for idx in sequence:
                led, _ = stages[idx]
                led.on()
                wait_ms(on_ms)
                led.off()
                wait_ms(gap_ms)

            display.draw_row(1, "Your turn!")

            failed = False
            for expected_idx in sequence:
                pressed_idx = _wait_for_any_press()
                if pressed_idx != expected_idx:
                    print(f"Expected button {expected_idx + 1}, got {pressed_idx + 1}")
                    failed = True
                    break

            if failed:
                flash_all(300, 2000, wait_ms)
                print(f"Game over on round {round_num} - wrong button")
                print(f"You survived {round_num - 1} rounds")
                return round_num - 1, "GAME OVER", [
                    "Wrong button!",
                    f"Rounds: {round_num - 1}",
                ]

            print(f"Round {round_num} complete")
            display.draw_row(1, "Correct!")

            light_all(2, wait_ms)
            wait_ms(2000)

            round_num += 1
    finally:
        all_leds_off()


def run_endless(encoder):
    """TEMPORARY: placeholder mode to try out multi-mode menus. Scores a random number."""
    rounds = random.randint(5, 40)
    return rounds, "GAME OVER", ["Endless mode", f"Rounds: {rounds}"]


MODES = [
    Mode("classic", "Classic", run_classic, lambda rounds: f"{rounds} rnds", higher_is_better=True),
    Mode("endless", "Endless Mode", run_endless, lambda rounds: f"{rounds} rnds", higher_is_better=True),  # TEMPORARY
]
