# Driftline — personal project management

A local, single-user tool to plan your own work, forecast workload against the time you
actually have, and track how tasks and milestones drift from their baseline. It runs in
your browser on your own computer; nothing leaves the machine and no internet is needed.

The name: Driftline shows how your tasks and milestones drift from their baseline over
time, and where your work lands on the timeline.

Specifications: [`docs/requirements.txt`](docs/requirements.txt),
[`docs/data_model_spec.md`](docs/data_model_spec.md),
[`docs/architecture_spec.md`](docs/architecture_spec.md).

## Install

Needs Python 3.11 or newer. Run this once in the project folder (the one with
`pyproject.toml`):

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # or: pip install .   (without test tools)
```

## Launch the dashboard

1. Open a terminal in the project folder and activate the environment:
   `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`).
2. Start the tool:

   ```bash
   driftline                             # same as: python -m driftline
   ```

   Without activating, `.venv/bin/driftline` (Windows: `.venv\Scripts\driftline`) works too.
3. Open **http://127.0.0.1:8050** in your browser. The app opens on the Dashboard.
4. Stop it with **Ctrl+C** in the terminal. Your data is saved after every change, so
   there is nothing to save before stopping.

The terminal shows where the database is and which address to open:

```text
INFO    driftline: Database ready at /home/<you>/.driftline/driftline.db (schema version 1)
INFO    driftline: Open http://127.0.0.1:8050 in your browser
```

Flask also prints a red "WARNING: This is a development server" line. That is expected:
the tool is a single-user app that only listens on your own computer (127.0.0.1), so no
other machine can reach it. If port 8050 is taken, use another one, e.g.
`DRIFTLINE_PORT=8060 driftline` (Windows PowerShell: `$env:DRIFTLINE_PORT=8060; driftline`).

## Where your data is stored

Everything lives in one folder, by default `.driftline` in your home directory:

| Operating system | Default folder |
|---|---|
| Linux | `/home/<you>/.driftline/` |
| macOS | `/Users/<you>/.driftline/` |
| Windows | `C:\Users\<you>\.driftline\` |

| File | Content |
|---|---|
| `driftline.db` | **The database**: one SQLite file with all tasks, milestones, labels, comments, change history and settings. |
| `backups/driftline_YYYYMMDD_HHMMSS.db` | A copy of the database made at every start (not on the very first one); the newest 10 are kept, configurable in Settings. |
| `driftline.log` | Log file; errors shown in the app are written here with details. |

The folder and the database are created on the first start. To use another folder, set
`DRIFTLINE_DATA_DIR` before starting, e.g. `DRIFTLINE_DATA_DIR=~/Documents/pm driftline`
(Windows PowerShell: `$env:DRIFTLINE_DATA_DIR="D:\pm"; driftline`). Each folder is a separate,
independent project.

- **Back up or move your data:** stop the tool and copy the whole folder.
- **Restore a backup:** stop the tool, copy the backup file over `driftline.db`, start again.
- **Share data with other tools:** use Settings → Export (Excel or CSV) instead of
  opening the database file directly.

**Formerly pmtool.** Driftline used to be called pmtool, with its data in `~/.pmtool`.
On the first start with the default folder, Driftline moves `~/.pmtool` to `~/.driftline`
once and renames the files inside (`pmtool.db` → `driftline.db`, the log and the backups);
nothing is copied or deleted, and the terminal says when it happened. If both folders
exist, nothing is moved. The specifications in `docs/` still use the old name.

### Try it with demo data

```bash
scripts/demo.sh                    # demo project in ~/.driftline-demo on http://127.0.0.1:8051
scripts/demo.sh --keep             # restart it without resetting your changes
```

The demo has 30 tasks, 4 milestones and 8 weeks of history (slips, re-baselines, milestone
drift, blocked, at-risk, stale and overdue tasks), all relative to today. It uses its own
folder `~/.driftline-demo` and port 8051, so it can run next to your real data, which it
never touches. To seed another file by hand:
`python scripts/seed_demo.py --db /path/driftline.db [--force]`.

## What's in the app

| Page | What you do there |
|---|---|
| **Dashboard** | Load ratio for the next weeks (OK / Tight / Overloaded), counts of overdue, at-risk, blocked and stale tasks. **Your day**: the work the plan puts on today (or the next working day), split by priority against the plannable hours, in focus order with a line where the day's capacity runs out; blocked work listed apart. Then milestone and dependency warnings and the most delayed items. Click a task to open it. |
| **Tasks** | Filter bar on top; sortable, filterable table. Click a row for details: edit, labels, milestone, at-risk flag, dependencies, comments and full change history. Select rows to mark them reviewed, re-baseline or archive them. "+ New task" is in the top bar. |
| **Timeline** | Gantt chart: forecast bars by status inside baseline outlines, milestones as diamonds, today line, and arrows from each task to the tasks that depend on it (red when the successor starts too early). Switches turn milestones and dependencies on or off. Show a week, a month, a year or all dates, and step with ‹ › (Today jumps back). Click a bar to open the task. |
| **Milestones** | Create, edit (with a reason), mark achieved, reopen, re-baseline, archive. The trend chart shows how each forecast moved over time. |
| **Workload** | Whether the work fits (cumulative demand as bars, the shortfall above capacity in apricot) and where the peaks are (stacked weekly load by priority or label against capacity), for 1–12 weeks. |
| **Settings** | Working hours and days, plannable share, thresholds, absences, public holidays; export to Excel or CSV; import tasks from CSV; restore or permanently delete archived items. |

The **filter bar** sits on the pages that show tasks: Tasks and Timeline (labels,
milestones, priority, status; "More filters" for label matching, dates, at-risk only and
archived) and Workload (only what changes demand: labels, milestones, priority, at-risk).
The filter is shared, so a filter set on Tasks also applies on Timeline and Workload, and
every chart says which filter is active. The Dashboard always shows all open work.

### Design

Colors come from Sanzo Wada's *A Dictionary of Color Combinations*, No. 309: Golden
Yellow, Apricot Orange, Vandar Poel's Blue and Violet Blue, on warm paper. The interface
uses them as printed; charts use the same hues adjusted for readability and checked for
color-vision deficiencies (`driftline/ui/theme.py`, `driftline/ui/assets/theme.css`). The font is
IBM Plex Sans (SIL Open Font License, bundled in `driftline/ui/assets/fonts/`).

### Importing tasks from CSV

UTF-8, comma-separated, with a header row ("Download CSV template" in Settings gives an
example). Required columns: `title, forecast_start, forecast_end, estimated_effort_h`
(dates as `YYYY-MM-DD`). Optional: `priority` (1–4 or Critical/High/Medium/Low),
`labels` (separated by `;`), `description`. Other columns are ignored, so an exported
`tasks.csv` imports as is. If any row is invalid, nothing is imported and every problem
is listed with its line number.

## Development

```bash
pytest                              # all tests (incl. performance, ~10 s)
pytest -m "not perf"                # skip the performance tests
python -m unittest discover -s tests -t .   # same suite without pytest
ruff check . && ruff format --check .
```

Layers (one-way): `ui → services → repo → db`, `ui → calc → domain`; a test enforces the
import rules. Writes go through services (one transaction per user action, change log in
the same transaction); `calc/` and the chart builders in `ui/charts.py` are pure.

### Status

| Phase | Content | State |
|---|---|---|
| 1 Foundation | config, clock, errors, database (schema, migrations, backup), domain models | done |
| 2 Repositories + services | 8 repositories; task, milestone, baseline, settings, snapshot services; every R-xx / VAL-xx rule tested | done |
| 3 Calculations | calendar, status, schedule, workload, filters | done |
| 4 UI shell + Tasks | app shell, filter (now the filter bar), Tasks grid with bulk actions, task form and detail, confirm dialog, demo data | done |
| 5 Views | Dashboard, Timeline, Milestones (with trend analysis), Workload; pure chart builders | done |
| 6 Settings + I/O | Settings page, Excel/CSV export, CSV import, archive management | done |
| 7 Hardening | performance test (NFR-05), error messages for every failure path, this README | done |

Performance (NFR-05, `tests/perf/`): with 500 tasks and 5,000 history entries, loading the
data takes about 20 ms and the slowest view's calculations and charts about 65 ms on a
standard laptop; the test fails above 1.5 s.

### Decisions where the specification was open

Data and rules (phase 2)
- A status equal to the current one counts as "unchanged", so a full edit form can resend
  it. Setting remaining effort > 0 on a done task therefore asks for confirmation (R-05).
- Archived tasks and milestones cannot be edited, commented or re-baselined until restored.
- "Re-baseline all" covers open tasks and open milestones only; done tasks and achieved
  milestones keep their baseline so their final variance stays visible.
- An achieved milestone's forecast is locked to its achieved date; reopen it to change it.

Calculations (phase 3)
- If a task's interval [max(today, start), end] has no working day, its effort goes to the
  next working day on or after max(today, start): today (or the next working day) for
  overdue tasks, the following Monday for a future weekend-only task.
- If no working day exists within a year (e.g. a very long absence), the effort stays on
  the interval start so no hours disappear from the chart.
- Milestone trend lines are staircases carried forward to today, or to the achieved date
  for achieved milestones, so those end on the diagonal.
- Dependency warnings only concern open successors. The delayed list shows open tasks (by
  end-date variance) and open milestones that are late.

User interface (phases 4–6)
- Writes run as JSON "actions" (`driftline/ui/actions.py`), so an action waiting for
  confirmation (R-05, R-11) is repeated exactly with `confirmed=True`.
- Bulk actions (mark reviewed, archive) run one transaction per task; re-baseline is one
  batch. If a bulk action fails part-way, the tasks before the failure stay changed.
- Archived milestones and tasks stay in the dropdowns, disabled and marked "(archived)",
  so existing links are shown and not removed by saving a form.
- Forms reload after every successful save, so unsaved edits elsewhere in the same panel
  (e.g. the task form when you add a comment, the settings form when you add a holiday)
  are replaced.
- Milestone and dependency warnings are checked against all active tasks, so a
  predecessor outside a filter can still be reported as late.
- Chart colors follow their job: status colors for task states (blocked bars are also
  hatched), one blue ramp for priority, fixed colors per label and milestone that do not
  change with the filter. Light theme only.
- Bootstrap's CSS is bundled in `driftline/ui/assets/`, so the app works offline (NFR-01).
- Export contains everything, archived items included. CSV files are UTF-8 with a byte
  order mark so Excel shows umlauts; Excel cells hold real dates and timestamps as ISO text.
- Import creates new planned tasks from the plan columns only; status, remaining effort,
  milestone and dependencies in the file are ignored, and duplicates are not checked.

Hardening (phase 7)
- Any error a page does not handle itself becomes a message in the app ("Something went
  wrong …") and a full traceback in `driftline.log`, via Dash's global `on_error` handler.
- The tests use plain helper modules instead of the `tests/conftest.py` fixtures named in
  the architecture, so the suite also runs with `unittest`.

UI iteration (after phase 7)
- The sidebar filter was replaced by a filter bar on Tasks, Timeline and Workload; the
  Dashboard is unfiltered and Milestones has its own "Show archived" switch.
- Workload ignores the status, date and archive filters: demand is always the open work.
- With more than seven labels, the six with the most open hours keep their own color (judged
  on all open work, so filtering never repaints the chart); the rest share "Other".
- Timeline dependency arrows run from the predecessor's end to the successor's start; links
  to tasks outside the filter are not drawn (the dependency warnings still check them).

Features after phase 7
- Your day (dashboard): hours per task come from the workload model (each task's remaining
  effort spread over its working days; overdue work lands on the next working day, WL-04).
  Focus order: priority, then due date, at-risk first among equals; blocked tasks keep their
  hours but are listed apart. A task counts as "within capacity" if it starts before the
  day's plannable hours are used up.
- Timeline window: a task is shown if its forecast or its baseline touches the period;
  milestones if their forecast or baseline date falls in it. The chosen period is kept for
  the browser session.
- Requirements review: the task table now shows start and end variance (SCH-03), Settings
  has "Re-baseline everything" for SCH-02's "all items", and the dashboard marks at-risk
  (⚠) and overdue (brick red) tasks in its lists (FUN-04, FUN-12).
- WL-06 now asks for a stacked line (area) chart instead of stacked bars (requirements
  v0.3, review log R-15), matching the weekly chart since the UI iteration.

### Open points (`TODO(spec)` in the code)

- Saving the task form writes fields and labels as two service calls
  (`driftline/ui/actions.py`); if the field update fails, labels are not saved either.
- "Re-baseline all" = open items only (`driftline/services/baseline_service.py`).
- Weekly workload chart: the current week shows the capacity of the full Mon–Sun week even
  late in the week (`calc/workload.weekly_capacity`); the cumulative chart counts from today.

### Backlog

- Requirements open points O-01 (time logging), O-02 (plannable share per week),
  O-03 (gaps in dependency chains).
