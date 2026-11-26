"""A visit is deleted whole: by one of its tab sessions' ids, by its own id, and by retention (agentcake/delete.py,
agentcake/store.py prune).

    python3 -I -m unittest discover -s tests -p test_visit_delete.py -v

Deleting the id of one tab session deletes every tab session of its visit and the visit's row, in the database, in
the backups and in the log; so does the visit's own id (a browser session id names no tab session); another visit
stays as it was. Retention deletes a visit once its last tab session is older than the retention, never part of one.
"""
import os
import shutil
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_visit_join import BS, MINUTE_MS, OTHER_VISITOR, T0, JoinCase, tab  # noqa: E402
from agentcake import delete, paths, store  # noqa: E402
from agentcake.storage_config import SETTINGS, ms_from_days  # noqa: E402
from agentcake.units import MS_PER_DAY  # noqa: E402


class Delete(JoinCase):
    def setUp(self):
        super().setUp()
        self.send(tab(1), T0)  # tabs 1 and 2: one visit the collector joined
        self.send(tab(2), T0 + MINUTE_MS)
        self.send(tab(3), T0, bs=BS)  # tabs 3 and 4: one visit named by its browser session id
        self.send(tab(4), T0 + MINUTE_MS, bs=BS)
        self.send(tab(5), T0, visitor=OTHER_VISITOR)  # another visitor's visit
        self.assertEqual(self.grouping(), [[tab(1), tab(2)], [tab(3), tab(4)], [tab(5)]])
        self.con.commit()

    def deleted(self, ids):
        self.con.close()
        result = delete.delete_sessions(ids)
        self.con = store.db()
        self.addCleanup(self.con.close)
        return result

    def left(self):
        return sorted(session for (session,) in self.rows("SELECT id FROM sessions"))

    def test_one_tab_sessions_id_deletes_its_whole_visit(self):
        result = self.deleted([tab(2)])
        self.assertEqual(sorted(item["id"] for item in result["sessions"]), [tab(1), tab(2)])
        self.assertEqual(self.left(), [tab(3), tab(4), tab(5)])
        self.assertEqual(sorted(self.visits()), sorted([BS, tab(5)]))
        for (table,) in self.con.execute(store.SESSION_TABLES).fetchall():
            self.assertEqual(self.rows(f"SELECT session_id FROM {table} WHERE session_id IN (?, ?)", tab(1), tab(2)),
                             [], table)

    def test_a_visits_own_id_deletes_it(self):
        self.deleted([BS])
        self.assertEqual(self.left(), [tab(1), tab(2), tab(5)])
        self.assertNotIn(BS, self.visits())

    def test_a_visits_own_id_lists_its_tab_sessions_not_itself_as_nothing_recorded(self):
        """A browser session id names a visit and no tab session: `agentcake delete` and its --dry-run printed
        "nothing recorded under" it above the tab sessions they deleted."""
        self.assertEqual([(item["id"], item["found"]) for item in self.deleted([BS])["sessions"]],
                         [(tab(3), True), (tab(4), True)])

    def test_an_id_that_names_nothing_is_still_reported_as_such(self):
        unknown = "f" * len(BS)
        self.assertEqual([(item["id"], item["found"]) for item in self.deleted([unknown])["sessions"]],
                         [(unknown, False)])

    def test_the_preview_names_the_whole_visit_and_changes_nothing(self):
        self.con.close()
        found = delete.preview([tab(3)])
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.assertEqual(sorted(item["id"] for item in found["sessions"]), [tab(3), tab(4)])
        self.assertEqual(self.left(), [tab(1), tab(2), tab(3), tab(4), tab(5)])

    def test_the_backups_lose_the_visits_rows_too(self):
        folder = os.path.join(paths.home(), SETTINGS["backup_dir"])
        os.makedirs(folder)
        backup = os.path.join(folder, "cake-backup.db")
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copyfile(paths.db_file(), backup)
        result = self.deleted([BS])
        self.assertGreater(result["backups"][0]["rows"], 0)
        copy = sqlite3.connect(backup)
        try:
            self.assertEqual(copy.execute("SELECT COUNT(*) FROM visits WHERE id=?", (BS,)).fetchone()[0], 0)
            self.assertEqual(copy.execute("SELECT COUNT(*) FROM sessions WHERE id IN (?, ?)", (tab(3), tab(4)))
                             .fetchone()[0], 0)
            self.assertEqual(copy.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 2, "the others stay")
        finally:
            copy.close()

    def test_the_log_loses_the_lines_naming_the_visit(self):
        with open(paths.log_file(), "w") as log:
            log.write(f"error in {BS}\nanother line\nerror in {tab(4)}\n")
        result = self.deleted([tab(3)])
        self.assertEqual(result["log_lines"], 2)
        with open(paths.log_file()) as log:
            self.assertEqual(log.read(), "another line\n")


class Retention(JoinCase):
    def prune_at(self, now_ms, days=30):
        return store.prune(self.con, days, now_ms)

    def test_a_visit_goes_once_its_last_tab_session_is_older_than_the_retention(self):
        self.received = T0 - 40 * MS_PER_DAY  # tab 1 began 40 days ago, tab 2 joined it a minute later
        self.send(tab(1), T0)
        self.received = T0 - 29 * MS_PER_DAY  # tab 2's latest upload came 29 days ago
        self.send(tab(2), T0 + MINUTE_MS)
        self.assertEqual(self.grouping(), [[tab(1), tab(2)]])
        self.assertEqual(self.prune_at(T0), 0, "kept whole: its last tab session ended 29 days ago")
        self.assertEqual(sorted(s for (s,) in self.rows("SELECT id FROM sessions")), [tab(1), tab(2)])
        self.assertEqual(self.prune_at(T0 + 2 * MS_PER_DAY), 2, "31 days after: whole")
        self.assertEqual((self.rows("SELECT id FROM sessions"), self.rows("SELECT id FROM visits")), ([], []))

    def test_a_tab_session_in_no_visit_yet_goes_by_its_own_end(self):
        old = T0 - ms_from_days(31)
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms) VALUES(?,?,?)", (tab(9), old, old))
        self.assertEqual(self.prune_at(T0), 1)
        self.assertEqual(self.rows("SELECT id FROM sessions"), [])


if __name__ == "__main__":
    unittest.main()
