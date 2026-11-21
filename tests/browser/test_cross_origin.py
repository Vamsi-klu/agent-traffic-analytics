"""The subdomain route in a real browser: the website's pages and AgentCake on two origins (cross_origin.mjs).

cross_origin.mjs runs a scratch `agentcake serve` with the subdomain route's settings, behind a stand-in for Caddy,
and has Chromium visit the website (www.example.localhost) and then another site (shop.elsewhere.localhost) whose pages
carry the line the settings API gives. Checked on its report: the line loads cake.js from public_url, on another
origin than the page; every upload is answered 204, none fails, no batch is sent twice (counted at the front door,
where the batches a page sends as it is left show too), none is left parked in sessionStorage, and the console shows
no CORS error; no preflight reaches the front door. The website's visit is kept as the site's and listed; the other
site's is kept too, as another site's, and left out of the session list.

Skipped, saying what is missing, without node, playwright-core or a Chromium that starts (see harness.py).
"""
import json
import os
import subprocess
import unittest
from urllib.parse import urlsplit

from . import harness

SCRIPT = os.path.join(harness.HERE, "cross_origin.mjs")
ANSWERED = 204
VISITS = ("site", "other")


class CrossOrigin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        out = harness.out_dir("cross-origin")
        cls.done = subprocess.run(["node", SCRIPT, "--out", out], capture_output=True, text=True,
                                 timeout=harness.DRIVE_TIMEOUT_S, env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
        report = os.path.join(out, "cross-origin.json")
        if not os.path.exists(report):
            raise AssertionError("cross_origin.mjs wrote no report:\n" + cls.done.stdout + cls.done.stderr)
        with open(report, encoding="utf-8") as f:
            cls.report = json.load(f)
        cls.visits = {visit["name"]: visit for visit in cls.report["visits"]}

    def test_the_run_ends_cleanly_with_both_visits(self):
        self.assertEqual(self.done.returncode, 0, self.done.stdout + self.done.stderr)
        self.assertEqual(sorted(self.visits), sorted(VISITS))

    def test_the_line_loads_cake_js_from_public_url_on_another_origin_than_the_page(self):
        for name, visit in self.visits.items():
            with self.subTest(visit=name):
                script = urlsplit(visit["script_src"])
                self.assertTrue(script.hostname.startswith("cake."), script.hostname)
                self.assertNotEqual(script.netloc, urlsplit(visit["page"]).netloc)
                self.assertIn(visit["script_src"], self.report["line"])

    def test_every_upload_is_answered_once_and_none_is_left_parked(self):
        for name, visit in self.visits.items():
            with self.subTest(visit=name):
                browser, door = visit["browser"], visit["front_door"]
                self.assertGreater(browser["uploads"], 0)
                self.assertEqual((browser["answered"], browser["other_statuses"], browser["failed"]),
                                 (browser["uploads"], [], []))
                self.assertGreaterEqual(door["batches"], browser["uploads"])
                self.assertEqual((door["copies_of_a_batch_already_sent"], browser["copies_of_a_batch_already_sent"]), (0, 0))
                self.assertEqual(browser["parked_at_the_end"], 0)
                self.assertEqual(browser["console_cors_errors"], [])

    def test_no_preflight(self):
        """cake.js sends text/plain without credentials: a simple request, which a browser sends without asking."""
        for name, visit in self.visits.items():
            with self.subTest(visit=name):
                self.assertNotIn("OPTIONS", visit["front_door"]["by_method"])
                self.assertEqual(visit["browser"]["preflights"], 0)
                self.assertEqual(visit["front_door"]["not_forwarded"], 0)

    def test_the_websites_visit_is_listed_and_another_sites_is_kept_but_left_out(self):
        site, other = self.visits["site"]["agentcake"], self.visits["other"]["agentcake"]
        self.assertEqual((site["session_kept"], site["origin"], site["in_the_session_list"]), (True, "site", True))
        self.assertEqual((other["session_kept"], other["origin"], other["in_the_session_list"]), (True, "other", False))


if __name__ == "__main__":
    unittest.main()
