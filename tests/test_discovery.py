"""Tests for NYRR listing/race-page parsing, against saved fixtures.

Fixtures were captured 2026-09-18 from the live site. Re-capture them with
tests/refresh_fixtures.py if NYRR changes the page structure.
"""

import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import check  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ExtractRacePageUrls(unittest.TestCase):
    def test_finds_volunteer_race_pages_on_listing(self):
        urls = check.extract_race_page_urls(fixture("listing.html"))

        self.assertIn(
            "https://www.nyrr.org/races-and-events/2026/nyrr-staten-island-half-volunteers",
            urls,
        )

    def test_returns_absolute_urls_only(self):
        urls = check.extract_race_page_urls(fixture("listing.html"))

        self.assertTrue(urls)
        for u in urls:
            self.assertTrue(u.startswith("https://www.nyrr.org/races-and-events/"), u)

    def test_deduplicates(self):
        urls = check.extract_race_page_urls(fixture("listing.html"))

        self.assertEqual(len(urls), len(set(urls)))

    def test_empty_page_yields_no_urls(self):
        self.assertEqual(check.extract_race_page_urls("<html><body></body></html>"), [])


if __name__ == "__main__":
    unittest.main()
