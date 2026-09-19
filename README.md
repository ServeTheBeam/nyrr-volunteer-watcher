# NYRR volunteer-slot watcher

Checks NYRR volunteer opportunities every 15 minutes from GitHub Actions (always-on,
laptop-independent) and sends a push notification to your phone the moment a
**9+1-eligible role** flips from "All Spots Filled" to "Available" — or a new
volunteer event is posted.

Built 2026-06-05. Catches both release patterns: new event postings AND the
cancellation churn that happens 7–10 days before each event (reminder emails →
cancellations → spaces reopen).

## How it works

1. **Listing** — headless Chromium (Playwright) loads
   `nyrr.org/get-involved-volunteer-opportunities` and collects every
   `/races-and-events/<year>/<slug>-volunteers` link.
2. **Availability** — each race page is loaded in the same browser and parsed
   for role-level status. Parsing is anchored on `data-event-status` and
   `data-registration-option-id`, not on NYRR's build-hashed CSS class names.
3. **Diff & notify** — compares against `state.json` (committed back to the
   repo each run) and notifies via [ntfy.sh](https://ntfy.sh) and email only on
   transitions, so no notification spam. The state commits also keep the repo
   "active," which stops GitHub from auto-disabling the scheduled workflow
   after 60 days of inactivity.

A full pass is ~27 page loads and takes well under a minute.

`www.nyrr.org` renders client-side and sits behind Queue-it, so a real browser
engine is required. `events.nyrr.org` used to serve the same data as plain HTML
and an earlier version of this watcher used it, but most of its event ids now
301 back to `www`, so it is no longer used.

## Tests

```bash
python -m unittest discover -s tests
```

Parser tests run against HTML fixtures captured from the live site, so they
catch NYRR layout changes without hitting the network. The workflow runs them
before each check.

## Setup (~10 minutes)

1. **Phone:** install the **ntfy** app (iOS/Android). Subscribe to a topic with an
   unguessable name (topics are public namespaces — the random suffix is the only
   access control). **Chosen topic: `nathan-nyrr-vol-wyaHWzqX`.**
2. **GitHub:** repo already created — `nathankg/nyrr-volunteer-watcher` (public,
   has a LICENSE). Public = unlimited free Actions minutes; this schedule uses
   ~3,000–6,000 min/month, which would exceed the 2,000 free minutes on a
   *private* repo — keep it public, or change the cron to `*/30` / `0 * * * *`.
3. Push this folder's contents to the repo root (`check.py`, `README.md`,
   `.github/workflows/watch.yml`).
4. Add the notify secret `NTFY_TOPIC` (CLI below, or repo **Settings → Secrets and
   variables → Actions → New repository secret**).
5. **Actions tab → NYRR volunteer watch → Run workflow** to test. First run
   notifies for every currently-available 9+1 role (everything is "new" to it)
   and writes `state.json`; later runs only notify on changes.

The repo already has a LICENSE commit, so layer these files *onto* that history
rather than `git init`-ing a fresh one. From inside this folder:

```bash
git init
git remote add origin https://github.com/nathankg/nyrr-volunteer-watcher.git
git fetch origin
git checkout -b main                       # use 'master' if that's the repo default
git branch --set-upstream-to=origin/main main
git add -A
git commit -m "NYRR volunteer watcher"
git pull --rebase origin main              # replays your commit on top of the LICENSE
git push -u origin main

gh secret set NTFY_TOPIC --body "nathan-nyrr-vol-wyaHWzqX" \
  --repo nathankg/nyrr-volunteer-watcher
```

(If `git pull --rebase` flags a conflict on README.md, keep this version:
`git checkout --theirs README.md && git add README.md && git rebase --continue`.)

## Tuning

- `ONLY_NINE_PLUS_ONE` (workflow env): set `"false"` to alert on *all* role
  openings, not just 9+1-tagged ones.
- `EXCLUDE_TAGS` (workflow env): comma-separated role tags that never alert.
  Defaults to `medical` — those roles require a NYS medical license.
- Cron cadence: in `watch.yml`. GitHub cron is best-effort and runs can lag
  well behind schedule. Scheduled workflows in *forked* repos are throttled
  especially hard — this repo saw ~6-9 runs/day against a `*/15` cron while
  the upstream non-fork hit ~12 minutes.

## Known limitations

- **Member+ advance windows:** the watcher sees the *anonymous* view of each
  page. If a slot is visible only to logged-in Member+ accounts during the
  advance window, the watcher may only catch it at general opening.
- Registration itself goes through `register.nyrr.org` with reCAPTCHA — the
  watcher only notifies; the click is on you, so speed still matters.
- NYRR's own listing contains dead links (a 404 body with no registration
  options). Those pages are skipped and logged.
- If NYRR changes the race-page markup, the tests fail before the watcher
  silently stops finding anything. Re-capture the fixtures in `tests/fixtures/`
  and update the parser.
