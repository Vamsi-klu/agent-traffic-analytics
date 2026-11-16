"""cake.js cuts a tab's session by PostHog's time rules: agentcake/static/src/session.js run on its own in Node
(tests/browser/session_logic.mjs, with stand-ins for the parts it talks to and a clock the cases set).

Activity within 30 minutes keeps the session; once the tab is idle, replay events are dropped while signal records
and inactive input still go; the first activity after the idle time sends what is buffered under the old id, keeps a
new id, pushes a session record saying why (with the page's source fields) and takes a full snapshot; a session that
lasted 24 hours ends at its next activity however busy; a page view begins a new session when the stored clock ran out
(the page count starts over), keeps a session whose clock is recent, and keeps an older cake.js's id that has no
clock; a path record is activity; forget() removes the id and its clock.

Skipped without node.
"""
import json
import os
import shutil
import subprocess
import unittest

from . import harness

DRIVER = os.path.join(harness.HERE, "session_logic.mjs")


class SessionLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("needs node")
        out = subprocess.run(["node", DRIVER], check=True, capture_output=True, text=True, timeout=60).stdout
        cls.cases = json.loads(out)

    def test_activity_within_the_idle_time_keeps_the_session(self):
        case = self.cases["idle_drop"]
        self.assertEqual((case["first"], case["stored"], case["kept"], case["log"]), ("id1", "id1", True, []))

    def test_once_idle_replay_events_are_dropped_and_signals_still_go(self):
        case = self.cases["idle_drop"]
        self.assertFalse(case["replayWhileIdle"])
        self.assertTrue(case["signalWhileIdle"])
        self.assertTrue(case["keyWhileIdle"])  # a key press is no activity (PostHog counts the input it makes)

    def test_activity_after_the_idle_time_begins_a_new_session_on_the_page(self):
        case = self.cases["idle_rotation"]
        self.assertEqual(case["stored"], "id2")
        steps = [entry[0] for entry in case["log"]]
        self.assertEqual(steps, ["flush", "transport", "push", "snapshot"])
        record = case["log"][2][2]
        self.assertEqual((record["ty"], record["why"], record["rd"]), ("session", "idle", "www.example.org"))
        self.assertEqual(case["clock"]["s"], case["clock"]["l"])

    def test_a_session_ends_after_twenty_four_hours(self):
        pushed = [entry[2] for entry in self.cases["max_rotation"]["log"] if entry[0] == "push"]
        self.assertEqual([record["why"] for record in pushed], ["max"])

    def test_a_page_view_after_the_idle_time_begins_a_new_session(self):
        case = self.cases["begin"]
        self.assertEqual(case["expired"], "id1")
        self.assertNotIn("expiredPageNumber", case)  # the page count was removed with the old session

    def test_a_page_view_within_the_idle_time_and_an_older_scripts_id_are_kept(self):
        case = self.cases["begin"]
        self.assertEqual((case["fresh"], case["older"]), ("old", "old"))
        self.assertLess(case["olderClock"]["s"], case["olderClock"]["l"])

    def test_a_new_path_is_activity_and_forget_removes_the_id_and_clock(self):
        case = self.cases["path_and_forget"]
        self.assertEqual(case["afterPath"], "id2")
        self.assertNotIn("session", case)
        self.assertNotIn("clock", case)


if __name__ == "__main__":
    unittest.main()
