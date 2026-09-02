#!/usr/bin/env python3
"""Publish the TrainingPeaks plan for the static web app.

The GitHub Pages site is static. Historic plan activities are retained, while
the rolling live window is replaced with the previous three days plus the next
56 days from TrainingPeaks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
TP_SOURCE = Path("/home/exedev/.openclaw/third-party/trainingpeaks-mcp/src")


def format_duration(hours: float | None) -> str | None:
    if hours is None:
        return None
    minutes = round(hours * 60)
    if minutes < 60:
        return f"{minutes} min"
    whole_hours, remainder = divmod(minutes, 60)
    return f"{whole_hours}h" if remainder == 0 else f"{whole_hours}h {remainder}m"


async def fetch_plan(start: date, end: date) -> list[dict[str, object]]:
    sys.path.insert(0, str(TP_SOURCE))
    from tp_mcp.tools.workouts import tp_get_workouts

    result = await tp_get_workouts(start.isoformat(), end.isoformat(), "planned")
    if result.get("isError"):
        raise RuntimeError(result.get("message", "TrainingPeaks request failed"))
    return [
        {
            "id": workout["id"],
            "date": workout["date"],
            "title": workout["title"],
            "sport": workout["sport"],
            "duration": format_duration(workout.get("duration_planned")),
            "tss": workout.get("tss_planned"),
            "optional": "optional" in (workout.get("title") or "").lower(),
        }
        for workout in result["workouts"]
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", type=date.fromisoformat, help="YYYY-MM-DD; useful for testing")
    args = parser.parse_args()
    today = args.today or datetime.now(timezone.utc).date()
    start, end = today - timedelta(days=3), today + timedelta(days=56)
    workouts = asyncio.run(fetch_plan(start, end))
    payload = {
        "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "workouts": workouts,
    }
    output = REPO / "trainingpeaks-plan.json"
    if output.exists():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
            historic = [
                workout for workout in existing.get("workouts", [])
                if isinstance(workout, dict) and workout.get("date", "") < start.isoformat()
            ]
            payload["workouts"] = historic + workouts
        except (json.JSONDecodeError, OSError):
            pass
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['workouts'])} TrainingPeaks workouts; refreshed {start} to {end}")


if __name__ == "__main__":
    main()
