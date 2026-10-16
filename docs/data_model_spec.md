# Data Model Specification — Personal PM Tool

Version 0.1.1 (draft) · 2026-10-10 · Implements: `requirements.txt` v0.2

---

## 0. How to read this document (for the implementer)

- This document is **normative**. Where it conflicts with your own design instincts, follow this document.
- Requirement IDs in brackets (e.g. `[DAT-01]`) link back to `requirements.txt`.
- **Stored** data lives in SQLite (section 3). **Derived** data is computed at runtime and is **never stored** (section 5).
- All writes go through one service layer that enforces the rules in section 4. The UI never writes SQL directly. `[NFR-07]`
- When something is not specified here, choose the simplest option and leave a `# TODO(spec):` comment.

---

## 1. Conventions

| Item | Rule |
|---|---|
| Database | SQLite, single file, `PRAGMA foreign_keys = ON` on every connection `[DAT-07]` |
| Table names | singular, snake_case (`task`, `milestone`) |
| Primary keys | `id INTEGER PRIMARY KEY AUTOINCREMENT` (IDs are never reused) |
| Planning dates | `TEXT`, ISO date `YYYY-MM-DD` `[NFR-06]` |
| Timestamps | `TEXT`, ISO local time with offset `YYYY-MM-DDTHH:MM:SS+02:00` `[NFR-06]` |
| Booleans | `INTEGER` 0/1 with `CHECK (x IN (0,1))` |
| Effort | `REAL`, hours, `>= 0` `[VAL-02]` |
| Enums | `TEXT` with `CHECK (x IN (...))`; values listed in section 2 |
| Soft delete | `archived_at TEXT NULL`; `NULL` = active `[DAT-08]` |

---

## 2. Enumerations

| Enum | Values | Default |
|---|---|---|
| `task_status` `[DAT-02]` | `planned`, `in_progress`, `blocked`, `done` | `planned` |
| `priority` `[DAT-03]` | `1` Critical, `2` High, `3` Medium, `4` Low (stored as INTEGER) | `3` |
| `milestone_status` `[DAT-05]` | `open`, `achieved` | `open` |
| `comment_kind` | `note`, `risk_set`, `risk_cleared`, `blocked`, `system` | `note` |
| `entity_type` | `task`, `milestone` | — |
| `change_kind` | `create`, `edit`, `rebaseline`, `archive`, `restore` | — |

---

## 3. Stored entities

### 3.1 Overview

```
 milestone 1 ──── 0..n task ──── 0..n comment
                    │  │
                    │  └── n..m label        (via task_label)
                    └───── n..m task         (via task_dependency: predecessor → successor)

 change_log   ── polymorphic: (entity_type, entity_id) → task | milestone
 app_settings ── exactly one row
 absence, public_holiday ── calendar inputs for capacity
 schema_version ── migrations
```

### 3.2 `task` `[DAT-01]`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INTEGER PK | no | auto | |
| title | TEXT | no | | `CHECK (length(trim(title)) > 0)` |
| description | TEXT | yes | NULL | |
| baseline_start | TEXT date | no | | set = forecast_start on create `[SCH-01]` |
| baseline_end | TEXT date | no | | set = forecast_end on create |
| forecast_start | TEXT date | no | | |
| forecast_end | TEXT date | no | | |
| estimated_effort_h | REAL | no | | `>= 0` |
| remaining_effort_h | REAL | no | | `>= 0`; set = estimated on create |
| status | TEXT | no | `planned` | enum `task_status` |
| priority | INTEGER | no | 3 | `CHECK (priority BETWEEN 1 AND 4)` |
| at_risk | INTEGER bool | no | 0 | reason lives in `comment` (kind `risk_set`) `[VAL-06]` |
| milestone_id | INTEGER FK → milestone.id | yes | NULL | `ON DELETE SET NULL` `[FUN-05]` |
| last_review_at | TEXT timestamp | no | = created_at | see rule R-07 |
| created_at | TEXT timestamp | no | now | |
| updated_at | TEXT timestamp | no | now | |
| archived_at | TEXT timestamp | yes | NULL | `[DAT-08]` |

Table constraints:
- `CHECK (baseline_end >= baseline_start)` `[VAL-01]`
- `CHECK (forecast_end >= forecast_start)` `[VAL-01]`
- `CHECK (status <> 'done' OR remaining_effort_h = 0)` `[VAL-03]`

