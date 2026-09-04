# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 brunos3d
# This program comes with ABSOLUTELY NO WARRANTY. See LICENSE and the
# hardware disclaimer in README.md.
"""NVML backend: reads the card's power range and applies a power limit.
Requires root and pynvml (python-nvidia-ml-py). Works on Wayland because
NVML does not depend on the display server.

NVML reports power in milliwatts; this wrapper speaks whole watts.
"""
import pynvml


class NvmlBackend:
    def __init__(self, index=0):
        pynvml.nvmlInit()
        self._h = pynvml.nvmlDeviceGetHandleByIndex(index)

    def name(self):
        name = pynvml.nvmlDeviceGetName(self._h)
        return name.decode() if isinstance(name, bytes) else name

    def limits(self):
        mn, mx = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(self._h)
        default = pynvml.nvmlDeviceGetPowerManagementDefaultLimit(self._h)
        # performance target = rated default, not the absolute hardware max
        return (round(mn / 1000), round(default / 1000), round(mx / 1000))

    def get_limit(self):
        return round(pynvml.nvmlDeviceGetPowerManagementLimit(self._h) / 1000)

    def get_draw(self):
        return round(pynvml.nvmlDeviceGetPowerUsage(self._h) / 1000)

    def set_limit(self, watts):
        pynvml.nvmlDeviceSetPowerManagementLimit(self._h, int(watts) * 1000)

    def close(self):
        pynvml.nvmlShutdown()
