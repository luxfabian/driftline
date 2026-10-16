# pmtool — personal project management

Local, single-user tool for workload forecasting and schedule tracking.
Specifications: `docs/requirements.txt`, `docs/data_model_spec.md`, `docs/architecture_spec.md`.

## Status

| Phase | Content | State |
|---|---|---|
| 1 Foundation | config, clock, errors, database (schema, migrations, backup), domain models | done |
| 2 Repositories + services | 8 repositories; task, milestone, baseline, settings, snapshot services; every R-xx / VAL-xx rule tested | done |
| 3 Calculations | calendar, status, schedule, workload, filters | done |
| 4 UI shell + Tasks | needs Dash, Plotly, dash-bootstrap-components, dash-ag-grid | next |
| 5–7 | views, I/O, hardening | open |

Export and import services exist as placeholders and arrive in phase 6.

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

Until phase 4, this only creates or upgrades the database in `~/.pmtool/`
(override with `PMTOOL_DATA_DIR`) and makes a backup on every start.

## Tests

```bash
pytest                              # or, without pytest:
python -m unittest discover -s tests -t .
ruff check . && ruff format --check .
```
