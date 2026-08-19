# ClawjCal — Jamie’s 2026 calendar web app

ClawjCal is a responsive, installable whole-year calendar and training dashboard published with GitHub Pages:

**https://jamieasp.github.io/calendar-view/**

It is a static web app: the main interface and event data live in `index.html`, with health data and encrypted saved-tweet data loaded from adjacent JSON files. No server-side application is required.

## Main navigation

The fixed bottom navigation jumps between five areas and updates as the page is scrolled:

- **Races** — upcoming and considered races, countdowns, race metadata, registration links, watched-status labels, and destination/trip context.
- **Calendar** — a Monday-first calendar beginning in January 2026. It shows the current day prominently, multi-day event spans, trips, races, interesting ideas, completed/cancelled items, daily Suunto run distance, and training streak badges.
- **Charts** — health, running, elevation, consistency, and sleep visualisations.
- **Train** — timed workout blocks, abs, stretches, and press-up training.
- **Fartlek** — a guided interval session with spoken prompts.

On smaller screens the app is optimised for one-handed use; on larger screens the content remains centred and readable.

## Header controls

- **Bird icon** — opens the encrypted Saved tweets library.
- **Copy icon** — copies the current calendar URL to the clipboard.
- **Refresh icon** — performs a hard refresh by clearing service-worker registrations/caches before reloading.

## Calendar and event model

Events are embedded in the `events` array in `index.html`. Each event has a stable `syncId`, start date, optional end date, status, display titles, metadata, and optional URL. Statuses drive the visual treatment and include trips, races, upcoming items, interesting/considered items, completed items, cancelled items, and injuries.

Calendar behaviour includes:

- Current-year calendar rendering with future months and an expandable earlier-history view.
- Optional 2027 continuation.
- Monday-first weeks and event spans across days/weeks.
- Clickable event links where a URL is available.
- Daily Suunto run-distance labels.
- **🧘 stretch badges** from the stretch log; the streak number appears on the latest day of a contiguous streak.
- **💪 strength/abs badges** combining manual strength/abs entries with Suunto gym sessions; the same latest-day numbering convention is used.
- A separate press-up score badge when a completed press-up session has been logged.

## Races

The race panels are generated from calendar events marked as races. They show:

- Upcoming race countdowns.
- Considered-race entries and registration links.
- Distance, elevation, location, date, and other event metadata.
- Last-checked/watched labels where present.
- Automatic race-title styling, with explicit `race: false` available for trail-run ideas that are not races.

## Charts and health dashboard

The Charts area contains SVG-based visualisations and year filters:

- Resting heart rate, HRV, body fat, weight, and other health panels from `health-data.json`.
- Latest-value labels and percentiles where supplied by the health dataset.
- Cumulative running distance through the year.
- Cumulative elevation gain.
- Daily running-distance histogram with All/2024/2025/2026 filters.
- Daily elevation-gain histogram with the same year filters.
- GitHub-style daily running-distance heatmap.
- GitHub-style daily elevation-gain heatmap.
- Stretch-consistency heatmap.
- Bedtime heatmap, where darker cells represent later bedtimes.

Charts are drawn in-browser and remain usable without a charting framework.

## Training tools

The Train area contains the current workout library and interactive timers:

- Warm-up and strength blocks with exercise descriptions, sets, reps, sides, and rest guidance.
- Stretch block including calf stretch, 90/90/deer stretch, hamstring stretch, runner’s lunge, deep squat, windshield wipers, sleeping pigeon, supine figure four, cobra flow, and cossack squat.
- Abs/core circuit with timed work and rest intervals.
- Reusable interval timers generated from `data-seconds` and `data-rest-seconds` attributes.
- Spoken timer cues designed to keep the session usable while moving; the implementation includes Android timer/speech handling to reduce background-timer problems.
- Press-up ladder: start/pause/reset controls, rep progression, rest timing, last-completed-set scoring, and local history.
- Fartlek session: guided running intervals with start/reset controls, spoken phase prompts, and current/next interval display.

Press-up history is stored locally in the browser (`localStorage`); it is not uploaded.

## Encrypted Saved tweets library

The Saved tweets overlay contains Jamie’s intent-organised bookmark library rather than memory files.

### Unlocking

- Enter the passphrase in the overlay.
- The browser fetches `notes-encrypted.json` and decrypts it locally.
- Once unlocked, the password panel disappears and the page shows a Lock button.
- Locking clears the in-session passphrase/data and restores the password form.
- A session-only decrypted-key/passphrase cache can allow reopening during the current browser session.

