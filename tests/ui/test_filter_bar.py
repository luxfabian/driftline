"""Filter bar: fields per page and the "More filters" counter."""

from __future__ import annotations

import unittest
from datetime import date

from driftline.domain.filters import Filter
from driftline.ui import ids
from driftline.ui.app import create_app  # noqa: F401 - registers the pages
from driftline.ui.components import filter_bar
from driftline.ui.state import filter_to_store
from tests.ui.test_app import component_ids


def control_fields(component) -> set[str]:
    found = [component, *component._traverse()]
    return {
        c.id["field"]
        for c in found
        if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == ids.FILTER_CTL
    }


class FilterBarTest(unittest.TestCase):
    def test_task_pages_show_every_field(self):
        self.assertEqual(control_fields(filter_bar.layout("tasks")), set(filter_bar.TASK_FIELDS))

    def test_workload_shows_only_demand_fields(self):
        bar = filter_bar.layout("workload", filter_bar.WORKLOAD_FIELDS)
        self.assertEqual(control_fields(bar), set(filter_bar.WORKLOAD_FIELDS))
        self.assertNotIn("statuses", control_fields(bar))

    def test_bar_ids(self):
        bar = filter_bar.layout("tasks")
        self.assertEqual(bar.id, ids.filter_bar("tasks"))
        self.assertIn(ids.FILTER_MORE_PANEL, component_ids(bar))

    def test_more_count(self):
        self.assertEqual(filter_bar.more_count(None), 0)
        store = filter_to_store(Filter(at_risk_only=True, date_from=date(2026, 10, 1)))
        self.assertEqual(filter_bar.more_count(store), 2)
        main_only = filter_to_store(Filter(labels=frozenset({1})))
        self.assertEqual(filter_bar.more_count(main_only), 0)


if __name__ == "__main__":
    unittest.main()
