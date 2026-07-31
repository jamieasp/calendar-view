#!/usr/bin/env python3
"""Update calendar-view/index.html with Jamie's stretch streak badges.

Source of truth is memory/stretch-reminders.md. A day counts as stretched when:
- a stretch reminder row for that local date has status=done, or
- an unmatched_done callback references a stretch_YYYYMMDD... reminder id.

The badge rendered in index.html is 🧘N where N is the consecutive stretched-day
chain ending on that date.
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
LOG = WORKSPACE / "memory" / "stretch-reminders.md"
YEAR = 2026

ROW_RE = re.compile(r"^\|\s*(?P<id>[^|]+?)\s*\|\s*(?P<sent_utc>[^|]*?)\s*\|\s*(?P<sent_local>[^|]*?)\s*\|\s*(?P<status>[^|]*?)\s*\|\s*(?P<done_utc>[^|]*?)\s*\|\s*(?P<latency>[^|]*?)\s*\|\s*(?P<text>.*?)\s*\|\s*$")
REMINDER_DATE_RE = re.compile(r"stretch_(\d{8})t?", re.I)


def local_date_from_row(row: dict[str, str]) -> dt.date | None:
    # The reminder id represents the intended stretch day. Prefer it because
    # Done may be tapped after midnight/morning for the previous day.
    for field in ("id", "text"):
        match = REMINDER_DATE_RE.search(row.get(field, ""))
        if match:
            try:
                return dt.datetime.strptime(match.group(1), "%Y%m%d").date()
            except ValueError:
                pass
    sent_local = row.get("sent_local", "").strip()
    if sent_local:
        try:
            return dt.date.fromisoformat(sent_local[:10])
        except ValueError:
            pass
    return None


def stretched_dates() -> set[dt.date]:
    dates: set[dt.date] = set()
    if not LOG.exists():
        return dates
    for raw in LOG.read_text(errors="ignore").splitlines():
        if not raw.startswith("|") or raw.startswith("| ---") or "reminder_id" in raw:
            continue
        match = ROW_RE.match(raw)
        if not match:
            continue
        row = {k: v.strip() for k, v in match.groupdict().items()}
        status = row.get("status", "").lower()
        is_done = status == "done" or (row["id"].startswith("unmatched_done") and "stretch_done" in row.get("text", ""))
        if not is_done:
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
    replacement = "    const stretchStreaks = " + json.dumps(streaks, indent=6).replace("\n", "\n    ") + ";"
    updated, count = re.subn(r"    const stretchStreaks = \{.*?\};", replacement, html, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("Could not find exactly one stretchStreaks block in index.html")
    if updated == html:
        return False
    INDEX.write_text(updated)
    return True


def git_commit_push() -> None:
    subprocess.run(["git", "add", "index.html", "scripts/update_stretch_streaks.py"], cwd=REPO, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO)
    if diff.returncode == 0:
        print("No stretch calendar changes to commit.")
        return
    subprocess.run(["git", "commit", "-m", "Update stretch streak badges"], cwd=REPO, check=True)
    subprocess.run(["git", "push"], cwd=REPO, check=True)


def main() -> int:
    changed = update_index(build_streaks(stretched_dates()))
    if "--commit" in __import__("sys").argv:
        git_commit_push()
    else:
        print("stretch streaks updated" if changed else "stretch streaks already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
