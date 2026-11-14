"""`agentcake migrate`: a cake 0.3.4 database into the new storage, nothing lost.

    python3 -I -m unittest discover -s tests -p test_migrate.py -v      (from the cake folder)

A database with 0.3.4's own tables (as tests/test_space.py builds them) is migrated: a checked backup comes first,
the replay rows are copied into chunks that read back byte for byte, and the original rows stay. Running it again
copies only what changed; a running cake, a full disk and a dry run change nothing.
"""
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import cli, migrate, paths, store, streams  # noqa: E402
from cake_server import free_port  # noqa: E402

NOW = 1794517500000
CSS = "main{display:grid;gap:1rem}" * 40

# cake 0.3.4's schema.sql (fce7503), the database migrate starts from
SCHEMA_034 = """
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, start_ms INT, end_ms INT, url TEXT, ua TEXT,
    webdriver INT, sec_fetch TEXT, source TEXT, group_id TEXT, verdict TEXT, human_pct INT, agent_pct INT, unsure_pct INT,
    segs TEXT, is_test INT DEFAULT 0, origin TEXT DEFAULT 'site', judged_ms INT DEFAULT 0, net TEXT,
    replay_freed_ms INT, events_dropped INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS events(session_id TEXT, ts INT, body TEXT);
CREATE INDEX IF NOT EXISTS ev_s ON events(session_id, ts);
CREATE TABLE IF NOT EXISTS srv(id TEXT PRIMARY KEY, session_id TEXT, recv_ms INT, page_ms INT, path TEXT,
    body TEXT, net_match INT);
CREATE INDEX IF NOT EXISTS srv_s ON srv(session_id, page_ms);
"""


def replay_event(ts, i):
    if i == 0:
        return {"type": 2, "data": {"node": {"type": 0, "childNodes": [
            {"type": 2, "tagName": "style", "attributes": {"_cssText": CSS}, "childNodes": []}]}}, "timestamp": ts}
    return {"type": 3, "data": {"source": 2, "type": 2, "x": i, "y": i, "id": 5}, "timestamp": ts}


def make_034_database(sessions=4, events=120):
    """0.3.4's tables and rows, written the way 0.3.4's collect wrote them (json.dumps with default separators)."""
    con = sqlite3.connect(paths.db_file())
    con.executescript(SCHEMA_034)
    for n in range(sessions):
        sid, end = f"visit{n}", NOW - (n + 1) * 3600_000
        con.execute("INSERT INTO sessions(id, start_ms, end_ms, url, ua, verdict, segs, judged_ms) VALUES(?,?,?,?,?,?,?,?)",
                    (sid, end - 60_000, end, "https://example.com/", "Mozilla/5.0", "human", "[]", end))
        for i in range(events):
            ts = end - 60_000 + (i // 2) * 800  # events come in pairs that share a millisecond: rowid keeps their order
            con.execute("INSERT INTO events VALUES(?,?,?)", (sid, ts, json.dumps(replay_event(ts, i))))
        con.execute("INSERT INTO srv VALUES(?,?,?,?,?,?,?)", (f"tok-{n}", sid, end, end, "/", '{"bs": 1}', 1))
    con.commit()
    con.close()


def rows(db, sql):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["migrate", *args])
    return code, out.getvalue()


