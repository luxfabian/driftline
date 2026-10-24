-- Schema version 1. Source: docs/data_model_spec.md section 7 (spec v0.1.1, copied verbatim).
-- Do not edit for later changes: add a migration in migrations.py instead.

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
