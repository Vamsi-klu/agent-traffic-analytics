"""A browser's tabs are one session, from cake.js in real tabs to AgentCake's database.

One `agentcake serve` runs in a scratch CAKE_HOME on a free port, and the test site's shop (tests/site) loads cake.js
from it. In one browser a visitor opens the shop and another of its pages in a second tab and goes back and forth
(visit_tabs.mjs); in another browser, a second visitor opens one tab. The database must then hold two visits named by
their browser session ids (joined_by browser): the first visitor's with both tab sessions, each with its own tab id
(w) and the visit's id as its browser session, the second visitor's with one; and each visit's verdict merged from its
tabs' (visit_verdict.merge).

Skipped, saying what is missing, without node, playwright-core or Chromium (see harness.py).
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from . import harness

from agentcake import visit_verdict  # noqa: E402  (collector.py, which harness imports, puts the repository on sys.path)
from cake_server import POLL_S, free_port  # noqa: E402  (tests/, the folder unittest discover starts in, is on sys.path)
sys.path.insert(0, os.path.join(harness.ROOT, "tests", "site"))
import site_server  # noqa: E402

AGENTCAKE = [sys.executable, "-I", os.path.join(harness.ROOT, "agentcake", "__main__.py")]
DRIVER = os.path.join(harness.HERE, "visit_tabs.mjs")
SITE_KEY = "ck_browser_tabs"
START_TIMEOUT_S = 10
LANDED_S = 1  # the server's threads write the last uploads


class TabsOfOneBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.home = tempfile.mkdtemp(prefix="agentcake-tabs-")
        cls.env = dict(os.environ, CAKE_HOME=cls.home)
        cls.env.pop("CAKE_PORT", None)
        port = free_port()
        cls.base = f"http://127.0.0.1:{port}"
        for key, value in (("port", port), ("site_key", SITE_KEY), ("disk_min_free_mb", 0),
                           ("lists_auto_update", "false")):
            subprocess.run(AGENTCAKE + ["config", "set", key, str(value)], env=cls.env, check=True,
                           capture_output=True)
        cls.server = subprocess.Popen(AGENTCAKE + ["serve"], env=cls.env, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        cls.site = None
        try:
            cls.wait_until_up()
            cls.site = site_server.serve(cls.base, SITE_KEY)
            log = os.path.join(harness.out_dir("visit-tabs"), "visit_tabs.json")
            subprocess.run(["node", DRIVER, "--base", cls.site.url, "--out", log], check=True,
                           timeout=harness.DRIVE_TIMEOUT_S, env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
            with open(log, encoding="utf-8") as f:
                cls.driven = json.load(f)
            time.sleep(LANDED_S)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.site:
            cls.site.shutdown()
            cls.site.server_close()
        cls.server.terminate()
        cls.server.wait(5)
        shutil.rmtree(cls.home, ignore_errors=True)

    @classmethod
    def wait_until_up(cls):
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(cls.base + "/api/health", timeout=1):
                    return
            except OSError:
                time.sleep(POLL_S)
        raise RuntimeError(f"agentcake serve did not answer within {START_TIMEOUT_S} s")

    def query(self, sql, *args):
        con = sqlite3.connect(os.path.join(self.home, "cake.db"))
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def tabs_by_visit(self):
        """{visit id: [(window_id, browser_session), ...]} of the site's tab sessions."""
        found = {}
        for visit, window, named in self.query(
                "SELECT w.visit_id, w.window_id, w.browser_session FROM session_web w JOIN sessions s ON "
                "s.id = w.session_id WHERE s.origin = 'site' ORDER BY s.start_ms"):
            found.setdefault(visit, []).append((window, named))
        return found

    def test_the_tabs_of_one_browser_are_one_visit_and_another_browser_another(self):
        visits = self.tabs_by_visit()
        self.assertEqual(sorted(len(tabs) for tabs in visits.values()), [1, len(self.driven["first"])])
        self.assertEqual({row[0] for row in self.query("SELECT joined_by FROM visits")}, {"browser"})
        for visit, tabs in visits.items():
            self.assertEqual({named for _, named in tabs}, {visit}, "every tab session carried the visit's bs")
        several = next(tabs for tabs in visits.values() if len(tabs) > 1)
        self.assertEqual(len({window for window, _ in several}), len(several), "each tab its own w")

    def test_each_visits_verdict_is_merged_from_its_tabs(self):
        for visit, cls in self.query("SELECT id, verdict_class FROM visits"):
            tabs = self.query("SELECT s.verdict_class, s.verdict FROM sessions s JOIN session_web w ON "
                              "w.session_id = s.id WHERE w.visit_id = ?", visit)
            self.assertEqual(cls, visit_verdict.merge(visit_verdict.tab_class(*tab) for tab in tabs))


if __name__ == "__main__":
    unittest.main()