### 3.3 `milestone` `[DAT-05]`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INTEGER PK | no | auto | |
| name | TEXT | no | | non-empty |
| description | TEXT | yes | NULL | |
| baseline_date | TEXT date | no | | set = forecast_date on create `[SCH-01]` |
| forecast_date | TEXT date | no | | entered manually `[SCH-05]` |
| status | TEXT | no | `open` | enum `milestone_status` |
| achieved_date | TEXT date | yes | NULL | |
| created_at | TEXT timestamp | no | now | |
| updated_at | TEXT timestamp | no | now | |
| archived_at | TEXT timestamp | yes | NULL | |

Table constraint: `CHECK ((status = 'achieved') = (achieved_date IS NOT NULL))`

### 3.4 `label` `[DAT-04]`

| Column | Type | Null | Notes |
|---|---|---|---|
| id | INTEGER PK | no | |
| name | TEXT | no | display form, as first entered |
| name_key | TEXT | no | `lower(trim(name))`, `UNIQUE` — prevents case duplicates |

### 3.5 `task_label` (join)

| Column | Type | Notes |
|---|---|---|
| task_id | INTEGER FK → task.id | `ON DELETE CASCADE` |
| label_id | INTEGER FK → label.id | `ON DELETE CASCADE` |

PK `(task_id, label_id)`.

### 3.6 `task_dependency` `[DAT-06]`

| Column | Type | Notes |
|---|---|---|
| predecessor_id | INTEGER FK → task.id | `ON DELETE CASCADE` |
| successor_id | INTEGER FK → task.id | `ON DELETE CASCADE` |

PK `(predecessor_id, successor_id)`; `CHECK (predecessor_id <> successor_id)` `[VAL-05]`.
Metadata only — no code may change dates based on this table.

### 3.7 `comment` `[FUN-03]`

| Column | Type | Null | Notes |
|---|---|---|---|
| id | INTEGER PK | no | |
| task_id | INTEGER FK → task.id | no | `ON DELETE CASCADE` |
| kind | TEXT | no | enum `comment_kind` |
| text | TEXT | no | non-empty |
| created_at | TEXT timestamp | no | |

Append-only: no UPDATE, no DELETE (except cascade on permanent task deletion).

### 3.8 `change_log` `[DAT-09]`

| Column | Type | Null | Notes |
|---|---|---|---|
| id | INTEGER PK | no | |
| entity_type | TEXT | no | enum `entity_type` |
| entity_id | INTEGER | no | no FK (polymorphic) |
| change_kind | TEXT | no | enum `change_kind` |
| field | TEXT | yes | column name; NULL for `archive` / `restore` |
| old_value | TEXT | yes | NULL on `create` |
| new_value | TEXT | yes | |
| reason | TEXT | yes | mandatory for `rebaseline` |
| batch_id | TEXT | yes | UUID shared by all rows of one user action |
| changed_at | TEXT timestamp | no | |

Index: `(entity_type, entity_id, field, changed_at)`.

Value encoding in `old_value` / `new_value`: dates as `YYYY-MM-DD`, numbers via `repr(float)`, enums as stored, booleans as `0`/`1`.

**Logged fields** (exactly these, no others):

| Entity | Fields |
|---|---|
| task | baseline_start, baseline_end, forecast_start, forecast_end, remaining_effort_h, status |
| milestone | baseline_date, forecast_date, status |

### 3.9 `app_settings` (exactly one row) `[WL-01, WL-07, WL-08, NFR-04]`

| Column | Type | Default | Constraint |
|---|---|---|---|
| id | INTEGER PK | 1 | `CHECK (id = 1)` |
| weekly_hours | REAL | 40.0 | `> 0` |
| working_weekdays | TEXT | `1,2,3,4,5` | ISO weekdays, Mon = 1 … Sun = 7, comma-separated, no duplicates |
| plannable_fraction | REAL | 0.65 | `> 0 AND <= 1` |
| default_horizon_weeks | INTEGER | 4 | `BETWEEN 1 AND 12` |
| load_green_max | REAL | 0.85 | ratio |
| load_amber_max | REAL | 1.00 | `>= load_green_max` |
| stale_after_days | INTEGER | 14 | `> 0` |
| backup_keep_count | INTEGER | 10 | `> 0` |
| top_delayed_n | INTEGER | 10 | `> 0` |

