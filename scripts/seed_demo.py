"""Fill a database with demo data: ~30 tasks, 4 milestones, 8 weeks of history.

Usage:
    python scripts/seed_demo.py                 # default database (~/.pmtool/pmtool.db)
    python scripts/seed_demo.py --db demo.db    # another file
    python scripts/seed_demo.py --force         # replace an existing database

Everything goes through the services with a clock that travels from 8 weeks
ago to now, so the change log, milestone drift (MTA), re-baselines and
stale/overdue/at-risk tasks look like real use. All dates are relative to today.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pmtool.clock import FixedClock, SystemClock
from pmtool.config import load_config
from pmtool.db.connection import connect
from pmtool.db.migrations import apply_migrations, ensure_settings_row
from pmtool.domain.commands import MilestoneCreate, MilestoneUpdate, TaskCreate, TaskUpdate
from pmtool.domain.enums import Priority, TaskStatus
from pmtool.services import Services, build_services

HISTORY_DAYS = 56


@dataclass(frozen=True)
class TaskSpec:
    key: int
    title: str
    labels: tuple[str, ...]
    priority: int
    start: int  # days relative to today
    end: int
    effort_h: float
    milestone: str | None = None
    created: int = -HISTORY_DAYS
    predecessors: tuple[int, ...] = ()
    description: str | None = None


# fmt: off
MILESTONES = {  # key: (name, initial forecast, description)
    "paper": ("Paper submission", 10, "Journal submission of the main paper."),
    "review": ("Project review meeting", 30, "Yearly review with the project partners."),
    "tax": ("Tax return filed", 7, None),
    "grant": ("Grant report sent", -14, "Final report for the seed grant."),
}

TASKS = [
    TaskSpec(1, "Literature review update", ("research", "writing"), 2, -50, -30, 16, "paper"),
    TaskSpec(2, "Run final experiments", ("research",), 1, -35, -7, 30, "paper"),
    TaskSpec(3, "Write results section", ("writing", "research"), 2, -5, 8, 14, "paper",
             predecessors=(2,)),
    TaskSpec(4, "Prepare figures", ("research",), 3, 2, 10, 8, "paper", predecessors=(2,)),
    TaskSpec(5, "Internal proofreading", ("writing",), 3, 12, 16, 6, "paper",
             predecessors=(3,)),
    TaskSpec(6, "Submit to journal portal", ("admin",), 2, 18, 19, 2, "paper",
             predecessors=(5,)),
    TaskSpec(7, "Draft status report", ("work", "writing"), 2, 3, 12, 10, "review"),
    TaskSpec(8, "Update budget sheet", ("work", "finance"), 2, -10, -2, 6, "review"),
    TaskSpec(9, "Collect partner inputs", ("work",), 3, -20, 5, 5, "review"),
    TaskSpec(10, "Prepare review slides", ("work",), 2, 21, 30, 12, "review",
             predecessors=(7,)),
    TaskSpec(11, "Book meeting room and catering", ("admin",), 4, 14, 16, 1, "review"),
    TaskSpec(12, "Gather receipts", ("finance", "admin"), 2, -30, -15, 4, "tax"),
    TaskSpec(13, "Fill in tax forms", ("finance",), 1, -14, 5, 8, "tax", created=-20),
    TaskSpec(14, "Ask accountant about home office", ("finance",), 3, -8, -4, 1, "tax",
             created=-20),
    TaskSpec(15, "Write grant report", ("work", "writing"), 1, -40, -12, 20, "grant"),
    TaskSpec(16, "Financial statement for grant", ("finance", "work"), 1, -30, -13, 6, "grant"),
    TaskSpec(17, "Prepare lecture 5", ("teaching",), 2, -3, 2, 6, created=-21),
    TaskSpec(18, "Prepare lecture 6", ("teaching",), 2, 4, 9, 6, created=-21),
    TaskSpec(19, "Grade assignment set 3", ("teaching",), 2, 1, 6, 8, created=-21),
    TaskSpec(20, "Update course website", ("teaching", "admin"), 4, -20, 30, 3),
    TaskSpec(21, "Renew passport", ("admin", "home"), 2, -25, -5, 2),
    TaskSpec(22, "Book dentist appointment", ("health",), 3, -40, -35, 0.5),
    TaskSpec(23, "Fix bike brakes", ("home",), 4, 3, 10, 2, created=-14),
    TaskSpec(24, "Plan summer vacation", ("home",), 4, 20, 40, 4),
    TaskSpec(25, "Annual health check-up", ("health",), 3, 25, 25, 3, created=-14),
    TaskSpec(26, "Review paper for conference", ("research",), 2, 0, 12, 6, created=-14),
    TaskSpec(27, "Set up new laptop", ("work", "admin"), 3, -45, -40, 4),
    TaskSpec(28, "Read thesis draft of student", ("research", "teaching"), 2, 5, 15, 8,
             created=-10),
    TaskSpec(29, "Write blog post on results", ("writing",), 4, 30, 45, 5, created=-3),
    TaskSpec(30, "Clean up shared drive", ("work", "admin"), 4, 40, 50, 6, created=-3),
]
STALE = {20, 21, 24}  # never reviewed after creation, so they show up as stale
# fmt: on


class TravelClock(FixedClock):
    def set(self, moment: datetime) -> None:
        self._now = moment


@dataclass
class Seeder:
    svc: Services
    clock: TravelClock
    real_now: datetime  # history ends here; nothing is written in the future
    tasks: dict[int, int] = field(default_factory=dict)  # spec key -> task id
    milestones: dict[str, int] = field(default_factory=dict)
    events: list[tuple[int, int, Callable[[], None]]] = field(default_factory=list)

    def d(self, offset: int) -> date:
        return self.real_now.date() + timedelta(days=offset)

    def at(self, day: int, hour: int, fn: Callable[[], None]) -> None:
        self.events.append((day, hour, fn))

    def run(self) -> None:
        tz = self.clock.now().tzinfo
        for day, hour, fn in sorted(self.events, key=lambda e: (e[0], e[1])):
            moment = datetime.combine(self.d(day), time(hour, 0), tzinfo=tz)
            self.clock.set(min(moment, self.real_now))
            fn()

    # --- shortcuts ---------------------------------------------------------------

    def update(self, key: int, **fields) -> None:
        self.svc.tasks.update(TaskUpdate(task_id=self.tasks[key], **fields), confirmed=True)

    def progress(self, key: int, remaining: float, **fields) -> None:
        self.update(key, status=TaskStatus.IN_PROGRESS, remaining_effort_h=remaining, **fields)

    def done(self, key: int) -> None:
        self.update(key, status=TaskStatus.DONE)

    def comment(self, key: int, text: str) -> None:
        self.svc.tasks.add_comment(self.tasks[key], text)

    def move_milestone(self, key: str, offset: int, reason: str) -> None:
        self.svc.milestones.update(
            MilestoneUpdate(self.milestones[key], forecast_date=self.d(offset), reason=reason)
        )


def build(seed: Seeder) -> None:
    s = seed

    # --- creation ----------------------------------------------------------------
    for key, (name, forecast, description) in MILESTONES.items():

        def create_ms(key=key, name=name, forecast=forecast, description=description):
            s.milestones[key] = s.svc.milestones.create(
                MilestoneCreate(name, s.d(forecast), description)
            )

        s.at(-HISTORY_DAYS, 8, create_ms)

    for spec in TASKS:

        def create_task(spec=spec):
            s.tasks[spec.key] = s.svc.tasks.create(
                TaskCreate(
                    title=spec.title,
                    forecast_start=s.d(spec.start),
                    forecast_end=s.d(spec.end),
                    estimated_effort_h=spec.effort_h,
                    description=spec.description,
                    priority=Priority(spec.priority),
                    label_names=spec.labels,
                    predecessor_ids=tuple(s.tasks[p] for p in spec.predecessors),
                    milestone_id=s.milestones.get(spec.milestone) if spec.milestone else None,
                )
            )

        s.at(spec.created, 9, create_task)

    # --- milestone drift (MTA) ---------------------------------------------------
    s.at(-42, 10, lambda: s.move_milestone("paper", 14, "Experiments need more runs"))
    s.at(-30, 10, lambda: s.move_milestone("grant", -10, "Partner asked for extra section"))
    s.at(-28, 10, lambda: s.move_milestone("paper", 18, "Co-author on vacation"))
    s.at(-21, 10, lambda: s.move_milestone("review", 35, "Partners asked for a later date"))
    s.at(-20, 10, lambda: s.svc.baselines.rebaseline_milestones(
        [s.milestones["review"]], "New review date agreed with partners"))  # fmt: skip
    s.at(-20, 11, lambda: s.move_milestone("tax", 14, "Bank statement arrives late"))
    s.at(-14, 10, lambda: s.move_milestone("paper", 21, "Experiments slipped again"))
    s.at(-10, 16, lambda: s.svc.milestones.set_achieved(s.milestones["grant"], s.d(-10)))

    # --- task progress -----------------------------------------------------------
    s.at(-48, 9, lambda: s.progress(1, 10))
    s.at(-40, 15, lambda: s.done(27))
    s.at(-36, 11, lambda: s.done(22))
    s.at(-35, 9, lambda: s.progress(15, 16))
    s.at(-34, 9, lambda: s.progress(2, 26))
    s.at(-30, 17, lambda: s.done(1))
    s.at(-28, 9, lambda: s.progress(16, 4))
    s.at(-25, 9, lambda: s.progress(12, 2))
    s.at(-24, 14, lambda: s.comment(2, "Cluster queue is slow; runs take twice as long."))
    s.at(-21, 9, lambda: s.update(7, forecast_start=s.d(7), forecast_end=s.d(20),
                                  reason="Waiting for partner input"))  # fmt: skip
    s.at(-20, 9, lambda: s.svc.baselines.rebaseline_tasks(
        [s.tasks[7]], "Review date moved by partners"))  # fmt: skip
    s.at(-20, 15, lambda: s.svc.tasks.archive(s.tasks[27]))
    s.at(-18, 9, lambda: s.progress(15, 8))
    s.at(-16, 12, lambda: s.done(12))
    s.at(-15, 9, lambda: s.progress(13, 6))
    s.at(-14, 9, lambda: s.update(2, forecast_end=s.d(3), remaining_effort_h=14,
                                  reason="Additional runs needed"))  # fmt: skip
    s.at(-12, 17, lambda: s.done(16))
    s.at(-11, 17, lambda: s.done(15))
    s.at(-10, 9, lambda: s.progress(8, 3))
    s.at(-9, 10, lambda: s.svc.tasks.set_at_risk(
        s.tasks[13], True, "Annual statement from the bank is still missing"))  # fmt: skip
    s.at(-8, 9, lambda: s.update(13, remaining_effort_h=10, reason="Forms more complex"))
    s.at(-6, 11, lambda: s.update(9, status=TaskStatus.BLOCKED,
                                  status_reason="Two partners have not replied yet"))  # fmt: skip
    s.at(-5, 9, lambda: s.progress(17, 4))
    s.at(-5, 14, lambda: s.comment(17, "Slides done, exercises still missing."))
    s.at(-4, 9, lambda: s.progress(2, 8))
    s.at(-4, 10, lambda: s.svc.tasks.set_at_risk(
        s.tasks[3], True, "Depends on experiments that are late"))  # fmt: skip
    s.at(-3, 16, lambda: s.comment(9, "Sent a reminder to all partners."))
    s.at(-1, 9, lambda: s.progress(26, 5))

    # Weekly review: everything open except the deliberately stale tasks.
    def weekly_review():
        snap = s.svc.snapshot.load()
        stale_ids = {s.tasks[k] for k in STALE}
        for t in snap.tasks:
            if t.status is not TaskStatus.DONE and t.id not in stale_ids:
                s.svc.tasks.mark_reviewed(t.id)

    s.at(-2, 17, weekly_review)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=load_config().db_path)
    parser.add_argument("--force", action="store_true", help="replace an existing database")
    args = parser.parse_args(argv)

    if args.db.exists():
        if not args.force:
            print(f"{args.db} exists. Use --force to replace it.", file=sys.stderr)
            return 1
        args.db.unlink()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db)
    try:
        apply_migrations(conn)
        ensure_settings_row(conn)
    finally:
        conn.close()

    real_now = SystemClock().now()
    clock = TravelClock(real_now)
    seeder = Seeder(build_services(args.db, clock), clock, real_now)
    build(seeder)
    seeder.run()

    snap = seeder.svc.snapshot.load(include_archived=True)
    print(f"Seeded {args.db}: {len(snap.tasks)} tasks, {len(snap.milestones)} milestones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
