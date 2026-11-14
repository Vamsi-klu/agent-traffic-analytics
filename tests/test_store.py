"""Opening the database (S1.1, S2.2): agentcake/store.py's db().

    python3 -I -m unittest discover -s tests -p test_store.py -v      (from the Agent Cake folder)

db() sets a database up once: a new one, or one an older cake made, gets schema.sql's tables, indexes and triggers
and the newer columns, in WAL mode, and is marked with PRAGMA user_version = store.SCHEMA_VERSION. A database
already marked is opened without running them again: every upload request opens the database, and the script and
the column checks were most of what that cost. The version is derived from schema.sql and ADDED_COLUMNS, so a cake
whose schema changed sets every older database up once more, with nothing to raise by hand. A database of cake 0.3.4,
of S2.2 (before S2.1's batches and refusals, S2.3's requests.pv, S3.4's verdict columns and S4.2's srv columns), from
before the S3.4 wiring and from before S4.2 ends up with every table, column, index and trigger a new database has.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import paths, store  # noqa: E402  (needs the path above)
from test_migrate import SCHEMA_034  # noqa: E402

SIGNED_32_BITS = 2 ** 31  # PRAGMA user_version holds a signed 32-bit integer
# the sessions columns the S3.4 wiring added, and the srv columns of S4.2
VERDICT_COLUMNS = ("verdict_class", "agent_row", "agent_name", "confidence", "reasons", "layers", "verdict_detail")
SRV_COLUMNS = ("pv", "ua_match", "lang_match", "reuses")


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

    def older_database(self, columns, tables=(), version=None):
        """Today's database without these columns ({table: names}) and tables, marked with `version`; by default
        the version a cake without those columns wrote (asserted to be another one)."""
        if version is None:
            before = {table: tuple(column for column in added if column[0] not in columns.get(table, ()))
                      for table, added in store.ADDED_COLUMNS.items()}
            version = store.schema_version(store.SCHEMA, before)
            self.assertNotEqual(version, store.SCHEMA_VERSION)
        store.db().close()
        change_file(*[f"ALTER TABLE {table} DROP COLUMN {name}" for table, names in columns.items() for name in names],
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

    def test_a_database_from_s2_2(self):
        # before S2.1's batches, refusals and events_refused, S2.3's requests.pv, S3.4's and S4.2's columns; S2.2's
        # cake did not set user_version either
        self.older_database({"sessions": VERDICT_COLUMNS + ("events_refused",), "requests": ("pv",),
                             "srv": SRV_COLUMNS}, tables=("batches", "refusals"), version=0)
        self.assertEqual(self.upgraded(), self.new_layout())

    def test_a_database_from_before_the_verdict_wiring(self):
        self.older_database({"sessions": VERDICT_COLUMNS, "srv": SRV_COLUMNS})
        upgraded = self.upgraded()
        self.assertEqual(upgraded, self.new_layout())
        self.assertLessEqual(set(VERDICT_COLUMNS), set(upgraded[0]["sessions"]))

    def test_a_database_from_before_s4_2(self):
        self.older_database({"srv": SRV_COLUMNS})
        upgraded = self.upgraded()
        self.assertEqual(upgraded, self.new_layout())
        self.assertLessEqual(set(SRV_COLUMNS), set(upgraded[0]["srv"]))

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


if __name__ == "__main__":
    unittest.main()
