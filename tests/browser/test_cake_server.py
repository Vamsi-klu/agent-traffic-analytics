"""cake.js served by cake itself: a site's pages to database.

One `agentcake serve` runs in a scratch CAKE_HOME on a free port. /cake.js must be the built script with this
installation's site key and the page script's settings filled in. Then Chromium buys a shirt the direct way (drive.mjs)
in the test site's shop (tests/site, on a port of its own, its pages loading cake.js from cake as a dev server's do),
and cake's database must hold one visit from the site with every page's meta event and full snapshot among its replay
events, each page view's under its own id (rrweb chunks, streams.read_events): the collector takes cake.js's
gzipped batches.

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
from collections import Counter
from unittest import mock

from . import harness, uploads

from agentcake import store, streams  # noqa: E402  (collector.py, which harness imports, puts the repository on sys.path)
from cake_server import POLL_S, free_port  # noqa: E402  (tests/, the folder unittest discover starts in, is on sys.path)
sys.path.insert(0, os.path.join(harness.ROOT, "tests", "site"))
import site_server  # noqa: E402

AGENTCAKE = [sys.executable, "-I", os.path.join(harness.ROOT, "agentcake", "__main__.py")]
SITE_KEY = "ck_browser_test"
START_TIMEOUT_S = 10


class CakeServesCakeJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.home = tempfile.mkdtemp(prefix="agentcake-browser-")
        cls.env = dict(os.environ, CAKE_HOME=cls.home)
        cls.env.pop("CAKE_PORT", None)
        port = free_port()
        cls.base = f"http://127.0.0.1:{port}"
        # replays are stored whatever this computer's free disk (disk_min_free_mb, is tested in test_space); the
        # monthly update is off, so a test never goes online (agentcake/updates.py)
        for key, value in (("port", port), ("site_key", SITE_KEY), ("disk_min_free_mb", 0), ("lists_auto_update", "false")):
            subprocess.run(AGENTCAKE + ["config", "set", key, str(value)], env=cls.env, check=True, capture_output=True)
        cls.server = subprocess.Popen(AGENTCAKE + ["serve"], env=cls.env, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        try:
            cls.wait_until_up()
            with urllib.request.urlopen(cls.base + "/cake.js", timeout=5) as response:
                cls.script = response.read().decode()
            cls.site = site_server.serve(cls.base, SITE_KEY)
            cls.logs = harness.drive(cls.site.url, harness.out_dir("cake-server"), "direct:1")
            time.sleep(1)  # the last uploads are written by the server's threads
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "site", None):
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

    def test_cake_js_is_the_built_script_with_the_site_key(self):
        self.assertIn("AgentCake page script (cake.js)", self.script)
        # with the page script's two settings as a fresh installation has them: hook_dom off, nothing hidden
        self.assertIn('/*cake:runtime*/{"hide_selectors":"","hook_dom":false,"site_key":"%s"}/*cake:runtime*/' % SITE_KEY,
                      self.script)

    def test_the_visit_is_stored_with_every_page_snapshot(self):
        pages = len(self.logs["direct-1"]["pages"])
        sessions = self.query("SELECT id FROM sessions WHERE origin='site'")
        self.assertEqual(len(sessions), 1)
        with mock.patch.dict(os.environ, {"CAKE_HOME": self.home}):
            con = store.db()
            try:
                events = [(json.loads(text)["type"], page) for _, _, text, page in
                          streams.read_events(con, sessions[0][0], ["rrweb"], with_page=True)]
            finally:
                con.close()
        per_page = Counter(page for kind, page in events if kind in (uploads.RRWEB_META, uploads.RRWEB_FULL_SNAPSHOT))
        self.assertEqual(len(per_page), pages, "one page view id per page")
        self.assertEqual(set(per_page.values()), {2}, "each page view: its meta event and its full snapshot")


if __name__ == "__main__":
    unittest.main()
