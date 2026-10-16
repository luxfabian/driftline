"""Phase 1 acceptance: import-rule test passes (architecture §3, P1, P2, P7).

Scans every module of the package with ``ast`` (no imports executed), so it
also guards modules that are written in later phases.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PACKAGE = "pmtool"
PACKAGE_DIR = Path(__file__).resolve().parents[2] / PACKAGE

INTERNAL_LAYERS = {"db", "repo", "services", "calc", "ui", "domain", "clock", "config", "errors"}

# layer -> internal layers it must NOT import
FORBIDDEN_INTERNAL: dict[str, set[str]] = {
    "domain": {"db", "repo", "services", "ui", "calc", "clock", "config"},
    "calc": {"db", "repo", "services", "ui", "clock", "config"},  # P2: only domain
    "db": {"repo", "services", "ui", "calc"},
    "repo": {"services", "ui", "calc"},
    "services": {"ui"},
}
# layer -> third-party top-level packages it must NOT import
FORBIDDEN_EXTERNAL: dict[str, set[str]] = {
    "domain": {"dash", "plotly", "dash_bootstrap_components", "dash_ag_grid", "pandas", "sqlite3"},
    "calc": {"dash", "plotly", "dash_bootstrap_components", "dash_ag_grid", "sqlite3"},
    "db": {"dash", "plotly", "dash_bootstrap_components", "dash_ag_grid"},
    "repo": {"dash", "plotly", "dash_bootstrap_components", "dash_ag_grid"},
    "services": {"dash", "plotly", "dash_bootstrap_components", "dash_ag_grid"},
}
# P7: only clock.py may read the system clock
CLOCK_CALLS = {("date", "today"), ("datetime", "now"), ("datetime", "today"),
               ("datetime", "utcnow"), ("time", "time")}  # fmt: skip
CLOCK_ALLOWED = {"pmtool/clock.py"}


def module_name(path: Path) -> str:
    rel = path.relative_to(PACKAGE_DIR.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def layer_of(module: str) -> str | None:
    parts = module.split(".")
    if parts[0] != PACKAGE or len(parts) < 2:
        return None
    return parts[1] if parts[1] in INTERNAL_LAYERS else None


def imported_modules(source: str, module: str, is_package: bool) -> set[str]:
    """Absolute names of everything imported by ``source``."""
    found: set[str] = set()
    package_parts = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            found.add(prefix)
            found.update(f"{prefix}.{alias.name}" for alias in node.names)
    return found


def violations_for(source: str, module: str, is_package: bool = False) -> list[str]:
    layer = layer_of(module)
    if layer is None:
        return []
    problems = []
    for imported in sorted(imported_modules(source, module, is_package)):
        target = layer_of(imported)
        if target and target in FORBIDDEN_INTERNAL.get(layer, set()):
            problems.append(f"{module} imports {imported} ({layer} -> {target})")
        top = imported.split(".")[0]
        if top in FORBIDDEN_EXTERNAL.get(layer, set()):
            problems.append(f"{module} imports {imported} (third-party {top} in {layer})")
    return problems


def clock_calls(source: str) -> list[str]:
    calls = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and (owner.id, node.func.attr) in CLOCK_CALLS:
                calls.append(f"{owner.id}.{node.func.attr}() line {node.lineno}")
    return calls


def package_files() -> list[Path]:
    return sorted(PACKAGE_DIR.rglob("*.py"))


class ImportRuleTest(unittest.TestCase):
    def test_package_found(self):
        self.assertGreater(len(package_files()), 10)

    def test_no_forbidden_imports(self):
        problems = []
        for path in package_files():
            module = module_name(path)
            problems += violations_for(path.read_text(), module, path.name == "__init__.py")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_only_clock_reads_system_time(self):
        problems = []
        for path in package_files():
            rel = path.relative_to(PACKAGE_DIR.parent).as_posix()
            if rel in CLOCK_ALLOWED:
                continue
            problems += [f"{rel}: {c}" for c in clock_calls(path.read_text())]
        self.assertEqual(problems, [], "\n".join(problems))


class CheckerSelfTest(unittest.TestCase):
    """Proves the checker actually catches violations."""

    def test_detects_absolute_upward_import(self):
        src = "from pmtool.repo import task_repo\n"
        self.assertTrue(violations_for(src, "pmtool.calc.workload"))

    def test_detects_relative_upward_import(self):
        src = "from ..services import task_service\n"
        self.assertTrue(violations_for(src, "pmtool.repo.task_repo"))

    def test_detects_dash_in_calc(self):
        self.assertTrue(violations_for("import plotly.graph_objects as go\n", "pmtool.calc.x"))

    def test_allows_calc_to_use_domain(self):
        src = "from pmtool.domain.models import Task\nimport pandas as pd\n"
        self.assertEqual(violations_for(src, "pmtool.calc.workload"), [])

    def test_allows_ui_anything(self):
        src = "from pmtool.services import x\nfrom pmtool.calc import y\nimport dash\n"
        self.assertEqual(violations_for(src, "pmtool.ui.app"), [])

    def test_detects_clock_call(self):
        self.assertTrue(clock_calls("from datetime import date\nx = date.today()\n"))


if __name__ == "__main__":
    unittest.main()
