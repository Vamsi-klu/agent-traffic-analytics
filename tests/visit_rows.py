"""Sessions (visits) for test data written straight into the tables: what the collector and the upgrade make of tab
sessions (visit_join.py, visit_upgrade.py), so a test can say which tab sessions are one session.

    alone(con)                       every tab session that is in no visit yet becomes a session of its own, as the
                                     upgrade makes a tab session no other tab joins: its visit's id is its own, its
                                     class its own (visit_verdict.remerge)
    joined(con, visit_id, tabs)      tabs: [(tab session id, window id or None)], oldest first: one session of these,
                                     their earlier sessions gone, its class merged from theirs
    refreshed(con)                   every session's start, end and class again from its tab sessions, after a test
                                     rewrote their rows (start_ms, end_ms, verdict_class) as the judge would have
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentcake import visit_verdict  # noqa: E402

JOINED_BY = "collector"  # visits.joined_by of a session the collector joined by the visitor id


def alone(con):
    """See the module docstring; returns the ids of the sessions made."""
    con.execute("INSERT OR IGNORE INTO session_web(session_id, tab_id) SELECT id, id FROM sessions")
    made = [session_id for (session_id,) in con.execute(
        "SELECT w.session_id FROM session_web w LEFT JOIN visits v ON v.id = w.visit_id WHERE v.id IS NULL")]
    for session_id in made:
        _visit(con, session_id, [(session_id, None)])
    con.commit()
    return made


def joined(con, visit_id, tabs):
    """See the module docstring."""
    con.execute("INSERT OR IGNORE INTO session_web(session_id, tab_id) SELECT id, id FROM sessions")
    ids = [session_id for session_id, _ in tabs]
    marks = ",".join("?" * len(ids))
    con.execute(f"DELETE FROM visits WHERE id IN (SELECT visit_id FROM session_web WHERE session_id IN ({marks}))", ids)
    _visit(con, visit_id, tabs)
    con.commit()


def refreshed(con):
    """See the module docstring."""
    con.execute("UPDATE visits SET start_ms=(SELECT MIN(s.start_ms) FROM session_web w JOIN sessions s ON "
                "s.id = w.session_id WHERE w.visit_id = visits.id), end_ms=(SELECT MAX(s.end_ms) FROM session_web w "
                "JOIN sessions s ON s.id = w.session_id WHERE w.visit_id = visits.id)")
    for (visit_id,) in con.execute("SELECT id FROM visits").fetchall():
        visit_verdict.remerge(con, visit_id)
    con.commit()


def _visit(con, visit_id, tabs):
    for session_id, window in tabs:
        con.execute("UPDATE session_web SET visit_id=?, window_id=? WHERE session_id=?", (visit_id, window, session_id))
    ids = [session_id for session_id, _ in tabs]
    marks = ",".join("?" * len(ids))
    start, end, visitor = con.execute(f"SELECT MIN(s.start_ms), MAX(s.end_ms), MAX(w.visitor) FROM sessions s JOIN "
                                      f"session_web w ON w.session_id = s.id WHERE s.id IN ({marks})", ids).fetchone()
    con.execute("INSERT OR REPLACE INTO visits(id, joined_by, visitor, start_ms, end_ms, created_ms) "
                "VALUES(?,?,?,?,?,?)", (visit_id, JOINED_BY, visitor, start, end, start or 0))
    visit_verdict.remerge(con, visit_id)
