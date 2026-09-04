#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 brunos3d
# This program comes with ABSOLUTELY NO WARRANTY. See LICENSE and the
# hardware disclaimer in README.md.
"""gpupowerd: system D-Bus service for GPU power-limit management.

Runs as root (systemd). Exposes org.bruno.GpuPowerMode on the system bus so
the unprivileged GNOME extension can pick a power mode. Persists the chosen
watts and re-applies it on start, so the mode survives reboots.
"""
import json
import os
import signal
import sys

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from controller import PowerController  # noqa: E402
from nvml_backend import NvmlBackend  # noqa: E402

BUS_NAME = "org.bruno.GpuPowerMode"
OBJ_PATH = "/org/bruno/GpuPowerMode"
IFACE = "org.bruno.GpuPowerMode"

STATE_FILE = "/var/lib/gpu-power-mode/state.json"


def load_saved_watts():
    try:
        with open(STATE_FILE) as f:
            return int(json.load(f)["watts"])
    except Exception:
        return None


def save_watts(watts):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"watts": int(watts)}, f)
    except Exception as e:
        sys.stderr.write(f"could not persist state: {e}\n")


class PowerService(dbus.service.Object):
    def __init__(self, bus, controller):
        super().__init__(bus, OBJ_PATH)
        self._c = controller

    @dbus.service.method(IFACE, in_signature="u", out_signature="u")
    def SetWatts(self, watts):
        applied = self._c.set_watts(int(watts))
        save_watts(applied)
        self._emit_changed()
        return applied

    @dbus.service.method(IFACE, in_signature="s", out_signature="u")
    def SetMode(self, name):
        applied = self._c.set_mode(str(name))
        save_watts(applied)
        self._emit_changed()
        return applied

    @dbus.service.method(IFACE, in_signature="", out_signature="a{sv}")
    def GetStatus(self):
        return self._status_variant()

    @dbus.service.signal(IFACE, signature="a{sv}")
    def Changed(self, status):
        pass

    def _status_variant(self):
        s = self._c.status()
        return {
            "mode": dbus.String(s["mode"]),
            "watts": dbus.UInt32(s["watts"]),
            "min": dbus.UInt32(s["min"]),
            "performance": dbus.UInt32(s["performance"]),
            "balanced": dbus.UInt32(s["balanced"]),
            "hw_max": dbus.UInt32(s["hw_max"]),
            "draw": dbus.Int32(s["draw"]),
        }

    def _emit_changed(self):
        self.Changed(self._status_variant())

    def refresh(self):
        # Periodic Changed so an open menu sees live power draw.
        self._emit_changed()
        return True


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    name = dbus.service.BusName(BUS_NAME, bus)  # noqa: F841 (holds the name)

    backend = NvmlBackend()
    controller = PowerController(backend)

    saved = load_saved_watts()
    if saved is not None:
        controller.set_watts(saved)  # re-apply persisted mode at boot

    service = PowerService(bus, controller)
    GLib.timeout_add_seconds(2, service.refresh)

    loop = GLib.MainLoop()

    def shutdown(*_):
        try:
            backend.close()
        finally:
            loop.quit()

    try:
        from gi.repository import GLibUnix
        add_signal = lambda s: GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, s, shutdown)
    except ImportError:
        add_signal = lambda s: GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, s, shutdown)
    for sig in (signal.SIGTERM, signal.SIGINT):
        add_signal(sig)

    mn, perf, hw = backend.limits()
    sys.stderr.write(
        f"gpupowerd ready: {backend.name()} | {mn}-{perf}W (hw max {hw}W) | "
        f"current {controller.watts}W\n")
    loop.run()


if __name__ == "__main__":
    main()
