"""Colour themes: the registry, its generated CSS and the contrast rules of each role."""

from __future__ import annotations

import re
import unittest

import dash_bootstrap_components as dbc

from driftline.domain.enums import ColorTheme
from driftline.ui import charts, ids, theme
from driftline.ui.layout import shell
from driftline.ui.pages import dashboard
from driftline.ui.pages.settings import theme_options

HEX = re.compile(r"^#[0-9a-f]{6}$")


def _luminance(hex_color: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(int(hex_color[i : i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class ThemeRegistryTest(unittest.TestCase):
    def tearDown(self):
        theme.use(theme.DEFAULT)

    def test_one_palette_per_enum_value(self):
        self.assertEqual(set(theme.THEMES), set(ColorTheme))
        self.assertEqual(len(theme.THEMES), 5)

    def test_palettes_are_complete(self):
        for p in theme.THEMES.values():
            with self.subTest(theme=p.label):
                self.assertEqual(len(p.categorical), 7)
                self.assertEqual(len(set(p.categorical)), 7)
                self.assertEqual(len(p.priority_ramp), 4)
                self.assertIn(len(p.wada), (3, 4))
                colours = [v for v in vars(p).values() if isinstance(v, str) and v.startswith("#")]
                colours += [*p.categorical, *p.priority_ramp, *(h for _, h in p.wada)]
                for c in colours:
                    self.assertRegex(c, HEX)

    def test_text_contrast_of_each_role(self):
        for p in theme.THEMES.values():
            with self.subTest(theme=p.label):
                self.assertGreaterEqual(contrast(p.primary, "#ffffff"), 4.5)  # navbar, buttons
                self.assertGreaterEqual(contrast(p.secondary, "#ffffff"), 4.5)  # segments
                self.assertGreaterEqual(contrast(p.accent, theme.INK), 4.5)  # "New task"
                self.assertGreaterEqual(contrast(p.accent_hover, theme.INK), 4.5)
                self.assertGreaterEqual(contrast(p.primary, theme.PAPER), 4.5)  # links

    def test_priority_ramp_runs_dark_to_light(self):
        for p in theme.THEMES.values():
            lum = [_luminance(c) for c in p.priority_ramp]
            self.assertEqual(lum, sorted(lum), p.label)

    def test_status_colours_stay_out_of_the_series(self):
        for p in theme.THEMES.values():
            self.assertNotIn(theme.CRITICAL, p.categorical, p.label)

    def test_use_switches_charts_and_falls_back(self):
        theme.use("no278")
        self.assertEqual(charts.categorical(), theme.THEMES[ColorTheme.NO278].categorical)
        self.assertEqual(charts.priority_colors()["Critical"], "#025a50")
        self.assertIs(theme.use("unknown"), theme.THEMES[theme.DEFAULT])
        self.assertIs(theme.use(None), theme.THEMES[theme.DEFAULT])

    def test_default_theme_keeps_the_original_colours(self):
        p = theme.THEMES[theme.DEFAULT]
        statuses = charts.task_status_colors()
        self.assertEqual(p.number, 309)
        self.assertEqual(statuses[charts.TaskStatus.IN_PROGRESS], "#006692")
        self.assertEqual(statuses[charts.TaskStatus.PLANNED], "#8cb8d2")

    def test_generated_css_is_up_to_date(self):
        self.assertEqual(
            theme.CSS_PATH.read_text(encoding="utf-8"),
            theme.themes_css(),
            "run: python -m driftline.ui.theme",
        )

    def test_shell_carries_the_theme_class(self):
        frame = shell([], theme.THEMES[ColorTheme.NO134])
        self.assertEqual(frame.className, "pm-theme-no134")

    def test_settings_offer_every_theme(self):
        options = theme_options()
        self.assertEqual([o["value"] for o in options], [t.value for t in theme.THEMES])


class DashboardOrderTest(unittest.TestCase):
    def test_day_spans_the_page_and_warnings_come_last(self):
        blocks = dashboard.layout().children[2:]  # after the header and the KPI row
        found = [{getattr(c, "id", None) for c in block._traverse()} for block in blocks]
        self.assertIsInstance(blocks[0], dbc.Card)  # full width, not inside a column
        self.assertIn(ids.DASH_DAY, found[0])
        self.assertIn(ids.DASH_DELAYED, found[1])
        self.assertLessEqual({ids.DASH_MS_WARNINGS, ids.DASH_DEP_WARNINGS}, found[2])
        self.assertEqual(len(blocks), 3)


if __name__ == "__main__":
    unittest.main()
