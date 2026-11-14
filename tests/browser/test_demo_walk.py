"""A site's server half in a real browser (plan step S2.4, N1): tests/browser/demo_walk.mjs, run from the suite.

demo_walk.mjs starts its own `agentcake serve` (a scratch CAKE_HOME, a free port, a secret), walks the test site's
shop (tests/site, signed with that secret) in Chromium at two paces (settle and brisk: six page requests each) and writes demo-walk.json. Every page request
must carry a token that verifies, with the Sec-Fetch values and header names Chrome sent, and every token must be kept
in the srv table for the walk's session: N1, 100%.

Skipped, saying what is missing, without node, playwright-core or Chromium (see harness.py).
"""
import json
import os
import subprocess
import unittest

from . import harness

WALK = os.path.join(harness.HERE, "demo_walk.mjs")
PACES = ["settle", "brisk"]
PAGES = ["/demo", "/demo?q=t-shirt", "/demo/product?id=classic-tee", "/demo/cart", "/demo/checkout", "/demo/done"]


class DemoWalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        out = harness.out_dir("demo-walk")
        cls.walk = subprocess.run(["node", WALK, "--out", out, "--paces", ",".join(PACES)], capture_output=True,
                                  text=True, timeout=harness.DRIVE_TIMEOUT_S,
                                  env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
        report = os.path.join(out, "demo-walk.json")
        if not os.path.exists(report):
            raise AssertionError("demo_walk.mjs wrote no report:\n" + cls.walk.stdout + cls.walk.stderr)
        with open(report, encoding="utf-8") as f:
            cls.report = json.load(f)
        cls.steps = [(w["pace"], s) for w in cls.report["walks"] for s in w["steps"]]

    def test_the_walk_passes(self):
        self.assertEqual(self.walk.returncode, 0, self.walk.stdout + self.walk.stderr)

    def test_each_pace_opens_the_six_pages(self):
        self.assertEqual({w["pace"]: [s["path"] for s in w["steps"]] for w in self.report["walks"]},
                         {pace: PAGES for pace in PACES})

    def test_every_page_has_a_token_that_verifies(self):
        self.assertEqual([(pace, s["path"], s["token_verifies"]) for pace, s in self.steps],
                         [(pace, s["path"], "ok") for pace, s in self.steps])

    def test_every_token_has_the_sec_fetch_values_and_header_names_chrome_sent(self):
        for pace, s in self.steps:
            with self.subTest(pace=pace, page=s["path"]):
                self.assertEqual(s["sec_fetch_in_token"], s["sec_fetch_sent"])
                self.assertEqual(sorted(s["header_names_in_token"]), sorted(s["header_names_sent"]))

    def test_every_page_sees_its_own_token(self):
        self.assertEqual({s["token_the_page_sees"] for _, s in self.steps}, {"this response's"})

    def test_n1_every_token_is_kept_for_its_session(self):
        self.assertEqual({w["pace"]: (w["kept_for_this_session"], w["srv_rows_for_this_session"])
                          for w in self.report["walks"]}, {pace: (len(PAGES), len(PAGES)) for pace in PACES})


if __name__ == "__main__":
    unittest.main()
