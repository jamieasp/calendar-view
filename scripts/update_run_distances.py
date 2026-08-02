#!/usr/bin/env python3
"""Refresh Jamie's 2026 calendar running distances from local Suunto data.

- Pulls fresh 2026 Suunto workouts with bin/suuntool.
- Treats Suunto activityIds 1 and 22 as running, based on Jamie's existing run data.
- Aggregates total running distance and ascent per UTC calendar day.
- Rounds daily km and elevation gain to integers.
- Updates the `const runDistances = {...};` and `const runElevations = {...};` blocks in index.html.
- Monthly totals and the cumulative chart are intentionally derived client-side
  from `runDistances`, so refreshing this one block updates the calendar cells,
  month-title totals, and chart together.
- Upcoming race countdowns are client-side date calculations, so they stay fresh
  on page load; race-looking future events are detected from the event list.
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
HEALTH_DATA = REPO / "health-data.json"
DATA_DIR = WORKSPACE / "data" / "suunto"
FRESH_NDJSON = DATA_DIR / "workouts_2026_fresh.ndjson"
RUN_ACTIVITY_IDS = {1, 22}
YEAR = 2026
HEALTH_START = "2025-11-01"
TRT_DATE = dt.date(2026, 3, 9)
VIRUS_DATE = dt.date(2026, 3, 19)
TURMERIC_DATE = dt.date(2026, 5, 27)
MANUAL_LONG_DATES = {
    dt.date(2025, 11, 8),
    dt.date(2025, 11, 12),
    dt.date(2025, 11, 15),
    dt.date(2025, 11, 28),
}


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


def load_running_totals() -> tuple[dict[str, int], dict[str, int]]:
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
    daily_ascent_m: dict[str, float] = collections.defaultdict(float)
    for workout in seen.values():
        if workout.get("activityId") not in RUN_ACTIVITY_IDS:
            continue
        distance_m = workout.get("totalDistance") or 0
        if distance_m <= 0:
            continue
        start_ms = workout.get("startTime")
        if not start_ms:
            continue
        day = dt.datetime.fromtimestamp(start_ms / 1000, dt.UTC).date().isoformat()
        daily_km[day] += distance_m / 1000
        daily_ascent_m[day] += workout.get("totalAscent") or 0

    distances = {day: math.floor(km + 0.5) for day, km in sorted(daily_km.items()) if math.floor(km + 0.5) > 0}
    elevations = {day: math.floor(meters + 0.5) for day, meters in sorted(daily_ascent_m.items()) if math.floor(meters + 0.5) > 0}
    return distances, elevations



def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{proc.stderr or proc.stdout}")
    return json.loads(proc.stdout)


def load_metric_points(payload: dict, value_key: str, start: dt.date) -> list[tuple[dt.date, float]]:
    points: list[tuple[dt.date, float]] = []
    for point in payload.get("dataPoints", []):
        try:
            day = dt.date.fromisoformat(point["date"])
            value = float(point[value_key])
        except Exception:
            continue
        if day >= start:
            points.append((day, value))
    return sorted(points)


def build_ratio_points(rhr_points: list[tuple[dt.date, float]], hrv_points: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float]]:
    rhr_by_date = dict(rhr_points)
    hrv_by_date = dict(hrv_points)
    out: list[tuple[dt.date, float]] = []
    for day in sorted(set(rhr_by_date) & set(hrv_by_date)):
        hrv = hrv_by_date[day]
        if hrv > 0:
            out.append((day, rhr_by_date[day] / hrv))
    return out


def parse_long_run_dates(exercise_payload: dict, start: dt.date) -> list[dt.date]:
    dates = set(MANUAL_LONG_DATES)
    run_segments_by_date: dict[dt.date, list[tuple[dt.datetime, dt.datetime, float]]] = {}
    for point in exercise_payload.get("dataPoints", []):
        typ = point.get("exerciseType")
        name = (point.get("displayName") or "").lower()
        if typ not in {"RUNNING", "TRAIL_RUN"} and "run" not in name:
            continue
        try:
            km = float(point.get("metricsSummary", {}).get("distanceMillimeters") or 0) / 1e6
            start_time = dt.datetime.fromisoformat(point["start"].replace("Z", "+00:00"))
            end_time = dt.datetime.fromisoformat(point["end"].replace("Z", "+00:00"))
        except Exception:
            continue
        if km <= 0:
            continue
        run_segments_by_date.setdefault(start_time.date(), []).append((start_time, end_time, km))

    for day, segments in run_segments_by_date.items():
        total_km = 0.0
        current_cluster: list[tuple[dt.datetime, dt.datetime, float]] = []
        current_end: dt.datetime | None = None
        for segment in sorted(segments, key=lambda item: item[0]):
            seg_start, seg_end, _ = segment
            if current_end is not None and seg_start < current_end:
                current_cluster.append(segment)
                current_end = max(current_end, seg_end)
            else:
                if current_cluster:
                    total_km += max(km for _, _, km in current_cluster)
                current_cluster = [segment]
                current_end = seg_end
        if current_cluster:
            total_km += max(km for _, _, km in current_cluster)
        if total_km >= 8:
            dates.add(day)
    return sorted(day for day in dates if day >= start)


def latest_percentile(values: list[float], *, lower_is_better: bool) -> float:
    if len(values) <= 1:
        return 100.0
    latest = values[-1]
    sorted_values = sorted(values)
    tie_positions = [i for i, value in enumerate(sorted_values) if value == latest]
    if not tie_positions:
        return 100.0
    avg_index = sum(tie_positions) / len(tie_positions)
    if lower_is_better:
        return 100.0 * (len(values) - 1 - avg_index) / (len(values) - 1)
    return 100.0 * avg_index / (len(values) - 1)


def serialize_points(points: list[tuple[dt.date, float]]) -> list[dict[str, float | str]]:
    return [{"date": day.isoformat(), "value": round(value, 4)} for day, value in points]


def build_health_chart_data() -> dict:
    start = dt.date.fromisoformat(HEALTH_START)
    rhr_payload = run_json(["ghealth", "data", "daily-resting-heart-rate", "list", "--from", HEALTH_START, "--limit", "500"])
    hrv_payload = run_json(["ghealth", "data", "daily-heart-rate-variability", "list", "--from", HEALTH_START, "--limit", "500"])
    exercise_payload = run_json(["ghealth", "data", "exercise", "list", "--from", HEALTH_START, "--limit", "1200"])
    rhr_points = load_metric_points(rhr_payload, "beatsPerMinute", start)
    hrv_points = load_metric_points(hrv_payload, "averageHeartRateVariabilityMilliseconds", start)
    ratio_points = build_ratio_points(rhr_points, hrv_points)
    long_dates = parse_long_run_dates(exercise_payload, start)

    def panel(kind: str, title: str, ylabel: str, unit: str, points: list[tuple[dt.date, float]], lower_is_better: bool) -> dict:
        values = [value for _, value in points]
        return {
            "kind": kind,
            "title": title,
            "ylabel": ylabel,
            "unit": unit,
            "lowerIsBetter": lower_is_better,
            "points": serialize_points(points),
            "latestPercentile": round(latest_percentile(values, lower_is_better=lower_is_better), 1) if values else None,
        }

    return {
        "generatedAt": dt.datetime.now(dt.UTC).isoformat(),
        "start": HEALTH_START,
        "eventMarkers": [
            {"date": VIRUS_DATE.isoformat(), "label": "Virus", "color": "#333333", "yoff": 0.86},
        ],
        "longRunDates": [day.isoformat() for day in long_dates],
        "panels": [
            panel("RHR", "Resting Heart Rate", "RHR (bpm)", "bpm", rhr_points, True),
            panel("HRV", "Heart Rate Variability", "HRV (ms)", "ms", hrv_points, False),
            panel("RHR/HRV", "RHR / HRV", "RHR / HRV (bpm/ms)", "", ratio_points, True),
        ],
    }


def write_health_chart_data() -> bool:
    data = build_health_chart_data()
    serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if HEALTH_DATA.exists() and HEALTH_DATA.read_text() == serialized:
        return False
    HEALTH_DATA.write_text(serialized)
    return True

def update_index(run_distances: dict[str, int], run_elevations: dict[str, int]) -> bool:
    html = INDEX.read_text()
    required_dynamic_consumers = [
        "function monthRunTotal(totalYear, month)",
        "function renderDistanceChart()",
        "cumulativeSeries(runDistances, year)",
        "cumulativeSeries(runElevations, year)",
        "function renderElevationChart()",
        "function renderUpcomingRaces()",
        "function isRaceEvent(event)",
        "renderUpcomingRaces();",
        "function renderHealthCharts()",
        "health-data.json",
        "const stretchStreaks =",
        "stretch-streak",
    ]
    missing = [needle for needle in required_dynamic_consumers if needle not in html]
    if missing:
        raise RuntimeError(
            "index.html no longer derives monthly totals/chart from runDistances; "
            f"missing: {', '.join(missing)}"
        )

    replacement = "    const runDistances = " + json.dumps(run_distances, indent=6).replace("\n", "\n    ") + ";"
    pattern = re.compile(r"    const runDistances = \{.*?\};", re.S)
    updated, count = pattern.subn(replacement, html, count=1)
    if count != 1:
        raise RuntimeError("Could not find exactly one runDistances block in index.html")

    elevation_replacement = "    const runElevations = " + json.dumps(run_elevations, indent=6).replace("\n", "\n    ") + ";"
    elevation_pattern = re.compile(r"    const runElevations = \{.*?\};", re.S)
    updated, elevation_count = elevation_pattern.subn(elevation_replacement, updated, count=1)
    if elevation_count != 1:
        raise RuntimeError("Could not find exactly one runElevations block in index.html")
    if updated == html:
        return False
    INDEX.write_text(updated)
    return True


def update_stretch_streaks() -> bool:
    before = INDEX.read_text()
    script = REPO / "scripts" / "update_stretch_streaks.py"
    run([str(script)], cwd=REPO)
    return INDEX.read_text() != before


def git_commit_push() -> None:
    run(["git", "add", "index.html", "health-data.json", "scripts/update_run_distances.py", "scripts/update_stretch_streaks.py", "sw.js"], cwd=REPO)
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
    distances, elevations = load_running_totals()
    changed = update_index(distances, elevations)
    stretch_changed = update_stretch_streaks()
    health_changed = write_health_chart_data()
    print(f"Loaded {len(distances)} run-distance days and {len(elevations)} elevation days for {YEAR}.")
    print(f"Stretch streak badges {'updated' if stretch_changed else 'already up to date'}.")
    print(f"Health chart data {'updated' if health_changed else 'already up to date'}.")
    if changed or stretch_changed or health_changed:
        git_commit_push()
    else:
        print("index.html already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
