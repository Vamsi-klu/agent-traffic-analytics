"""Opening the database: agentcake/store.py's db().

    python3 -I -m unittest discover -s tests -p test_store.py -v      (from the AgentCake folder)

db() sets a database up once: a new one, or one an older cake made, gets schema.sql's tables, indexes and triggers
and the newer columns, in WAL mode, and is marked with PRAGMA user_version = store.SCHEMA_VERSION. A database
already marked is opened without running them again: every upload request opens the database, and the script and
the column checks were most of what that cost. The version is derived from schema.sql and ADDED_COLUMNS, so a cake
whose schema changed sets every older database up once more, with nothing to raise by hand. A database of cake 0.3.4,
or of an earlier development build of 0.4.0 (before the batches and refusals, requests.pv, the verdict columns and the
srv columns), ends up with every table, column, index and trigger a new database has. A new database opened by several
connections at the same moment (the threads answering a page's first requests, and a command run meanwhile in another
process) is set up by one connection of each process at most, and every connection gets it set up: none meets
"database is locked".
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path[:0] = [ROOT, TESTS]
from agentcake import config, paths, store  # noqa: E402  (needs the path above)
from test_migrate import SCHEMA_034  # noqa: E402

SIGNED_32_BITS = 2 ** 31  # PRAGMA user_version holds a signed 32-bit integer
# the sessions columns the verdict added, and the srv columns that keep reuses and comparisons
VERDICT_COLUMNS = ("verdict_class", "agent_row", "agent_name", "confidence", "reasons", "layers", "verdict_detail")
SRV_COLUMNS = ("pv", "ua_match", "lang_match", "reuses")
VISIT_COLUMNS = ("visit_id", "window_id", "browser_session")  # 0.6.2: session_web's visit, tab and bs
THREADS = 8  # more than the requests a browser sends at once for the first page
SET_UP = "set up"  # what OpenedAtOnce.set_ups() records for a set-up that finished
LOCKED = "database is locked"  # SQLite's words for SQLITE_BUSY
SHORT_TIMEOUT_S = 0.1  # db_timeout_s of the test whose other process never lets go of the lock
# Other processes on the same CAKE_HOME, as commands run while the server answers; argv[1] is this repository. Each
# prints a line once it has done its part, then waits for one before the next.
HOLDS_THE_WRITE_LOCK = """\
import sqlite3, sys
sys.path.insert(0, sys.argv[1])
from agentcake import paths, store
con = sqlite3.connect(paths.db_file())
con.execute("BEGIN IMMEDIATE")  # the write lock, as a set-up holds it while it writes the new database
print("holding", flush=True)
then = sys.stdin.readline().strip()
con.rollback()
if then == "set up":
    store.db().close()
print("done", flush=True)
"""
OPENS_THE_DATABASE = """\
import sqlite3, sys
sys.path.insert(0, sys.argv[1])
from agentcake import store
print("ready", flush=True)
sys.stdin.readline()
try:
    print(store.db().execute("PRAGMA user_version").fetchone()[0], flush=True)
except sqlite3.OperationalError as error:
    print(error, flush=True)
