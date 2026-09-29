from time import sleep_ms
from hardware import RotaryEncoder
from ili9341 import color565
from ui import card_menu, game_menu, last_mode, best_line, pick_player
import players
import reflex
import memory
import touch

encoder = RotaryEncoder()

# Calibrate touch on first boot, or when the encoder button is held at power-on.
if touch.needs_calibration() or encoder.sw.value() == 0:
    while encoder.sw.value() == 0:  # let go first, so the held click doesn't select in the menu
        sleep_ms(10)
    touch.calibrate()

# Each game module provides NAME, TITLE, COLOR, MODES, difficulty and run_settings().
GAMES = [reflex, memory]
PLAYERS_COLOR = color565(80, 150, 255)


def _game_card(game, player):
    # Show the best in the mode played last, named on its own line once a game has several.
    mode = game.MODES[last_mode(game)]
    best = best_line(game, mode, player)
    lines = best if len(game.MODES) == 1 else [mode.name, best]
    return (game.TITLE, game.COLOR, game.difficulty.upper(), lines)


def _cards(player):
    # Built fresh each time so the tags and bests reflect the latest games.
    return [_game_card(game, player) for game in GAMES] + [
        ("Change Player", PLAYERS_COLOR, "", f"{len(players.names())} players"),
    ]


choice = 0
while True:
    player = players.current()
    # The title bar shows whose scores the next game will be credited to (14 chars fit).
    choice = card_menu(encoder, f"[ {player[:10]} ]", _cards(player), choice)
    if choice < len(GAMES):
        game_menu(encoder, GAMES[choice])
    else:
        pick_player(encoder)
