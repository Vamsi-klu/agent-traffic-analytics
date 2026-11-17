"""The collector cuts sessions by PostHog's time rules: agentcake/session_split.py (with collect.py and delete.py).

    python3 -I -m unittest discover -s tests -p test_session_split.py -v

A tab's uploads stay one session while its activity has no gap over 30 minutes and lasts at most 24 hours; the
first activity after a longer gap, or past 24 hours, begins the next session (an id of its own, the tab's id kept in
session_web.tab_id), which starts with what the session before knew of the visitor (and its identify hash), source
and device. A copy of a batch, or one that waited, goes to the session it was sent in; a batch without activity never
begins a session; a cake 0.3.4 batch keeps its id; `agentcake delete` with the tab's id deletes every session cut
from it. The settings are the page script's own (data/cakejs.json "session"), so cake.js and the collector cut alike.
"""
import unittest

from web_uploads import MINUTE_MS, PV, T0, TAB, VISITOR, WebCase, upload
from agentcake import delete, session_split, store
from agentcake.datafiles import load

RULES = load("data/cakejs.json")["script"]["session"]
IDLE_MS, MAX_MS = RULES["idle_ms"], RULES["max_ms"]


class Splitting(WebCase):
    def sessions(self):
        return [row[0] for row in self.rows("SELECT session_id FROM session_web WHERE tab_id=? ORDER BY active_from",
                                            TAB)]

    def batches_of(self, session_id):
        return self.one("SELECT COUNT(*) FROM batches WHERE session_id=?", session_id)[0]

    def test_the_rules_are_posthogs_thirty_minutes_and_twenty_four_hours(self):
        self.assertEqual((IDLE_MS, MAX_MS), (30 * MINUTE_MS, 24 * 60 * MINUTE_MS))

    def test_activity_within_the_idle_time_stays_one_session(self):
        for seq in range(3):
            self.post(upload(seq, T0 + seq * 29 * MINUTE_MS))
        self.assertEqual(self.sessions(), [TAB])
        self.assertEqual(self.batches_of(TAB), 3)

    def test_activity_after_the_idle_time_begins_the_next_session(self):
        self.post(upload(0, T0, page={"rd": "www.google.com"}))
        self.post(upload(1, T0 + IDLE_MS + MINUTE_MS))
        first, second = self.sessions()
        self.assertEqual(first, TAB)
        self.assertEqual(second, session_split.continuation_id(TAB, 2))
        self.assertEqual((self.batches_of(first), self.batches_of(second)), (1, 1))
        self.assertIsNotNone(self.one("SELECT id FROM sessions WHERE id=?", second))

    def test_a_session_past_twenty_four_hours_begins_the_next_one(self):
        step = 20 * MINUTE_MS
        seq, t = 0, T0
        while t - T0 <= MAX_MS + step:  # the last activity is one step past 24 hours
            self.post(upload(seq, t))
            seq, t = seq + 1, t + step
        self.assertEqual(len(self.sessions()), 2)

    def test_the_next_session_starts_with_what_the_one_before_knew(self):
        self.post(upload(0, T0, page={"rd": "www.google.com", "utm": {"utm_source": "news"}}, person="a" * 64))
        self.post(upload(1, T0 + IDLE_MS + MINUTE_MS))
        second = self.sessions()[1]
        row = self.one("SELECT visitor, person, referring_domain, utm_source, channel, browser FROM session_web WHERE "
                       "session_id=?", second)
        self.assertEqual(row, (VISITOR, "a" * 64, "www.google.com", "news", "Organic Search", "Chrome"))

    def test_a_copy_of_a_batch_stays_in_the_session_it_was_sent_in(self):
        early = upload(0, T0)
        self.post(early)
        self.post(upload(1, T0 + IDLE_MS + MINUTE_MS))
        self.post(early)
        self.assertEqual(self.batches_of(TAB), 1)
        self.assertEqual(self.batches_of(self.sessions()[1]), 1)

    def test_a_batch_that_waited_goes_to_the_session_its_time_falls_in(self):
        self.post(upload(0, T0))
        self.post(upload(2, T0 + IDLE_MS + MINUTE_MS))
        self.post(upload(1, T0 + MINUTE_MS))  # sent late, from the first session's time
        self.assertEqual(self.batches_of(TAB), 2)

    def test_a_batch_without_activity_never_begins_a_session(self):
        self.post(upload(0, T0))
        self.post(upload(1, T0 + 2 * IDLE_MS, activity=False))
        self.assertEqual(self.sessions(), [TAB])
        self.assertEqual(self.batches_of(TAB), 2)

    def test_a_page_view_counts_as_activity(self):
        self.post(upload(0, T0))
        self.post(upload(1, T0 + IDLE_MS + MINUTE_MS, activity=False, page={}))
        self.assertEqual(len(self.sessions()), 2)

    def test_a_cake_0_3_4_batch_keeps_its_id(self):
        old = {"k": "ck_web_test", "s": TAB, "u": "https://shop.example.com/", "ua": "Mozilla/5.0", "wd": False,
               "e": [{"type": 3, "data": {"source": 1}, "timestamp": T0 + i * IDLE_MS} for i in range(3)]}
        self.post(old)
        self.assertEqual(self.one("SELECT COUNT(*) FROM session_web WHERE tab_id=?", TAB)[0], 1)
        self.assertEqual(self.one("SELECT id FROM sessions")[0], TAB)

    def test_deleting_by_the_tabs_id_deletes_every_session_cut_from_it(self):
        self.post(upload(0, T0))
        self.post(upload(1, T0 + IDLE_MS + MINUTE_MS))
        self.con.close()
        delete.delete_sessions([TAB])
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.assertEqual(self.one("SELECT COUNT(*) FROM sessions")[0], 0)
        self.assertEqual(self.one("SELECT COUNT(*) FROM session_web")[0], 0)
        self.assertEqual(self.one("SELECT COUNT(*) FROM batches")[0], 0)

    def test_a_session_cut_after_retention_deleted_an_earlier_one_gets_an_id_of_its_own(self):
        # retention deletes a tab's oldest sessions whole, while a script that never cuts its own may go on sending
        for n in range(3):
            self.post(upload(n, T0 + n * (IDLE_MS + MINUTE_MS)))
        first, second, third = self.sessions()
        for (table,) in self.con.execute(store.SESSION_TABLES).fetchall():  # as store.prune deletes a session
            self.con.execute(f"DELETE FROM {table} WHERE session_id=?", (first,))
        self.con.execute("DELETE FROM sessions WHERE id=?", (first,))
        self.con.commit()
        self.post(upload(3, T0 + 3 * (IDLE_MS + MINUTE_MS)))
        sessions = self.sessions()
        self.assertEqual((len(sessions), sessions[:2]), (3, [second, third]))
        self.assertEqual(self.batches_of(third), 1, "the new activity is not added to the session before it")

    def test_a_tab_whose_script_cuts_its_own_sessions_is_never_cut_again(self):
        self.post(upload(0, T0))
        self.post(upload(0, T0 + IDLE_MS + MINUTE_MS, tab="ffeeddccbbaa99887766554433221100", pv=PV[::-1]))
        self.assertEqual(self.rows("SELECT session_id, tab_id FROM session_web ORDER BY active_from"),
                         [(TAB, TAB), ("ffeeddccbbaa99887766554433221100", "ffeeddccbbaa99887766554433221100")])


if __name__ == "__main__":
    unittest.main()
