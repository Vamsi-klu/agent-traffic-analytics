"""The database: one SQLite file in WAL mode, $CAKE_HOME/cake.db, with the tables of schema.sql.

db() opens it. A new database, or one an older cake made, is set up once: write-ahead-log mode (readers do not wait for
the writer), the tables of schema.sql, the columns newer versions brought, then PRAGMA user_version = SCHEMA_VERSION, a
fingerprint of schema.sql and ADDED_COLUMNS; a database with that version is opened as it is (every upload request
opens the database). Changing schema.sql or ADDED_COLUMNS changes the version by itself. Replays live next to it in
chunk files (streams.py).
prune(con, days) deletes whole sessions older than the retention the user chose (by default nothing is deleted by
age), chunks included. setting(), set_setting() and delete_setting() read and write the database's own state
(the settings table: what `agentcake migrate` did, whether dropped chunks wait for a reclaim, the address salt). LOCK
lets one writer at a time into the database and the chunk files within this process (collect, the judging before a
page, the maintenance thread).
"""
import json
import os
import pathlib
import sqlite3
import threading
import zlib

from agentcake import paths
from agentcake.config import load_cfg
from agentcake.storage_config import ms_from_days, now_ms as clock_ms

LOCK = threading.Lock()
SCHEMA = pathlib.Path(paths.SCHEMA_FILE).read_text(encoding="utf-8")
# Columns newer than a table's first version: {table: ((name, type), ...)}, the same as in schema.sql
ADDED_COLUMNS = {"sessions": (("origin", "TEXT DEFAULT 'site'"),  # 0.3.2: site or other; 'demo' until 0.4.0
                              ("judged_ms", "INT DEFAULT 0"), ("net", "TEXT"),  # 0.3.3: lazy judging, network facts
                              ("replay_freed_ms", "INT"), ("events_dropped", "INT DEFAULT 0"),  # 0.3.4: space
                              ("events_refused", "INT DEFAULT 0"),  # records over the per-session limit
                              ("verdict_class", "TEXT"), ("agent_row", "TEXT"), ("agent_name", "TEXT"),
                              ("confidence", "TEXT"), ("reasons", "TEXT"), ("layers", "TEXT"),
                              ("verdict_detail", "TEXT"),  # the four layers' verdict
                              ("first_action_ms", "INT"), ("last_action_ms", "INT"),  # the action span
                              ("model_version", "TEXT")),  # the judge that made the verdict (judging.py)
                 "requests": (("pv", "TEXT"),),  # the page view of the batch a request brought
                 "srv": (("pv", "TEXT"), ("ua_match", "INT"), ("lang_match", "INT"),  # reuse, comparisons
                         ("reuses", "INT DEFAULT 0"))}
# The tables whose rows belong to a session: every table with a session_id column, as the database has them now.
SESSION_TABLES = ("SELECT m.name FROM sqlite_master m JOIN pragma_table_info(m.name) p "
                  "WHERE m.type = 'table' AND p.name = 'session_id' ORDER BY m.name")
RECLAIM_DUE = "reclaim_due_ms"  # settings key: chunks were dropped and their file space is not back yet


def schema_version(schema, added_columns):
    """The PRAGMA user_version of a database set up with this schema text and these added columns: a fingerprint
    of both, so that changing either (a table, index, trigger or column) gives another version and every database
    is set up once more. Halved to stay positive: user_version is a signed 32-bit integer."""
    return zlib.crc32((schema + repr(added_columns)).encode("utf-8")) >> 1


SCHEMA_VERSION = schema_version(SCHEMA, ADDED_COLUMNS)  # nothing to raise by hand when schema.sql changes


def db():
    os.makedirs(paths.home(), exist_ok=True)
    con = sqlite3.connect(paths.db_file(), timeout=load_cfg()["db_timeout_s"])
    if con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        _set_up(con)
    return con


def _set_up(con):
    """A new database, or one an older cake (or a cake with another schema) set up: WAL mode, the tables of
    schema.sql and the newer columns, then the version, last, so that a setup cut short runs again."""
    con.execute("PRAGMA journal_mode=WAL")  # kept in the file: every later connection is in WAL mode too
    con.executescript(SCHEMA)
    for table, added in ADDED_COLUMNS.items():
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        for col, typ in added:
            if col not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def prune(con, days, now_ms=None):
    """Only when the user chose 30 or 90 days (the default, 0, keeps everything): delete the sessions that ended
    longer ago than that, whole. Every row of every table with a session_id column goes with them (chunks and open
    windows of every stream, small events, server half, segments, labels, network facts), read from the database so
    that a table a later step adds is not left behind. Returns how many sessions were deleted; their chunk files give
    the bytes back at the next maintenance round (space.reclaim_if_due)."""
    if not days or int(days) <= 0:
        return 0
    now_ms = clock_ms() if now_ms is None else now_ms
    cut = now_ms - ms_from_days(int(days))
    count = con.execute("SELECT COUNT(*) FROM sessions WHERE end_ms < ?", (cut,)).fetchone()[0]
    if count:
        for (table,) in con.execute(SESSION_TABLES).fetchall():
            con.execute(f"DELETE FROM {table} WHERE session_id IN (SELECT id FROM sessions WHERE end_ms < ?)", (cut,))
        con.execute("DELETE FROM sessions WHERE end_ms < ?", (cut,))
        mark_reclaim_due(con, now_ms)
    return count


def mark_reclaim_due(con, now_ms):
    """Chunks were dropped: the next maintenance round gives their file space back (space.reclaim_if_due)."""
    set_setting(con, RECLAIM_DUE, now_ms, now_ms)


def setting(con, key, default=None):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(con, key, value, now_ms):
    con.execute("INSERT INTO settings(key, value, updated_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET "
                "value=excluded.value, updated_ms=excluded.updated_ms", (key, json.dumps(value), now_ms))


def delete_setting(con, key):
    con.execute("DELETE FROM settings WHERE key=?", (key,))
