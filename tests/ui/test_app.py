"""App smoke test (architecture §11): app builds, pages register, IDs are consistent."""

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

import dash

from pmtool.clock import FixedClock
from pmtool.db.connection import connect
from pmtool.db.migrations import apply_migrations
from pmtool.services import build_services
from pmtool.ui import ids
from pmtool.ui.app import ASSETS_DIR, PAGES, create_app
from tests.helpers import T0


def component_ids(component) -> list[str]:
    """String IDs in a layout tree; pattern-matching (dict) IDs are left out."""
    found = [getattr(component, "id", None)]
    found += [getattr(c, "id", None) for c in component._traverse()]
    return [i for i in found if isinstance(i, str)]


def callback_ids(app: dash.Dash) -> set[str]:
    """IDs referenced by any callback output, input or state."""
    used: set[str] = set()
    for cb in app._callback_list:
        outputs = cb["output"].strip(".").split("...")
        used.update(o.split("@")[0].rsplit(".", 1)[0] for o in outputs)
        used.update(dep["id"] for dep in cb["inputs"] + cb["state"])
    return {i for i in used if not i.startswith("{")}  # pattern-matching IDs are JSON


class AppSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        db = Path(cls._tmp.name) / "app.db"
        conn = connect(db)
        apply_migrations(conn)
        conn.close()
        cls.app = create_app(build_services(db, FixedClock(T0)))
        cls.client = cls.app.server.test_client()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def all_ids(self) -> list[str]:
        result = component_ids(self.app.layout)
        for page in PAGES:
            result += component_ids(page.layout())
        return result

    def test_all_pages_registered(self):
        paths = {p["path"] for p in dash.page_registry.values()}
        self.assertTrue({p.PATH for p in PAGES} <= paths)
        self.assertEqual(len({p.PATH for p in PAGES}), len(PAGES))

    def test_pages_and_layout_endpoints_respond(self):
        for page in PAGES:
            self.assertEqual(self.client.get(page.PATH).status_code, 200, page.PATH)
        self.assertEqual(self.client.get("/_dash-layout").status_code, 200)
        self.assertEqual(self.client.get("/_dash-dependencies").status_code, 200)

    def test_no_duplicate_ids(self):
        """Only one page is in the browser at a time: check the shell plus each page."""
        shell = component_ids(self.app.layout)
        for page in PAGES:
            with self.subTest(page=page.NAME):
                ids_on_screen = shell + component_ids(page.layout())
                dupes = [i for i, n in Counter(ids_on_screen).items() if n > 1]
                self.assertEqual(dupes, [])

    def test_every_callback_id_exists_in_a_layout(self):
        missing = callback_ids(self.app) - set(self.all_ids())
        self.assertEqual(missing, set())

    def test_ids_come_from_ids_module(self):
        constants = {v for k, v in vars(ids).items() if k.isupper() and isinstance(v, str)}
        forms = {getattr(f, n) for f in (ids.NEW_FORM, ids.EDIT_FORM) for n in ids.TASK_FORM_FIELDS}
        dash_internal = {i for i in self.all_ids() if i.startswith("_pages_")}
        unknown = set(self.all_ids()) - constants - forms - dash_internal
        self.assertEqual(unknown, set())

    def test_runs_offline(self):  # NFR-01: no stylesheet or script from the internet
        self.assertEqual(self.app.config.external_stylesheets, [])
        self.assertEqual(self.app.config.external_scripts, [])
        self.assertTrue((ASSETS_DIR / "bootstrap.min.css").is_file())
        html = self.client.get("/tasks").get_data(as_text=True)
        self.assertNotIn("cdn.", html)


if __name__ == "__main__":
    unittest.main()
