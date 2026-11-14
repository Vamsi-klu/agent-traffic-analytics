"""The registration card end to end: register_walk.mjs in Chromium against a real AgentCake.

AgentCake runs here on a free port of this computer, with the built local pages (web/dist) and register_url pointing at
a stand-in receiver (tests/receiver.py). Pressing "Register & Continue" makes one request, which carries exactly the
text "See what's sent" showed, and AgentCake keeps it; with nothing listening at register_url the card says so,
Continue opens the pages, nothing is kept, and the card asks again when the page is opened again.

Skipped, saying what is missing, without node, playwright-core (harness.py) or the built pages (cd web && npm run
build). CAKE_EVIDENCE_DIR keeps the screenshots (the walk's report, which holds the e-mail address typed in, is read
from its output and not written down).
"""
import json
import os
import subprocess
import tempfile
import threading
import unittest

from . import harness
from api_client import Client  # noqa: E402  (tests/ is on the path when the suite runs)
from receiver import Receiver, closed_url, free_port  # noqa: E402
from agentcake import config, server  # noqa: E402

WALK = os.path.join(harness.HERE, "register_walk.mjs")
PAGES = os.path.join(harness.ROOT, "web", "dist")
SETTINGS = ("CAKE_HOME", "CAKE_PORT", "CAKE_WEB_DIR")


def restore(saved):
    """Put these environment variables back as they were ({name: value, None for unset})."""
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class RegisterWalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing() + ([] if os.path.isfile(os.path.join(PAGES, "index.html"))
                                       else ["the built local pages (cd web && npm run build)"])
        if lacking:
            raise unittest.SkipTest("the registration walk needs " + "; ".join(lacking))

    def setUp(self):
        self.addCleanup(restore, {name: os.environ.get(name) for name in SETTINGS})
        os.environ.update(CAKE_HOME=tempfile.mkdtemp(prefix="cake-test-"), CAKE_PORT=str(free_port()), CAKE_WEB_DIR=PAGES)
        config.save_user(site_key="ck_register_walk", disk_min_free_mb=0)

    def walk(self, scenario, register_url):
        config.save_user(register_url=register_url)
        local, _ = server.make_listeners(config.load_cfg())
        threading.Thread(target=local.serve_forever, daemon=True).start()
        out = harness.out_dir("register-walk")
        try:
            walked = subprocess.run(["node", WALK, "--base", config.base_url(), "--out", out, "--scenario", scenario],
                                    check=True, capture_output=True, text=True, timeout=harness.DRIVE_TIMEOUT_S,
                                    env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
        finally:
            local.shutdown()
            local.server_close()
        return json.loads(walked.stdout.strip().splitlines()[-1])

    def test_the_press_sends_once_exactly_what_was_shown(self):
        receiver = Receiver()
        self.addCleanup(receiver.close)
        report = self.walk("sent", receiver.url)
        self.assertEqual([r["body"] for r in receiver.requests], [report["shown"].encode("utf-8")])
        self.assertEqual(json.loads(report["shown"])["company"], "Bäckerei Ünal")
        state = Client().get("/api/register").body
        self.assertEqual((state["registered"], state["sent"]["body"]), (True, report["shown"]))

    def test_when_nothing_answers_it_says_so_lets_in_keeps_nothing_and_asks_again(self):
        url = closed_url()
        report = self.walk("not-sent", url)
        self.assertIn(url.split("/")[2], report["alert"])
        self.assertEqual(report["steps"], ["card", "not-sent", "pages", "asked-again"])
        self.assertFalse(Client().get("/api/register").body["registered"])


if __name__ == "__main__":
    unittest.main()
