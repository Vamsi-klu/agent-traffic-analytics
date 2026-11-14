"""The server half when a browser shows a page again (case T8, N1, N2): token_revisits.mjs from the suite.

token_revisits.mjs starts its own `agentcake serve` (a scratch CAKE_HOME, a free port, a secret of its own) and walks
the Node middleware's test site (HTML revalidated: no-cache + ETag; and with noStore) and the test site's shop (tests/site): home, a link, the link
home (a 304), reload, back, forward, an SPA route change. Checked on its report: every page view whose navigation entry
had a token is linked to a token of its visit (N1: 100%); a 304 shows the 304's own token; a page shown from the
browser's cache brings its stored token back as reuse, never as replay, and it is kept once; the SPA route stays in
its page view; a token whose first upload is refused goes again until it is taken; a real token with a changed byte
is bad, from another visit replay, past the max age stale (N2).

The suite runs Chromium (CAKE_REVISIT_BROWSERS: e.g. "chromium,chromium-bfcache,webkit,firefox" for all of them). Skipped, saying what is missing, without node or playwright-core
(see harness.py); a browser that is not installed is named in the report and fails the run.
"""
import json
import os
import subprocess
import unittest

from . import harness

REVISITS = os.path.join(harness.HERE, "token_revisits.mjs")
SITES = ["etag", "nostore", "demo"]
BROWSERS = os.environ.get("CAKE_REVISIT_BROWSERS", "chromium").split(",")
STORED = "an earlier response's"


def first_answer(step):
    """What collect answered the first batch of the step's page view that carried its token."""
    return (step.get("answers") or ["no batch"])[0]


class TokenRevisits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        out = harness.out_dir("token-revisits")
        cls.walk = subprocess.run(["node", REVISITS, "--out", out, "--browsers", ",".join(BROWSERS), "--sites", ",".join(SITES)],
                                  capture_output=True, text=True, timeout=harness.DRIVE_TIMEOUT_S,
                                  env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
        report = os.path.join(out, "token-revisits.json")
        if not os.path.exists(report):
            raise AssertionError("token_revisits.mjs wrote no report:\n" + cls.walk.stdout + cls.walk.stderr)
        with open(report, encoding="utf-8") as f:
            cls.report = json.load(f)
        cls.runs = {(r["browser"], r["site"]): r for r in cls.report["runs"]}

    def test_the_run_passes_in_every_browser_asked_for(self):
        self.assertEqual(self.walk.returncode, 0, self.walk.stdout + self.walk.stderr)
        self.assertEqual(self.report["skipped"], {})
        self.assertEqual(sorted(self.runs), sorted((b, s) for b in BROWSERS for s in SITES))

    def test_every_page_view_with_a_token_is_linked_to_its_visit(self):
        for (browser, site), run in self.runs.items():
            with self.subTest(browser=browser, site=site):
                self.assertGreaterEqual(run["n1"]["pages_with_a_token"], 4)
                self.assertEqual(run["n1"]["linked"], run["n1"]["pages_with_a_token"])

    def test_a_304_shows_the_304s_own_token(self):
        for browser in BROWSERS:
            revalidated = [s for s in self.runs[(browser, "etag")]["steps"] if s["served"] and s["served"]["status"] == 304]
            with self.subTest(browser=browser):
                self.assertTrue(revalidated, "following the link home is a 304")
                self.assertEqual({s["token_the_page_sees"] for s in revalidated}, {"this response's"})
                self.assertEqual({first_answer(s) for s in revalidated}, {"ok"})

    def test_a_stored_token_comes_back_as_reuse_and_is_kept_once(self):
        for (browser, site), run in self.runs.items():
            stored = [s for s in run["steps"] if s["token_the_page_sees"] == STORED]
            with self.subTest(browser=browser, site=site):
                self.assertEqual({first_answer(s) for s in stored} - {"reuse"}, set())
                self.assertEqual(run["replay_answers"], 0)
                self.assertEqual(run["reuses_kept"], run["reuse_answers"])
                self.assertEqual(len({row["id"] for row in run["srv_rows"]}), len(run["srv_rows"]))

    @unittest.skipUnless("chromium" in BROWSERS, "Playwright's Chromium (no back-forward cache) is not in this run")
    def test_without_the_back_forward_cache_going_back_shows_the_stored_token(self):
        for site in ("etag", "demo"):
            steps = self.runs[("chromium", site)]["steps"]
            with self.subTest(site=site):
                self.assertEqual([s["token_the_page_sees"] for s in steps if s["seen"]["type"] == "back_forward"], [STORED] * 2)

    def test_an_spa_route_change_stays_in_its_page_view(self):
        for (browser, site), run in self.runs.items():
            with self.subTest(browser=browser, site=site):
                self.assertEqual(run["spa"], {"route": "/spa-route", "batch_seen": True, "same_page_view": True,
                                              "token_sent_again": False})

    def test_a_token_goes_again_until_collect_takes_it(self):
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                taken = self.report["until_taken"][browser]
                self.assertTrue(taken["intercepted"])
                self.assertTrue(taken["taken"], taken["answers"])
                self.assertNotEqual(taken["answers"][0], "ok", "the first upload carrying it was refused")

    def test_a_real_token_changed_replayed_or_too_old_is_refused(self):
        self.assertEqual({check: (r["status"], r["answer"]) for check, r in self.report["n2"].items()},
                         {"changed_byte": (204, "bad"), "another_visit": (204, "replay"), "past_max_age": (204, "stale")})


if __name__ == "__main__":
    unittest.main()
