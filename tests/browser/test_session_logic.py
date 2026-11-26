"""cake.js's session ids: agentcake/static/src/session.js run on its own in Node (tests/browser/session_logic.mjs, with
stand-ins for the parts it talks to, Maps for sessionStorage and localStorage, and a clock the cases set). The same part
in real tabs is tests/browser/test_session_tabs.py.

A tab's session is cut as before: activity within 30 minutes keeps it; once the tab is idle, replay events are dropped
while signal records and inactive input still go; the first activity after the idle time sends what is buffered under
the old ids, keeps new ones, pushes a session record saying why (with the page's source fields) and takes a full
snapshot; a session that lasted 24 hours ends at its next activity however busy; one tab with pages and activity at
random is cut at the same moments, for the same reasons, as cake.js 0.6.1's rule cut it. A page view keeps the tab's
session while it lasts and names the browser's session that is stored, and begins a new one otherwise: after the idle
time (the page count starts over), when it names another browser session, or none (an older cake.js's).

The browser's session: a clock that names another session counts as none; where localStorage takes no writes it is
the page's own; another tab's newer session is taken at the next activity (why "tab", or idle or max when the one the
page had ended by then); reset() begins the next one with a new tab id, the visitor changing between the batches; a new
tab session carries the visitor id and hash another tab stored. The mark that a page holds the tab is set when it
starts, removed when it is left (never another page's) and set again when it comes back; a page that finds a live page's
mark holds a copy and takes a new tab id and session; a prerendered page does not, and marks and writes its ids once
shown.
forget() removes every id and clock.

Skipped without node.
"""
import json
import os
import shutil
import subprocess
import unittest

from . import harness

DRIVER = os.path.join(harness.HERE, "session_logic.mjs")
with open(os.path.join(harness.ROOT, "agentcake", "data", "cakejs.json"), encoding="utf-8") as f:
    KEY = json.load(f)["script"]["storage"]


class SessionLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("needs node")
        out = subprocess.run(["node", DRIVER], check=True, capture_output=True, text=True, timeout=60).stdout
        cls.cases = json.loads(out)

    def test_activity_within_the_idle_time_keeps_the_session(self):
        case = self.cases["idle_drop"]
        self.assertEqual(case["stored"]["tab"][KEY["session"]], case["first"]["s"])
        self.assertEqual((case["kept"], case["log"]), (True, []))

    def test_once_idle_replay_events_are_dropped_and_signals_still_go(self):
        case = self.cases["idle_drop"]
        self.assertFalse(case["replayWhileIdle"])
        self.assertTrue(case["signalWhileIdle"])
        self.assertTrue(case["keyWhileIdle"])  # a key press is no activity (PostHog counts the input it makes)

    def test_activity_after_the_idle_time_begins_a_new_session_on_the_page(self):
        case = self.cases["idle_rotation"]
        steps = [entry[0] for entry in case["log"]]
        self.assertEqual(steps, ["flush", "transport", "push", "snapshot"])
        sent = case["log"][1][1]
        self.assertEqual(sent["s"], case["stored"]["tab"][KEY["session"]])
        self.assertNotEqual(sent["s"], case["first"]["s"])
        record = case["log"][2][2]
        self.assertEqual((record["ty"], record["why"], record["rd"]), ("session", "idle", "www.example.org"))
        clock = json.loads(case["stored"]["tab"][KEY["clock"]])
        self.assertEqual((clock["s"], clock["b"]), (clock["l"], sent["bs"]))

    def test_a_session_ends_after_twenty_four_hours(self):
        self.assertEqual(self.cases["max_rotation"]["whys"], ["max"])

    def test_one_tab_is_cut_where_the_tab_rule_cut_it_before(self):
        case = self.cases["single_tab"]
        self.assertEqual(case["got"], case["expected"])
        kinds = {kind for kind, _ in case["expected"]}
        self.assertEqual(kinds, {"same", "idle", "max", "new"}, "every kind of cut was tried")

    def test_a_page_view_after_the_idle_time_begins_a_new_session(self):
        case = self.cases["begin"]
        self.assertNotEqual(case["expired"]["s"], "old")
        self.assertIsNone(case["expiredPageNumber"])  # the page count was removed with the old session

    def test_a_page_view_within_the_idle_time_keeps_the_session_and_ids(self):
        case = self.cases["begin"]
        self.assertEqual(case["fresh"], {"s": "old", "bs": "bs-old", "w": "w-old"})
        self.assertEqual(case["freshClock"]["b"], "bs-old")

    def test_a_tab_session_of_another_browser_session_or_an_older_script_is_not_continued(self):
        case = self.cases["begin"]
        for name in ("otherBrowser", "olderClock", "older"):
            self.assertNotEqual(case[name]["s"], "old", name)
            self.assertEqual(case[name]["bs"], "bs-old", name)

    def test_a_new_path_is_activity_and_forget_removes_every_id_and_clock(self):
        case = self.cases["path_and_forget"]
        self.assertTrue(case["afterPath"]["tab"][KEY["session"]])
        self.assertEqual(case["afterForget"], {"tab": {}, "browser": {}})

    def test_a_clock_naming_another_session_is_no_clock(self):
        case = self.cases["torn"]
        self.assertEqual((case["ids"]["bs"], case["whys"]), ("bs-new", []))
        self.assertEqual(case["clock"]["b"], "bs-new")  # written again, now its own

    def test_where_localstorage_takes_no_writes_the_session_is_the_pages_own(self):
        case = self.cases["refused"]
        self.assertNotEqual(case["ids"]["bs"], "bs-stale")
        self.assertEqual(case["whys"], ["idle"], "one cut, after 41 minutes: no cut at every activity")
        self.assertNotIn(case["after"][0]["bs"], ("bs-stale", case["ids"]["bs"]))
        self.assertEqual(case["browser"][KEY["browser_session"]], "bs-stale")

    def test_where_localstorage_takes_no_writes_the_tabs_next_page_goes_on_with_its_session(self):
        case = self.cases["refused_pages"]
        self.assertEqual((case["next"]["bs"], case["next"]["s"]), (case["first"]["bs"], case["first"]["s"]))
        self.assertEqual(case["localStorage"], {}, "nothing written where writes are refused")
        self.assertEqual(case["afterForget"], {"tab": {}, "browser": {}}, "forget() removes the tab's own copy too")

    def test_a_browser_session_another_tabs_stop_removed_is_never_written_back(self):
        case = self.cases["removed"]
        self.assertIsNone(case["afterSave"], "not written back when the tab is left")
        self.assertEqual(case["whys"], ["tab"], "the next activity begins the next session")
        self.assertNotEqual(case["sent"][0]["bs"], case["ids"]["bs"])
        self.assertEqual(case["stored"], case["sent"][0]["bs"], "only the new one is stored")

    def test_another_tabs_newer_session_is_taken_at_the_next_activity(self):
        case = self.cases["taken"]
        for name, why in (("tab", "tab"), ("idle", "idle"), ("max", "max")):
            self.assertEqual(case[name]["whys"], [why], name)
            self.assertEqual(case[name]["sent"][0]["bs"], "bs-other", name)

    def test_reset_begins_the_browsers_next_session_with_a_new_tab_id(self):
        case = self.cases["reset"]
        steps = [entry[0] for entry in case["log"]]
        self.assertEqual(steps, ["flush", "between", "transport", "push", "snapshot"])
        sent, before = case["log"][2][1], case["before"]
        self.assertTrue(all(sent[key] != before[key] for key in ("s", "bs", "w")))
        self.assertEqual((case["log"][3][2]["why"], case["stored"]), ("reset", sent["bs"]))

    def test_a_new_tab_session_carries_the_visitor_another_tab_stored(self):
        case = self.cases["follow"]
        self.assertEqual(case["steps"], ["flush", "visitor", "identity", "transport", "push", "snapshot"])
        self.assertEqual((case["log"][1][1], case["log"][2][1]), ("visitor-new", "hash-new"))

    def test_the_mark_is_set_removed_when_left_and_set_again_on_return(self):
        case = self.cases["mark"]
        self.assertTrue(case["mark"])
        self.assertIsNone(case["afterLeave"])
        self.assertEqual(case["afterReturn"], case["mark"])
        self.assertEqual(case["othersKept"], "another-page")

    def test_a_copy_of_a_live_pages_storage_gets_a_new_tab_id_and_session(self):
        case = self.cases["copy"]
        self.assertEqual(case["ids"]["bs"], "bs-live")
        self.assertNotIn(case["ids"]["w"], ("w-old", None))
        self.assertNotEqual(case["ids"]["s"], "s-original")
        self.assertNotEqual(case["mark"], "original-page")

    def test_a_prerendered_page_is_no_copy_and_marks_the_tab_once_shown(self):
        case = self.cases["prerender"]
        self.assertEqual(case["ids"], {"s": "s-tab", "bs": "bs-live", "w": "w-old"})
        self.assertEqual(case["whilePrerendering"], "initiator-page")
        shown = case["shown"]
        self.assertEqual((shown[KEY["session"]], shown[KEY["window"]]), ("s-tab", "w-old"))
        self.assertNotIn(shown[KEY["window_open"]], ("initiator-page", None))
        self.assertEqual(json.loads(shown[KEY["clock"]])["b"], "bs-live")


if __name__ == "__main__":
    unittest.main()
