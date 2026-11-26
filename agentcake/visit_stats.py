"""`agentcake session-counts [--db FILE]`: a database's sessions counted both ways, one per tab (AgentCake before 0.6.2)
and across tabs (0.6.2), changing nothing: the dashboard's numbers before and after the change.

It opens the database read only (immutable when no AgentCake runs on its folder and no write-ahead log holds anything:
SQLite then touches no file at all; beside a running AgentCake, read only as SQLite's readers read). One per tab, it
counts the tab sessions that count, as the dashboard did: not a self-check, not another site's, not a prefetch the
browser never showed (api/visits.py). Across tabs, it joins every tab session the way 0.6.2 does, whatever the database
holds of visits so far, so it counts an older AgentCake's database the way 0.6.2 will once it has upgraded it: those
whose uploads carried a browser session id are its session; the others are joined by their visitor id (visit_join.join);
one without a visitor id is a session of its own. A session counts when one of its tab sessions does; its verdict is
merged from theirs (visit_verdict.merge), its numbers are theirs, and it begins when its first tab session began
(sessions.start_ms).

For the dashboard's default range, the last 7 days (api/periods.py, in AgentCake's timezone), and for all time, it
prints as JSON, one per tab and across tabs:
    sessions            all; with a visitor id (the ones the collector can join without a bs); human, with limited
                        evidence among them; agent, agent only and human + agent among them; script bot
    agent_share_pct     agent sessions in all, in percent
    visitors            the distinct visitors of the sessions, and of the human, agent and script bot ones (a visitor
                        counts as the identify hash it was first sent with, as on the dashboard: api/web.py)
    page_views          all, and of the human, agent and script bot sessions
    pages_per_session   page views / sessions, all and by verdict
    active_time_ms      the average active time of a session in whole ms, the dashboard's (web_time.session_active:
                        the time its tabs' pages were shown, together; a moment two tabs were both shown counts once),
                        and
    time_ms             its average time, from the first record of its tabs to the last, all and by verdict
    tabs                the sessions of several tab sessions, the tab sessions in them, and the most in one
It prints no id, address, place, path or name: counts only. While it reads, CAKE_HOME is the database's folder, so
that the replay chunks a session's active time is read from (web_time.visible_spans) are that folder's, as are the
settings (the timezone).

    counts(con, now_ms, zone) -> {range: {"one_per_tab": block, "across_tabs": block}}
    main(path) -> exit code
"""
import contextlib
import json
import os
import pathlib
import sqlite3
from collections import Counter

from agentcake import daemon, paths, timezone, visit_join, visit_verdict, web_time
from agentcake.api import periods, web
from agentcake.config import JSON_INDENT, load_cfg
from agentcake.detect.verdict import AGENT, BOT, EXCLUDED, HUMAN
from agentcake.storage_config import now_ms as clock_ms
from agentcake.units import PERCENT

RANGES = ("7d", periods.ALL_TIME)  # the dashboard's default range, and every session
WAL_SUFFIX = "-wal"  # protocol: SQLite's write-ahead log is the database's name + "-wal"
READ_ONLY, IMMUTABLE = "mode=ro", "&immutable=1"  # protocol: SQLite URI parameters
CONTRACT = visit_verdict.CONTRACT
GROUPS = {"human": CONTRACT["verdicts"][HUMAN], "agent": CONTRACT["verdicts"][AGENT],
          "script_bot": CONTRACT["verdicts"][BOT]}
THIN, AGENT_ONLY, HUMAN_AGENT = "thin", "agent_only", "human_agent"  # protocol: data/api.json's evidence and turns
ACTIVE, SPAN = 0, 1  # what web_time.session_active gives: the active time, then the time
HOME_VARIABLE = "CAKE_HOME"  # protocol: the variable paths.home() reads
# One row per tab session, counting or not (each joins tabs as the collector joins them; `counts` says which count).
# The browser session id is read only where the database has the column (0.6.2).
TAB_ROWS = ("SELECT s.id, s.start_ms, s.verdict_class, s.verdict, s.is_test, s.origin, w.visitor, w.person, "
            "{named} AS named, COALESCE(w.active_from, w.first_t), "
            "COALESCE(w.active_last, w.last_t, w.active_from, w.first_t), w.first_t, w.last_t, w.hidden_ms, "
            "w.hidden_since, (SELECT COALESCE(SUM(p.views), 0) FROM web_paths p WHERE p.session_id = s.id) "
            "FROM sessions s LEFT JOIN session_web w ON w.session_id = s.id")


