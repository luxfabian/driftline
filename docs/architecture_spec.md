# Architecture Specification — Personal PM Tool

Version 0.1 (draft) · 2026-10-10
Implements: `requirements.txt` v0.2 · Builds on: `data_model_spec.md` v0.1

---

## 0. How to read this document (for the implementer)

- This document is **normative** for structure, module boundaries, interfaces and control flow.
- `data_model_spec.md` is normative for tables, write rules (R-xx) and derived values. This document says **where** that logic lives, not **what** it computes.
- Function signatures are binding in name, parameters and return type. Internals are your choice.
- Build in the order of section 12. Each phase has acceptance criteria — do not start the next phase before they pass.
- When something is not specified, choose the simplest option and leave `# TODO(spec): <question>`.

---

## 1. Architectural principles

| # | Principle | Why |
|---|---|---|
| P1 | **Layered, one-way dependencies:** `ui → services → repo → db`; `ui → calc`; `calc` depends only on `domain`. | Keeps calculations testable and the UI replaceable `[NFR-07]` |
| P2 | **Calculations are pure functions.** No DB access, no clock access, no Dash imports in `calc/`. `today` is always a parameter. | Deterministic tests for workload and schedule logic |
| P3 | **All writes go through services.** Each service method = one transaction = one user action. The change log is written inside that transaction. | Guarantees DAT-09 and the R-xx rules |
| P4 | **Repositories contain SQL only.** No business rules. | Rules stay in one place |
| P5 | **Read = snapshot.** A view loads one immutable `Snapshot` of all active data, then filters and calculates in memory. | Simple, fast enough for 500 tasks `[NFR-05]` |
| P6 | **Figure builders are pure:** data in → `plotly.graph_objects.Figure` out. | Charts testable without a browser |
| P7 | **Time is injected** through a `Clock`. | Reproducible tests, no hidden `date.today()` |

---

## 2. Technology stack

| Purpose | Choice | Note |
|---|---|---|
| Language | Python 3.11+ | `[NFR-01]` |
| Web UI | Dash (multi-page via `dash.register_page`) | Plotly's app framework |
| Charts | Plotly (`graph_objects`) | |
| Layout widgets | `dash-bootstrap-components` | forms, modals, toasts, navbar |
| Task table | `dash-ag-grid` | sorting, filtering, row selection `[FUN-08]` |
| Database | stdlib `sqlite3`, no ORM | DDL in `data_model_spec.md` §7 |
| Data handling | `pandas` only in `calc/workload.py` and export | keep elsewhere plain Python |
| Excel export | `openpyxl` | `[NFR-03]` |
| Tests | `pytest` | |
| Lint/format | `ruff` | |

Pin versions in `pyproject.toml`. No other runtime dependencies without a `TODO(spec)` note.

---

## 3. Package layout

```
pmtool/
├── pyproject.toml
├── README.md
├── pmtool/
│   ├── __main__.py            # entry point: python -m pmtool
│   ├── config.py              # paths, host/port, logging setup
│   ├── clock.py               # Clock protocol, SystemClock, FixedClock
│   ├── errors.py              # DomainError, ValidationError, ConfirmationRequired, NotFound
│   │
│   ├── db/
│   │   ├── schema.sql         # DDL from data_model_spec.md §7 (version 1)
│   │   ├── connection.py      # connect(), transaction()
│   │   ├── migrations.py      # apply_migrations(conn)
│   │   └── backup.py          # backup_on_start(db_path, keep)
│   │
│   ├── domain/
│   │   ├── enums.py           # TaskStatus, Priority, MilestoneStatus, CommentKind, ...
│   │   ├── models.py          # frozen dataclasses: Task, Milestone, Label, Comment,
│   │   │                      # ChangeLogEntry, Settings, Absence, Holiday, Snapshot
│   │   ├── commands.py        # input dataclasses: TaskCreate, TaskUpdate, ...
│   │   └── filters.py         # Filter dataclass + apply_filter() + describe()
│   │
│   ├── repo/                  # SQL only (P4)
│   │   ├── task_repo.py
│   │   ├── milestone_repo.py
│   │   ├── label_repo.py
│   │   ├── dependency_repo.py
│   │   ├── comment_repo.py
│   │   ├── changelog_repo.py
│   │   ├── settings_repo.py
│   │   └── calendar_repo.py   # absence + public_holiday
│   │
│   ├── services/              # business rules R-01..R-14, transactions (P3)
│   │   ├── snapshot_service.py
│   │   ├── task_service.py
│   │   ├── milestone_service.py
│   │   ├── baseline_service.py
│   │   ├── settings_service.py
│   │   ├── export_service.py
│   │   └── import_service.py
│   │
│   ├── calc/                  # pure functions (P2)
│   │   ├── calendar.py        # working days, capacity
│   │   ├── status.py          # overdue, stale, overrun, risk reason
│   │   ├── schedule.py        # variances, warnings, MTA series, top delayed
│   │   └── workload.py        # demand, allocation, load ratio
│   │
│   └── ui/
│       ├── app.py             # create_app(services) -> dash.Dash
│       ├── ids.py             # all component IDs as constants
│       ├── layout.py          # shell: navbar, filter panel, stores, toasts, modals
│       ├── state.py           # helpers to (de)serialize Filter in dcc.Store
│       ├── charts.py          # pure figure builders (P6)
│       ├── components/
│       │   ├── filter_panel.py
│       │   ├── task_form.py
│       │   ├── task_detail.py # comments, history, dependencies
│       │   └── confirm_modal.py
│       └── pages/
│           ├── dashboard.py
│           ├── tasks.py
│           ├── timeline.py
│           ├── milestones.py
│           ├── workload.py
│           └── settings.py
└── tests/
    ├── conftest.py            # in-memory DB fixture, FixedClock, factories
    ├── calc/
    ├── services/
    ├── ui/                    # figure builders + app import smoke test
    └── perf/                  # NFR-05
```