### Content and presentation

- The encrypted payload contains only `Saved tweets by intent.md`.
- Category guide chips link to sections in the same page and show per-category counts.
- Categories include Buy / try, Go / experience, HealthTech, Relationships, Work behaviours, Life behaviours, Mental models, Quick watch, Watch / listen later, Personal operating system experiments, Taste / craft references, Share / discuss, News / worldview, Humour, and Needs clarification.
- Tweet cards show author, formatted timestamp, body, notes, and an **Open tweet** link.
- Raw URLs are removed from beneath tweet bodies while the primary tweet link remains tappable.
- Saved image/media URLs are rendered inline as lazy-loaded thumbnails, with each image still linking to its source.
- The saved-tweets header is a full-width opaque yellow navigation bar and tweet-card headers scroll normally rather than sticking.

### Encryption

`scripts/encrypt_notes.py` is run from the workspace root and writes `calendar-view/notes-encrypted.json` using:

- AES-256-GCM encryption.
- PBKDF2-HMAC-SHA256 key derivation with a random salt and 100,000 iterations.
- A random per-build IV.
- `NOTES_PASSPHRASE` read from `.secrets/notes.env`.

The passphrase and plaintext bookmark source are not committed to the GitHub Pages repository. `MEMORY.md` and `memory/*` are deliberately excluded from the encrypted app payload.

## Progressive Web App and offline behaviour

The app includes:

- `manifest.webmanifest` with install metadata and icons.
- Standard, maskable, Apple-touch, and favicon assets.
- `sw.js` service worker for installation caching and network-first loading with cached fallback.
- A refresh control that clears old service-worker registrations/caches when a deployment is not appearing because of browser caching.

The encrypted notes file is fetched separately and is not part of the static service-worker asset list.

## Data and maintenance scripts

Run commands from the repository root unless noted otherwise.

### Google Calendar sync

`scripts/sync_google_calendar.py` syncs events embedded in `index.html` to Jamie’s primary Google Calendar.

```bash
python scripts/sync_google_calendar.py                 # safe dry-run
python scripts/sync_google_calendar.py --apply --calendar-id primary
```

- OAuth token default: `../.secrets/google-calendar-token.json` relative to the repository.
- Required scope: `https://www.googleapis.com/auth/calendar.events`.
- `syncId` is stored as a private extended property so edits update existing events rather than creating duplicates.
- Injury events are intentionally excluded; trips, races, interesting, completed, and cancelled events are eligible for sync.

### Live-data refreshes

- `scripts/update_run_distances.py` refreshes embedded daily Suunto running distances.
- `scripts/update_stretch_streaks.py` rebuilds stretch streaks from `../memory/stretch-reminders.md`.
- `scripts/update_abs_streaks.py` combines `../memory/abs-workouts.md` with Suunto gym sessions to rebuild strength/abs streaks. Use `--no-pull` to rely on locally available workout data.
- `scripts/update_pressup_log.py` maintains press-up completion data.
- `scripts/authorize_google_calendar.py` handles Google Calendar OAuth setup.
- `health-data.json` is the chart dataset consumed by the health panels.

Example streak refresh:

```bash
python scripts/update_stretch_streaks.py
python scripts/update_abs_streaks.py --no-pull
```

### Encrypted notes refresh

From `/home/exedev/.openclaw/workspace`:

```bash
python3 scripts/encrypt_notes.py
```

Then commit the regenerated `calendar-view/notes-encrypted.json` together with any source/UI changes.

## Local development

Serve the directory over HTTP so the service worker, manifest, JSON fetches, and clipboard behaviour work normally:

```bash
cd calendar-view
python3 -m http.server 8080
```

Open `http://localhost:8080/`. Avoid opening `index.html` directly with `file://`; browser security rules prevent several app features from working correctly.

Before committing frontend changes, perform at least:

```bash
node --check /tmp/relevant-script.js
```

For full UI verification, load the app in a browser, check the five navigation tabs, test the refresh control, and unlock the Saved tweets overlay on a mobile-sized viewport.

## Deployment

The `main` branch is published through GitHub Pages. The normal deployment workflow is:

```bash
git add index.html README.md health-data.json notes-encrypted.json
git commit -m "Describe the change"
git push origin main
```

GitHub Pages then serves the updated app at:

https://jamieasp.github.io/calendar-view/
