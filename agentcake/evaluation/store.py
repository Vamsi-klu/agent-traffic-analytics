"""The sessions of a CAKE_HOME that a truth list names, read without writing anything (cases T3, T5,
T6, T8 and T22 run on a real AgentCake and labelled afterwards).

    labelled(truth_rows, settings, home=None) -> [{"h", "truth", "evidence", "page_views", "tokens"}]

The database is opened read only (connect_readonly), in the CAKE_HOME given or the current one; its replay chunks are
read from its replay folder and its settings from its config.json, which the readers find through CAKE_HOME, so
CAKE_HOME is set to it while they read. A session is listed by its short hash, sha256("cake-goal|" + session id)[:12]
(data/eval.json "short_hash"), so the list never holds a session id. Its evidence is exactly what AgentCake judges:
agentcake/evidence.py's session_evidence(), with the behaviour layer run as verdict.judge() runs
it. page_views and tokens: the session's page views, and those whose server-half token reached cake.
"""
import contextlib
import os
import pathlib
import sqlite3

from agentcake import evidence as stored_evidence, paths
from agentcake.evaluation import datasets, evidence as evidence_builder

HOME_VARIABLE = "CAKE_HOME"  # protocol: the variable paths.home() reads
WAL_SUFFIX = "-wal"  # protocol: SQLite's write-ahead log is the database's name + "-wal"
READ_ONLY, IMMUTABLE = "mode=ro", "&immutable=1"  # protocol: SQLite URI parameters


def connect_readonly(home=None):
    """A read-only connection to the database of `home` (default: the current CAKE_HOME), or None without one.

    With no write-ahead log next to it (AgentCake is not running) the file is opened as immutable, so SQLite does
    not even create its -wal and -shm files; with one (it is running), read-only, so the newest rows are seen.
    """
    home = home or paths.home()
    name = os.path.relpath(paths.db_file(), paths.home())
    db = os.path.join(home, name)
    if not os.path.isfile(db):
        return None
    mode = READ_ONLY if os.path.exists(db + WAL_SUFFIX) else READ_ONLY + IMMUTABLE
    return sqlite3.connect(f"{pathlib.Path(db).as_uri()}?{mode}", uri=True)


def labelled(truth_rows, settings, home=None):
    """The listed sessions found in the database, with their answer and evidence (see the module docstring)."""
    if not truth_rows:  # before connecting: a connection is closed only on the way out of the try below
        return []
    with _cake_home(home):
        con = connect_readonly()
        if con is None:
            return []
        try:
            wanted = {row["h"]: row for row in truth_rows}
            prefix = settings["short_hash"]["goal"]
            out = []
            for (sid,) in con.execute("SELECT id FROM sessions ORDER BY start_ms, id"):
                h = datasets.short_hash(prefix, sid, settings)
                if h in wanted:
                    out.append(_session(con, sid, wanted[h]))
            return out
        finally:
            con.close()


def _session(con, sid, truth):
    built, raw, rrweb = stored_evidence.session_evidence(con, sid)
    views = {pv: bool(token) for pv, token in con.execute(
        "SELECT pv, MAX(token_id IS NOT NULL) FROM batches WHERE session_id=? GROUP BY pv", (sid,))}
    return {"h": truth["h"], "truth": truth, "evidence": evidence_builder.with_behaviour(built, raw, rrweb),
            "page_views": len(views), "tokens": sum(views.values())}


@contextlib.contextmanager
def _cake_home(home):
    """CAKE_HOME set to `home` while its files are read (streams.py and config.py find them through CAKE_HOME)."""
    before = os.environ.get(HOME_VARIABLE)
    if home:
        os.environ[HOME_VARIABLE] = home
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(HOME_VARIABLE, None)
        else:
            os.environ[HOME_VARIABLE] = before