**Import rule (enforce with a test):** `calc/` and `domain/` must not import from `db/`, `repo/`, `services/` or `ui/`. `repo/` must not import from `services/` or `ui/`. `services/` must not import from `ui/`.

---

## 4. Cross-cutting modules

### 4.1 `clock.py`
```python
class Clock(Protocol):
    def now(self) -> datetime: ...   # timezone-aware, local zone
    def today(self) -> date: ...

class SystemClock: ...               # uses local system time zone
class FixedClock:                    # for tests
    def __init__(self, now: datetime): ...
```

### 4.2 `errors.py`
```python
class DomainError(Exception):
    code: str          # e.g. "VAL-01", "R-05"; used by UI and tests
    message: str       # human-readable, shown in a toast

class ValidationError(DomainError): ...
class NotFound(DomainError): ...
class ConfirmationRequired(DomainError):
    # raised when a rule needs user confirmation (R-05, R-11)
    # UI shows a modal and repeats the call with confirmed=True
    ...
```

### 4.3 `db/connection.py`
```python
def connect(db_path: Path | str) -> sqlite3.Connection
    # row_factory = sqlite3.Row; PRAGMA foreign_keys = ON
    # use ":memory:" in tests

@contextmanager
def transaction(conn) -> Iterator[sqlite3.Connection]
    # BEGIN IMMEDIATE ... COMMIT; ROLLBACK on any exception, then re-raise
```
**Connection policy:** one connection per callback invocation (open → use → close). Dash may run callbacks in threads; do not share a connection between threads.

### 4.4 `config.py`
| Setting | Default | Override |
|---|---|---|
| data directory | `~/.pmtool/` | env `PMTOOL_DATA_DIR` |
| database file | `<data>/pmtool.db` | — |
| backup directory | `<data>/backups/` | — |
| log file | `<data>/pmtool.log` | — |
| host | `127.0.0.1` (fixed) `[NFR-02]` | not overridable |
| port | `8050` | env `PMTOOL_PORT` |

---

## 5. Domain layer

### 5.1 Models (`domain/models.py`)
Frozen dataclasses mirroring the tables in `data_model_spec.md` §3, with Python types:
`date` for planning dates, aware `datetime` for timestamps, enums from `enums.py`, `bool` for flags.

Additional fields on `Task` filled by the repository for convenience:
- `label_ids: frozenset[int]`
- `predecessor_ids: frozenset[int]`

```python
@dataclass(frozen=True)
class Snapshot:
    tasks: tuple[Task, ...]                  # active only unless include_archived
    milestones: tuple[Milestone, ...]
    labels: tuple[Label, ...]
    settings: Settings
    absences: tuple[Absence, ...]
    holidays: frozenset[date]
    risk_reasons: Mapping[int, str]          # task_id -> latest risk_set text
    milestone_forecast_log: Mapping[int, tuple[ChangeLogEntry, ...]]  # for MTA
```