### 3.10 `absence` `[WL-01]`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| start_date | TEXT date | inclusive |
| end_date | TEXT date | inclusive, `>= start_date` |
| note | TEXT NULL | e.g. "Vacation" |

Overlapping absences are allowed; a day counts as absent if covered by any row.

### 3.11 `public_holiday` `[WL-01]`

| Column | Type | Notes |
|---|---|---|
| date | TEXT date PK | |
| name | TEXT NULL | |

### 3.12 `schema_version`

| Column | Type | Notes |
|---|---|---|
| version | INTEGER | single row; start at 1; increment with every migration |

---

## 4. Write rules (enforced in the service layer)

Each rule runs **inside the same transaction** as the write it belongs to.

| ID | Trigger | Required behavior | Req. |
|---|---|---|---|
| R-01 | Create task | Set baseline = forecast dates, remaining = estimated, last_review_at = created_at. Write one `create` row in `change_log` per logged field (old_value NULL). | SCH-01, DAT-09 |
| R-02 | Create milestone | Set baseline_date = forecast_date. Log `create` rows as in R-01. | SCH-01, SCH-04 |
| R-03 | Edit any logged field | If the value actually changed: write one `edit` row (old, new, optional reason). Unchanged values are not logged. | DAT-09 |
| R-04 | Set task status `done` | Set remaining_effort_h = 0 (logged). | VAL-03 |
| R-05 | Set remaining > 0 on a `done` task | Ask the user for confirmation; on yes, set status `in_progress` (logged). On no, abort. | VAL-03 |
| R-06 | Set at_risk = 1, or status `blocked` | Reason text required; insert `comment` with kind `risk_set` / `blocked`. Clearing at_risk inserts kind `risk_cleared` (reason optional). | VAL-06 |
| R-07 | Any change to remaining effort, status or forecast dates — or the explicit "Mark reviewed" action | Set last_review_at = now. | WL-08 |
| R-08 | Re-baseline (one item or all) | Reason required. For each item, copy forecast → baseline fields; write `rebaseline` rows (old baseline, new baseline, reason). All rows share one batch_id. Old baselines remain readable through the log. | SCH-02 |
| R-09 | Milestone status → `achieved` | Set achieved_date (default today) and set forecast_date = achieved_date (logged). Reverting to `open` clears achieved_date. | SCH-04 |
| R-10 | Archive / restore | Set or clear archived_at; write one `archive` / `restore` row. Links (labels, dependencies, milestone) are kept. Archiving a milestone does **not** archive its tasks. | DAT-08 |
| R-11 | Permanent delete | Only for already archived items, after confirmation. Delete the row (cascades remove labels, dependencies, comments) and delete its `change_log` rows. | DAT-08 |
| R-12 | Add label to task | Normalize to name_key; reuse existing label if found, else create. | DAT-04 |
| R-13 | Add dependency | Both tasks must exist; reject self-reference. Cycles are allowed (metadata only) but should be shown as a warning. | VAL-05, DAT-06 |
| R-14 | Any task/milestone update | Set updated_at = now. | — |

---

## 5. Derived values (never stored)

`today` = local date at time of calculation. "Active" = `archived_at IS NULL`.

