"""Tests for which role transitions actually produce a notification."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import check  # noqa: E402

URL = "https://www.nyrr.org/races-and-events/2026/nyrr-staten-island-half-volunteers"


def event(status, nine_one=True, tags=("9+1",), role="Bag Check"):
    return {URL: {"name": "SI Half", "roles": {role: {
        "status": status, "nine_one": nine_one, "tags": list(tags)}}}}


class DiffAlerts(unittest.TestCase):
    def test_alerts_when_nine_plus_one_role_opens(self):
        alerts = check.diff_alerts(event("sold-out"), event("available"))

        self.assertEqual(len(alerts), 1)
        self.assertIn("Bag Check", alerts[0])
        self.assertIn(URL, alerts[0])

    def test_does_not_alert_when_role_was_already_available(self):
        self.assertEqual(check.diff_alerts(event("available"), event("available")), [])

    def test_does_not_alert_when_role_stays_sold_out(self):
        self.assertEqual(check.diff_alerts(event("sold-out"), event("sold-out")), [])

    def test_alerts_for_a_brand_new_event_with_an_open_role(self):
        self.assertEqual(len(check.diff_alerts({}, event("available"))), 1)

    def test_skips_non_nine_plus_one_role_by_default(self):
        current = event("available", nine_one=False, tags=("No +1",))

        self.assertEqual(check.diff_alerts({}, current), [])

    def test_includes_non_nine_plus_one_when_filter_is_off(self):
        current = event("available", nine_one=False, tags=("No +1",))

        self.assertEqual(len(check.diff_alerts({}, current, only_nine_plus_one=False)), 1)

    def test_skips_medical_roles_by_default(self):
        """Requires a NYS license — not actionable, so not worth a push."""
        current = event("available", tags=("medical", "9+1"), role="Medical Volunteers")

        self.assertEqual(check.diff_alerts({}, current), [])

    def test_includes_medical_when_not_excluded(self):
        current = event("available", tags=("medical", "9+1"), role="Medical Volunteers")

        self.assertEqual(len(check.diff_alerts({}, current, exclude_tags=())), 1)

    def test_unknown_status_never_alerts(self):
        self.assertEqual(check.diff_alerts(event("sold-out"), event("waitlist")), [])


if __name__ == "__main__":
    unittest.main()