def main(path=None):
    """Print the counts of the database at path (default: this data folder's); returns the exit code."""
    path = path or paths.db_file()
    if not os.path.isfile(path):
        print(f"no database at {paths.tilde(path)}")
        return 1
    with _home_of(path):
        con = connect_readonly(path)
        try:
            found = counts(con, clock_ms(), timezone.chosen(load_cfg()))
        finally:
            con.close()
    print(json.dumps(found, indent=JSON_INDENT))
    return 0


@contextlib.contextmanager
def _home_of(path):
    """CAKE_HOME set to the folder of the database at path while it is read (see the module docstring)."""
    before = os.environ.get(HOME_VARIABLE)
    os.environ[HOME_VARIABLE] = os.path.dirname(os.path.abspath(path))
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(HOME_VARIABLE)
        else:
            os.environ[HOME_VARIABLE] = before


def connect_readonly(path):
    """A read-only connection; immutable (SQLite then touches no file) only when nothing writes the database meanwhile:
    no write-ahead log holds anything (none, or an empty one) and no AgentCake runs on its folder (daemon.running_here;
    CAKE_HOME is that folder while it reads). A running AgentCake closes its last connection after an upload, which
    writes the log into the database and removes it, so a missing log alone is no sign; read only, SQLite reads beside
    the writer the way its readers do, what the log holds included."""
    wal = path + WAL_SUFFIX
    written = (os.path.exists(wal) and os.path.getsize(wal)) or daemon.running_here()
    mode = READ_ONLY if written else READ_ONLY + IMMUTABLE
    return sqlite3.connect(f"{pathlib.Path(os.path.abspath(path)).as_uri()}?{mode}", uri=True)


def counts(con, now_ms, zone):
    tabs = _tabs(con)
    sessions = _across_tabs(tabs)
    out = {}
    for range_key in RANGES:
        start = periods.window(range_key, now_ms, zone)[0]
        in_range = (lambda unit: True) if start is None else (lambda unit: unit["start_ms"] >= start)
        out[range_key] = {"one_per_tab": _block(con, [[tab] for tab in tabs if tab["counts"] and in_range(tab)],
                                                _one_tab),
                          "across_tabs": _block(con, [unit for unit in sessions if in_range(unit)], None)}
    return out


def _tabs(con):
    columns = {row[1] for row in con.execute("PRAGMA table_info(session_web)")}
    named = "w.browser_session" if "browser_session" in columns else "NULL"
    hashes = web.first_hashes(con)  # the dashboard's own rule
    tabs = []
    for row in con.execute(TAB_ROWS.format(named=named)):
        (session_id, start_ms, cls, old, is_test, origin, visitor, person, named_by, start, end, first_t, last_t,
         hidden_ms, hidden_since, views) = row
        found = visit_verdict.tab_class(cls, old)
        person = person or hashes.get(visitor)
        tabs.append({"id": session_id, "start_ms": start_ms, "cls": found, "visitor": visitor, "named": named_by,
                     "counts": visit_verdict.counts(is_test, origin) and visit_verdict.merge([found]) != EXCLUDED,
                     "counted_as": ("person", person) if person else ("visitor", visitor) if visitor else None,
                     "start": start, "end": end, "times": web_time.TabTime(session_id, first_t, last_t, hidden_ms,
                                                                           hidden_since), "views": views})
    return tabs