### 5.2 Commands (`domain/commands.py`)
Input objects for writes. All optional fields in `*Update` commands mean "unchanged" when `None`.
```python
TaskCreate(title, forecast_start, forecast_end, estimated_effort_h,
           description=None, priority=Priority.MEDIUM, label_names=(),
           predecessor_ids=(), milestone_id=None)
TaskUpdate(task_id, title=None, description=None, forecast_start=None,
           forecast_end=None, estimated_effort_h=None, remaining_effort_h=None,
           status=None, status_reason=None, priority=None, milestone_id=None,
           reason=None)
MilestoneCreate(name, forecast_date, description=None)
MilestoneUpdate(milestone_id, name=None, description=None, forecast_date=None,
                reason=None)
```
`milestone_id` in `TaskUpdate` needs a way to express "unlink": use the sentinel `UNLINK = -1`.

### 5.3 Filters (`domain/filters.py`) `[FUN-09, FUN-10]`
```python
@dataclass(frozen=True)
class Filter:   # fields exactly as data_model_spec.md §6
    ...
def apply_filter(tasks: Iterable[Task], f: Filter) -> list[Task]
def describe(f: Filter, labels: Mapping[int, str], milestones: Mapping[int, str]) -> str
    # one line, e.g. "Labels: work, admin (any) · Priority: 1–2 · Status: open"
    # returns "No filter" for the default filter
```

---

## 6. Repository layer

One module per table group. Functions take `conn` as first argument and return domain objects or IDs. **No validation, no logging to `change_log`, no transactions** (the caller owns the transaction).

Minimum interface (add helpers as needed, same style):

```python
# task_repo
def insert(conn, values: dict) -> int
def update_fields(conn, task_id: int, values: dict) -> None
def get(conn, task_id: int) -> Task | None
def list_all(conn, include_archived: bool) -> list[Task]
def delete(conn, task_id: int) -> None

# milestone_repo — same shape as task_repo

# label_repo
def get_or_create(conn, name: str) -> int          # uses name_key
def set_task_labels(conn, task_id: int, label_ids: Iterable[int]) -> None
def list_all(conn) -> list[Label]

# dependency_repo
def set_predecessors(conn, task_id: int, predecessor_ids: Iterable[int]) -> None
def list_all(conn) -> list[tuple[int, int]]         # (predecessor, successor)

# comment_repo
def insert(conn, task_id: int, kind: CommentKind, text: str, created_at: datetime) -> int
def list_for_task(conn, task_id: int) -> list[Comment]   # newest first
def latest_risk_reasons(conn) -> dict[int, str]

# changelog_repo
def insert_many(conn, entries: Iterable[ChangeLogEntry]) -> None
def list_for_entity(conn, entity_type: str, entity_id: int) -> list[ChangeLogEntry]
def list_field(conn, entity_type: str, field: str) -> list[ChangeLogEntry]
def delete_for_entity(conn, entity_type: str, entity_id: int) -> None

# settings_repo / calendar_repo — get/update settings; CRUD for absences and holidays
```

---

## 7. Service layer

### 7.1 Construction
```python
@dataclass
class Services:
    snapshot: SnapshotService
    tasks: TaskService
    milestones: MilestoneService
    baselines: BaselineService
    settings: SettingsService
    export: ExportService
    importer: ImportService

def build_services(db_path: Path | str, clock: Clock) -> Services
```
Each service holds `db_path` and `clock`, opens its own connection per call (§4.3) and runs one transaction per public method.

### 7.2 Change-log helper
A private helper used by all write services:
```python
def diff_and_log(conn, entity_type, entity_id, before: dict, after: dict,
                 logged_fields: Sequence[str], change_kind: str, reason: str | None,
                 batch_id: str, now: datetime) -> None
    # writes one change_log row per logged field whose value changed (R-03)
```
`logged_fields` per entity are defined once as constants (data_model_spec §3.8).

### 7.3 Public methods and rule mapping

