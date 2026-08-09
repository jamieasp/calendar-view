#!/usr/bin/env python3
"""
update_pressup_log.py  –  inject pressup ladder scores into index.html

Usage:
  # Add / update a single score (date defaults to today if omitted):
  python3 update_pressup_log.py --set-score 7 [--date 2026-08-09]

  # Regenerate from the JSON log file only (no new score):
  python3 update_pressup_log.py

The JSON log lives at  <repo>/memory/pressup_log.json
Format: { "2026-08-09": 7, "2026-08-10": 8, ... }  (date → last-complete-set)

The script replaces the   const pressupLog = { ... };   block in index.html.
"""

import argparse
import datetime
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
LOG_FILE  = REPO.parent / "memory" / "pressup_log.json"
INDEX_HTML = REPO / "index.html"


def load_log() -> dict[str, int]:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except json.JSONDecodeError:
            print(f"[pressup] Warning: could not parse {LOG_FILE}", file=sys.stderr)
    return {}


def save_log(log: dict[str, int]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(dict(sorted(log.items())), indent=2) + "\n")


def inject_html(log: dict[str, int]) -> bool:
    html = INDEX_HTML.read_text(encoding="utf-8")
    sorted_log = dict(sorted(log.items()))
    rows = "\n".join(f'          "{k}": {v},' for k, v in sorted_log.items())
    if rows:
        replacement = f"    const pressupLog = {{\n{rows}\n    }};"
    else:
        replacement = "    const pressupLog = {\n    };"

    updated, n = re.subn(
        r"    const pressupLog = \{.*?\};",
        replacement,
        html,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise RuntimeError("Could not find pressupLog block in index.html")
    if updated == html:
        return False
    INDEX_HTML.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Update press-up log in calendar")
    parser.add_argument("--set-score", type=int, metavar="N",
                        help="Record that the last-complete set was N")
    parser.add_argument("--date", type=str, metavar="YYYY-MM-DD",
                        default=None,
                        help="Date for the score (default: today London time)")
    args = parser.parse_args()

    log = load_log()

    if args.set_score is not None:
        if args.date:
            date_str = args.date
        else:
            london = datetime.timezone(datetime.timedelta(hours=1))  # BST; UTC+1 in summer
            date_str = datetime.datetime.now(tz=london).strftime("%Y-%m-%d")

        old = log.get(date_str, 0)
        new_score = max(old, args.set_score)
        if new_score != old:
            log[date_str] = new_score
            save_log(log)
            print(f"[pressup] {date_str}: {old} → {new_score}")
        else:
            print(f"[pressup] {date_str}: score {old} unchanged (submitted {args.set_score})")

    changed = inject_html(log)
    if changed:
        print("[pressup] index.html updated")
    else:
        print("[pressup] index.html already up to date")


if __name__ == "__main__":
    main()
