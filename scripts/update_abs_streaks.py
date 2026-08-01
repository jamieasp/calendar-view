#!/usr/bin/env python3
"""Update calendar-view/index.html with Jamie's abs/core workout streak badges.

Source of truth is memory/abs-workouts.md. A day counts as abs/core done when
there is a row for that local date with status=done.

The badge rendered in index.html is 💪N in the bottom-right of the day cell,
where N is the consecutive abs-workout-day chain ending on that date.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
INDEX = REPO / "index.html"
LOG = WORKSPACE / "memory" / "abs-workouts.md"
YEAR = 2026

ROW_RE = re.compile(
    r"^\|\s*(?P<id>[^|]+?)\s*\|\s*(?P<workout_utc>[^|]*?)\s*\|\s*"
    r"(?P<workout_local>[^|]*?)\s*\|\s*(?P<status>[^|]*?)\s*\|\s*(?P<notes>.*?)\s*\|\s*$"
)
ABS_DATE_RE = re.compile(r"(?:abs|core)_(\d{8})t?", re.I)


def local_date_from_row(row: dict[str, str]) -> dt.date | None:
    for field in ("id", "notes"):
        match = ABS_DATE_RE.search(row.get(field, ""))
        if match:
            try:
                return dt.datetime.strptime(match.group(1), "%Y%m%d").date()
            except ValueError:
                pass
    workout_local = row.get("workout_local", "").strip()
    if workout_local:
        try:
            return dt.date.fromisoformat(workout_local[:10])
        except ValueError:
            pass
    workout_utc = row.get("workout_utc", "").strip()
    if workout_utc:
        try:
            return dt.date.fromisoformat(workout_utc[:10])
        except ValueError:
            pass
    return None


def abs_dates() -> set[dt.date]:
    dates: set[dt.date] = set()
    if not LOG.exists():
        return dates
    for raw in LOG.read_text(errors="ignore").splitlines():
        if not raw.startswith("|") or raw.startswith("| ---") or "workout_id" in raw:
            continue
        match = ROW_RE.match(raw)
        if not match:
            continue
        row = {k: v.strip() for k, v in match.groupdict().items()}
        if row.get("status", "").lower() != "done":
            continue
        day = local_date_from_row(row)
        if day and day.year == YEAR:
            dates.add(day)
    return dates


def build_streaks(dates: set[dt.date]) -> dict[str, int]:
    streaks: dict[str, int] = {}
    current = 0
    day = dt.date(YEAR, 1, 1)
    end = dt.date(YEAR, 12, 31)
    while day <= end:
        if day in dates:
            current += 1
            streaks[day.isoformat()] = current
        else:
            current = 0
        day += dt.timedelta(days=1)
    return streaks


def update_index(streaks: dict[str, int]) -> bool:
    html = INDEX.read_text()
    replacement = "    const absStreaks = " + json.dumps(streaks, indent=6).replace("\n", "\n    ") + ";"
    updated, count = re.subn(r"    const absStreaks = \{.*?\};", replacement, html, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("Could not find exactly one absStreaks block in index.html")
    if updated == html:
        return False
    INDEX.write_text(updated)
    return True


def git_commit_push() -> None:
    subprocess.run(["git", "add", "index.html", "scripts/update_abs_streaks.py"], cwd=REPO, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO)
    if diff.returncode == 0:
        print("No abs calendar changes to commit.")
        return
    subprocess.run(["git", "commit", "-m", "Update abs workout badges"], cwd=REPO, check=True)
    subprocess.run(["git", "push"], cwd=REPO, check=True)


def main() -> int:
    changed = update_index(build_streaks(abs_dates()))
    if "--commit" in __import__("sys").argv:
        git_commit_push()
    else:
        print("abs streaks updated" if changed else "abs streaks already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
