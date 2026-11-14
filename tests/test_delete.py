"""Deleting a visit in the process that owns the data folder (plan step S6.5): agentcake/delete.py.

    python3 -I -m unittest discover -s tests -p test_delete.py -v      (from the Agent Cake folder)

After the first of two planted visits (tests/delete_fixtures.py) is deleted, its id and its canary are nowhere: not in
any table, not in the database file's raw bytes, not in any replay chunk once decompressed, not in the backup, not in
the log. The other visit reads back exactly as before, and the space follows S2.2's reclaim (a file with nothing live
is deleted, a mostly dead one compacted). A chunk row that points at another visit's chunk stops everything; a delete
cut short after wiping is finished by running it again.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from delete_fixtures import NOW, SETTINGS, Planted  # noqa: E402
from agentcake import delete, paths, store, streams  # noqa: E402

class DeleteInProcess(Planted):
    def test_every_trace_is_gone_and_the_other_visit_is_as_before(self):
        before = os.stat(paths.log_file()).st_ino
        result = delete.delete_sessions([self.gone], now_ms=NOW)
        self.assertEqual([s["found"] for s in result["sessions"]], [True])
        self.assert_gone_everywhere()
        self.assert_kept_as_before()
        self.assertEqual(os.stat(paths.log_file()).st_ino, before, "the log is rewritten in place: a running cake "
                                                                   "keeps writing to the same file")
        self.assertEqual((result["log_lines"], result["backups"][0]["rows"] > 0), (2, True))

    def test_freed_space_comes_back_the_s22_way(self):
        root = os.path.join(self.home, SETTINGS["replay_dir"])
        result = delete.delete_sessions([self.gone], now_ms=NOW)
        old, mixed, current = (os.path.join(root, f) for f in self.files.values())
        self.assertFalse(os.path.exists(old), "a file with no live chunk is deleted")
        self.assertFalse(os.path.exists(mixed), "a file mostly dead is compacted: its live chunks move to this hour's")
        self.assertTrue(os.path.exists(current), "this hour's file is never touched by reclaim; its dead bytes are zeros")
        self.assertEqual((result["reclaim"]["deleted"], result["reclaim"]["compacted"]), (1, 1))
        con = store.db()
        try:
            self.assertEqual({f for (f,) in con.execute("SELECT DISTINCT file FROM chunks")}, {self.files[NOW]})
            self.assertEqual(con.execute("SELECT COUNT(*) FROM styles").fetchone()[0], 2,
                             "the other visit's own stylesheet and the shared one; the deleted visit's own is gone")
        finally:
            con.close()

    def test_two_ids_at_once(self):
        result = delete.delete_sessions([self.gone, self.kept], now_ms=NOW)
        self.assertEqual([s["found"] for s in result["sessions"]], [True, True])
        con = store.db()
        try:
            for (table,) in con.execute(store.SESSION_TABLES).fetchall():
                self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
        finally:
            con.close()

    def test_a_chunk_row_pointing_at_another_visits_chunk_stops_everything(self):
        con = store.db()
        con.execute("UPDATE chunks SET file=(SELECT file FROM chunks WHERE session_id=? LIMIT 1), "
                    "byte_offset=(SELECT byte_offset FROM chunks WHERE session_id=? LIMIT 1) WHERE id=(SELECT MIN(id) "
                    "FROM chunks WHERE session_id=?)", (self.kept, self.kept, self.gone))
        con.commit()
        con.close()
        with self.assertRaises(delete.WipeRefused):
            delete.delete_sessions([self.gone], now_ms=NOW)
        con = store.db()
        try:
            self.assertEqual(list(streams.read_events(con, self.kept)), self.kept_events, "nothing of the other visit")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM sessions WHERE id=?", (self.gone,)).fetchone()[0], 1,
                             "and nothing deleted")
        finally:
            con.close()

    def test_a_delete_cut_short_after_wiping_is_finished_by_running_it_again(self):
        con = store.db()
        for file, offset, length in con.execute("SELECT file, byte_offset, byte_length FROM chunks WHERE session_id=?",
                                                (self.gone,)).fetchall():
            with open(os.path.join(self.home, SETTINGS["replay_dir"], file), "r+b") as f:
                f.seek(offset)
                f.write(bytes(length))
        con.close()
        delete.delete_sessions([self.gone], now_ms=NOW)
        self.assert_gone_everywhere()
        self.assert_kept_as_before()


if __name__ == "__main__":
    unittest.main()
