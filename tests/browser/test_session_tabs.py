"""A browser's tabs of a site share one session, in real Chromium tabs (tests/browser/session_tabs.mjs) against the
stand-in collector.

The rules, in real tabs of one profile on a clock the test sets (session.js with the tabs' real sessionStorage and
localStorage): two tabs have the same browser session (`bs`), each its own tab id (`w`) and tab session (`s`); a tab
quiet for 40 minutes while another is busy keeps the browser session and its tab id, and its own session is cut as
before; once no tab has acted for 30 minutes the next activity begins the browser's next session (with a new tab id)
and the other tab takes it, keeping its tab id; the same at 24 hours; a window opened with window.open gets a copy of
the opener's sessionStorage from Chromium, and it and a duplicated tab get a new tab id and tab session while the
original keeps its own, also after a reload; reset() in one tab begins a new browser session, tab id, tab session and
visitor, and the other tab takes the session and the visitor at its next activity (its session record saying "tab");
where localStorage is refused, each tab has a browser session of its own, kept in its sessionStorage (its next page
goes on with it), and nothing throws; where it takes no writes and holds a session that ended, the page keeps a session
of its own without a cut per activity.

The whole cake.js, in real time: every batch carries `bs` and `w` (32 hexadecimal digits) besides the fields it always
had; two tabs and a window opened by one of them send the same `bs` with different `w` and `s`; a tab that goes to
another page of the site and back keeps its `w` and `s`; after reset() in one tab and a click in the other, both send
the new `bs` and the new visitor id.

Skipped, saying what is missing, without node, playwright-core or Chromium (see harness.py).
"""
import json
import os
import re
import subprocess
import unittest

from . import collector, harness, uploads

DRIVER = os.path.join(harness.HERE, "session_tabs.mjs")
with open(os.path.join(harness.ROOT, "agentcake", "data", "cakejs.json"), encoding="utf-8") as f:
    SCRIPT = json.load(f)["script"]
KEY = SCRIPT["storage"]
HEX_ID = re.compile(r"[0-9a-f]{32}")
HEADER = ("v", "k", "s", "bs", "w", "vid", "pv", "seq", "t", "u", "ua", "wd", "why")