| Service | Method | Rules |
|---|---|---|
| SnapshotService | `load(include_archived=False) -> Snapshot` | read-only |
| TaskService | `create(cmd: TaskCreate) -> int` | R-01, R-12, R-13 |
| | `update(cmd: TaskUpdate, confirmed=False) -> None` | R-03, R-04, R-05, R-06, R-07, R-14, VAL-01..04 |
| | `set_labels(task_id, label_names) -> None` | R-12 |
| | `set_predecessors(task_id, predecessor_ids) -> None` | R-13 |
| | `set_at_risk(task_id, at_risk: bool, reason: str \| None) -> None` | R-06 |
| | `add_comment(task_id, text) -> int` | FUN-03 |
| | `mark_reviewed(task_id) -> None` | R-07 |
| | `archive(task_id)` / `restore(task_id)` | R-10 |
| | `delete_permanently(task_id, confirmed=False)` | R-11 |
| | `detail(task_id) -> TaskDetail` | read: task, comments, history, predecessors, successors |
| MilestoneService | `create`, `update`, `set_achieved(id, achieved_date=None)`, `reopen(id)`, `archive`, `restore`, `delete_permanently` | R-02, R-03, R-09, R-10, R-11 |
| BaselineService | `rebaseline_tasks(task_ids, reason) -> str` (batch_id) | R-08 |
| | `rebaseline_milestones(milestone_ids, reason) -> str` | R-08 |
| | `rebaseline_all(reason) -> str` | R-08 |
| SettingsService | `get()`, `update(**fields)`, `add_absence`, `remove_absence`, `add_holiday`, `remove_holiday` | WL-01 |
| ExportService | `to_excel() -> bytes`, `to_csv_zip() -> bytes` | NFR-03 |
| ImportService | `from_csv(content: bytes) -> ImportResult` | NFR-08 |

### 7.4 Error behavior
- Rule violation → raise `ValidationError(code=...)` **before** any write; the transaction rolls back.
- Rule needs user confirmation (R-05, R-11) → raise `ConfirmationRequired`; nothing is written.
- Database `CHECK` failures are a safety net only. Services must validate first so the user gets a clear message.

### 7.5 Import format `[NFR-08]`
CSV, UTF-8, comma-separated, header row. Columns: `title, forecast_start, forecast_end, estimated_effort_h, priority, labels, description`. `labels` = semicolon-separated. All-or-nothing: if any row fails validation, nothing is imported and `ImportResult` lists row numbers with errors.

---

## 8. Calculation layer (pure)

All functions take plain domain objects and `today` explicitly. Formulas: `data_model_spec.md` §5.

```python
# calc/calendar.py
def is_working_day(d: date, settings: Settings, holidays: frozenset[date],
                   absences: Sequence[Absence]) -> bool
def capacity_h(d: date, ...) -> float
def working_days(start: date, end: date, ...) -> list[date]          # inclusive
def next_working_day(d: date, ..., max_lookahead_days: int = 366) -> date | None

# calc/status.py
def is_open(t: Task) -> bool
def is_overdue(t: Task, today: date) -> bool
def is_stale(t: Task, now: datetime, stale_after_days: int) -> bool
def is_effort_overrun(t: Task) -> bool

# calc/schedule.py
@dataclass(frozen=True)
class Variance: start_d: int; end_d: int
def task_variance(t: Task) -> Variance
def milestone_variance(m: Milestone) -> int
def dependency_warnings(tasks: Sequence[Task]) -> dict[int, list[int]]  # task -> late predecessors
def dependency_cycles(tasks: Sequence[Task]) -> list[list[int]]
def milestone_task_warnings(milestones, tasks) -> dict[int, date]       # milestone -> latest task end
def mta_series(entries: Sequence[ChangeLogEntry], today: date) -> list[tuple[date, date]]
def top_delayed(tasks, milestones, n: int) -> list[DelayItem]

# calc/workload.py
def due_date(t: Task, today: date) -> date
def cumulative_curves(tasks, today, horizon_end, calendar_ctx) -> pd.DataFrame
    # columns: date, demand_h, capacity_h, shortfall_h
def daily_allocation(tasks, today, horizon_end, calendar_ctx) -> pd.DataFrame
    # columns: date, task_id, hours
def weekly_load(allocation: pd.DataFrame, tasks, group_by: Literal["priority","label"],
                calendar_ctx) -> pd.DataFrame
    # columns: week_start, group, hours; plus capacity per week
def load_ratio(tasks, today, horizon_weeks, calendar_ctx) -> float | None   # None = n/a
def load_level(ratio: float | None, settings: Settings) -> Literal["green","amber","red","na"]
```
`calendar_ctx` is a small frozen dataclass bundling `settings`, `holidays`, `absences` to keep signatures short.

**Grouping by label:** a task with several labels contributes its hours to **each** label group in the weekly chart; the chart subtitle must say "tasks with several labels appear in each". A task without labels goes to group "(no label)".

---

## 9. UI layer

