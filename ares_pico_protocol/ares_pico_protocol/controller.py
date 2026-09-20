"""Framebuffer operations and host-generated LED animations."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
import math
import random
from typing import Sequence

from .protocol import MAX_LED_COUNT


class CommandError(ValueError):
    """Raised when a ROS command array is invalid."""


@dataclass
class Animation:
    left: int
    right: int
    effect: int
    params: tuple[int, ...]
    phase: int = 0


class LedController:
    """Own the complete RGB framebuffer and apply inclusive-range commands."""

    EFFECT_NAMES = {
        0: 'stop',
        1: 'chase_forward',
        2: 'chase_reverse',
        3: 'rainbow',
        4: 'theater_chase',
        5: 'breathing',
        6: 'scanner',
        7: 'twinkle',
        8: 'color_wipe',
        9: 'two_color_marquee',
        10: 'comet',
    }

    _DEFAULT_PARAMS = {
        1: (255, 0, 0, 1),
        2: (0, 0, 255, 1),
        3: (3,),
        4: (255, 160, 0, 3),
        5: (255, 255, 255, 60),
        6: (0, 255, 255, 3),
        7: (255, 255, 255, 15),
        8: (0, 255, 0, 1),
        9: (255, 0, 0, 0, 0, 255, 3),
        10: (255, 0, 255, 8, 1),
    }

    def __init__(self, *, random_seed: int = 0xA2E5):
        self.led_count = 0
        self.frame = bytearray()
        self.animation: Animation | None = None
        self._random = random.Random(random_seed)

    def _validate_header(self, data: Sequence[int], minimum_length: int) -> tuple[int, int, int]:
        if len(data) < minimum_length:
            raise CommandError(f'command requires at least {minimum_length} integers')
        led_count, left, right = (int(data[0]), int(data[1]), int(data[2]))
        if not 1 <= led_count <= MAX_LED_COUNT:
            raise CommandError(f'LED count must be in 1..{MAX_LED_COUNT}')
        if left < 0 or right < left or right >= led_count:
            raise CommandError(
                f'invalid inclusive range [{left}, {right}] for {led_count} LEDs'
            )
        return led_count, left, right

    @staticmethod
    def _validate_rgb(values: Sequence[int]) -> tuple[int, int, int]:
        if len(values) != 3:
            raise CommandError('RGB color requires exactly three integers')
        rgb = tuple(int(value) for value in values)
        if any(value < 0 or value > 255 for value in rgb):
            raise CommandError('RGB channels must be in 0..255')
        return rgb

    def _resize(self, led_count: int) -> None:
        if led_count == self.led_count:
            return
        resized = bytearray(led_count * 3)
        copied_leds = min(led_count, self.led_count)
        resized[:copied_leds * 3] = self.frame[:copied_leds * 3]
        self.frame = resized
        self.led_count = led_count

    def _set_pixel(self, index: int, rgb: Sequence[int]) -> None:
        offset = index * 3
        self.frame[offset:offset + 3] = bytes(rgb)

    def _fill(self, left: int, right: int, rgb: Sequence[int]) -> None:
        pixel = bytes(rgb)
        self.frame[left * 3:(right + 1) * 3] = pixel * (right - left + 1)

    def apply_single(self, values: Sequence[int]) -> bytes:
        led_count, left, right = self._validate_header(values, 6)
        expected_length = 3 + (right - left + 1) * 3
        if len(values) != expected_length:
            raise CommandError(
                f'single command length must be {expected_length}, got {len(values)}'
            )
        colors = values[3:]
        for offset in range(0, len(colors), 3):
            self._validate_rgb(colors[offset:offset + 3])
        self.animation = None
        self._resize(led_count)
        self.frame[left * 3:(right + 1) * 3] = bytes(colors)
        return bytes(self.frame)

    def apply_segment(self, values: Sequence[int]) -> bytes:
        if len(values) != 6:
            raise CommandError(f'segment command length must be 6, got {len(values)}')
        led_count, left, right = self._validate_header(values, 6)
        rgb = self._validate_rgb(values[3:6])
        self.animation = None
        self._resize(led_count)
        self._fill(left, right, rgb)
        return bytes(self.frame)

    def start_animation(self, values: Sequence[int]) -> bytes:
        led_count, left, right = self._validate_header(values, 4)
        effect = int(values[3])
        if effect not in self.EFFECT_NAMES:
            raise CommandError(f'unknown animation effect {effect}')
        self._resize(led_count)
        if effect == 0:
            if len(values) != 4:
                raise CommandError('stop animation does not accept parameters')
            self.animation = None
            return bytes(self.frame)

        supplied = tuple(int(value) for value in values[4:])
        defaults = self._DEFAULT_PARAMS[effect]
        if supplied and len(supplied) != len(defaults):
            raise CommandError(
                f'effect {effect} accepts either 0 or {len(defaults)} parameters'
            )
        params = supplied or defaults
        self._validate_animation_params(effect, params)
        self.animation = Animation(left, right, effect, params)
        return bytes(self.frame)

    def _validate_animation_params(self, effect: int, params: tuple[int, ...]) -> None:
        if effect in (1, 2, 4, 5, 6, 7, 8, 10):
            self._validate_rgb(params[:3])
        if effect == 9:
            self._validate_rgb(params[:3])
            self._validate_rgb(params[3:6])
        scalar = params[-1]
        if effect in (1, 2, 4, 6, 9) and scalar < 1:
            raise CommandError('width/gap parameter must be at least 1')
        if effect == 3 and not 1 <= scalar <= 255:
            raise CommandError('rainbow speed must be in 1..255')
        if effect == 5 and scalar < 2:
            raise CommandError('breathing period must be at least 2 frames')
        if effect == 7 and not 1 <= scalar <= 100:
            raise CommandError('twinkle density must be in 1..100 percent')
        if effect in (8, 10) and scalar not in (-1, 1):
            raise CommandError('direction must be -1 or 1')
        if effect == 10 and params[3] < 1:
            raise CommandError('comet tail length must be at least 1')

    def tick(self) -> bytes | None:
        animation = self.animation
        if animation is None:
            return None
        left, right = animation.left, animation.right
        length = right - left + 1
        effect = animation.effect
        params = animation.params
        phase = animation.phase

        if effect in (1, 2):
            r, g, b, width = params
            self._fill(left, right, (0, 0, 0))
            head = phase % length if effect == 1 else right - (phase % length) - left
            for offset in range(min(width, length)):
                position = (head + offset) % length if effect == 1 else (head - offset) % length
                self._set_pixel(left + position, (r, g, b))
        elif effect == 3:
            speed = params[0]
            for offset in range(length):
                hue = ((offset * 256 // length) + phase * speed) % 256
                rgb = colorsys.hsv_to_rgb(hue / 256.0, 1.0, 1.0)
                self._set_pixel(left + offset, tuple(round(channel * 255) for channel in rgb))
        elif effect == 4:
            r, g, b, gap = params
            for offset in range(length):
                color = (r, g, b) if (offset + phase) % gap == 0 else (0, 0, 0)
                self._set_pixel(left + offset, color)
        elif effect == 5:
            r, g, b, period = params
            level = (math.sin(2.0 * math.pi * (phase % period) / period) + 1.0) / 2.0
            self._fill(left, right, (round(r * level), round(g * level), round(b * level)))
        elif effect == 6:
            r, g, b, width = params
            self._fill(left, right, (0, 0, 0))
            span = length - 1
            if span == 0:
                position = 0
            else:
                cycle = span * 2
                cursor = phase % cycle
                position = cursor if cursor <= span else cycle - cursor
            for offset in range(-(width // 2), width - width // 2):
                pixel = position + offset
                if 0 <= pixel < length:
                    self._set_pixel(left + pixel, (r, g, b))
        elif effect == 7:
            r, g, b, density = params
            self._fill(left, right, (0, 0, 0))
            count = max(1, length * density // 100)
            for pixel in self._random.sample(range(length), min(count, length)):
                self._set_pixel(left + pixel, (r, g, b))
        elif effect == 8:
            r, g, b, direction = params
            position = phase % (length + 1)
            if position == 0:
                self._fill(left, right, (0, 0, 0))
            elif direction == 1:
                self._set_pixel(left + position - 1, (r, g, b))
            else:
                self._set_pixel(right - position + 1, (r, g, b))
        elif effect == 9:
            r1, g1, b1, r2, g2, b2, block = params
            for offset in range(length):
                group = ((offset + phase) // block) % 2
                self._set_pixel(left + offset, (r1, g1, b1) if group == 0 else (r2, g2, b2))
        elif effect == 10:
            r, g, b, tail, direction = params
            self._fill(left, right, (0, 0, 0))
            head = phase % length
            if direction == -1:
                head = length - 1 - head
            for distance in range(min(tail, length)):
                pixel = head - distance * direction
                if 0 <= pixel < length:
                    level = (tail - distance) / tail
                    self._set_pixel(
                        left + pixel,
                        (round(r * level), round(g * level), round(b * level)),
                    )

        animation.phase += 1
        return bytes(self.frame)
