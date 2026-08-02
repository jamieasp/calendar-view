#!/usr/bin/env python3
"""Sync calendar-view events into a Google Calendar.

By default this runs as a dry-run. To write events, provide OAuth authorized-user
credentials with Calendar write scope and pass --apply.

Credentials lookup order:
  1. --token-json PATH
  2. GOOGLE_CALENDAR_TOKEN_JSON environment variable
  3. ../.secrets/google-calendar-token.json relative to this repo

The script uses private extended properties to identify events created from this
calendar, so title/date changes update the existing Google Calendar event instead
of creating duplicates.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
INDEX = ROOT / "index.html"
DEFAULT_TOKEN = WORKSPACE / ".secrets" / "google-calendar-token.json"
SOURCE_URL = "https://jamieasp.github.io/calendar-view/"
SOURCE_NAME = "calendar-view"
DEFAULT_CALENDAR_ID = "primary"

SYNC_STATUSES = {"trip", "upcoming", "completed", "interesting", "cancelled"}
SKIP_STATUSES = {"injury"}


@dataclass(frozen=True)
class SourceEvent:
    source_id: str
    start: str
    end: str | None
    status: str
    title: str
    list_title: str
    meta: str
    race: bool

    @property
    def google_summary(self) -> str:
        title = self.list_title or self.title
        if self.race and not title.startswith("🏁"):
            title = f"🏁 {title}"
        if self.status == "interesting" and not title.startswith("✨"):
            title = f"✨ {title}"
        if self.status == "cancelled" and not title.lower().startswith("cancelled:"):
            title = f"Cancelled: {title}"
        return title

    @property
    def google_end_exclusive(self) -> str:
        end = self.end or self.start
        return (date.fromisoformat(end) + timedelta(days=1)).isoformat()

    @property
    def description(self) -> str:
        bits = []
        if self.meta:
            bits.append(self.meta)
        bits.append(f"Status: {self.status}")
        bits.append(f"Source: {SOURCE_URL}")
        return "\n".join(bits)

    def body(self) -> dict[str, Any]:
        return {
            "summary": self.google_summary,
            "description": self.description,
            "start": {"date": self.start},
            "end": {"date": self.google_end_exclusive},
            "transparency": "transparent",
            "source": {"title": "Jamie’s Race Calendar", "url": SOURCE_URL},
            "extendedProperties": {
                "private": {
                    "openclawSource": SOURCE_NAME,
                    "openclawSourceId": self.source_id,
                    "openclawStatus": self.status,
                }
            },
        }


def js_string(value: str) -> str:
    return ast.literal_eval(f'"{value}"')


def extract_events() -> list[SourceEvent]:
    text = INDEX.read_text(encoding="utf-8")
    match = re.search(r"const events = \[(.*?)\n\s*\];", text, re.S)
    if not match:
        raise RuntimeError("Could not find const events block in index.html")
    block = match.group(1)
    objects = re.findall(r"\{(.*?)\}", block, re.S)
    events: list[SourceEvent] = []
    for obj in objects:
        raw: dict[str, str] = {}
        for key in ["syncId", "start", "end", "status", "title", "listTitle", "meta"]:
            m = re.search(rf'{key}:\s*"((?:[^"\\]|\\.)*)"', obj)
            if m:
                raw[key] = js_string(m.group(1))
        if "start" not in raw or "title" not in raw:
            continue
        status = raw.get("status", "")
        if status in SKIP_STATUSES or status not in SYNC_STATUSES:
            continue
        source_id = raw.get("syncId")
        if not source_id:
            raw_id = "|".join([raw.get("start", ""), raw.get("end", ""), raw.get("title", "")])
            source_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:20]
        events.append(
            SourceEvent(
                source_id=source_id,
                start=raw["start"],
                end=raw.get("end"),
                status=status,
                title=raw["title"],
                list_title=raw.get("listTitle", raw["title"]),
                meta=raw.get("meta", ""),
                race="race: true" in obj,
            )
        )
    return events


def load_credentials(path: Path) -> Credentials:
    if not path.exists():
        raise FileNotFoundError(
            f"No Google Calendar OAuth token found at {path}. "
            "Create one with scope https://www.googleapis.com/auth/calendar.events"
        )
    creds = Credentials.from_authorized_user_file(
        str(path), scopes=["https://www.googleapis.com/auth/calendar.events"]
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("Google Calendar credentials are not valid and could not be refreshed")
    return creds


def find_existing(service: Any, calendar_id: str, source_id: str) -> dict[str, Any] | None:
    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            privateExtendedProperty=[
                f"openclawSource={SOURCE_NAME}",
                f"openclawSourceId={source_id}",
            ],
            showDeleted=False,
            singleEvents=True,
            maxResults=10,
        )
        .execute()
    )
    items = result.get("items", [])
    return items[0] if items else None


def sync(events: list[SourceEvent], *, token_path: Path, calendar_id: str, apply: bool) -> int:
    if not apply:
        for event in events:
            print(f"DRY-RUN upsert {event.start}–{event.end or event.start}: {event.google_summary}")
        print(f"DRY-RUN: {len(events)} event(s) would be synced to Google Calendar '{calendar_id}'.")
        return 0

    creds = load_credentials(token_path)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    inserted = updated = 0
    for event in events:
        body = event.body()
        existing = find_existing(service, calendar_id, event.source_id)
        try:
            if existing:
                service.events().patch(calendarId=calendar_id, eventId=existing["id"], body=body).execute()
                updated += 1
                print(f"UPDATED {event.start}: {event.google_summary}")
            else:
                service.events().insert(calendarId=calendar_id, body=body).execute()
                inserted += 1
                print(f"INSERTED {event.start}: {event.google_summary}")
        except HttpError as exc:
            print(f"ERROR syncing {event.start} {event.google_summary}: {exc}", file=sys.stderr)
            raise
    print(f"Synced {len(events)} event(s): {inserted} inserted, {updated} updated.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes to Google Calendar")
    parser.add_argument("--calendar-id", default=DEFAULT_CALENDAR_ID, help="Google calendar id, default: primary")
    parser.add_argument("--token-json", type=Path, default=None, help="authorized-user OAuth token JSON")
    args = parser.parse_args()

    token_path = args.token_json or Path(__import__("os").environ.get("GOOGLE_CALENDAR_TOKEN_JSON", DEFAULT_TOKEN))
    events = extract_events()
    return sync(events, token_path=token_path, calendar_id=args.calendar_id, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
