# calendar-view

A simple whole-year 2026 calendar view, published with GitHub Pages.

## Google Calendar sync

`scripts/sync_google_calendar.py` syncs the events embedded in `index.html` into Jamie's primary Google Calendar using the Google Calendar API.

- Default mode is safe dry-run: `python scripts/sync_google_calendar.py`
- Real write mode: `python scripts/sync_google_calendar.py --apply --calendar-id primary`
- OAuth token path defaults to `../.secrets/google-calendar-token.json` relative to this repo.
- Required OAuth scope: `https://www.googleapis.com/auth/calendar.events`
- Each source event has a stable `syncId`; the script stores that as a private extended property so later edits update the existing Google event instead of duplicating it.
- Events with status `injury` are intentionally not synced; trips, races, interesting, completed, and cancelled events are synced.
