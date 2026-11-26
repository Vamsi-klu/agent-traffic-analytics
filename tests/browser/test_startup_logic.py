"""cake.js starting on a page: agentcake/static/src/cake_main.js with its real session and transport parts, run in Node
(tests/browser/startup_logic.mjs: every other part a stand-in, a clock that moves on while the page starts).

The page view's session is chosen once, at the moment the page begins, and its page record is made at that moment: a
tab's session that reaches its idle time while the page starts stays the page's session, and nothing is cut or thrown
before the batches have a header to carry the session. A session that went quiet long before begins anew; one that
went quiet a minute ago goes on. The batches carry the browser's session and the tab's id with it.

Skipped without node.
"""
import json
import os
import shutil
import subprocess
import unittest

from . import harness

DRIVER = os.path.join(harness.HERE, "startup_logic.mjs")


class Startup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("needs node")
        out = subprocess.run(["node", DRIVER], check=True, capture_output=True, text=True, timeout=60).stdout
        cls.cases = json.loads(out)

    def test_a_session_reaching_its_idle_time_as_the_page_begins_is_the_pages_session(self):
        case = self.cases["edge_of_idle"]
        self.assertIsNone(case["threw"])
        self.assertEqual((case["stored"], [batch["s"] for batch in case["batches"]]), ("old", ["old"]))

    def test_the_page_record_is_made_at_the_moment_its_session_was_chosen(self):
        for name, case in self.cases.items():
            self.assertEqual(case["batches"][0]["x"][0], ["page", 0], name)

    def test_a_recent_session_goes_on_and_an_old_one_begins_anew(self):
        recent, expired = self.cases["recent"], self.cases["expired"]
        self.assertEqual((recent["stored"], recent["batches"][0]["s"]), ("old", "old"))
        self.assertNotEqual(expired["stored"], "old")
        self.assertEqual(expired["batches"][0]["s"], expired["stored"])
        self.assertEqual([kind for kind, _ in expired["batches"][0]["x"]], ["page"], "no session record: a new page")

    def test_the_batches_carry_the_browsers_session_and_the_tabs_id(self):
        recent, expired = self.cases["recent"], self.cases["expired"]
        self.assertEqual((recent["batches"][0]["bs"], recent["batches"][0]["w"]), ("bs-old", "w-old"))
        self.assertNotEqual(expired["batches"][0]["bs"], "bs-old", "the browser's session ended too: a new one")
        self.assertEqual(expired["batches"][0]["w"], expired["window"], "with a new tab id, as posthog-js's window id")


if __name__ == "__main__":
    unittest.main()
