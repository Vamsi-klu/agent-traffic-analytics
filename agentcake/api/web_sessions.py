"""The dashboard's sessions (api/web.py): one dict per session with what its numbers are made of.

A session is a visit and its tabs (tabs.py). Its verdict is the visit's; its agents are named as the session list names
them (rows.names: the tabs whose own verdict is the session's, one name each); its page views are all its tabs'
(web_time.py); its visitor (and the identify hash it carried, the first of its tabs that carried one), its source and
entry page, its device and its place are its first tab's (the source and the entry page are the first tab's; the
device and the place are the browser's, which its tabs share). Its active time is Microsoft Clarity's over all its tabs:
the time the website was in front, the union of the stretches each tab's page was shown, never their sum; its time
runs from the first record of any tab to the last (web_time.session_active, which `agentcake session-counts` counts
by too). A session of one tab keeps the numbers it always had, from its own session_web row (web_time.active).

    load(con, scope) -> [{"id", "verdict", "agents", "visitor", "person", "page_views", "start_ms", "time",
                          <dimension>: key}]   time: (active_ms, total_ms), or None without a time
"""
from collections import namedtuple

from agentcake import web_time
from agentcake.api import rows, visits, web_dimensions

TAB_COLUMNS = ("v.id, ps.id, cake_verdict(ps.verdict_class, ps.verdict), ps.verdict_detail, pw.person, "
               "(SELECT COALESCE(SUM(p.views), 0) FROM web_paths p WHERE p.session_id = ps.id), pw.first_t, "
               "pw.last_t, pw.hidden_ms, pw.hidden_since")
Tab = namedtuple("Tab", "visit id verdict detail person views first_t last_t hidden_ms hidden_since")


def load(con, scope):
    with visits.snapshot(con):
        return _load(con, scope)


def _load(con, scope):
    keys = [f"{expression} AS {dimension}" for dimension, expression in web_dimensions.EXPRESSIONS.items()]
    cursor = con.execute(f"SELECT v.id AS id, {visits.VERDICT} AS verdict, w.visitor AS visitor, w.person AS person, "
                         f"v.start_ms AS start_ms, {', '.join(keys)} FROM {visits.SESSIONS} LEFT JOIN session_web w "
                         f"ON w.session_id = s.id WHERE {scope.sql()}", scope.args)
    names = [column[0] for column in cursor.description]
    sessions = [dict(zip(names, row)) for row in cursor]
    tabs_of = {}
    for row in con.execute(f"SELECT {TAB_COLUMNS} FROM {visits.SESSIONS} {visits.TABS} WHERE {scope.sql()} "
                           "ORDER BY v.id, ps.start_ms, ps.id", scope.args):
        tabs_of.setdefault(row[0], []).append(Tab._make(row))
    for session in sessions:
        listed = tabs_of[session["id"]]
        session["page_views"] = sum(tab.views for tab in listed)
        session["person"] = session["person"] or next((tab.person for tab in listed if tab.person), None)
        session["agents"] = [name for name, _ in rows.names(listed, session["verdict"])]
        times = [(tab.id, tab.first_t, tab.last_t, tab.hidden_ms, tab.hidden_since) for tab in listed]
        session["time"] = web_time.session_active(con, times)
    return sessions
