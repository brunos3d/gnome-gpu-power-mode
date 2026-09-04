#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 brunos3d
"""Read-only check of the card's power range. Sets nothing, so it cannot
cause a shutdown. Run: sudo python3 spike_nvml.py
"""
import sys

try:
    import pynvml
except ImportError:
    print("FAIL: pynvml not installed (pacman -S python-nvidia-ml-py)")
    sys.exit(2)

pynvml.nvmlInit()
h = pynvml.nvmlDeviceGetHandleByIndex(0)
name = pynvml.nvmlDeviceGetName(h)
mn, mx = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(h)
default = pynvml.nvmlDeviceGetPowerManagementDefaultLimit(h)
cur = pynvml.nvmlDeviceGetPowerManagementLimit(h)
draw = pynvml.nvmlDeviceGetPowerUsage(h)
print(f"gpu:        {name.decode() if isinstance(name, bytes) else name}")
print(f"min:        {round(mn/1000)} W   (Power Saver)")
print(f"default:    {round(default/1000)} W   (Performance)")
print(f"hw max:     {round(mx/1000)} W")
print(f"current:    {round(cur/1000)} W")
print(f"draw now:   {round(draw/1000)} W")
pynvml.nvmlShutdown()
