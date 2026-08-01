#!/usr/bin/env python3
"""Update calendar-view/index.html with Jamie's strength/abs workout streak badges.

Sources of truth:
- memory/abs-workouts.md for manual abs/core completions.
- local/fresh Suunto workout data for strength-training sessions.

A day counts when either source has a completed session on that UTC date.

The badge rendered in index.html is 💪N in the bottom-right of the day cell,
where N is the consecutive strength/abs-workout-day chain ending on that date.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
INDEX = REPO / "index.html"
LOG = WORKSPACE / "memory" / "abs-workouts.md"
SUUNTOOL = WORKSPACE / "bin" / "suuntool"
DATA_DIR = WORKSPACE / "data" / "suunto"
FRESH_NDJSON = DATA_DIR / "workouts_2026_fresh.ndjson"
YEAR = 2026
# Suunto activityId 23 is GYM, the activity currently used for strength training.
SUUNTO_STRENGTH_ACTIVITY_IDS = {23}

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


def pull_workouts() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FRESH_NDJSON.open("w") as out:
        result = subprocess.run([
            str(SUUNTOOL),
            "workouts",
            "list",
            "--since",
            f"{YEAR}-01-01",
            "--stream",
            "--format",
            "json",
        ], stdout=out, cwd=WORKSPACE, text=True)
    if result.returncode != 0:
        if not FRESH_NDJSON.exists() or FRESH_NDJSON.stat().st_size == 0:
            raise subprocess.CalledProcessError(result.returncode, result.args)
        print(f"suuntool exited {result.returncode}; using captured NDJSON plus local cache.")


def iter_workouts_from_file(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    if path.suffix == ".ndjson":
        for raw in path.read_text(errors="ignore").splitlines():
            if not raw.strip():
                continue
            try:
                workout = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(workout, dict):
                yield workout
        return

    try:
        data = json.loads(path.read_text(errors="ignore"))
    except json.JSONDecodeError:
        return
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        for workout in data["items"]:
            if isinstance(workout, dict):
                yield workout
    elif isinstance(data, dict) and "activityId" in data:
        yield data
    elif isinstance(data, list):
        for workout in data:
            if isinstance(workout, dict):
                yield workout


def suunto_strength_dates() -> set[dt.date]:
    dates: set[dt.date] = set()
    seen: dict[str, dict] = {}
    sources = [
        FRESH_NDJSON,
        DATA_DIR / "workouts_since_2025-06-18.ndjson",
        DATA_DIR / "workouts_all.ndjson",
        DATA_DIR / "pages" / "workouts_offset_0.json",
    ]
    for source in sources:
        for workout in iter_workouts_from_file(source) or []:
            key = workout.get("key")
            if key:
                seen[key] = workout

    for workout in seen.values():
        if workout.get("activityId") not in SUUNTO_STRENGTH_ACTIVITY_IDS:
            continue
        start_ms = workout.get("startTime")
        if not start_ms:
            continue
        day = dt.datetime.fromtimestamp(start_ms / 1000, dt.UTC).date()
        if day.year == YEAR:
            dates.add(day)
    return dates


def manual_abs_dates() -> set[dt.date]:
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


def workout_dates() -> set[dt.date]:
    return manual_abs_dates() | suunto_strength_dates()


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
    if "--no-pull" not in __import__("sys").argv:
        pull_workouts()
    changed = update_index(build_streaks(workout_dates()))
    if "--commit" in __import__("sys").argv:
        git_commit_push()
    else:
        print("abs streaks updated" if changed else "abs streaks already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
