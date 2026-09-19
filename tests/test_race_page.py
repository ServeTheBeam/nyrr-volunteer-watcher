"""Tests for parsing role availability off a www.nyrr.org race page.

events.nyrr.org is being retired — most of its event ids now 301 back here —
so role status is read from the race page itself.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import check  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
RACE_PAGE = (FIXTURES / "race_page.html").read_text(encoding="utf-8")


class ParseRacePage(unittest.TestCase):
    def test_reads_event_name(self):
        self.assertEqual(
            check.parse_race_page(RACE_PAGE)["name"],
            "NYRR Staten Island Half - Volunteers",
        )

    def test_finds_every_registration_option(self):
        self.assertEqual(len(check.parse_race_page(RACE_PAGE)["roles"]), 9)

    def test_reads_sold_out_status(self):
        roles = check.parse_race_page(RACE_PAGE)["roles"]

        self.assertEqual(roles["Bag Check"]["status"], "sold-out")

    def test_reads_available_status(self):
        roles = check.parse_race_page(RACE_PAGE)["roles"]

        self.assertEqual(
            roles["Medical Volunteers (Must be licensed in NYS)"]["status"], "available"
        )

    def test_tags_nine_plus_one_role(self):
        roles = check.parse_race_page(RACE_PAGE)["roles"]

        self.assertTrue(roles["Bag Check"]["nine_one"])

    def test_does_not_tag_no_plus_one_role(self):
        """'No +1' must not be mistaken for a 9+1 tag."""
        roles = check.parse_race_page(RACE_PAGE)["roles"]

        self.assertFalse(
            roles["Volunteer Leaders and Leaders in Training (NO +1)"]["nine_one"]
        )

    def test_role_can_be_available_and_nine_plus_one(self):
        """The case the whole watcher exists to catch."""
        roles = check.parse_race_page(RACE_PAGE)["roles"]
        medical = roles["Medical Volunteers (Must be licensed in NYS)"]

        self.assertEqual(medical["status"], "available")
        self.assertTrue(medical["nine_one"])

    def test_page_with_no_options_yields_no_roles(self):
        parsed = check.parse_race_page("<html><h1><span>Some Race</span></h1></html>")

        self.assertEqual(parsed["roles"], {})
        self.assertEqual(parsed["name"], "Some Race")

    def test_records_role_tags(self):
        roles = check.parse_race_page(RACE_PAGE)["roles"]

        self.assertEqual(
            roles["Medical Volunteers (Must be licensed in NYS)"]["tags"],
            ["medical", "9+1"],
        )


class IsAvailable(unittest.TestCase):
    def test_available_status_counts_as_open(self):
        self.assertTrue(check.is_available("available"))

    def test_sold_out_does_not(self):
        self.assertFalse(check.is_available("sold-out"))

    def test_unknown_status_does_not(self):
        """Unrecognised statuses must not trigger alerts."""
        self.assertFalse(check.is_available("waitlist"))


if __name__ == "__main__":
    unittest.main()
