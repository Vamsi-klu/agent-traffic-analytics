"""The tab sessions an older AgentCake recorded are placed in visits: agentcake/visit_upgrade.py.

    python3 -I -m unittest discover -s tests -p test_visit_upgrade.py -v

A database with tab sessions in no visit (an older AgentCake's) is backed up first, then placed the way the collector
places uploads as they come: the same visits, each with its tabs' verdicts merged, nothing judged again; a tab session
recorded before session_web existed gets its row and is a visit of its own. Placing again changes nothing and makes no
second backup. It can stop after any batch and go on later to the same end; without room for the backup it changes
nothing until there is room; tab sessions an older AgentCake records later are placed after a new backup. The
maintenance round runs it.
"""
import os
import sqlite3
import sys
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_visit_join import BS, MINUTE_MS, OTHER_VISITOR, T0, JoinCase, tab  # noqa: E402
from agentcake import config, maintenance, paths, store, visit_upgrade  # noqa: E402
from agentcake.storage_config import SETTINGS  # noqa: E402

KEY = visit_upgrade.KEY
OLD = "0a" * 16  # a tab session recorded before session_web existed (cake 0.3.4)
THIRD_VISITOR = "dd" * 16
PAST = 0  # a deadline already gone: one batch per step
UNPLUGGED = types.SimpleNamespace(on_ac_power=lambda: False, load_per_cpu=lambda: 1.0)  # no night work in the round


class Upgrade(JoinCase):
    def setUp(self):
        super().setUp()
        for n, minutes in enumerate((0, 20, 70, 85, 200)):  # visitor: visits [0, 1], [2, 3], [4]
            self.send(tab(n), T0 + minutes * MINUTE_MS)
        self.send(tab(5), T0, visitor=OTHER_VISITOR)
        self.send(tab(6), T0 + 2 * MINUTE_MS, visitor=OTHER_VISITOR)
        self.send(tab(7), T0, visitor=None)
        self.send(tab(8), T0, bs=BS, visitor=THIRD_VISITOR)
        self.collected = self.state()
        self.verdicts = self.rows("SELECT id, verdict_class, judged_ms FROM sessions ORDER BY id")
        self.make_it_older()

    def state(self):
        return (self.rows("SELECT id, joined_by, visitor, start_ms, end_ms, active_from, active_last, verdict_class "
                          "FROM visits ORDER BY id"),
                self.rows("SELECT session_id, visit_id FROM session_web ORDER BY session_id"))

    def make_it_older(self):
        """The database as an older AgentCake left it: no visits (and no bs), and one tab session without a
        session_web row."""
        self.con.execute("DELETE FROM visits")
        self.con.execute("UPDATE session_web SET visit_id=NULL, browser_session=NULL, window_id=NULL")
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms, verdict) VALUES(?,?,?,'human')", (OLD, T0, T0))
        self.con.commit()

    def step(self, deadline=None, now_ms=T0, **settings):
        if settings:
            config.save_user(**settings)
        self.con.close()
        found = visit_upgrade.step(now_ms, deadline=deadline)
        self.con = store.db()
        self.addCleanup(self.con.close)
        return found

    def backups(self):
        folder = os.path.join(paths.home(), SETTINGS["backup_dir"])
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def expected(self):
        """The visits the collector made, with the old tab session as a visit of its own and tab 8 (whose bs an
        older AgentCake never kept) as one the collector names after it."""
        visits, tabs = self.collected
        visits = [row for row in visits if row[0] != BS]
        tab_8 = self.one("SELECT start_ms, end_ms FROM sessions WHERE id=?", tab(8))
        span = self.one("SELECT active_from, active_last FROM session_web WHERE session_id=?", tab(8))
        cls = dict((session, cls) for session, cls, _ in self.verdicts)[tab(8)]
        visits.append((tab(8), "collector", THIRD_VISITOR, *tab_8, *span, cls))
        visits.append((OLD, "collector", None, T0, T0, None, None, "human"))
        tabs = [(session, tab(8) if session == tab(8) else visit) for session, visit in tabs] + [(OLD, OLD)]
        return sorted(visits), sorted(tabs)

    def test_a_backup_first_then_the_visits_the_collector_would_make(self):
        state = self.step()
        self.assertEqual(self.state(), self.expected())
        (backup,) = self.backups()
        self.assertEqual(state["backup"], f"{SETTINGS['backup_dir']}/{backup}")
        self.assertEqual((state["tabs"], state["visits"]), (10, 7))
        copy = sqlite3.connect(os.path.join(paths.home(), state["backup"]))
        try:
            self.assertEqual(copy.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 0, "made before any change")
        finally:
            copy.close()

    def test_nothing_is_judged_again(self):
        self.step()
        self.assertEqual(self.rows("SELECT id, verdict_class, judged_ms FROM sessions WHERE id != ? ORDER BY id", OLD),
                         self.verdicts)

    def test_placing_again_changes_nothing_and_makes_no_second_backup(self):
        self.step()
        placed = self.state()
        self.assertIn("done_ms", self.step(now_ms=T0 + MINUTE_MS))
        self.assertEqual(self.state(), placed)
        self.assertEqual(len(self.backups()), 1)

    def test_it_can_stop_after_any_batch_and_go_on_to_the_same_end(self):
        steps = 0
        while "done_ms" not in self.step(deadline=PAST, visit_upgrade_batch_visitors=1):
            steps += 1
            self.assertLess(steps, 20)
        self.assertGreater(steps, 2, "one visitor, or one tab session of its own, per step")
        self.assertEqual(self.state(), self.expected())

    def test_without_room_for_the_backup_nothing_changes_until_there_is(self):
        with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=1)):
            state = self.step()
        self.assertIn("not enough free disk", state["error"])
        self.assertEqual((self.backups(), self.rows("SELECT id FROM visits")), ([], []))
        self.step()
        self.assertEqual(self.state(), self.expected())

    def test_tab_sessions_an_older_agentcake_records_later_are_placed_after_a_new_backup(self):
        self.step()
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms) VALUES(?,?,?)", (tab(9), T0, T0))
        self.con.execute("INSERT INTO session_web(session_id, tab_id) VALUES(?,?)", (tab(9), tab(9)))
        self.con.commit()
        self.step(now_ms=T0 + MINUTE_MS)
        self.assertEqual(len(self.backups()), 2)
        self.assertEqual(self.one("SELECT visit_id FROM session_web WHERE session_id=?", tab(9)), (tab(9),))

    def test_the_maintenance_round_runs_it(self):
        self.con.close()
        maintenance.Upkeep(probes=UNPLUGGED).tick(int(time.time() * 1000))
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.assertIn("done_ms", store.setting(self.con, KEY))
        self.assertEqual(self.state()[1], self.expected()[1], "the round goes on to judge the never-judged one")


class NewDatabase(JoinCase):
    def test_a_new_database_has_nothing_to_place_and_no_backup(self):
        self.con.close()
        state = visit_upgrade.step(T0)
        self.assertEqual(state, {"done_ms": T0})
        self.assertFalse(os.path.isdir(os.path.join(paths.home(), SETTINGS["backup_dir"])))


if __name__ == "__main__":
    unittest.main()