| Name | Definition | Req. |
|---|---|---|
| is_open | active AND status ≠ `done` | — |
| is_overdue | is_open AND forecast_end < today | FUN-12 |
| start_variance_d | forecast_start − baseline_start (calendar days, + = late) | SCH-03 |
| end_variance_d | forecast_end − baseline_end | SCH-03 |
| milestone_variance_d | forecast_date − baseline_date | SCH-03 |
| is_effort_overrun | remaining_effort_h > estimated_effort_h | VAL-04 |
| is_stale | is_open AND (now − last_review_at) > stale_after_days | WL-08 |
| current_risk_reason | text of latest `risk_set` comment, if at_risk = 1 | FUN-04 |
| successors(t) | tasks where `task_dependency.predecessor_id = t` | FUN-06 |
| dependency_warning(t) | exists active predecessor p with t.forecast_start < p.forecast_end | FUN-07 |
| milestone_task_warning(m) | max(forecast_end of open tasks linked to m) > m.forecast_date | SCH-05 |
| is_working_day(d) | weekday(d) in working_weekdays AND d not a public_holiday AND d not in any absence | WL-01 |
| capacity_h(d) | is_working_day(d) ? weekly_hours / count(working_weekdays) × plannable_fraction : 0 | WL-02 |
| due_date(t) | max(t.forecast_end, today) — overdue work is due today | WL-04 |
| cumulative_demand(D) | Σ remaining_effort_h of open tasks (incl. `blocked`) with due_date ≤ D, after filters | WL-03, WL-05, FUN-10 |
| cumulative_capacity(D) | Σ capacity_h(d) for d from today to D (inclusive) | WL-03 |
| shortfall_h(D) | max(0, cumulative_demand(D) − cumulative_capacity(D)) | WL-03 |
| daily_allocation(t, d) | remaining_effort_h / N on each working day d in [max(today, forecast_start), forecast_end], where N = number of such days. If N = 0: whole effort on the next working day ≥ today. | WL-06 |
| load_ratio(H) | cumulative_demand(today + H weeks − 1 day) / cumulative_capacity(same date) | WL-07 |
| mta_series(m) | from `change_log` rows of m with field `forecast_date`, ordered by changed_at: list of (date(changed_at), new_value); carry the value forward between changes | SCH-04 |
| baseline_history(x) | `change_log` rows with change_kind `rebaseline` for x | SCH-02 |

Edge cases to test:
- `load_ratio` when capacity = 0 (e.g. horizon fully in vacation): return "n/a", not division by zero.
- Task with `forecast_start` in the future: counts in cumulative demand by its due date, but daily_allocation only starts at forecast_start.
- `today` is not a working day: capacity_h(today) = 0; overdue effort still counts in demand on today.

---

## 6. Filters `[FUN-09, FUN-10]`

A filter is an in-memory object applied before any view or calculation. It is not stored (it may be remembered as a UI convenience).

| Field | Type | Semantics |
|---|---|---|
| labels | set of label_id | empty = no restriction |
| label_mode | `any` \| `all` | task matches if it has any / all selected labels |
| priorities | set of 1..4 | empty = no restriction |
| statuses | set of task_status | default: `planned`, `in_progress`, `blocked` |
| at_risk_only | bool | default false |
| milestone_ids | set of id | empty = no restriction |
| date_from, date_to | date \| null | task matches if [forecast_start, forecast_end] overlaps the range |
| include_archived | bool | default false |

Every chart shows a one-line text summary of the active filter.

---

## 7. Reference DDL

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);

CREATE TABLE app_settings (
  id                    INTEGER PRIMARY KEY CHECK (id = 1),
  weekly_hours          REAL    NOT NULL DEFAULT 40.0 CHECK (weekly_hours > 0),
  working_weekdays      TEXT    NOT NULL DEFAULT '1,2,3,4,5',
  plannable_fraction    REAL    NOT NULL DEFAULT 0.65
                        CHECK (plannable_fraction > 0 AND plannable_fraction <= 1),
  default_horizon_weeks INTEGER NOT NULL DEFAULT 4
                        CHECK (default_horizon_weeks BETWEEN 1 AND 12),
  load_green_max        REAL    NOT NULL DEFAULT 0.85,
  load_amber_max        REAL    NOT NULL DEFAULT 1.00,
  stale_after_days      INTEGER NOT NULL DEFAULT 14 CHECK (stale_after_days > 0),
  backup_keep_count     INTEGER NOT NULL DEFAULT 10 CHECK (backup_keep_count > 0),
  top_delayed_n         INTEGER NOT NULL DEFAULT 10 CHECK (top_delayed_n > 0),
  CHECK (load_amber_max >= load_green_max)
);
INSERT INTO app_settings (id) VALUES (1);

CREATE TABLE milestone (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT NOT NULL CHECK (length(trim(name)) > 0),
  description    TEXT,
  baseline_date  TEXT NOT NULL,
  forecast_date  TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','achieved')),
  achieved_date  TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  archived_at    TEXT,
  CHECK ((status = 'achieved') = (achieved_date IS NOT NULL))
);

