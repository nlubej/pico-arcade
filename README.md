# rpi-pico-arcade-game

An arcade-style game written in MicroPython for the Raspberry Pi Pico 2 W (RP2350 + wireless).

## Hardware

- Raspberry Pi Pico 2 W (Pico 2 WH — with pre-soldered headers)
- Micro-USB cable

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

Run a file on the Pico without copying it (great for iterating):

```powershell
py -m mpremote run main.py
```

Copy `main.py` onto the board so it runs automatically on power-up:

```powershell
py -m mpremote fs cp main.py :main.py
```

Open a REPL:

```powershell
py -m mpremote
```

(Ctrl-] to exit, or Ctrl-C to interrupt a running program.)

## Current state

`main.py` blinks the onboard LED once per second — confirms the toolchain and board are working end to end. Game logic starts from here.