class Migrate(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        os.environ["CAKE_HOME"] = self.home
        os.environ["CAKE_PORT"] = str(free_port())  # no cake answers there: never the person's own cake
        self.addCleanup(os.environ.pop, "CAKE_PORT", None)
        make_034_database()
        # 0.3.4's columns: a newer cake adds sessions columns (store.ADDED_COLUMNS), which leaves these as they were
        self.columns = {t: ", ".join(c[1] for c in rows(paths.db_file(), f"PRAGMA table_info({t})"))
                        for t in ("sessions", "events", "srv")}
        self.before = {t: rows(paths.db_file(), f"SELECT {cols} FROM {t} ORDER BY rowid") for t, cols in self.columns.items()}

    def backups(self):
        folder = os.path.join(self.home, "backups")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_backup_first_then_chunks_that_read_back_byte_for_byte_and_the_rows_stay(self):
        code, out = run()
        self.assertEqual(code, 0, out)
        (backup,) = self.backups()
        for table, before in self.before.items():
            cols = self.columns[table]
            self.assertEqual(rows(os.path.join(self.home, "backups", backup), f"SELECT {cols} FROM {table} ORDER BY rowid"),
                             before, f"backup {table}")
            self.assertEqual(rows(paths.db_file(), f"SELECT {cols} FROM {table} ORDER BY rowid")[:len(before)], before,
                             f"original {table} rows still there")
        con = store.db()
        self.addCleanup(con.close)
        for n in range(4):
            sid = f"visit{n}"
            want = [b for (b,) in con.execute("SELECT body FROM events WHERE session_id=? ORDER BY ts, rowid", (sid,))]
            got = [text for _, _, text in streams.read_events(con, sid, ["rrweb"])]
            self.assertEqual(got, want, sid)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM open_chunks").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM styles").fetchone()[0], 1, "the shared stylesheet, once")
        self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        record = store.setting(con, "migration")
        self.assertEqual((record["from"], record["sessions"], record["events"]), ("0.3.4", 4, 480))
        self.assertEqual(record["backup"], f"backups/{backup}")
        self.assertIn("480 replay events", out)
        self.assertNotIn(os.path.expanduser("~") + "/", out, "the home folder is shown as ~")

    def test_running_again_copies_only_what_changed(self):
        run()
        code, out = run()
        self.assertEqual(code, 0)
        self.assertIn("nothing to migrate", out)
        self.assertEqual(len(self.backups()), 1, "no new backup when there is nothing to do")
        con = sqlite3.connect(paths.db_file())
        con.execute("INSERT INTO events VALUES('visit1', ?, ?)", (NOW, json.dumps(replay_event(NOW, 7))))
        con.commit()
        con.close()
        code, out = run()
        self.assertEqual(code, 0, out)
        con = store.db()
        self.addCleanup(con.close)
        got = [t for _, _, t in streams.read_events(con, "visit1", ["rrweb"])]
        self.assertEqual(len(got), 121)
        self.assertEqual(got[-1], json.dumps(replay_event(NOW, 7)))
        self.assertEqual(store.setting(con, "migration")["sessions"], 1, "only visit1 was copied again")
        self.assertEqual(con.execute("SELECT SUM(n_events) FROM chunks").fetchone()[0], 481)

    def test_a_visit_that_went_on_after_the_upgrade_keeps_its_new_events(self):
        """0.3.4 recorded the start of visit1 as rows; after the upgrade, before migrate ran, the new collect wrote
        the rest of the visit into chunks. Migrate copies the rows next to those chunks and deletes nothing."""
        con = store.db()  # the new cake opens the database the new way when it starts
        newer = [(NOW + i * 100, json.dumps({"type": 3, "data": {"n": i}, "timestamp": NOW + i * 100},
                                            separators=(",", ":")), "pv1") for i in range(30)]
        streams.append(con, "visit1", "rrweb", newer[:20], NOW)
        streams.seal(con, NOW, force=True)  # some of it already sealed into a chunk ...
        streams.append(con, "visit1", "rrweb", newer[20:], NOW)  # ... and some still in an open window
        con.commit()
        con.close()
        code, out = run()
        self.assertEqual(code, 0, out)
        con = store.db()
        self.addCleanup(con.close)
        old = [b for (b,) in con.execute("SELECT body FROM events WHERE session_id='visit1' ORDER BY ts, rowid")]
        got = list(streams.read_events(con, "visit1", ["rrweb"], with_page=True))
        self.assertEqual([text for _, _, text, _ in got], old + [text for _, text, _ in newer])
        self.assertEqual([page for *_, page in got], [None] * len(old) + ["pv1"] * len(newer))
        self.assertEqual(store.setting(con, "migration")["events"], 480, "every row copied once")
        code, out = run()
        self.assertIn("nothing to migrate", out, "the newer chunks do not make the rows look uncopied")

    def test_a_dry_run_says_what_it_would_do_and_changes_nothing(self):
        code, out = run("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("4 sessions", out)
        self.assertEqual(self.backups(), [])
        self.assertEqual(rows(paths.db_file(), "SELECT name FROM sqlite_master WHERE name='chunks'"), [])

    def test_a_running_cake_is_not_migrated_under_its_feet(self):
        with mock.patch("agentcake.daemon.running", return_value={"home": self.home}):
            code, out = run()
        self.assertEqual(code, 1)
        self.assertIn("stop", out)
        self.assertEqual(self.backups(), [])
        with mock.patch("agentcake.daemon.running", return_value={"home": tempfile.mkdtemp()}):
            self.assertEqual(run()[0], 0, "a cake with another data folder is not this one")

    def test_without_room_for_the_backup_nothing_happens(self):
        full = mock.Mock(free=1)
        with mock.patch("shutil.disk_usage", return_value=full):
            code, out = run()
        self.assertEqual(code, 1)
        self.assertIn("free", out)
        self.assertEqual(self.backups(), [])

    def test_no_database_means_nothing_to_migrate(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        code, out = run()
        self.assertEqual(code, 0)
        self.assertIn("nothing to migrate", out)

    def test_a_row_that_cannot_be_copied_is_reported_and_its_session_left_as_it_was(self):
        con = sqlite3.connect(paths.db_file())
        con.execute("INSERT INTO events VALUES('visit2', ?, ?)", (NOW, '{"type": 3,\n"broken": true}'))
        con.commit()
        con.close()
        code, out = run()
        self.assertEqual(code, 1)
        self.assertIn("visit2", out)
        con = store.db()
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM chunks WHERE session_id='visit2'").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(DISTINCT session_id) FROM chunks").fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