### 9.1 App shell (`ui/layout.py`)
```
┌─────────────────────────────────────────────────────────────┐
│ Navbar: Dashboard · Tasks · Timeline · Milestones ·          │
│         Workload · Settings                     [+ New task] │
├───────────────┬─────────────────────────────────────────────┤
│ Filter panel  │  page container (dash.page_container)        │
│ (collapsible, │                                              │
│  all pages    │                                              │
│  except       │                                              │
│  Settings)    │                                              │
└───────────────┴─────────────────────────────────────────────┘
 Global, invisible: dcc.Store(FILTER, storage="session")
                    dcc.Store(DATA_VERSION, storage="memory")
                    toast container, confirm modal, task form modal
```

### 9.2 State and refresh pattern
| Store | Content | Written by | Read by |
|---|---|---|---|
| `FILTER` | serialized `Filter` | filter panel callbacks | every view callback |
| `DATA_VERSION` | integer counter | every write callback (increment after success) | every view callback (as `Input`) |

**Read callback template**
```
Inputs: DATA_VERSION, FILTER, page-specific controls
1. snap = services.snapshot.load()
2. tasks = apply_filter(snap.tasks, filter)
3. results = calc.*(tasks, today=clock.today(), ...)
4. return charts.build_*(results, filter_text=describe(filter, ...))
```

**Write callback template**
```
1. build command from form values
2. try: services.x.method(cmd)
   except ConfirmationRequired: open confirm modal, keep pending action in a store
   except DomainError as e: show error toast with e.message; return no_update
3. on success: DATA_VERSION += 1, success toast, close form
```
Confirm modal "Yes" repeats the pending action with `confirmed=True`.

### 9.3 Pages

| Page | Content | Requirements |
|---|---|---|
| **Dashboard** | KPI cards: load ratio (traffic light) for default horizon, # overdue, # at risk, # blocked, # stale. Lists: top delayed items; milestone warnings; dependency warnings. | WL-07, WL-08, FUN-12, SCH-05, SCH-06, FUN-07 |
| **Tasks** | AG Grid: ID, title, status, priority, labels, forecast start/end, end variance, remaining h, flags (at risk ⚠, overdue, stale, overrun). Sort on any column. Row click opens task detail. Bulk actions on selected rows: mark reviewed, re-baseline, archive. | FUN-01, FUN-04, FUN-08, FUN-12, SCH-03 |
| **Task detail** (offcanvas/modal) | Edit form; labels with autocomplete from existing labels; predecessors (multi-select) and successors (read-only); at-risk toggle with reason; "Mark reviewed"; comments (newest first, add box); change history table; archive. | FUN-02..06, DAT-04, VAL-06, R-07 |
| **Timeline** | Gantt: forecast bars colored by status, baseline bars as outlines behind them, milestones as diamonds (forecast) and hollow diamonds (baseline), today line, at-risk marker. Hover: dates, variance, remaining h. | FUN-11 |
| **Milestones** | Table with baseline, forecast, variance, status, warning. Actions: create, edit, achieve, reopen, re-baseline, archive. MTA chart below (select milestones to show). | DAT-05, SCH-03..05 |
| **Workload** | Horizon selector (1–12 weeks). Chart 1: cumulative demand vs. capacity, shortfall shaded. Chart 2: weekly stacked bars + capacity line, color-by selector (priority/label). Load ratio card. | WL-03..07 |
| **Settings** | Capacity settings; thresholds; stale period; absences and holidays (add/remove); export buttons (Excel, CSV zip); CSV import; archived items list with restore / delete permanently. | WL-01, WL-07, WL-08, NFR-03, NFR-08, DAT-08 |

### 9.4 Chart builders (`ui/charts.py`)
```python
def build_gantt(tasks, milestones, today, filter_text, risk_ids) -> go.Figure
def build_mta(series: Mapping[str, list[tuple[date, date]]], today, filter_text) -> go.Figure
def build_cumulative(curves: pd.DataFrame, filter_text) -> go.Figure
def build_weekly_load(weekly: pd.DataFrame, capacity: pd.DataFrame,
                      group_label: str, filter_text) -> go.Figure
```
Every builder puts `filter_text` in the chart subtitle `[FUN-10]`. No data loading or calculation inside builders.

### 9.5 Component IDs
All IDs are string constants in `ui/ids.py` (e.g. `TASK_GRID = "task-grid"`). Never write an ID literal elsewhere.

---

## 10. Startup and shutdown

