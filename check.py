#!/usr/bin/env python3
"""NYRR volunteer-slot watcher.

Scrapes the NYRR volunteer listing and every volunteer race page linked from
it, and notifies when a 9+1-eligible role flips to available.

www.nyrr.org renders client-side and sits behind Queue-it, so a real browser
engine is required. (events.nyrr.org used to serve the same data as plain
HTML, but most of its event ids now 301 back to www, so it is no longer used.)

State lives in state.json and is committed back by the GitHub Actions
workflow, so notifications fire only on transitions.

Env vars:
  NTFY_TOPIC          ntfy.sh topic for push notifications
  EMAIL_TO            Gmail address to notify (also the SMTP username)
  GMAIL_APP_PASSWORD  Gmail app password
  ONLY_NINE_PLUS_ONE  default "true" — only alert on 9+1-tagged roles
  EXCLUDE_TAGS        default "medical" — role tags that never alert
"""

import json
import os
import re
import smtplib
import sys
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

LISTING_URL = "https://www.nyrr.org/get-involved-volunteer-opportunities"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
ONLY_NINE_PLUS_ONE = os.environ.get("ONLY_NINE_PLUS_ONE", "true").lower() != "false"

# Roles nobody can act on without extra credentials. Comma-separated override.
EXCLUDE_TAGS = tuple(
    t.strip() for t in os.environ.get("EXCLUDE_TAGS", "medical").split(",") if t.strip()
)

EMAIL_TO = os.environ.get("EMAIL_TO", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

MAX_SCRAPE_FAILURES_BEFORE_ALERT = 8

# Anchored on data-* attributes, not the build-hashed CSS class names, which
# change on every NYRR frontend deploy.
RACE_PAGE_RE = re.compile(
    r'href="(?:https://www\.nyrr\.org)?(/races-and-events/[^"?#]*?-volunteers)[^"]*"'
)
ROLE_SPLIT_RE = re.compile(r'<article[^>]*data-registration-option-id="')
STATUS_RE = re.compile(r'data-event-status="([^"]+)"')
ROLE_NAME_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
TAG_RE = re.compile(r"<li>\s*<span[^>]*>(.*?)</span>\s*</li>", re.S)
EVENT_NAME_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
STRIP_TAGS_RE = re.compile(r"<[^>]+>")

NINE_PLUS_ONE_TAG = "9+1"
AVAILABLE = "available"


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}")


# ----------------------------------------------------------------- parsing


def _text(html: str) -> str:
    return " ".join(STRIP_TAGS_RE.sub(" ", html).split())


def is_available(status: str) -> bool:
    """Only an explicit 'available' counts — unknown statuses never alert."""
    return status == AVAILABLE


def extract_race_page_urls(html: str) -> list[str]:
    """Volunteer race-page URLs from the listing page, absolute and deduped."""
    paths = {m.group(1).rstrip("/") for m in RACE_PAGE_RE.finditer(html)}
    return sorted(f"https://www.nyrr.org{path}" for path in paths)


def parse_race_page(html: str) -> dict:
    """Role-level availability from a volunteer race page."""
    name_m = EVENT_NAME_RE.search(html)
    name = _text(name_m.group(1)) if name_m else "Unknown event"

    roles: dict[str, dict] = {}

    for chunk in ROLE_SPLIT_RE.split(html)[1:]:
        status_m = STATUS_RE.search(chunk)
        role_m = ROLE_NAME_RE.search(chunk)

        if not status_m or not role_m:
            continue

        tags = [_text(t) for t in TAG_RE.findall(chunk)]
        roles[_text(role_m.group(1))] = {
            "status": status_m.group(1),
            "nine_one": NINE_PLUS_ONE_TAG in tags,
            "tags": tags,
        }

    return {"name": name, "roles": roles}


# ---------------------------------------------------------------- scraping


