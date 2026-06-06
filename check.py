#!/usr/bin/env python3
"""NYRR volunteer-slot watcher.

Discovers volunteer events from the NYRR listing page (headless browser,
since www.nyrr.org blocks plain HTTP clients), then checks each event page
on events.nyrr.org (plain HTTP, server-rendered HTML) for role-level
availability. Notifies via ntfy.sh when a 9+1-eligible role opens up.

State is persisted in state.json and committed back to the repo by the
GitHub Actions workflow, so notifications fire only on *transitions*
(filled -> available, or a brand-new event appearing).

Env vars:
  NTFY_TOPIC          required for notifications (ntfy.sh topic name)
  ONLY_NINE_PLUS_ONE  default "true" — only alert on 9+1-tagged roles
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

LISTING_URL = "https://www.nyrr.org/getinvolved/volunteeropportunities"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
ONLY_NINE_PLUS_ONE = os.environ.get("ONLY_NINE_PLUS_ONE", "true").lower() != "false"
MAX_DISCOVERY_FAILURES_BEFORE_ALERT = 8  # ~2h of failures at 15-min cadence


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}")


# ---------------------------------------------------------------- discovery

def discover_event_urls() -> list[str] | None:
    """Scrape the listing page with headless Chromium. Returns None on failure."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)
            page.goto(LISTING_URL, wait_until="networkidle", timeout=60_000)
            hrefs = page.eval_on_selector_all(
                'a[href*="events.nyrr.org"]',
                "els => els.map(e => e.href)",
            )
            browser.close()
        urls = sorted({h.split("?")[0].rstrip("/") for h in hrefs if "events.nyrr.org" in h})
        return urls or None
    except Exception as e:  # noqa: BLE001
        log(f"discovery failed: {e}")
        return None


# ----------------------------------------------------------------- parsing

def fetch_event_page(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_event(html: str) -> dict:
    """Return {"name": str, "roles": {role: {"status": "AVL"|"SOL", "nine_one": bool}}}."""
    name_m = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    name = name_m.group(1).strip() if name_m else "Unknown event"

    roles: dict[str, dict] = {}
    # Each role lives in a div whose class starts with "category-box" and which
    # carries data-filterable-status="AVL" (available) or "SOL" (all spots filled).
    chunks = re.split(r'class="category-box', html)[1:]
    for chunk in chunks:
        status_m = re.search(r'data-filterable-status="(\w+)"', chunk[:400])
        role_m = re.search(r'class="category-name[^"]*"[^>]*>([^<]+)<', chunk)
        if not status_m or not role_m:
            continue
        role = role_m.group(1).strip()
        nine_one = re.search(r">\s*9\+1\s*<", chunk) is not None
        roles[role] = {"status": status_m.group(1), "nine_one": nine_one}
    return {"name": name, "roles": roles}


# ------------------------------------------------------------- notification

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
        log(f"notified ({resp.status}): {title}")


# -------------------------------------------------------------------- main

def main() -> int:
    state = {"events": {}, "discovery_failures": 0}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    urls = discover_event_urls()
    if urls is None:
        state["discovery_failures"] = state.get("discovery_failures", 0) + 1
        urls = sorted(state["events"].keys())  # fall back to known events
        log(f"using {len(urls)} known event URLs from state "
            f"(consecutive discovery failures: {state['discovery_failures']})")
        if state["discovery_failures"] == MAX_DISCOVERY_FAILURES_BEFORE_ALERT:
            notify(
                "NYRR watcher: discovery degraded",
                "The listing page hasn't been reachable for a while; watching "
                "previously known events only. New events may be missed.",
                priority="default",
            )
    else:
        state["discovery_failures"] = 0
        log(f"discovered {len(urls)} event URLs")

    alerts: list[str] = []
    new_events: dict[str, dict] = {}

    for url in urls:
        try:
            parsed = parse_event(fetch_event_page(url))
        except Exception as e:  # noqa: BLE001
            log(f"failed to fetch/parse {url}: {e} — keeping previous snapshot")
            if url in state["events"]:
                new_events[url] = state["events"][url]
            continue

        new_events[url] = parsed
        prev = state["events"].get(url)
        for role, info in parsed["roles"].items():
            if ONLY_NINE_PLUS_ONE and not info["nine_one"]:
                continue
            if info["status"] != "AVL":
                continue
            prev_status = (prev or {}).get("roles", {}).get(role, {}).get("status")
            if prev_status != "AVL":  # newly available (or brand-new event/role)
                credit = "9+1" if info["nine_one"] else "no +1"
                alerts.append(f"{parsed['name']}: {role} ({credit}) — {url}")

    if alerts:
        notify(
            f"NYRR volunteer slot{'s' if len(alerts) > 1 else ''} open!",
            "\n".join(alerts),
        )
    else:
        log("no newly available roles")

    state["events"] = new_events
    state["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    log(f"state saved: {len(new_events)} events tracked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