class SessionTabs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.out = harness.out_dir("session-tabs")
        server = collector.serve(cls.out)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            env = dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir())
            subprocess.run(["node", DRIVER, "--base", base, "--out", cls.out], check=True,
                           timeout=harness.DRIVE_TIMEOUT_S, env=env)
        finally:
            server.shutdown()
            server.server_close()
        with open(os.path.join(cls.out, "rules.json"), encoding="utf-8") as f:
            cls.rules = json.load(f)
        with open(os.path.join(cls.out, "script.json"), encoding="utf-8") as f:
            cls.script = json.load(f)
        cls.batches = uploads.unique(uploads.load(cls.out))

    def assertNewTab(self, ids, original):
        self.assertEqual(ids["bs"], original["bs"])
        self.assertNotEqual(ids["w"], original["w"])
        self.assertNotEqual(ids["s"], original["s"])

    def test_two_tabs_share_the_browser_session_with_ids_of_their_own(self):
        case = self.rules["two_tabs"]
        self.assertNewTab(case["two"], case["one"])

    def test_a_tab_quiet_for_40_minutes_keeps_the_browser_session_and_cuts_its_own(self):
        case = self.rules["idle_tab"]
        first, after = case["first"], case["after"]
        self.assertEqual(after["one"], first["one"], "the busy tab goes on as it was")
        self.assertEqual((after["two"]["bs"], after["two"]["w"]), (first["two"]["bs"], first["two"]["w"]))
        self.assertNotEqual(after["two"]["s"], first["two"]["s"])
        self.assertEqual(case["whys"], {"one": [], "two": ["idle"]})

    def test_once_no_tab_acted_for_30_minutes_the_next_activity_begins_the_next_session(self):
        case = self.rules["all_idle"]
        first, after = case["first"], case["after"]
        self.assertTrue(all(after["one"][key] != first["one"][key] for key in ("bs", "w", "s")))
        self.assertEqual(after["two"]["bs"], after["one"]["bs"], "the other tab takes it")
        self.assertEqual(after["two"]["w"], first["two"]["w"])
        self.assertNotEqual(after["two"]["s"], first["two"]["s"])
        self.assertEqual(case["whys"], {"one": ["idle"], "two": ["idle"]})

    def test_the_browser_session_ends_at_24_hours_in_every_tab(self):
        case = self.rules["max"]
        first, after = case["first"], case["after"]
        self.assertEqual(first["two"]["bs"], first["one"]["bs"])
        self.assertNotEqual(after["one"]["bs"], first["one"]["bs"])
        self.assertEqual((after["two"]["bs"], after["two"]["w"]), (after["one"]["bs"], first["two"]["w"]))
        self.assertEqual(case["whys"], {"one": ["max"], "two": ["max"]})

    def test_window_open_gets_a_copy_of_the_tabs_storage_from_chromium(self):
        case = self.rules["copies"]
        self.assertEqual(case["popupBefore"].get(KEY["window"]), case["first"]["w"])
        self.assertTrue(case["popupBefore"].get(KEY["window_open"]), "the mark came with the copy")

    def test_a_window_opened_by_a_tab_and_a_duplicated_tab_get_ids_of_their_own(self):
        case = self.rules["copies"]
        self.assertNewTab(case["opened"], case["first"])
        self.assertNewTab(case["duplicated"], case["first"])
        self.assertNotEqual(case["opened"]["w"], case["duplicated"]["w"])

    def test_the_original_tab_keeps_its_ids_and_a_reload_keeps_them(self):
        case = self.rules["copies"]
        original = case["original"]
        self.assertEqual((original["ids"], original["whys"]), (case["first"], []))
        self.assertEqual(original["stored"]["tab"][KEY["window"]], case["first"]["w"])
        self.assertEqual(case["reloaded"], case["first"])

    def test_reset_in_one_tab_begins_a_new_session_and_visitor_that_the_other_tab_takes(self):
        case = self.rules["reset"]
        first, after = case["first"], case["after"]
        one, two = after["one"], after["two"]
        self.assertTrue(all(one["ids"][key] != first["one"]["ids"][key] for key in ("bs", "w", "s")))
        self.assertNotEqual(one["vid"], first["one"]["vid"])
        self.assertEqual((two["ids"]["bs"], two["ids"]["w"]), (one["ids"]["bs"], first["two"]["ids"]["w"]))
        self.assertNotEqual(two["ids"]["s"], first["two"]["ids"]["s"])
        self.assertEqual(two["vid"], one["vid"], "the other tab takes the new visitor id too")
        self.assertIn(["visitor", one["vid"]], case["log"])
        self.assertEqual(case["whys"], {"one": ["reset"], "two": ["tab"]})

    def test_where_localstorage_is_refused_each_tab_has_a_session_of_its_own(self):
        """As where it takes no writes: the browser's session is kept in the tab's sessionStorage, so the tab's next
        page goes on with it (one session per tab, as in 0.6.1), and another tab has its own."""
        case = self.rules["refused"]
        first, second, other = case["pages"]
        self.assertEqual(second, first)
        for key in ("bs", "w", "s"):
            self.assertNotEqual(other[key], first[key], key)
        self.assertEqual(case["whys"], [])

    def test_where_localstorage_takes_no_writes_the_page_keeps_a_session_of_its_own(self):
        case = self.rules["quota"]
        self.assertNotEqual(case["first"]["bs"], "bs-stale")
        self.assertEqual((case["last"], case["whys"]), (case["first"], []))
        self.assertEqual(case["stored"][KEY["browser_session"]], "bs-stale")

    def test_no_page_threw(self):
        self.assertEqual((self.rules["errors"], self.script["errors"]), ([], []))

    def test_every_batch_carries_the_browser_session_and_the_tab_id(self):
        self.assertTrue(self.batches)
        for batch in self.batches:
            self.assertEqual([key for key in HEADER if key not in batch], [], batch.get("u"))
            self.assertTrue(HEX_ID.fullmatch(batch["bs"]) and HEX_ID.fullmatch(batch["w"]), batch["u"])

    def tabs(self):
        """{"one" | "two" | "popup": [batches in the order they were made]}, by the page address each came from."""
        tabs = {}
        for batch in sorted(self.batches, key=lambda b: b["t"]):
            name = "popup" if "popup=1" in batch["u"] else "two" if "tab=2" in batch["u"] else "one"
            tabs.setdefault(name, []).append(batch)
        return tabs

    def test_a_tab_keeps_its_ids_when_it_goes_to_another_page_and_back(self):
        two = self.tabs()["two"]
        before_reset = [batch for batch in two if batch["bs"] == two[0]["bs"]]
        self.assertEqual({(batch["w"], batch["s"]) for batch in before_reset}, {(two[0]["w"], two[0]["s"])})
        self.assertTrue(any("page=2" in batch["u"] for batch in before_reset), "the second page sent under them")
        self.assertGreaterEqual(len({batch["pv"] for batch in before_reset}), 2)

    def test_tabs_and_a_window_opened_by_one_send_one_browser_session(self):
        tabs = self.tabs()
        one, two, popup = tabs["one"][0], tabs["two"][0], tabs["popup"][0]
        self.assertNewTab(two, one)
        self.assertNewTab(popup, one)

    def test_after_reset_both_tabs_send_the_new_session_and_visitor(self):
        tabs = self.tabs()
        one_first, one_last = tabs["one"][0], tabs["one"][-1]
        two_first, two_last = tabs["two"][0], tabs["two"][-1]
        self.assertTrue(all(one_last[key] != one_first[key] for key in ("bs", "w", "s", "vid")))
        self.assertEqual((two_last["bs"], two_last["vid"]), (one_last["bs"], one_last["vid"]))
        self.assertEqual(two_last["w"], two_first["w"])
        self.assertNotEqual(two_last["s"], two_first["s"])
        self.assertNotIn("idh", two_last)
        records = {name: [r["why"] for b in batches for r in b["x"] if r.get("ty") == SCRIPT["session"]["record"]]
                   for name, batches in tabs.items()}
        self.assertEqual(records, {"one": ["reset"], "two": ["tab"], "popup": []})


if __name__ == "__main__":
    unittest.main()
