# NYRR volunteer-slot watcher

Checks NYRR volunteer opportunities every 15 minutes from GitHub Actions (always-on,
laptop-independent) and sends a push notification to your phone the moment a
**9+1-eligible role** flips from "All Spots Filled" to "Available" — or a new
volunteer event is posted.

Built 2026-06-05. Catches both release patterns: new event postings AND the
cancellation churn that happens 7–10 days before each event (reminder emails →
cancellations → spaces reopen).

## How it works

1. **Discovery** — headless Chromium (Playwright) loads
   `nyrr.org/getinvolved/volunteeropportunities` and collects every
   `events.nyrr.org/<slug>` link. (The www listing blocks plain HTTP clients;
   a real browser engine is needed for this one page.)
2. **Availability** — each event page is plain server-rendered HTML; a simple
   GET reads role-level status (`AVL` / `SOL`) and whether the role carries the
   9+1 tag. Verified against the live Citizens Queens 10K page.
3. **Diff & notify** — compares against `state.json` (committed back to the repo
   each run), and POSTs to [ntfy.sh](https://ntfy.sh) only on transitions, so no
   notification spam. The state commits also keep the repo "active," which stops
   GitHub from auto-disabling the scheduled workflow after 60 days of inactivity.

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
- Cron cadence: in `watch.yml`. GitHub cron is best-effort — runs can lag
  3–10 min behind schedule at busy times of day.

## Known limitations

- **Member+ advance windows:** the watcher sees the *anonymous* view of each
  event page. If a slot is visible/registerable only to logged-in Member+
  accounts during the advance window, the watcher may only catch it at general
  opening. (Unverified either way — watch what happens with the next release.)
- Registration itself goes through `register.nyrr.org` with reCAPTCHA — the
  watcher only notifies; the click is on you, so speed still matters.
- If NYRR redesigns the event-page HTML, the parser regexes in `check.py` will
  need updating. The "discovery degraded" notification fires if the listing
  page becomes unreachable for ~2 hours.
