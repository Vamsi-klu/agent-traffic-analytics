"""Placing in visits the tab sessions an older AgentCake recorded: the upgrade to sessions across tabs.

A database an older AgentCake made holds tab sessions and no visits (store.py adds the table and the columns when it
opens it). The maintenance round places them (maintenance.py calls step()) the way the collector would have placed them
on arrival: each visitor's tab sessions are joined from the start (visit_join.regroup), and a tab session without a
visitor id is a visit of its own. A visit's verdict is merged from the verdicts its tab sessions have
(visit_verdict.py): nothing is judged again. Before it changes anything, it makes a checked backup the way `agentcake
migrate` does (migrate.backup: backups/cake-<UTC time>Z.db); without one (no room for it, or a copy that failed its
check, which is removed) it changes nothing, says why in cake.log once, and tries again in the next round; a round that
fails otherwise holds back nothing else of maintenance.py's. Then it places the visitors whose tab sessions ended last
first, visit_upgrade_batch_visitors at a time, each batch one transaction, for visit_upgrade_round_ms per round at most,
so that collect goes on in between (the tab session an upload brings is placed at once, beside its visitor's tab
sessions that are in a visit already: visit_join.place).

It can stop anywhere and go on in a later round, or after a restart: what is left to do is the tab sessions in no
visit, and joining a visitor's tab sessions again gives the visits it gave. When an older AgentCake ran on the database
again after this one (its tab sessions are in no visit), they are placed the same way, after a new backup. The settings
table keeps where it is (key "visit_upgrade"): the backup, when it began and ended, how many tab sessions and visits
there were when it ended, or why there is no backup yet.

    step(now_ms, cfg=None, deadline=None) -> state   one round's part: at least one batch, then more until deadline (a
                                                     time.monotonic() value; None: to the end)
"""
import time

from agentcake import migrate, paths, store, visit_join
from agentcake.config import load_cfg
from agentcake.storage_config import SETTINGS

KEY = "visit_upgrade"
IN_NO_VISIT = "SELECT 1 FROM session_web WHERE visit_id IS NULL LIMIT 1"
WITHOUT_ROW = ("SELECT 1 FROM sessions s WHERE NOT EXISTS (SELECT 1 FROM session_web w WHERE w.session_id = s.id) "
               "LIMIT 1")
# A tab session recorded before session_web existed gets its row (as web_props.fill gives one), to hold its visit.
GIVE_ROWS = ("INSERT OR IGNORE INTO session_web(session_id, tab_id) SELECT s.id, s.id FROM sessions s WHERE NOT EXISTS "
             "(SELECT 1 FROM session_web w WHERE w.session_id = s.id)")
VISITORS = ("SELECT w.visitor FROM session_web w JOIN sessions s ON s.id = w.session_id WHERE w.visit_id IS NULL AND "
            "w.visitor IS NOT NULL AND w.browser_session IS NULL GROUP BY w.visitor ORDER BY MAX(s.end_ms) DESC, "
            "w.visitor")
# Tab sessions in no visit that no visitor's joining places: without a visitor id, or with a browser session id.
ON_THEIR_OWN = ("SELECT session_id FROM session_web WHERE visit_id IS NULL AND (visitor IS NULL OR browser_session IS "
                "NOT NULL) LIMIT ?")
_TOLD = []  # the reason there is no backup yet, once per process in cake.log


def step(now_ms, cfg=None, deadline=None):
    """One round's part of the upgrade (see the module docstring); returns the state it leaves."""
    c = cfg or load_cfg()
    state = store.locked(lambda con: _begin(con, now_ms))
    if "backup" not in state or "done_ms" in state:
        return state
    visitors = store.locked(lambda con: [visitor for (visitor,) in con.execute(VISITORS)])
    size = c["visit_upgrade_batch_visitors"]
    while True:
        batch, visitors = visitors[:size], visitors[size:]
        placed, state = store.locked(lambda con: _place(con, batch, size, now_ms))
        if "done_ms" in state or not placed or (deadline is not None and time.monotonic() >= deadline):
            return state  # not placed: nothing this process can place is left (it goes on in a later round)
        if not visitors:  # a visitor with tab sessions in no visit again since the list was read
            visitors = store.locked(lambda con: [visitor for (visitor,) in con.execute(VISITORS)])


def _begin(con, now_ms):
    """The state to go on from: on a database with nothing to place, done; on one with tab sessions in no visit and no
    backup yet, the backup first."""
    state = store.setting(con, KEY)
    if state is None or "done_ms" in state:
        if not _to_place(con, state is None):
            return state or _record(con, {"done_ms": now_ms}, now_ms)
        state = {}
    if "backup" in state:
        return state
    try:
        made, _ = migrate.backup(paths.db_file(), now_ms, SETTINGS)
    except migrate.BackupFailed as error:
        if not _TOLD:
            _TOLD.append(error)
            print(f"sessions recorded before 0.6.2 wait to be joined across tabs: {error}", flush=True)
        return _record(con, {"error": str(error), "tried_ms": now_ms}, now_ms)
    con.execute(GIVE_ROWS)
    return _record(con, {"backup": made, "began_ms": now_ms}, now_ms)


def _to_place(con, first):
    """Whether some tab session is in no visit; the first time, also one without a session_web row."""
    return bool(con.execute(IN_NO_VISIT).fetchone() or (first and con.execute(WITHOUT_ROW).fetchone()))


def _place(con, visitors, size, now_ms):
    """Place the tab sessions of these visitors, else up to size tab sessions that are a visit on their own (or of a
    browser session); with none left in no visit, record the end. Returns (how many visitors or tab sessions, the
    state)."""
    for visitor in visitors:
        visit_join.regroup(con, visitor, now_ms, unplaced=True)
    alone = [] if visitors else [session_id for (session_id,) in con.execute(ON_THEIR_OWN, (size,)).fetchall()]
    for session_id in alone:
        visit_join.place(con, session_id, None, None, None, now_ms)
    state = store.setting(con, KEY)
    if con.execute(IN_NO_VISIT).fetchone():
        return len(visitors) + len(alone), state
    tabs, visits = (con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("session_web", "visits"))
    return len(visitors) + len(alone), _record(con, dict(state, done_ms=now_ms, tabs=tabs, visits=visits), now_ms)


def _record(con, state, now_ms):
    store.set_setting(con, KEY, state, now_ms)
    return state
