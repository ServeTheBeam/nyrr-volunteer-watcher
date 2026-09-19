"""Tests for collecting every volunteer event in one pass."""

import contextlib
import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import check  # noqa: E402

RACE_URL = "https://www.nyrr.org/races-and-events/2026/nyrr-staten-island-half-volunteers"
OTHER_URL = "https://www.nyrr.org/races-and-events/2026/nyrr-jersey-city-5k-volunteers"

LISTING = f'<a href="/races-and-events/2026/nyrr-staten-island-half-volunteers">SI</a>'
LISTING_TWO = LISTING + '<a href="/races-and-events/2026/nyrr-jersey-city-5k-volunteers">JC</a>'

RACE_HTML = (
    "<h1><span>SI Half</span></h1>"
    '<article data-registration-option-id="1">'
    '<span data-event-status="available"></span>'
    "<h3><span>Bag Check</span></h3>"
    "<ul><li><span>9+1</span></li></ul>"
    "</article>"
)


def loader(pages):
    def load(url):
        if url not in pages:
            raise RuntimeError(f"unexpected url {url}")
        page = pages[url]
        if isinstance(page, Exception):
            raise page
        return page

    return load


def quietly(fn):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()


class CollectEvents(unittest.TestCase):
    def test_returns_parsed_events_keyed_by_race_url(self):
        load = loader({check.LISTING_URL: LISTING, RACE_URL: RACE_HTML})

        events = quietly(lambda: check.collect_events(load))

        self.assertEqual(list(events), [RACE_URL])
        self.assertTrue(events[RACE_URL]["roles"]["Bag Check"]["nine_one"])

    def test_returns_none_when_listing_has_no_race_pages(self):
        load = loader({check.LISTING_URL: "<html>redesigned</html>"})

        self.assertIsNone(quietly(lambda: check.collect_events(load)))

    def test_returns_none_when_listing_fails_to_load(self):
        load = loader({check.LISTING_URL: RuntimeError("queue-it")})

        self.assertIsNone(quietly(lambda: check.collect_events(load)))

    def test_skips_a_race_page_that_fails_but_keeps_the_rest(self):
        load = loader(
            {
                check.LISTING_URL: LISTING_TWO,
                RACE_URL: RuntimeError("timeout"),
                OTHER_URL: RACE_HTML,
            }
        )

        events = quietly(lambda: check.collect_events(load))

        self.assertEqual(list(events), [OTHER_URL])

    def test_returns_none_when_every_race_page_fails(self):
        """Better to keep the previous snapshot than to report everything gone."""
        load = loader({check.LISTING_URL: LISTING, RACE_URL: RuntimeError("timeout")})

        self.assertIsNone(quietly(lambda: check.collect_events(load)))

    def test_skips_a_page_with_no_registration_options(self):
        """NYRR's listing contains dead links that render a 404 body."""
        load = loader(
            {
                check.LISTING_URL: LISTING_TWO,
                RACE_URL: "<h1><span>Oops!</span></h1>",
                OTHER_URL: RACE_HTML,
            }
        )

        events = quietly(lambda: check.collect_events(load))

        self.assertEqual(list(events), [OTHER_URL])


if __name__ == "__main__":
    unittest.main()
