"""What cake.js records for the dashboard's web analytics, in Chromium (tests/browser/web_metrics.mjs) against the
stand-in collector.

A visit from another site whose page hands over its whole address: the page record keeps only that site's domain,
and neither the referring page's path nor its query string reaches any upload; the landing page's campaign
parameters are kept, and its ad click id by name (the page's address, which every upload carries, still holds its
value, as PRIVACY.md says). A random visitor id is kept in localStorage and sent with every batch; another profile
gets another one. A single-page app's new path is a page view (a path record), a new query string alone is none.
Within the idle time a second page load stays in the session; a page load after the session's clock ran out begins a
new session for the same visitor. window.cake.stop() deletes the session id, its clock and the visitor id. With
data-consent="required", nothing is stored before the visitor agrees, and nothing is left after they refuse.

Skipped, saying what is missing, without node, playwright-core or Chromium (see harness.py).
"""
import json
import os
import subprocess
import unittest

from . import collector, harness, uploads

DRIVER = os.path.join(harness.HERE, "web_metrics.mjs")
REFERRER_SECRET = "REFERRERSECRET123"  # in the referring page's address (web_metrics.mjs)
CLICK_ID_VALUE = "CLICKIDVALUE999"  # the gclid in the landing page's address (pages/referrer.html)


class WebMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.out = harness.out_dir("web-analytics")
        server = collector.serve(cls.out)
        cls.base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            subprocess.run(["node", DRIVER, "--base", cls.base, "--out", cls.out], check=True,
                           timeout=harness.DRIVE_TIMEOUT_S, env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
        finally:
            server.shutdown()
            server.server_close()
        cls.logs = {}
        for name in ("sources", "profile", "consent"):
            with open(os.path.join(cls.out, f"{name}.json"), encoding="utf-8") as f:
                cls.logs[name] = json.load(f)
        cls.batches = uploads.unique(uploads.load(cls.out))
        with open(os.path.join(cls.out, "collect.ndjson"), encoding="utf-8") as f:
            cls.wire = f.read()

    def session_of(self, step):
        return self.logs["sources"][step]["session"]

    def visitor_of(self, scenario, step):
        stored = self.logs[scenario][step]["visitor"]
        return json.loads(stored)["id"] if stored else None

    def records(self, session, kind):
        return [record for batch in self.batches if batch["s"] == session for record in batch.get("x", [])
                if record["ty"] == kind]

    def test_the_browser_handed_over_the_whole_referring_address(self):
        self.assertIn(REFERRER_SECRET, self.logs["sources"]["referrer"])  # so keeping only the domain is cake.js's

    def test_only_the_referring_domain_is_kept(self):
        page = self.records(self.session_of("landing"), "page")[0]
        self.assertEqual(page["rd"], self.base.replace("http://127.0.0.1", "localhost"))
        self.assertNotIn(REFERRER_SECRET, self.wire)
        self.assertNotIn("referrer.html", self.wire)

    def test_campaign_parameters_are_kept_and_click_ids_by_name(self):
        page = self.records(self.session_of("landing"), "page")[0]
        self.assertEqual(page["utm"], {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "spring"})
        self.assertEqual(page["ck"], ["gclid"])
        self.assertNotIn(CLICK_ID_VALUE, json.dumps(page))
        self.assertIn(CLICK_ID_VALUE, self.wire)  # the page's own address still carries it (PRIVACY.md says so)

    def test_every_batch_carries_the_visitor_id_the_browser_keeps(self):
        visitor = self.visitor_of("sources", "landing")
        sent = {batch.get("vid") for batch in self.batches if batch["s"] == self.session_of("landing")}
        self.assertEqual(sent, {visitor})

    def test_another_profile_is_another_visitor(self):
        self.assertNotEqual(self.visitor_of("profile", "landing"), self.visitor_of("sources", "landing"))

    def test_a_new_path_is_a_page_view_and_a_new_query_string_is_none(self):
        paths = [record["p"] for record in self.records(self.session_of("landing"), "path")]
        self.assertEqual(paths, ["/pages/spa-b", "/pages/plain.html"])

    def test_a_second_page_load_within_the_idle_time_stays_in_the_session(self):
        self.assertEqual(self.session_of("secondPage"), self.session_of("landing"))
        self.assertEqual(len(self.records(self.session_of("landing"), "page")), 2)

    def test_a_page_load_after_the_idle_time_begins_a_new_session_for_the_same_visitor(self):
        self.assertNotEqual(self.session_of("afterIdle"), self.session_of("landing"))
        self.assertEqual(self.visitor_of("sources", "afterIdle"), self.visitor_of("sources", "landing"))
        page = self.records(self.session_of("afterIdle"), "page")[0]
        self.assertEqual(page["n"], 1)  # the page count started over with the session

    def test_stop_deletes_the_session_id_its_clock_and_the_visitor_id(self):
        self.assertEqual(self.logs["sources"]["afterStop"], {"visitor": None, "session": None, "clock": None})

    def test_nothing_is_stored_before_consent_and_nothing_left_after_a_refusal(self):
        log = self.logs["consent"]
        self.assertEqual(log["beforeAccept"], {"visitor": None, "session": None, "clock": None})
        self.assertIsNotNone(log["afterAccept"]["visitor"])
        self.assertEqual(log["afterReject"], {"visitor": None, "session": None, "clock": None})

    def test_no_upload_carries_a_cookie(self):
        self.assertFalse(any(entry["cookie"] for entry in uploads.load(self.out)))


if __name__ == "__main__":
    unittest.main()