`python -m pmtool` runs:
1. Load config, set up logging to file and console.
2. Create the data directory if missing.
3. If the DB file exists: `backup_on_start(db_path, keep=settings.backup_keep_count)` → copy to `backups/pmtool_YYYYMMDD_HHMMSS.db` using the SQLite backup API; delete oldest beyond `keep`. If the DB does not exist yet, use keep = 10. `[NFR-04]`
4. `apply_migrations(conn)`: if no `schema_version` table → run `schema.sql`; else run pending migrations in order.
5. Ensure the `app_settings` row exists.
6. `services = build_services(db_path, SystemClock())`
7. `app = create_app(services)`; `app.run(host="127.0.0.1", port=port, debug=False)` `[NFR-02]`

No explicit shutdown logic needed (each callback closes its connection).

---

## 11. Testing strategy

| Level | Scope | Tooling | Must cover |
|---|---|---|---|
| Unit — calc | every function in `calc/` | pytest, FixedClock dates | all edge cases in data_model_spec §5; variance sign; allocation sums equal remaining effort; load ratio n/a when capacity = 0 |
| Unit — domain | `apply_filter`, `describe` | pytest | label any/all, date overlap, default filter |
| Service | every public method | in-memory SQLite + schema.sql, FixedClock | each R-xx rule has at least one test named `test_R_xx_...`; each VAL-xx violation raises `ValidationError` with that code; change_log rows exactly as specified |
| UI — builders | `charts.py` | pytest | returns a Figure; subtitle contains filter text; correct number of traces |
| UI — smoke | `create_app` | pytest | app builds, all pages register, no duplicate IDs |
| Architecture | import rules (§3) | pytest scanning imports | no forbidden imports |
| Performance | `[NFR-05]` | pytest, marked `perf` | 500 tasks + 5,000 log rows: `snapshot.load` + full workload calc + all figure builders < 1.5 s (leaves margin for rendering) |

Test data: `tests/conftest.py` provides factories `make_task(**overrides)`, `make_milestone(**overrides)`.

---

## 12. Implementation phases

| Phase | Deliverable | Acceptance |
|---|---|---|
| 1 Foundation | project skeleton, config, clock, errors, db (connect, transaction, schema, migrations, backup), domain models/enums | schema applies to empty DB; backup test passes; import-rule test passes |
| 2 Repositories + services | all repos; Task, Milestone, Baseline, Settings, Snapshot services | all service tests green, incl. every R-xx and VAL-xx |
| 3 Calculations | `calc/` complete | all calc tests green |
| 4 UI shell + Tasks | app shell, filter panel, stores, Tasks page, task form, task detail | create/edit/comment/archive a task in the browser; filter changes the grid |
| 5 Views | Dashboard, Timeline, Milestones (with MTA), Workload | charts render with sample data; filter text visible on every chart |
| 6 Settings + I/O | Settings page, export, import, archive management | round trip: export → fresh DB → import tasks |
| 7 Hardening | perf test, error toasts for every DomainError path, README | perf test green; README explains install and start |

Provide a `scripts/seed_demo.py` in phase 4 that fills a database with ~30 realistic tasks, 4 milestones and some history, so every view can be checked visually.

---

## 13. Traceability (requirement → module)

| Requirement | Main modules |
|---|---|
| DAT-01..09 | `db/schema.sql`, `repo/*`, `services/*` |
| VAL-01..06 | `services/task_service.py`, `services/milestone_service.py` |
| FUN-01..07 | `services/task_service.py`, `ui/pages/tasks.py`, `ui/components/task_detail.py`, `calc/schedule.py` |
| FUN-08..12 | `ui/pages/tasks.py`, `ui/pages/timeline.py`, `domain/filters.py`, `ui/charts.py` |
| SCH-01..06 | `services/baseline_service.py`, `services/milestone_service.py`, `calc/schedule.py`, `ui/pages/milestones.py`, `ui/pages/dashboard.py` |
| WL-01..08 | `calc/calendar.py`, `calc/workload.py`, `calc/status.py`, `ui/pages/workload.py`, `ui/pages/settings.py` |
| NFR-01, NFR-02 | §2, `config.py`, `__main__.py` |
| NFR-03, NFR-08 | `services/export_service.py`, `services/import_service.py` |
| NFR-04 | `db/backup.py` |
| NFR-05 | `tests/perf/` |
| NFR-06 | `clock.py`, `domain/models.py` |
| NFR-07 | §1 P1–P4, import-rule test, `tests/` |

---

## 14. Explicit non-goals (do not build)

- Authentication, multiple users, remote access
- Automatic rescheduling from dependencies
- Undo/redo
- Real-time sync across browser tabs (a manual page reload is enough)
- Caching layers — only add if the perf test fails