CREATE TABLE task (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  title               TEXT NOT NULL CHECK (length(trim(title)) > 0),
  description         TEXT,
  baseline_start      TEXT NOT NULL,
  baseline_end        TEXT NOT NULL,
  forecast_start      TEXT NOT NULL,
  forecast_end        TEXT NOT NULL,
  estimated_effort_h  REAL NOT NULL CHECK (estimated_effort_h >= 0),
  remaining_effort_h  REAL NOT NULL CHECK (remaining_effort_h >= 0),
  status              TEXT NOT NULL DEFAULT 'planned'
                      CHECK (status IN ('planned','in_progress','blocked','done')),
  priority            INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
  at_risk             INTEGER NOT NULL DEFAULT 0 CHECK (at_risk IN (0,1)),
  milestone_id        INTEGER REFERENCES milestone(id) ON DELETE SET NULL,
  last_review_at      TEXT NOT NULL,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL,
  archived_at         TEXT,
  CHECK (baseline_end >= baseline_start),
  CHECK (forecast_end >= forecast_start),
  CHECK (status <> 'done' OR remaining_effort_h = 0)
);

CREATE TABLE label (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name      TEXT NOT NULL,
  name_key  TEXT NOT NULL UNIQUE
);

CREATE TABLE task_label (
  task_id   INTEGER NOT NULL REFERENCES task(id)  ON DELETE CASCADE,
  label_id  INTEGER NOT NULL REFERENCES label(id) ON DELETE CASCADE,
  PRIMARY KEY (task_id, label_id)
);

CREATE TABLE task_dependency (
  predecessor_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  successor_id   INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  PRIMARY KEY (predecessor_id, successor_id),
  CHECK (predecessor_id <> successor_id)
);

CREATE TABLE comment (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id     INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL DEFAULT 'note'
              CHECK (kind IN ('note','risk_set','risk_cleared','blocked','system')),
  text        TEXT NOT NULL CHECK (length(trim(text)) > 0),
  created_at  TEXT NOT NULL
);

CREATE TABLE change_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type  TEXT NOT NULL CHECK (entity_type IN ('task','milestone')),
  entity_id    INTEGER NOT NULL,
  change_kind  TEXT NOT NULL
               CHECK (change_kind IN ('create','edit','rebaseline','archive','restore')),
  field        TEXT,
  old_value    TEXT,
  new_value    TEXT,
  reason       TEXT,
  batch_id     TEXT,
  changed_at   TEXT NOT NULL,
  CHECK (change_kind <> 'rebaseline' OR (reason IS NOT NULL AND length(trim(reason)) > 0))
);
CREATE INDEX ix_change_log_entity
  ON change_log (entity_type, entity_id, field, changed_at);

CREATE TABLE absence (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  start_date  TEXT NOT NULL,
  end_date    TEXT NOT NULL,
  note        TEXT,
  CHECK (end_date >= start_date)
);

CREATE TABLE public_holiday (
  date  TEXT PRIMARY KEY,
  name  TEXT
);

CREATE INDEX ix_task_active   ON task (archived_at, status);
CREATE INDEX ix_task_ms       ON task (milestone_id);
CREATE INDEX ix_comment_task  ON comment (task_id, created_at);
```

---

## 8. Traceability

| Requirement | Covered by |
|---|---|
| DAT-01 | 3.2 |
| DAT-02, DAT-03 | 2, 3.2 |
| DAT-04 | 3.4, 3.5, R-12 |
| DAT-05 | 3.3 |
| DAT-06 | 3.6, R-13 |
| DAT-07 | 1, 7 |
| DAT-08 | `archived_at`, R-10, R-11 |
| DAT-09 | 3.8, R-01 to R-03 |
| VAL-01 … VAL-06 | CHECK constraints, R-04 to R-06, R-13 |
| FUN-03, FUN-04 | 3.7, R-06 |
| FUN-05 … FUN-07 | `milestone_id`, 3.6, section 5 |
| FUN-09, FUN-10 | section 6 |
| SCH-01 … SCH-05 | R-01, R-02, R-08, R-09, section 5 |
| WL-01 … WL-08 | 3.9 to 3.11, R-07, section 5 |
| NFR-04 | `backup_keep_count` (backup logic itself lives in the application) |
| NFR-06 | section 1 |

---

## 9. Out of scope for this model

- Time logging (open point O-01)
- Per-week plannable fraction (O-02)
- Users, permissions, sharing
- Undo (the change log is an audit trail, not an undo mechanism)

---

## 10. Change history

- 0.1.1: change_log CHECK now also rejects a NULL reason for `rebaseline` (`length(trim(NULL))` is NULL, and SQLite treats a NULL CHECK result as passed). Found while implementing phase 1.
