"""Tab sessions joined into visits, the sessions the dashboard counts: agentcake/visit_join.py.

    python3 -I -m unittest discover -s tests -p test_visit_join.py -v

Tab sessions whose uploads carry the same browser session id (bs) are one visit, named by it, and stay in it when a
later upload of theirs carries none. Those whose uploads carry none are joined by their visitor id with posthog-js's
rules: a gap of 29 minutes without activity in every tab joins, 31 minutes splits, and a visit ends after 24 hours;
activity in one tab keeps the visit going for a tab opened later. Uploads that come late, in any order, give the
visits they give in order; when a late upload joins two visits the one made first keeps its id. A tab session
without a visitor id is a visit of its own, named after it, as is a single one: a visit of one tab is that tab
session, its times and verdict included.
"""
import itertools
import os
import random
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web_uploads import KEY, MINUTE_MS, PV, T0, VISITOR, WebCase, upload  # noqa: E402
from agentcake import collect, config, store, visit_join  # noqa: E402

BS, BS2 = "b5" * 16, "b6" * 16
W1, W2 = "a1" * 16, "a2" * 16
OTHER_VISITOR = "cc" * 16
HOUR_MS = 60 * MINUTE_MS


def tab(n):
    return f"{n:032x}"


class JoinCase(WebCase):
    received = T0  # the collector's clock: a second later for every upload

    def send(self, session, t, seq=0, visitor=VISITOR, bs=None, w=None, **kwargs):
        """One upload of a tab session with activity at t (the browser's clock), received a second after the last."""
        body = upload(seq, t, tab=session, pv=PV[:-2] + f"{seq:02x}", visitor=visitor, **kwargs)
        if bs:
            body["bs"] = bs
        if w:
            body["w"] = w
        self.received += 1000
        with mock.patch.object(collect, "clock_ms", return_value=self.received):
            self.post(body)

    def visit_of(self, session):
        return self.one("SELECT visit_id FROM session_web WHERE session_id=?", session)[0]

    def visits(self):
        """{visit id: set of its tab sessions}, as the database holds them."""
        found = {}
        for session, visit in self.rows("SELECT session_id, visit_id FROM session_web"):
            found.setdefault(visit, set()).add(session)
        self.assertEqual(set(found), {visit for (visit,) in self.rows("SELECT id FROM visits")},
                         "every visit has tab sessions and every tab session a visit")
        return found

    def grouping(self):
        return sorted(sorted(tabs) for tabs in self.visits().values())


class Named(JoinCase):
    def test_two_tabs_with_one_browser_session_are_one_visit_named_by_it(self):
        self.send(tab(1), T0, bs=BS, w=W1)
        self.send(tab(2), T0 + MINUTE_MS, bs=BS, w=W2)
        self.assertEqual(self.visits(), {BS: {tab(1), tab(2)}})
        self.assertEqual(self.one("SELECT joined_by, visitor FROM visits WHERE id=?", BS), ("browser", VISITOR))
        self.assertEqual(self.rows("SELECT window_id, browser_session FROM session_web ORDER BY session_id"),
                         [(W1, BS), (W2, BS)])

    def test_another_browser_session_is_another_visit_whatever_the_time(self):
        self.send(tab(1), T0, bs=BS)
        self.send(tab(2), T0 + MINUTE_MS, bs=BS2)
        self.assertEqual(self.grouping(), [[tab(1)], [tab(2)]])

    def test_a_tab_session_stays_in_its_browser_sessions_visit_when_an_upload_carries_none(self):
        # a later page of the tab that an older cake.js ran from the browser's cache
        self.send(tab(1), T0, bs=BS)
        self.send(tab(1), T0 + MINUTE_MS, seq=1)
        self.assertEqual(self.visits(), {BS: {tab(1)}})

    def test_a_tab_session_that_carries_a_browser_session_later_leaves_the_visit_the_collector_joined(self):
        self.send(tab(1), T0)
        self.send(tab(2), T0 + MINUTE_MS)
        self.send(tab(2), T0 + 2 * MINUTE_MS, seq=1, bs=BS)
        self.assertEqual(self.visits(), {tab(1): {tab(1)}, BS: {tab(2)}})