def collect_events(load_page) -> dict[str, dict] | None:
    """Parse every volunteer race page on the listing.

    Returns None whenever the result can't be trusted — listing unreachable,
    listing empty (layout changed), or no race page parsed — so the caller
    keeps its previous snapshot instead of reporting every event as gone.
    """
    try:
        listing = load_page(LISTING_URL)
    except Exception as e:
        log(f"listing load failed: {e}")
        return None

    race_urls = extract_race_page_urls(listing)

    if not race_urls:
        log(
            "listing loaded but contained no volunteer race pages — "
            "the page layout may have changed"
        )
        return None

    log(f"listing has {len(race_urls)} volunteer race pages")
    events: dict[str, dict] = {}

    for url in race_urls:
        try:
            parsed = parse_race_page(load_page(url))
        except Exception as e:
            log(f"failed to load {url}: {e}")
            continue

        if not parsed["roles"]:
            log(f"no registration options on {url} — skipping")
            continue

        events[url] = parsed

    if not events:
        log("no race page could be read — keeping previous snapshot")
        return None

    return events


def scrape_events() -> dict[str, dict] | None:
    """collect_events against a real headless browser."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log(f"playwright unavailable: {e}")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            page = browser.new_page(user_agent=UA)

            def load(url):
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_selector("main", timeout=30_000)
                return page.content()

            return collect_events(load)
        finally:
            browser.close()


# ---------------------------------------------------------------- alerting


def diff_alerts(
    previous: dict,
    current: dict,
    only_nine_plus_one: bool = True,
    exclude_tags: tuple[str, ...] = EXCLUDE_TAGS,
) -> list[str]:
    """Alert lines for roles that just became available.

    Only transitions count: a role already available last run is not news.
    """
    alerts: list[str] = []

    for url, parsed in sorted(current.items()):
        prev_roles = previous.get(url, {}).get("roles", {})

        for role, info in sorted(parsed["roles"].items()):
            if only_nine_plus_one and not info["nine_one"]:
                continue

            if any(tag in exclude_tags for tag in info.get("tags", [])):
                continue

            if not is_available(info["status"]):
                continue

            if is_available(prev_roles.get(role, {}).get("status", "")):
                continue

            alerts.append(f"{parsed['name']}: {role} — {url}")

    return alerts


def notify(title: str, message: str, priority: str = "high") -> None:
    if not NTFY_TOPIC:
        log(f"NTFY_TOPIC not set — would have notified: {title} / {message}")
        return

    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": priority,
            "Tags": "running",
            "Click": LISTING_URL,
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        log(f"ntfy notified ({resp.status}): {title}")


def send_email(subject: str, body: str) -> None:
    if not EMAIL_TO or not GMAIL_APP_PASSWORD:
        log("email not configured")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_TO
    msg["To"] = EMAIL_TO
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_TO, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)

        log(f"email sent: {subject}")
    except Exception as e:
        log(f"email failed: {e}")


# -------------------------------------------------------------------- main


def main() -> int:
    state = {"events": {}, "scrape_failures": 0}

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    events = scrape_events()

    if events is None:
        state["scrape_failures"] = state.get("scrape_failures", 0) + 1
        log(f"scrape failed (consecutive: {state['scrape_failures']})")

        if state["scrape_failures"] == MAX_SCRAPE_FAILURES_BEFORE_ALERT:
            title = "NYRR watcher: scraping degraded"
            body = (
                "The NYRR volunteer listing hasn't been readable for a while. "
                "New openings may be missed."
            )
            notify(title, body, priority="default")
            send_email(title, body)
    else:
        state["scrape_failures"] = 0
        alerts = diff_alerts(state.get("events", {}), events, ONLY_NINE_PLUS_ONE)

        if alerts:
            title = f"NYRR volunteer slot{'s' if len(alerts) > 1 else ''} open!"
            body = "\n".join(alerts)

            notify(title, body)
            send_email(title, body)
        else:
            log("no newly available roles")

        state["events"] = events
        log(f"{len(events)} events tracked")

    state["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
