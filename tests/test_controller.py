"""Unit tests for PowerController. No test raises real GPU power; a fake
backend records the calls. Run: /usr/bin/python3 -m unittest -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "daemon"))

from controller import (  # noqa: E402
    PowerController,
    MODE_SAVER,
    MODE_BALANCED,
    MODE_PERFORMANCE,
    MODE_CUSTOM,
)


class FakeBackend:
    """Mimics an RTX 3060 Ti: 100W min, 225W default, 248W hw max."""

    def __init__(self, current=150):
        self._limit = current
        self.calls = []

    def limits(self):
        return (100, 225, 248)

    def get_limit(self):
        return self._limit

    def get_draw(self):
        return 90

    def set_limit(self, watts):
        self._limit = watts
        self.calls.append(watts)


class PresetTests(unittest.TestCase):
    def test_presets_map_to_card_range(self):
        c = PowerController(FakeBackend())
        p = c.presets()
        self.assertEqual(p[MODE_SAVER], 100)
        self.assertEqual(p[MODE_PERFORMANCE], 225)
        self.assertEqual(p[MODE_BALANCED], 162)  # (100+225)//2

    def test_set_mode_applies_watts(self):
        b = FakeBackend()
        c = PowerController(b)
        c.set_mode(MODE_SAVER)
        self.assertEqual(c.watts, 100)
        self.assertEqual(c.mode, MODE_SAVER)
        self.assertEqual(b.calls[-1], 100)

    def test_performance_is_default_not_hw_max(self):
        c = PowerController(FakeBackend())
        c.set_mode(MODE_PERFORMANCE)
        self.assertEqual(c.watts, 225)  # never 248
        self.assertEqual(c.mode, MODE_PERFORMANCE)

    def test_unknown_mode_raises(self):
        c = PowerController(FakeBackend())
        with self.assertRaises(ValueError):
            c.set_mode("turbo")


class ClampTests(unittest.TestCase):
    def test_clamped_below_min(self):
        c = PowerController(FakeBackend())
        self.assertEqual(c.set_watts(50), 100)

    def test_clamped_above_default(self):
        c = PowerController(FakeBackend())
        self.assertEqual(c.set_watts(300), 225)

    def test_custom_value_reports_custom_mode(self):
        c = PowerController(FakeBackend())
        c.set_watts(180)
        self.assertEqual(c.watts, 180)
        self.assertEqual(c.mode, MODE_CUSTOM)


class DetectTests(unittest.TestCase):
    def test_initial_mode_from_current_limit(self):
        self.assertEqual(PowerController(FakeBackend(100)).mode, MODE_SAVER)
        self.assertEqual(PowerController(FakeBackend(225)).mode, MODE_PERFORMANCE)
        self.assertEqual(PowerController(FakeBackend(162)).mode, MODE_BALANCED)
        self.assertEqual(PowerController(FakeBackend(150)).mode, MODE_CUSTOM)

    def test_status_shape(self):
        c = PowerController(FakeBackend(100))
        s = c.status()
        self.assertEqual(s["mode"], MODE_SAVER)
        self.assertEqual(s["watts"], 100)
        self.assertEqual(s["min"], 100)
        self.assertEqual(s["performance"], 225)
        self.assertEqual(s["hw_max"], 248)
        self.assertEqual(s["draw"], 90)


if __name__ == "__main__":
    unittest.main()
