"""Schedule variance, warnings, milestone trend data [SCH-03..SCH-06, FUN-07]."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pmtool.calc.status import is_open
from pmtool.domain.enums import MilestoneStatus
from pmtool.domain.models import ChangeLogEntry, Milestone, Task


@dataclass(frozen=True)
class Variance:
    """Calendar days, positive = late (forecast after baseline)."""

    start_d: int
    end_d: int


@dataclass(frozen=True)
class DelayItem:
    kind: Literal["task", "milestone"]
    id: int
    name: str
    variance_d: int
    baseline: date
    forecast: date


def task_variance(t: Task) -> Variance:
    return Variance(
        start_d=(t.forecast_start - t.baseline_start).days,
        end_d=(t.forecast_end - t.baseline_end).days,
    )


def milestone_variance(m: Milestone) -> int:
    return (m.forecast_date - m.baseline_date).days


def dependency_warnings(tasks: Sequence[Task]) -> dict[int, list[int]]:
    """FUN-07: open task -> active predecessors whose forecast end is after its start.

    Pass all active tasks (not a filtered subset), so predecessors outside the
    current filter are still checked. Display only; nothing is changed.
    """
    by_id = {t.id: t for t in tasks if t.archived_at is None}
    warnings: dict[int, list[int]] = {}
    for t in by_id.values():
        if not is_open(t):
            continue
        late = sorted(
            p_id
            for p_id in t.predecessor_ids
            if p_id in by_id and t.forecast_start < by_id[p_id].forecast_end
        )
        if late:
            warnings[t.id] = late
    return warnings


def dependency_cycles(tasks: Sequence[Task]) -> list[list[int]]:
    """Groups of tasks that depend on each other in a loop (R-13 warning).

    Strongly connected components with more than one task, each sorted, list
    sorted by first id. Edges point predecessor -> successor.
    """
    ids = {t.id for t in tasks}
    successors: dict[int, list[int]] = {i: [] for i in ids}
    for t in tasks:
        for p in t.predecessor_ids:
            if p in ids:
                successors[p].append(t.id)
    components = _strongly_connected(sorted(ids), successors)
    return sorted((sorted(c) for c in components if len(c) > 1), key=lambda c: c[0])


def milestone_task_warnings(
    milestones: Iterable[Milestone], tasks: Iterable[Task]
) -> dict[int, date]:
    """SCH-05: open milestone -> latest forecast end of its open tasks, if later."""
    latest: dict[int, date] = {}
    for t in tasks:
        if t.milestone_id is not None and is_open(t):
            current = latest.get(t.milestone_id)
            if current is None or t.forecast_end > current:
                latest[t.milestone_id] = t.forecast_end
    return {
        m.id: latest[m.id]
        for m in milestones
        if m.status is MilestoneStatus.OPEN
        and m.archived_at is None
        and m.id in latest
        and latest[m.id] > m.forecast_date
    }


def mta_series(
    entries: Sequence[ChangeLogEntry], today: date, until: date | None = None
) -> list[tuple[date, date]]:
    """SCH-04: (reporting date, forecast date) points for one milestone.

    Built from the milestone's change_log rows for ``forecast_date``. Several
    changes on one day keep the last. Values are carried forward as a
    staircase: before each change a point repeats the previous value, and the
    line is extended to ``until`` (default ``today``). Pass the achieved date as
    ``until`` for achieved milestones so their line ends on the diagonal.
    """
    per_day: dict[date, date] = {}
    ordered = sorted(
        (e for e in entries if e.field == "forecast_date" and e.new_value is not None),
        key=lambda e: (e.changed_at, e.id or 0),
    )
    for e in ordered:
        per_day[e.changed_at.date()] = date.fromisoformat(e.new_value)
    if not per_day:
        return []

    points: list[tuple[date, date]] = []
    previous: date | None = None
    for report_day in sorted(per_day):
        value = per_day[report_day]
        if previous is not None and value != previous:
            points.append((report_day, previous))
        points.append((report_day, value))
        previous = value

    end = until or today
    last_day = points[-1][0]
    if end > last_day:
        points.append((end, previous))
    return points


def top_delayed(tasks: Iterable[Task], milestones: Iterable[Milestone], n: int) -> list[DelayItem]:
    """SCH-06: open tasks (end variance) and open milestones, most delayed first."""
    items = [
        DelayItem("task", t.id, t.title, task_variance(t).end_d, t.baseline_end, t.forecast_end)
        for t in tasks
        if is_open(t) and task_variance(t).end_d > 0
    ]
    items += [
        DelayItem(
            "milestone", m.id, m.name, milestone_variance(m), m.baseline_date, m.forecast_date
        )
        for m in milestones
        if m.status is MilestoneStatus.OPEN and m.archived_at is None and milestone_variance(m) > 0
    ]
    items.sort(key=lambda i: (-i.variance_d, i.forecast, i.kind, i.id))
    return items[: max(n, 0)]


def _strongly_connected(nodes: list[int], edges: dict[int, list[int]]) -> list[list[int]]:
    """Tarjan's algorithm, iterative (no recursion limit on long chains)."""
    index: dict[int, int] = {}
    low: dict[int, int] = {}
    on_stack: set[int] = set()
    stack: list[int] = []
    result: list[list[int]] = []
    counter = 0

    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, i = work.pop()
            if i == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            neighbours = edges.get(node, [])
            if i < len(neighbours):
                work.append((node, i + 1))
                nxt = neighbours[i]
                if nxt not in index:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                result.append(component)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return result
