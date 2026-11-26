"""The database: one SQLite file in WAL mode, $CAKE_HOME/cake.db, with the tables of schema.sql.

db() opens it. A new database, or one an older cake made, is set up once: write-ahead-log mode (readers do not wait for
the writer), the columns newer versions brought to the tables it has, the tables and indexes of schema.sql, then
PRAGMA user_version = SCHEMA_VERSION, a
fingerprint of schema.sql and ADDED_COLUMNS; a database with that version is opened as it is (every upload request
opens the database). Changing schema.sql or ADDED_COLUMNS changes the version by itself. Connections that find the
database not set up take turns within this process (SETTING_UP), and each looks at the version again when its turn
comes: the first page of a new install sends several requests at once, and only one of them sets the database up. A
set-up that meets another process's (a command run while the server answers) waits for it and tries again, for
db_timeout_s at most. Replays live next to it in chunk files (streams.py).
prune(con, days) deletes whole visits (the sessions the dashboard counts: every tab session of one) older than the
retention the user chose (by default nothing is deleted by age), chunks included. parts(values) splits a list of
values to bind into lists one statement can take. setting(), set_setting() and delete_setting() read and write the database's own state
(the settings table: what `agentcake migrate` did, whether dropped chunks wait for a reclaim, the address salt). LOCK
lets one writer at a time into the database and the chunk files within this process (collect, the judging before a
page, the maintenance thread).
"""
import json
import os
import pathlib
import sqlite3
import threading
import time
import zlib

from agentcake import paths
from agentcake.config import load_cfg
from agentcake.storage_config import ms_from_days, now_ms as clock_ms

LOCK = threading.Lock()
SETTING_UP = threading.Lock()  # one set-up at a time in this process; not LOCK, which callers of db() may hold already
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
                         ("reuses", "INT DEFAULT 0")),
                 "session_web": (("person", "TEXT"),  # the identify hash (window.cake.identify())
                                 ("vis_t", "REAL"),  # the latest change of visibility followed (web_time.py)
                                 ("vis_pv", "TEXT"),  # the page view that is the tab's after it
                                 ("visit_id", "TEXT"), ("window_id", "TEXT"),  # 0.6.2: its visit, its tab (w)
                                 ("browser_session", "TEXT"))}  # 0.6.2: the browser session id (bs) it carried
# The tables whose rows belong to a session: every table with a session_id column, as the database has them now.
SESSION_TABLES = ("SELECT m.name FROM sqlite_master m JOIN pragma_table_info(m.name) p "
                  "WHERE m.type = 'table' AND p.name = 'session_id' ORDER BY m.name")
RECLAIM_DUE = "reclaim_due_ms"  # settings key: chunks were dropped and their file space is not back yet
SQL_VARIABLES = 999  # protocol: SQLITE_MAX_VARIABLE_NUMBER's default before SQLite 3.32, the most ? of one statement
# The tab sessions retention deletes: those of every visit whose last tab session ended before :cut, and each tab
# session in no visit yet (recorded before the upgrade to visits placed it, visit_upgrade.py) that did, by itself.
PRUNED = ("SELECT w.session_id FROM visits v JOIN session_web w ON w.visit_id = v.id WHERE v.end_ms < :cut UNION "
          "SELECT s.id FROM sessions s WHERE s.end_ms < :cut AND NOT EXISTS (SELECT 1 FROM session_web w WHERE "
          "w.session_id = s.id AND w.visit_id IS NOT NULL)")


def schema_version(schema, added_columns):
    """The PRAGMA user_version of a database set up with this schema text and these added columns: a fingerprint
    of both, so that changing either (a table, index, trigger or column) gives another version and every database
    is set up once more. Halved to stay positive: user_version is a signed 32-bit integer."""
    return zlib.crc32((schema + repr(added_columns)).encode("utf-8")) >> 1


SCHEMA_VERSION = schema_version(SCHEMA, ADDED_COLUMNS)  # nothing to raise by hand when schema.sql changes