"""


def table_names(con):
    return {name for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def layout(con):
    """Every table with its columns, and every index and trigger, of a database."""
    tables = {name: sorted(row[1] for row in con.execute(f"PRAGMA table_info({name})")) for name in table_names(con)}
    others = sorted(con.execute("SELECT type, name FROM sqlite_master WHERE type IN ('index', 'trigger') "
                                "AND name NOT LIKE 'sqlite_%'"))
    return tables, others


def change_file(*statements):
    """Run statements on the database file directly, as another program (or an older cake) would."""
    con = sqlite3.connect(paths.db_file())
    try:
        con.executescript(";\n".join(statements))
    finally:
        con.close()


def user_version(con):
    return con.execute("PRAGMA user_version").fetchone()[0]


class OtherProcess:
    """A Python process running `code` on this CAKE_HOME with this repository importable; the test and it take turns
    line by line. It ends with the test."""

    def __init__(self, test, code):
        self.process = subprocess.Popen([sys.executable, "-I", "-c", code, ROOT], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True)
        test.addCleanup(self.end)

    def say(self, line):
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def hear(self):
        return self.process.stdout.readline().strip()

    def ask(self, line):
        self.say(line)
        return self.hear()

    def end(self):
        self.process.kill()  # nothing happens to one that has ended
        self.process.communicate()  # waits for it and closes the pipes


class SetUpOnce(unittest.TestCase):
    def setUp(self):
        home = mock.patch.dict(os.environ, {"CAKE_HOME": tempfile.mkdtemp(prefix="cake-test-")})
        home.start()
        self.addCleanup(home.stop)

    def opened(self):
        con = store.db()
        self.addCleanup(con.close)
        return con

    def test_a_new_database_gets_the_tables_wal_mode_and_the_schema_version(self):
        con = self.opened()
        self.assertLessEqual({"sessions", "events", "chunks", "open_chunks", "totals", "styles", "settings"},
                             table_names(con))
        self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)

    def test_a_database_already_set_up_is_opened_without_running_the_schema_again(self):
        store.db().close()
        change_file("DROP TABLE refusals")  # schema.sql would make it again
        self.assertNotIn("refusals", table_names(self.opened()))

    def test_a_database_an_older_cake_made_is_set_up(self):
        store.db().close()
        change_file("DROP TABLE refusals", "PRAGMA user_version = 0")  # as before user_version was kept
        con = self.opened()
        self.assertIn("refusals", table_names(con))
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)

    def test_a_cake_with_another_schema_sets_the_database_up_again(self):
        store.db().close()
        change_file("DROP TABLE refusals")
        with mock.patch.object(store, "SCHEMA_VERSION", store.SCHEMA_VERSION + 1):
            con = self.opened()
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)
        self.assertIn("refusals", table_names(con))

    def test_the_version_follows_schema_sql_and_the_added_columns(self):
        self.assertEqual(store.schema_version(store.SCHEMA, store.ADDED_COLUMNS), store.SCHEMA_VERSION)
        another_table = store.SCHEMA + "\nCREATE TABLE IF NOT EXISTS later(a INT);\n"
        another_column = dict(store.ADDED_COLUMNS, requests=store.ADDED_COLUMNS["requests"] + (("later", "INT"),))
        versions = {store.SCHEMA_VERSION, store.schema_version(another_table, store.ADDED_COLUMNS),
                    store.schema_version(store.SCHEMA, another_column)}
        self.assertEqual(len(versions), 3, "a changed schema.sql or ADDED_COLUMNS gives another version")
        self.assertTrue(all(0 <= version < SIGNED_32_BITS for version in versions), "kept as it is by SQLite")


class Upgrade(unittest.TestCase):
    """A database an older cake made, opened by this one: every table, column, index and trigger of a new database."""

    def setUp(self):
        home = mock.patch.dict(os.environ, {"CAKE_HOME": tempfile.mkdtemp(prefix="cake-test-")})
        home.start()
        self.addCleanup(home.stop)

    def new_layout(self):
        with mock.patch.dict(os.environ, {"CAKE_HOME": tempfile.mkdtemp(prefix="cake-test-")}):
            con = store.db()
            try:
                return layout(con)
            finally:
                con.close()

    def older_database(self, columns, tables=(), version=None, indexes=()):
        """Today's database without these indexes, columns ({table: names}) and tables, marked with `version`; by
        default the version a cake without those columns wrote (asserted to be another one)."""
        if version is None:
            before = {table: tuple(column for column in added if column[0] not in columns.get(table, ()))
                      for table, added in store.ADDED_COLUMNS.items()}
            version = store.schema_version(store.SCHEMA, before)
            self.assertNotEqual(version, store.SCHEMA_VERSION)
        store.db().close()
        change_file(*[f"DROP INDEX {name}" for name in indexes],
                    *[f"ALTER TABLE {table} DROP COLUMN {name}" for table, names in columns.items() for name in names],
                    *[f"DROP TABLE {table}" for table in tables], f"PRAGMA user_version = {version}")

    def upgraded(self):
        """db() on the database as it is now (an older cake's), then its layout; it is marked as set up."""
        con = store.db()
        self.addCleanup(con.close)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)
        return layout(con)

    def test_a_cake_034_database(self):
        change_file(SCHEMA_034)  # 0.3.4 never set user_version: it is 0
        self.assertEqual(self.upgraded(), self.new_layout())

    def test_a_database_from_the_first_chunk_storage(self):
        # before the batches, refusals and events_refused, requests.pv, the verdict and srv columns; that development
        # build did not set user_version either
        self.older_database({"sessions": VERDICT_COLUMNS + ("events_refused",), "requests": ("pv",),
                             "srv": SRV_COLUMNS}, tables=("batches", "refusals"), version=0)
        self.assertEqual(self.upgraded(), self.new_layout())

    def test_a_database_from_before_the_verdict_wiring(self):
        self.older_database({"sessions": VERDICT_COLUMNS, "srv": SRV_COLUMNS})
        upgraded = self.upgraded()
        self.assertEqual(upgraded, self.new_layout())
        self.assertLessEqual(set(VERDICT_COLUMNS), set(upgraded[0]["sessions"]))

    def test_a_database_from_before_the_srv_reuse_columns(self):
        self.older_database({"srv": SRV_COLUMNS})
        upgraded = self.upgraded()
        self.assertEqual(upgraded, self.new_layout())
        self.assertLessEqual(set(SRV_COLUMNS), set(upgraded[0]["srv"]))

    def test_a_database_from_before_the_visits(self):
        # 0.6.1: no visits table, and session_web without the columns that place a tab session in its visit; the
        # index on one of them is made once the column is there
        self.older_database({"session_web": VISIT_COLUMNS}, tables=("visits",), indexes=("session_web_visit",))
        upgraded = self.upgraded()
        self.assertEqual(upgraded, self.new_layout())
        self.assertLessEqual(set(VISIT_COLUMNS), set(upgraded[0]["session_web"]))
        self.assertIn(("index", "session_web_visit"), upgraded[1])

    def later_cake(self, schema=None, added_columns=None):
        """This cake as a later one with another schema.sql or ADDED_COLUMNS: its version is worked out from them,
        as store.py does at import; nobody writes a number."""
        schema, added_columns = schema or store.SCHEMA, added_columns or store.ADDED_COLUMNS
        for name, value in (("SCHEMA", schema), ("ADDED_COLUMNS", added_columns),
                            ("SCHEMA_VERSION", store.schema_version(schema, added_columns))):
            patch = mock.patch.object(store, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def test_a_column_a_later_cake_adds_reaches_a_database_set_up_today(self):
        store.db().close()
        self.later_cake(added_columns=dict(store.ADDED_COLUMNS,
                                           sessions=store.ADDED_COLUMNS["sessions"] + (("later_ms", "INT"),)))
        self.assertIn("later_ms", self.upgraded()[0]["sessions"])

    def test_a_table_a_later_cake_adds_reaches_a_database_set_up_today(self):
        store.db().close()
        self.later_cake(schema=store.SCHEMA + "\nCREATE TABLE IF NOT EXISTS later(session_id TEXT, at_ms INT);\n")
        self.assertEqual(self.upgraded()[0]["later"], ["at_ms", "session_id"])


class OpenedAtOnce(unittest.TestCase):
    """A new database opened by several connections at the same moment. The change of journal mode a set-up begins
    with turns a read lock into a write lock, which SQLite does not wait for (two connections could wait for each
    other forever): a set-up doing it while another one writes meets "database is locked" at once, whatever
    db_timeout_s says."""

    def setUp(self):
        home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": home})
        patch.start()
        self.addCleanup(patch.stop)

    def opened(self):
        con = store.db()
        self.addCleanup(con.close)
        return con

    def set_ups(self, when_locked=None):
        """store._set_up, recorded: one entry per set-up begun, SET_UP or the error that ended it. when_locked() runs
        when the first set-up ends in an error, before the error goes on: another process acts then."""
        outcomes, real = [], store._set_up

        def recorded(con):
            try:
                real(con)
            except sqlite3.OperationalError as error:
                outcomes.append(str(error))
                if when_locked and len(outcomes) == 1:
                    when_locked()
                raise
            outcomes.append(SET_UP)

        patch = mock.patch.object(store, "_set_up", recorded)
        patch.start()
        self.addCleanup(patch.stop)
        return outcomes

    def open_at_once(self, threads, go=None):
        """Open the database in `threads` threads at the same moment, go() just before it; per thread, the
        user_version of the database it got, or the error it met."""
        barrier, found = threading.Barrier(threads + 1), [None] * threads

        def open_one(index):
            barrier.wait()
            try:
                con = store.db()
            except sqlite3.OperationalError as error:
                found[index] = str(error)
                return
            try:
                found[index] = user_version(con)
            finally:
                con.close()

        workers = [threading.Thread(target=open_one, args=(index,)) for index in range(threads)]
        for worker in workers:
            worker.start()
        if go:
            go()
        barrier.wait()
        for worker in workers:
            worker.join()
        return found

    def holding_the_write_lock(self):
        """Another process holding the write lock of the new database, as one setting it up does while it writes."""
        other = OtherProcess(self, HOLDS_THE_WRITE_LOCK)
        self.assertEqual(other.hear(), "holding")
        return other

    def test_threads_opening_a_new_database_at_once_set_it_up_once(self):
        set_ups = self.set_ups()
        self.assertEqual(self.open_at_once(THREADS), [store.SCHEMA_VERSION] * THREADS)
        self.assertEqual(set_ups, [SET_UP], "one thread sets it up; the others wait their turn and find it set up")

    def test_threads_and_another_process_opening_a_new_database_at_once_all_get_it_set_up(self):
        other = OtherProcess(self, OPENS_THE_DATABASE)
        self.assertEqual(other.hear(), "ready")
        set_ups = self.set_ups()
        self.assertEqual(self.open_at_once(THREADS, go=lambda: other.say("go")), [store.SCHEMA_VERSION] * THREADS)
        self.assertEqual(other.hear(), str(store.SCHEMA_VERSION))
        self.assertLessEqual(set_ups.count(SET_UP), 1, "the threads take turns: one set-up at most in this process")

    def test_a_set_up_that_meets_another_process_writing_waits_for_it_then_sets_the_database_up(self):
        other = self.holding_the_write_lock()
        set_ups = self.set_ups(when_locked=lambda: other.ask("let go"))
        self.assertEqual(user_version(self.opened()), store.SCHEMA_VERSION)
        self.assertEqual(set_ups, [LOCKED, SET_UP])

    def test_a_database_another_process_set_up_meanwhile_is_not_set_up_again(self):
        other = self.holding_the_write_lock()
        set_ups = self.set_ups(when_locked=lambda: other.ask("set up"))
        self.assertEqual(user_version(self.opened()), store.SCHEMA_VERSION)
        self.assertEqual(set_ups, [LOCKED], "the version is looked at again before trying again")

    def test_a_write_lock_held_past_db_timeout_s_ends_in_database_is_locked(self):
        self.holding_the_write_lock()  # never let go of
        config.save_user(db_timeout_s=SHORT_TIMEOUT_S)
        with self.assertRaisesRegex(sqlite3.OperationalError, LOCKED):
            store.db()

    def test_a_set_up_that_fails_closes_the_connection_it_opened(self):
        """db() gives its caller no connection when the set-up fails, so it closes the one it opened itself rather
        than leave it to the garbage collector (which warns: ResourceWarning, unclosed database)."""
        self.holding_the_write_lock()  # never let go of
        config.save_user(db_timeout_s=SHORT_TIMEOUT_S)
        opened, connect = [], sqlite3.connect

        def keeping(*args, **kwargs):
            opened.append(connect(*args, **kwargs))
            return opened[-1]

        with mock.patch.object(store.sqlite3, "connect", keeping), \
                self.assertRaisesRegex(sqlite3.OperationalError, LOCKED):
            store.db()
        self.assertEqual(len(opened), 1)
        with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
            opened[0].execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