def _across_tabs(tabs):
    """Every tab session joined into sessions across tabs; those with a tab session that counts, each as {"tabs": the
    ones that count, "start_ms": when its first tab session began, "cls": their merged class}."""
    by_key = {}
    for tab in tabs:
        key = (("named", tab["named"]) if tab["named"] else
               ("visitor", tab["visitor"]) if tab["visitor"] and tab["start"] is not None else ("alone", tab["id"]))
        by_key.setdefault(key, []).append(tab)
    units = []
    for (kind, _), group in by_key.items():
        if kind != "visitor":
            units.append(group)
            continue
        rows = {tab["id"]: tab for tab in group}
        joined = visit_join.join([visit_join.Tab(tab["id"], tab["start"], tab["end"], None, None, None, tab["cls"],
                                                 True) for tab in group])
        units += [[rows[tab.id] for tab in joined_tabs] for joined_tabs in joined]
    return [{"tabs": [tab for tab in unit if tab["counts"]], "start_ms": min(tab["start_ms"] for tab in unit),
             "cls": visit_verdict.merge(tab["cls"] for tab in unit if tab["counts"])}
            for unit in units if any(tab["counts"] for tab in unit)]


def _one_tab(unit):
    """A tab session as a session of its own: the shape _across_tabs gives one."""
    (tab,) = unit
    return {"tabs": unit, "start_ms": tab["start_ms"], "cls": tab["cls"]}


def _block(con, units, shape):
    sessions = [shape(unit) if shape else unit for unit in units]
    for session in sessions:
        session["time"] = web_time.session_active(con, [tab["times"] for tab in session["tabs"]])
        cls = session["cls"]
        session["verdict"] = CONTRACT["verdicts"].get(cls or visit_verdict.NEVER_JUDGED)
        session["turns"] = CONTRACT["agent_turns"].get(cls)
        session["thin"] = CONTRACT["evidence"].get(cls or visit_verdict.NEVER_JUDGED) == THIN
    of = {group: [s for s in sessions if s["verdict"] == verdict] for group, verdict in GROUPS.items()}
    agents = of["agent"]
    several = [len(s["tabs"]) for s in sessions if len(s["tabs"]) > 1]
    return {"sessions": {"all": len(sessions), "with_visitor_id": sum(1 for s in sessions if s["tabs"][0]["visitor"]),
                         "human": len(of["human"]), "human_limited_evidence": sum(1 for s in of["human"] if s["thin"]),
                         "agent": len(agents), "agent_only": sum(1 for s in agents if s["turns"] == AGENT_ONLY),
                         "human_agent": sum(1 for s in agents if s["turns"] == HUMAN_AGENT),
                         "script_bot": len(of["script_bot"])},
            "agent_share_pct": _ratio(len(agents) * PERCENT, len(sessions)),
            "visitors": {"all": _visitors(sessions), **{group: _visitors(chosen) for group, chosen in of.items()}},
            "page_views": {"all": _views(sessions), **{group: _views(chosen) for group, chosen in of.items()}},
            "pages_per_session": {"all": _ratio(_views(sessions), len(sessions)),
                                  **{group: _ratio(_views(chosen), len(chosen)) for group, chosen in of.items()}},
            "active_time_ms": {"all": _time(sessions, ACTIVE), **{group: _time(chosen, ACTIVE)
                                                                   for group, chosen in of.items()}},
            "time_ms": {"all": _time(sessions, SPAN), **{group: _time(chosen, SPAN) for group, chosen in of.items()}},
            "tabs": {"sessions_with_several": len(several), "tab_sessions_in_them": sum(several),
                     "most_in_one": max(several, default=0), "by_count": dict(sorted(Counter(several).items()))}}


def _visitors(sessions):
    return len({tab["counted_as"] for s in sessions for tab in s["tabs"] if tab["counted_as"]})


def _views(sessions):
    return sum(tab["views"] for s in sessions for tab in s["tabs"])


def _time(sessions, which):
    """The sessions' average active time (ACTIVE) or time (SPAN), whole ms, as the dashboard averages them; None
    without a time."""
    found = [session["time"][which] for session in sessions if session["time"]]
    return round(sum(found) / len(found)) if found else None


def _ratio(part, whole):
    return part / whole if whole else None
