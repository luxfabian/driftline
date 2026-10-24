# pmtool — personal project management

Local, single-user tool for workload forecasting and schedule tracking.
Specifications: `docs/requirements.txt`, `docs/data_model_spec.md`, `docs/architecture_spec.md`.

## Status

| Phase | Content | State |
|---|---|---|
| 1 Foundation | config, clock, errors, database (schema, migrations, backup), domain models | done |
| 2 Repositories + services | 8 repositories; task, milestone, baseline, settings, snapshot services; every R-xx / VAL-xx rule tested | done |
| 3 Calculations | calendar, status, schedule, workload, filters | done |
| 4 UI shell + Tasks | app shell, filter panel, Tasks grid with bulk actions, task form, task detail, confirm dialog, demo seed script | done |
| 5 Views | Dashboard, Timeline (Gantt), Milestones (table, actions, trend analysis), Workload; pure chart builders | done |
| 6 Settings + I/O | Settings page, export, import, archive management | next |
| 7 | hardening | open |

Export and import services exist as placeholders and arrive in phase 6, as does the
Settings page.

## Interpretations made in phase 2 (marked `TODO(spec)` where open)

- A status equal to the current one counts as "unchanged", so a full edit form can
  resend it. Setting remaining effort > 0 on a done task therefore triggers R-05.
- Archived tasks and milestones cannot be edited, commented or re-baselined until restored.
- "Re-baseline all" covers open tasks and open milestones only; done tasks and
  achieved milestones keep their baseline so their final variance stays visible.
- An achieved milestone's forecast is locked to its achieved date; reopen it to change it.

## Interpretations made in phase 3

- Workload spreading: if a task's interval [max(today, start), end] has no working day,
  its effort goes to the next working day on or after max(today, start). For overdue
  tasks that is today (or the next working day); for a future weekend-only task it is
  the following Monday, not today.
- If no working day exists within a year (e.g. a very long absence), the effort is
  kept on the interval start so no hours disappear from the chart.
- Milestone trend lines are staircases: a value is carried forward until the day it
  changes, then the line steps to the new value. The line extends to today, or to the
  achieved date for achieved milestones (pass it as `until`), so those end on the diagonal.
- Dependency warnings only concern open successors; done tasks are not flagged.
- Top delayed list: open tasks (by end-date variance) and open milestones, late only.

## Interpretations made in phase 4

- Writes run as JSON "actions" (`pmtool/ui/actions.py`), so an action waiting for
  confirmation (R-05) can be repeated exactly with `confirmed=True`.
- The edit form saves fields and labels with one click, as two service calls
  (`TODO(spec)` in `actions.py`). If the field update fails, labels are not saved.
- Bulk actions (mark reviewed, archive) run one transaction per task; re-baseline is
  one batch. If a bulk action fails part-way, the tasks before the failure stay changed.
- Bootstrap's CSS is bundled in `pmtool/ui/assets/`, so the app works offline (NFR-01).
- Archived milestones and tasks still appear in the dropdowns, disabled and marked
  "(archived)", so existing links display and are not removed by saving the form.
- The detail panel reloads after every successful write, so unsaved edits in its form
  are replaced when you, for example, add a comment first.

## Interpretations made in phase 5

- Dashboard KPIs, the delayed list and the load ratio follow the filter. Milestone and
  dependency warnings are checked against all active tasks (a predecessor outside the
  filter can still be late) and listed for the filtered tasks.
- Milestones only react to the milestone and "include archived" filters; their table and
  trend chart state exactly that part of the filter.
- Chart colors follow their job: task status uses fixed status colors (blocked bars are also
  hatched, as red/green alone is not colorblind-safe), priority uses one blue ramp (darkest =
  Critical), labels and milestones get fixed categorical slots keyed by the item, so a
  filter never repaints the rest. With more than eight labels, the rest share "Other".
- The weekly chart's first week shows the capacity of the full Mon–Sun week even when
  today is late in that week (phase 3 `weekly_capacity`); the cumulative chart counts
  capacity from today only. `TODO(spec)`: decide whether the first week should be prorated.
- Charts use a light theme only (the app has no dark mode).

## Backlog (UI iteration after phase 7)

- Timeline: draw task dependencies (predecessor -> successor arrows) in the Gantt chart.
- Weekly workload chart: decide whether the current week's capacity counts from today
  (see phase 5 notes).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```bash
python -m pmtool
```

Then open http://127.0.0.1:8050 (port: `PMTOOL_PORT`). The database lives in
`~/.pmtool/` (override with `PMTOOL_DATA_DIR`); every start makes a backup.

### Demo data

```bash
python scripts/seed_demo.py                       # into ~/.pmtool/pmtool.db (refuses to overwrite)
python scripts/seed_demo.py --db /tmp/demo.db     # another file
python scripts/seed_demo.py --force               # replace an existing database
```

The script creates 30 tasks, 4 milestones and 8 weeks of history (slips, re-baselines,
milestone drift, blocked, at-risk, stale and overdue tasks), all relative to today.
Quickest way to try it without touching your own data: `scripts/demo.sh` rebuilds a demo
project in `~/.pmtool-demo` and starts it on http://127.0.0.1:8051 (`--keep` keeps your
changes from the last run). Or by hand:

```bash
mkdir -p /tmp/pmdemo && python scripts/seed_demo.py --db /tmp/pmdemo/pmtool.db --force
PMTOOL_DATA_DIR=/tmp/pmdemo python -m pmtool
```

## Tests

```bash
pytest                              # or, without pytest:
python -m unittest discover -s tests -t .
ruff check . && ruff format --check .
```