def db():
    os.makedirs(paths.home(), exist_ok=True)
    timeout_s = load_cfg()["db_timeout_s"]
    con = sqlite3.connect(paths.db_file(), timeout=timeout_s)
    try:
        if not _is_set_up(con):
            _set_up_once(con, timeout_s)
    except BaseException:  # the caller gets no connection to close, so this one is closed here before the error goes on
        con.close()
        raise
    return con


def _is_set_up(con):
    return con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def _set_up_once(con, timeout_s):
    """Set the database up, unless another connection has by the time this one's turn comes. The change of journal
    mode a set-up begins with turns a read lock into a write lock, and SQLite does not wait for that (two connections
    could wait for each other forever): meeting another process's set-up as it writes, it answers "database is locked"
    at once, whatever the busy timeout. The set-up then waits for the writer, looks at the version again and tries
    again, until timeout_s (db_timeout_s) has passed."""
    with SETTING_UP:
        give_up_at = time.monotonic() + timeout_s
        while not _is_set_up(con):
            try:
                _set_up(con)
                return
            except sqlite3.OperationalError as error:
                if not _is_locked(error) or time.monotonic() >= give_up_at:
                    raise
            _wait_for_writer(con)


def _is_locked(error):
    """Whether SQLite answered "database is locked": SQLITE_BUSY, or one of its extended codes."""
    code = getattr(error, "sqlite_errorcode", sqlite3.SQLITE_OK)  # an error Python's sqlite3 made itself has none
    return code & 0xFF == sqlite3.SQLITE_BUSY  # protocol: an extended result code's low byte is its primary code


def _wait_for_writer(con):
    """Wait until no other connection is writing, for the busy timeout at most. SQLite waits for a write lock asked
    for before anything is read, as BEGIN IMMEDIATE asks for it; it does not for one asked for after reading."""
    con.execute("BEGIN IMMEDIATE")
    con.rollback()


def _set_up(con):
    """A new database, or one an older cake (or a cake with another schema) set up: WAL mode, the newer columns of the
    tables it has, then the tables and indexes of schema.sql (an index may be on a newer column: the column comes
    first), then the version, last, so that a setup cut short runs again. A table schema.sql makes is made with every
    column."""
    con.execute("PRAGMA journal_mode=WAL")  # kept in the file: every later connection is in WAL mode too
    for table, added in ADDED_COLUMNS.items():
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        for col, typ in added:
            if cols and col not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    con.executescript(SCHEMA)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def prune(con, days, now_ms=None):
    """Only when the user chose 30 or 90 days (the default, 0, keeps everything): delete the visits whose last tab
    session ended longer ago than that, whole (PRUNED: never part of a visit). Every row of every table with a
    session_id column goes with their tab sessions (chunks and open windows of every stream, small events, server half,
    segments, labels, network facts), read from the database so that a table a later step adds is not left behind,
    then the visits' rows. Returns how many tab sessions were deleted; their chunk files give the bytes back at the
    next maintenance round (space.reclaim_if_due)."""
    if not days or int(days) <= 0:
        return 0
    now_ms = clock_ms() if now_ms is None else now_ms
    cut = now_ms - ms_from_days(int(days))
    ids = [session_id for (session_id,) in con.execute(PRUNED, {"cut": cut})]
    tables = [table for (table,) in con.execute(SESSION_TABLES).fetchall()]
    for part in parts(ids):
        marks = ",".join("?" * len(part))
        for table in tables:
            con.execute(f"DELETE FROM {table} WHERE session_id IN ({marks})", part)
        con.execute(f"DELETE FROM sessions WHERE id IN ({marks})", part)
    con.execute("DELETE FROM visits WHERE end_ms < ? AND NOT EXISTS (SELECT 1 FROM session_web w WHERE "
                "w.visit_id = visits.id)", (cut,))
    if ids:
        mark_reclaim_due(con, now_ms)
    return len(ids)


def locked(work):
    """work(con) under LOCK, on a connection of its own, committed after it: what work returned."""
    with LOCK:
        con = db()
        try:
            out = work(con)
            con.commit()
            return out
        finally:
            con.close()

def parts(values):
    """values (a list) in consecutive lists of at most SQL_VARIABLES: what one statement can bind."""
    return [values[start:start + SQL_VARIABLES] for start in range(0, len(values), SQL_VARIABLES)]


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
