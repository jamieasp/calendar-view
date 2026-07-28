#!/usr/bin/env python3
"""Refresh Jamie's 2026 calendar running distances from local Suunto data.

- Pulls fresh 2026 Suunto workouts with bin/suuntool.
- Treats Suunto activityId 22 as running, based on Jamie's existing race/run data.
- Aggregates total running distance per UTC calendar day.
- Floors daily km to integers.
- Updates the `const runDistances = {...};` block in index.html.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
SUUNTOOL = WORKSPACE / "bin" / "suuntool"
INDEX = REPO / "index.html"
DATA_DIR = WORKSPACE / "data" / "suunto"
FRESH_NDJSON = DATA_DIR / "workouts_2026_fresh.ndjson"
RUN_ACTIVITY_ID = 22
YEAR = 2026


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, check=True, **kwargs)


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
        # The API sometimes ends a stream with BAD_ENVELOPE after writing usable NDJSON.
        # Keep going if we captured workouts; fail only when the file is empty.
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


def load_running_distances() -> dict[str, int]:
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

    daily_km: dict[str, float] = collections.defaultdict(float)
    for workout in seen.values():
        if workout.get("activityId") != RUN_ACTIVITY_ID:
            continue
        distance_m = workout.get("totalDistance") or 0
        if distance_m <= 0:
            continue
        start_ms = workout.get("startTime")
        if not start_ms:
            continue
        day = dt.datetime.fromtimestamp(start_ms / 1000, dt.UTC).date().isoformat()
        daily_km[day] += distance_m / 1000

    return {day: math.floor(km) for day, km in sorted(daily_km.items()) if math.floor(km) > 0}


def update_index(run_distances: dict[str, int]) -> bool:
    html = INDEX.read_text()
    replacement = "    const runDistances = " + json.dumps(run_distances, indent=6).replace("\n", "\n    ") + ";"
    pattern = re.compile(r"    const runDistances = \{.*?\};", re.S)
    updated, count = pattern.subn(replacement, html, count=1)
    if count != 1:
        raise RuntimeError("Could not find exactly one runDistances block in index.html")
    if updated == html:
        return False
    INDEX.write_text(updated)
    return True


def git_commit_push() -> None:
    run(["git", "add", "index.html"], cwd=REPO)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO)
    if diff.returncode == 0:
        print("No calendar changes to commit.")
        return
    run(["git", "commit", "-m", "Update Suunto run distances"], cwd=REPO)
    run(["git", "push"], cwd=REPO)


def main() -> int:
    if not SUUNTOOL.exists():
        raise FileNotFoundError(f"Missing suuntool at {SUUNTOOL}")
    pull_workouts()
    distances = load_running_distances()
    changed = update_index(distances)
    print(f"Loaded {len(distances)} run-distance days for {YEAR}.")
    if changed:
        git_commit_push()
    else:
        print("index.html already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
