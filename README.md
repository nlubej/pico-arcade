# rpi-pico-arcade-game

An arcade-style game written in MicroPython for the Raspberry Pi Pico 2 W (RP2350 + wireless).

## Hardware

- Raspberry Pi Pico 2 W (Pico 2 WH — with pre-soldered headers)
- Micro-USB cable
- 5 LEDs + push buttons (GPIO12-21, one LED/button pair per GPIO pair: 12/13, 14/15, 16/17, 18/19, 20/21)
- KY-040 rotary encoder for menu navigation: CLK → GPIO5, DT → GPIO6, SW → GPIO7, `+` → 3V3(OUT), GND → GND
- 2.8" ILI9341 240x320 SPI TFT (hardware SPI0): CS → GPIO0, RESET → GPIO1, SCK → GPIO2, SDI/MOSI → GPIO3, DC → GPIO4, VCC and LED → 3V3(OUT), GND → GND. SDO/MISO is not connected (nothing is read back from the display).
- The same board's XPT2046 resistive touch panel (hardware SPI1): T_CLK → GPIO10, T_CS → GPIO9, T_DIN → GPIO11, T_DO → GPIO8, T_IRQ → GPIO22. It is powered through the display's VCC/GND.

## One-time setup

### 1. Flash MicroPython firmware

1. Download the latest **Pico 2 W** UF2 build from https://micropython.org/download/RPI_PICO2_W/
2. Hold the **BOOTSEL** button on the board while plugging it into USB.
3. It mounts as a mass-storage drive (`RPI-RP2`). Drag the downloaded `.uf2` file onto it.
4. The board reboots automatically running MicroPython.

### 2. Install dev tools (on this machine)

```powershell
py -m pip install -r requirements-dev.txt
```

This installs `mpremote`, which talks to the board over its USB serial port to run code, copy files, and open a REPL. It's a host-side tool only — it doesn't run on the Pico, and there's nothing to install on-device for this project yet.

### 3. Editor

VS Code with the extension [MicroPico](https://marketplace.visualstudio.com/items?itemName=paulober.pico-w-go) gives you run/upload buttons and a REPL inside VS Code. Alternatively, [Thonny](https://thonny.org/) has first-class Pico support out of the box and is the easiest way to get started.

## Usage

The game is split across a few files (`main.py`, `hardware.py`, `ili9341.py`, `display.py`, `ui.py`, `storage.py`, `settings.py`, `scores.py`, `players.py`, `reflex.py`, `memory.py`, `touch.py`) plus the `players.txt` name list, which all need to be on the board together, since `main.py` imports the others.

Run it on the Pico without copying anything permanently (great for iterating — note this only runs `main.py`, so copy the rest first with the command below):

```powershell
py -m mpremote run main.py
```

Copy all the files onto the board so it runs automatically on power-up, then restart it:

```powershell
.\deploy.ps1
```

This copies every `.py` file in the folder plus `players.txt` (unchanged files are skipped) and leaves the saved scores and settings on the board alone. Use `.\deploy.ps1 -Port COM7` to pick a port. If the port is busy, disconnect MicroPico in VS Code first.

Open a REPL:

```powershell
py -m mpremote
```

(Ctrl-] to exit, or Ctrl-C to interrupt a running program.)

## Current state

The main menu on the LCD is a list of cards, one per game plus **Change Player**, navigated with the rotary encoder or by touch (also mirrored to USB serial for debugging). Each game card shows its difficulty and your rank and best score in the mode you played last. The games:

- **Reflex**: lights up 1/2/3 buttons at once (Easy/Normal/Hard) for 10 rounds and times how fast you press them, with an adjustable pre-light wait time.
- **Memory**: a Simon-Says style game. Repeat a growing LED sequence until you make a mistake; Easy/Normal/Hard control how much the playback speeds up and tightens as it goes.

Picking a game opens its screen: one card per mode (currently just **Classic**) showing your best in it, then **Leaderboard**, **Settings** and **Back**. After a game you return there to play again.

The leaderboard shows every player's best for one mode and difficulty. Turning changes whatever is highlighted and clicking moves down one step: mode (once a game has more than one) → difficulty → the list, where turning scrolls from your own entry → back to the top. **Back** is the stop after the last mode (or after Hard, while there is only one mode).

### Touch

Tapping a card or row opens it, dragging up or down scrolls long lists, and on the leaderboard tapping the left or right half of the mode/difficulty row steps it back or forward. The panel is resistive, so press with a fingernail or stylus rather than a fingertip. Gameplay itself stays on the buttons, apart from the red **Exit** button near the bottom of the screen while a game runs: tapping it abandons the game on the spot, recording no score and leaving the last-played mode unchanged.

On first boot the screen asks you to tap three crosses, which maps the panel's raw readings to pixels (saved in `settings.json`). To redo it, hold the encoder button while powering on or resetting the board, then let go.

### Adding a mode

Each game file (`reflex.py`, `memory.py`) ends with a `MODES` list. Write a `run_...(encoder)` function that plays one game and returns `(score, result_title, result_lines)`, then add a line such as:

```python
Mode("timeattack", "Time attack", run_time_attack, lambda n: f"{n} hits", higher_is_better=True),
```

The game screen, leaderboard, best-score tracking and "New best!" message all pick it up. To support the Exit button, call `display.draw_exit_button()` after drawing the game screen, pause with `ui.wait_ms()` instead of `sleep`/`sleep_ms`, and call `ui.check_exit()` inside any loop that waits for a button. Scores are stored per mode in `scores.json` under keys like `reflex/classic`.

Settings and leaderboards are saved to the Pico's flash, so they survive power-off:

- `settings.json`: the current player and each game's chosen difficulty (and Reflex's wait time), written only when a setting changes.
- `scores.json`: the leaderboards, written when a game sets a new personal best.

Writes go to a temporary file that then replaces the real one, so unplugging mid-save keeps the previous data instead of corrupting it. To reset, delete a file: `py -m mpremote fs rm :scores.json` (leaderboards) or `py -m mpremote fs rm :settings.json` (settings back to defaults).

## Players

Scores are credited to the current player, whose name is shown in the main menu's title bar. Pick a different one with the **Players** card in the main menu; the choice is remembered across power-off.

The names come from `players.txt`, one per line (blank lines and duplicates are ignored). Typing names with the encoder would be slow, so edit the file on the PC and copy it to the board:

```powershell
py -m mpremote fs cp players.txt :
```

The file is re-read each time it's needed, so there's no need to reboot. If it's missing or empty, scores go to a single `Player`. Removing a name keeps that player's scores on the leaderboards; if they were the current player, the first name in the file takes over. Up to 8 characters of each name are shown on the leaderboard (10 in the main menu title).

Each leaderboard keeps one entry per player, their personal best, so one strong player can't fill the board. A game only changes the board when you beat your own best, and the result screen then shows your new rank.
