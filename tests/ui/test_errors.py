"""Phase 7: every error reaches the user as a toast; nothing fails silently."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pmtool.clock import FixedClock
from pmtool.errors import ValidationError
from pmtool.services import build_services
from pmtool.ui import actions, ids
from pmtool.ui.app import create_app
from pmtool.ui.feedback import on_callback_error
from tests.helpers import T0
from tests.services.base import ServiceTestCase


class EveryActionAnswersTest(ServiceTestCase):
    def test_malformed_actions_give_an_error_outcome(self):
        """No action kind may raise: empty input -> error/confirm outcome, never an exception."""
        for kind in actions._HANDLERS:
            with self.subTest(kind=kind):
                outcome = actions.execute(self.svc, {"kind": kind})
                self.assertIn(outcome.status, {"ok", "error", "confirm"})
                self.assertTrue(outcome.message)

    def test_missing_key_is_logged_and_reported(self):
        with self.assertLogs("pmtool.ui", "ERROR"):
            outcome = actions.execute(self.svc, {"kind": "add_comment", "text": "x"})
        self.assertEqual(outcome.status, "error")
        self.assertIn("Invalid request", outcome.message)


class GlobalErrorHandlerTest(unittest.TestCase):
    def test_domain_error_toast(self):
        with mock.patch("pmtool.ui.feedback.set_props") as set_props:
            on_callback_error(ValidationError("VAL-01", "End before start."))
        component, props = set_props.call_args.args
        self.assertEqual(component, ids.TOAST)
        self.assertEqual((props["header"], props["children"]), ("Not saved", "End before start."))

    def test_unexpected_error_toast_and_log(self):
        with mock.patch("pmtool.ui.feedback.set_props") as set_props, \
                self.assertLogs("pmtool.ui", "ERROR"):  # fmt: skip
            on_callback_error(RuntimeError("disk full"))
        props = set_props.call_args.args[1]
        self.assertEqual(props["header"], "Something went wrong")
        self.assertIn("RuntimeError: disk full", props["children"])
        self.assertIn("pmtool.log", props["children"])

    def test_failing_callback_returns_toast_through_dash(self):
        """A database without tables makes a read callback fail; the page gets a toast."""
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(build_services(Path(tmp) / "empty.db", FixedClock(T0)))
            payload = {
                "output": f"{ids.LOOKUPS}.data",
                "outputs": {"id": ids.LOOKUPS, "property": "data"},
                "inputs": [{"id": ids.DATA_VERSION, "property": "data", "value": 0}],
                "changedPropIds": [f"{ids.DATA_VERSION}.data"],
                "state": [],
            }
            with self.assertLogs("pmtool.ui", "ERROR"):
                response = app.server.test_client().post("/_dash-update-component", json=payload)
        self.assertEqual(response.status_code, 200)
        toast = response.get_json()["sideUpdate"][ids.TOAST]
        self.assertTrue(toast["is_open"])
        self.assertIn("no such table", toast["children"])


if __name__ == "__main__":
    unittest.main()