class Joined(JoinCase):
    def test_a_gap_of_29_minutes_joins_and_31_minutes_splits(self):
        self.send(tab(1), T0)
        self.send(tab(2), T0 + 29 * MINUTE_MS)
        self.send(tab(3), T0 + 29 * MINUTE_MS + 31 * MINUTE_MS)
        self.assertEqual(self.visits(), {tab(1): {tab(1), tab(2)}, tab(3): {tab(3)}})

    def test_a_visit_ends_after_24_hours(self):
        # three tabs one after the other, each active for almost 8 hours, then a fourth 24 hours and 5 minutes after
        # the first began: never 30 minutes without activity
        for n in range(3):
            for step in range(17):
                self.send(tab(n), T0 + n * 8 * HOUR_MS + step * 29 * MINUTE_MS, seq=step)
        self.send(tab(3), T0 + 24 * HOUR_MS + 5 * MINUTE_MS)
        self.assertEqual(self.grouping(), [[tab(0), tab(1), tab(2)], [tab(3)]])

    def test_activity_in_one_tab_keeps_the_visit_going_for_a_tab_opened_later(self):
        for step in range(6):  # tab 1 active every 10 minutes for 50 minutes
            self.send(tab(1), T0 + step * 10 * MINUTE_MS, seq=step)
        self.send(tab(2), T0 + 75 * MINUTE_MS)  # 75 minutes after tab 1 began, 25 after its latest activity
        self.assertEqual(self.visits(), {tab(1): {tab(1), tab(2)}})

    def test_other_visitors_are_other_visits(self):
        self.send(tab(1), T0)
        self.send(tab(2), T0 + MINUTE_MS, visitor=OTHER_VISITOR)
        self.assertEqual(self.grouping(), [[tab(1)], [tab(2)]])

    def test_a_tab_session_without_a_visitor_id_is_a_visit_of_its_own(self):
        self.send(tab(1), T0, visitor=None)
        self.send(tab(2), T0 + MINUTE_MS, visitor=None)
        self.assertEqual(self.visits(), {tab(1): {tab(1)}, tab(2): {tab(2)}})

    def test_a_visit_of_one_tab_is_that_tab_session(self):
        self.send(tab(1), T0, page={})
        self.send(tab(1), T0 + MINUTE_MS, seq=1)
        session = self.one("SELECT start_ms, end_ms FROM sessions WHERE id=?", tab(1))
        web = self.one("SELECT active_from, active_last FROM session_web WHERE session_id=?", tab(1))
        visit = self.one("SELECT start_ms, end_ms, active_from, active_last FROM visits WHERE id=?", tab(1))
        self.assertEqual(visit, session + web)
        self.assertEqual(self.one("SELECT verdict_class FROM visits")[0],
                         self.one("SELECT verdict_class FROM sessions")[0])

    def test_a_late_tab_session_that_joins_two_visits_keeps_the_id_of_the_one_made_first(self):
        self.send(tab(1), T0)
        self.send(tab(3), T0 + 50 * MINUTE_MS)
        self.assertEqual(self.grouping(), [[tab(1)], [tab(3)]])
        self.send(tab(2), T0 + 25 * MINUTE_MS)  # came late: it bridges the gap
        self.assertEqual(self.visits(), {tab(1): {tab(1), tab(2), tab(3)}})
        self.assertEqual(self.visit_of(tab(3)), tab(1), "the other id is still the id of a tab session in it")

    def test_the_visit_made_first_keeps_its_id_also_when_it_began_later(self):
        self.send(tab(3), T0 + 50 * MINUTE_MS)
        self.send(tab(1), T0)  # began earlier, came later
        self.send(tab(2), T0 + 25 * MINUTE_MS)
        self.assertEqual(self.visits(), {tab(3): {tab(1), tab(2), tab(3)}})

    def test_a_late_upload_that_bridges_a_gap_joins_the_visits(self):
        self.send(tab(1), T0)
        self.send(tab(2), T0 + 50 * MINUTE_MS)
        self.send(tab(1), T0 + 25 * MINUTE_MS, seq=1)  # tab 1's activity at 25 minutes, sent late
        self.assertEqual(self.visits(), {tab(1): {tab(1), tab(2)}})

    def test_joining_again_changes_nothing(self):
        for n, minutes in enumerate((0, 20, 70, 85, 200)):
            self.send(tab(n), T0 + minutes * MINUTE_MS)
        before = self.rows("SELECT * FROM visits ORDER BY id"), self.rows("SELECT session_id, visit_id FROM "
                                                                          "session_web ORDER BY session_id")
        visit_join.regroup(self.con, VISITOR, T0, unplaced=True)
        after = self.rows("SELECT * FROM visits ORDER BY id"), self.rows("SELECT session_id, visit_id FROM "
                                                                         "session_web ORDER BY session_id")
        self.assertEqual(after, before)


