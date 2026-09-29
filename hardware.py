from machine import Pin
from time import sleep_ms
import random

# Each stage: (led, button)
stages = [
    (Pin(13, Pin.OUT), Pin(12, Pin.IN, Pin.PULL_UP)),
    (Pin(15, Pin.OUT), Pin(14, Pin.IN, Pin.PULL_UP)),
    (Pin(17, Pin.OUT), Pin(16, Pin.IN, Pin.PULL_UP)),
    (Pin(19, Pin.OUT), Pin(18, Pin.IN, Pin.PULL_UP)),
    (Pin(21, Pin.OUT), Pin(20, Pin.IN, Pin.PULL_UP)),
]


def shuffled(items):
    # MicroPython's random module has no shuffle(), so do Fisher-Yates by hand.
    items = list(items)
    for i in range(len(items) - 1, 0, -1):
        j = random.randint(0, i)
        items[i], items[j] = items[j], items[i]
    return items


def all_leds_off():
    for led, _ in stages:
        led.off()


def light_all(seconds, wait_ms=sleep_ms):
    # `wait_ms` lets a game pass a pause that can be interrupted (see ui.wait_ms).
    for led, _ in stages:
        led.on()
    wait_ms(int(seconds * 1000))
    all_leds_off()


def flash_all(interval_ms, total_ms, wait_ms=sleep_ms):
    elapsed_ms = 0
    state = False
    while elapsed_ms < total_ms:
        state = not state
        for led, _ in stages:
            led.value(state)
        wait_ms(interval_ms)
        elapsed_ms += interval_ms
    all_leds_off()


# Quadrature transition table indexed by (old_state << 2) | new_state, where state = (clk << 1) | dt.
# Invalid jumps (contact bounce) score 0, so noise cancels out instead of flipping direction.
_TRANSITIONS = (0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0)
_DETENT = 0b11  # KY-040 rests with both pins high between clicks


class RotaryEncoder:
    def __init__(self, clk_pin=5, dt_pin=6, sw_pin=7):
        self.clk = Pin(clk_pin, Pin.IN, Pin.PULL_UP)
        self.dt = Pin(dt_pin, Pin.IN, Pin.PULL_UP)
        self.sw = Pin(sw_pin, Pin.IN, Pin.PULL_UP)
        self._position = 0
        self._accum = 0
        self._state = self._read()
        edges = Pin.IRQ_FALLING | Pin.IRQ_RISING
        self.clk.irq(trigger=edges, handler=self._on_edge)
        self.dt.irq(trigger=edges, handler=self._on_edge)

    def _read(self):
        return (self.clk.value() << 1) | self.dt.value()

    def _on_edge(self, pin):
        new = self._read()
        self._accum += _TRANSITIONS[(self._state << 2) | new]
        self._state = new
        # Only count a step once the knob settles into a click, so bounce mid-turn can't add extra steps.
        if new == _DETENT:
            if self._accum >= 2:
                self._position += 1
            elif self._accum <= -2:
                self._position -= 1
            self._accum = 0

    def take_delta(self):
        delta = self._position
        self._position = 0
        return delta

    def pressed(self):
        if self.sw.value() == 0:
            while self.sw.value() == 0:
                pass
            return True
        return False
