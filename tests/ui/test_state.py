"""Filter (de)serialization for dcc.Store (architecture §9.2)."""

from __future__ import annotations

import json
import unittest
from datetime import date

from pmtool.domain.enums import TaskStatus
from pmtool.domain.filters import Filter
from pmtool.ui import ids
from pmtool.ui.state import filter_from_store, filter_to_store, merge_into_store, parse_date


class FilterStoreTest(unittest.TestCase):
    def test_round_trip_through_json(self):
        f = Filter(
            labels=frozenset({3, 1}),
            label_mode="all",
            priorities=frozenset({1, 2}),
            statuses=frozenset({TaskStatus.BLOCKED, TaskStatus.DONE}),
            at_risk_only=True,
            milestone_ids=frozenset({7}),
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            include_archived=True,
        )
        stored = json.loads(json.dumps(filter_to_store(f)))
        self.assertEqual(filter_from_store(stored), f)

    def test_default_round_trip(self):
        self.assertTrue(filter_from_store(filter_to_store(Filter())).is_default)

    def test_empty_store_is_default_filter(self):
        self.assertEqual(filter_from_store(None), Filter())
        self.assertEqual(filter_from_store({}), Filter())

    def test_broken_values_fall_back_per_field(self):
        f = filter_from_store(
            {"labels": ["x", 2], "label_mode": "weird", "priorities": [9, 1],
             "statuses": ["done", "nope"], "date_from": "not a date"}
        )  # fmt: skip
        self.assertEqual(f.labels, frozenset({2}))
        self.assertEqual(f.label_mode, "any")
        self.assertEqual(f.priorities, frozenset({1}))
        self.assertEqual(f.statuses, frozenset({TaskStatus.DONE}))
        self.assertIsNone(f.date_from)


class MergeIntoStoreTest(unittest.TestCase):
    def test_only_given_fields_change(self):
        store = filter_to_store(
            Filter(statuses=frozenset({TaskStatus.DONE}), date_from=date(2026, 10, 1))
        )
        merged = merge_into_store(store, {"labels": [2, 1], "priorities": [1]})
        f = filter_from_store(merged)
        self.assertEqual((f.labels, f.priorities), (frozenset({1, 2}), frozenset({1})))
        self.assertEqual(f.statuses, frozenset({TaskStatus.DONE}))  # kept
        self.assertEqual(f.date_from, date(2026, 10, 1))  # kept

    def test_empty_status_list_means_no_restriction(self):
        merged = merge_into_store(None, {"statuses": []})
        self.assertEqual(filter_from_store(merged).statuses, frozenset())

    def test_unknown_fields_are_ignored_and_values_cleaned(self):
        merged = merge_into_store(None, {"bogus": 1, "date_to": "", "at_risk_only": None})
        self.assertNotIn("bogus", merged)
        self.assertTrue(filter_from_store(merged).is_default)


class ParseDateTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(parse_date("2026-10-12"), date(2026, 10, 12))
        self.assertEqual(parse_date("2026-10-12T00:00:00"), date(2026, 10, 12))
        for bad in (None, "", "12.10.2026", 5):
            self.assertIsNone(parse_date(bad))


class TaskFormIdsTest(unittest.TestCase):
    def test_ids_are_prefixed_and_distinct(self):
        self.assertEqual(ids.NEW_FORM.title, "new-task-title")
        self.assertEqual(ids.EDIT_FORM.status_reason, "detail-status-reason")
        new = {getattr(ids.NEW_FORM, f) for f in ids.TASK_FORM_FIELDS}
        edit = {getattr(ids.EDIT_FORM, f) for f in ids.TASK_FORM_FIELDS}
        self.assertFalse(new & edit)

    def test_unknown_field_is_an_error(self):
        with self.assertRaises(AttributeError):
            _ = ids.NEW_FORM.titel


if __name__ == "__main__":
    unittest.main()
