# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 brunos3d
# This program comes with ABSOLUTELY NO WARRANTY. See LICENSE and the
# hardware disclaimer in README.md.
"""Core power-mode logic, independent of D-Bus and NVML.

PowerController maps three modes (saver / balanced / performance) onto the
card's own power range, discovered at runtime from the backend:

    limits() -> (min_w, performance_w, hw_max_w)
    get_limit() -> int   # current power limit, watts
    get_draw() -> int    # current power draw, watts
    set_limit(watts)     # apply a new power limit

Performance is the card's default (rated) limit, not the absolute hardware
max, so the tool never pushes the GPU past its stock power. Keeping this
pure makes the mapping unit-testable without a GPU, and with no test ever
raising real power.
"""

MODE_SAVER = "saver"
MODE_BALANCED = "balanced"
MODE_PERFORMANCE = "performance"
MODE_CUSTOM = "custom"


class PowerController:
    def __init__(self, backend):
        self._b = backend
        self.min_w, self.performance_w, self.hw_max_w = backend.limits()
        self._watts = self.clamp(self._b.get_limit())
        self._mode = self._detect_mode(self._watts)

    @property
    def watts(self):
        return self._watts

    @property
    def mode(self):
        return self._mode

    def balanced_w(self):
        return (self.min_w + self.performance_w) // 2

    def presets(self):
        return {
            MODE_SAVER: self.min_w,
            MODE_BALANCED: self.balanced_w(),
            MODE_PERFORMANCE: self.performance_w,
        }

    def clamp(self, watts):
        watts = int(round(watts))
        return max(self.min_w, min(self.performance_w, watts))

    def _detect_mode(self, watts):
        if watts <= self.min_w:
            return MODE_SAVER
        if watts >= self.performance_w:
            return MODE_PERFORMANCE
        if watts == self.balanced_w():
            return MODE_BALANCED
        return MODE_CUSTOM

    def set_watts(self, watts):
        self._watts = self.clamp(watts)
        self._mode = self._detect_mode(self._watts)
        self._b.set_limit(self._watts)
        return self._watts

    def set_mode(self, name):
        presets = self.presets()
        if name not in presets:
            raise ValueError(f"unknown mode: {name}")
        return self.set_watts(presets[name])

    def status(self):
        try:
            draw = self._b.get_draw()
        except Exception:
            draw = -1
        return {
            "mode": self._mode,
            "watts": self._watts,
            "min": self.min_w,
            "performance": self.performance_w,
            "balanced": self.balanced_w(),
            "hw_max": self.hw_max_w,
            "draw": draw,
        }