class InAnyOrder(JoinCase):
    """The same uploads, in time order and shuffled: the same visits, each named after one of its tab sessions."""
    # (tab, minutes): eight tab sessions, some of them active twice, with gaps on both sides of 30 minutes
    # tab 2's activity at 39 minutes bridges to tab 3, which began 37 minutes after tab 2's activity at 31; no tab's
    # own activity spans more than 29 minutes, so no order of arrival cuts a tab's session in two (session_split.py)
    UPLOADS = ((1, 0), (2, 10), (1, 25), (2, 31), (2, 39), (3, 68), (4, 95), (3, 97), (4, 120), (5, 160), (6, 189),
               (7, 225), (8, 226))

    def run_uploads(self, order):
        seqs = {}
        for n, minutes in order:
            seqs[n] = seqs.get(n, -1) + 1
            self.send(tab(n), T0 + minutes * MINUTE_MS, seq=seqs[n])
        return self.visits()

    def fresh(self):
        self.received = T0
        self.con.close()
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-visit-join-test-")
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def test_late_and_shuffled_uploads_give_the_visits_uploads_in_order_give(self):
        in_order = self.run_uploads(sorted(self.UPLOADS, key=lambda upload: upload[1]))
        expected = sorted(sorted(tabs) for tabs in in_order.values())
        self.assertEqual(expected, [[tab(1), tab(2), tab(3), tab(4)], [tab(5), tab(6)], [tab(7), tab(8)]])
        shuffles = random.Random(7)
        orders = [list(reversed(self.UPLOADS))] + [shuffles.sample(self.UPLOADS, len(self.UPLOADS)) for _ in range(6)]
        for order in orders:
            with self.subTest(order=order):
                self.fresh()
                found = self.run_uploads(order)
                self.assertEqual(sorted(sorted(tabs) for tabs in found.values()), expected)
                for visit, tabs in found.items():
                    self.assertIn(visit, tabs, "a visit the collector joined is named after one of its tab sessions")

    def test_the_rule_alone_does_not_depend_on_the_order(self):
        tabs = [visit_join.Tab(tab(n), start, end, None, None, None, None, True)
                for n, (start, end) in enumerate(((0, 5), (20, 40), (65, 66), (110, 111), (100, 120)))]
        minute = MINUTE_MS
        tabs = [t._replace(start=t.start * minute, end=t.end * minute) for t in tabs]
        groups = {tuple(sorted(t.id for t in group)) for group in visit_join.join(tabs)}
        for order in itertools.permutations(tabs):
            self.assertEqual({tuple(sorted(t.id for t in group)) for group in visit_join.join(list(order))}, groups)
        self.assertEqual(groups, {(tab(0), tab(1), tab(2)), (tab(3), tab(4))})


class ManyVisits(JoinCase):
    def test_a_visitor_with_more_visits_than_a_statement_binds_is_joined_again(self):
        """regroup reads the visitor's visits in parts, as every list of ids is bound (store.parts); here SQLite takes
        10 values in a statement (more than any statement of a fixed size binds), as an old one takes 999."""
        limit, visits = 10, 12
        for n in range(1, visits + 1):  # one visit an hour
            self.send(tab(n), T0 + n * HOUR_MS)
        self.con.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, limit)
        with mock.patch.object(store, "SQL_VARIABLES", limit):
            visit_join.regroup(self.con, VISITOR, T0 + (visits + 1) * HOUR_MS)
        self.assertEqual(self.grouping(), [[tab(n)] for n in range(1, visits + 1)])


if __name__ == "__main__":
    unittest.main()
