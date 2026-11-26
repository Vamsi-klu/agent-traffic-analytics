"""Joining tab sessions into visits: the sessions the dashboard counts, as PostHog defines them.

cake.js cuts each tab's session (sessions.id: the unit judged, replayed and stored; session_split.py cuts it the same
way for a script that does not) and, since 0.6.2, names in each upload the browser session all the site's tabs in the
browser share (bs) and the tab (w): docs/collect-format.md, "Sessions". A visit is the tab sessions of one browser
session:
  - a tab session whose uploads carried a bs belongs to the visit of that id, the first bs it carried (a later page of
    the tab that an older cake.js ran from the browser's cache sends its uploads without one);
  - one whose uploads carried none (an older cake.js, another script, and every session recorded before 0.6.2) is
    joined by the collector, by the visitor id its uploads carried (static/src/visitor.js: one per browser), with
    posthog-js's rules (sessionid.ts) and the settings the tab sessions are cut by (data/cakejs.json "session"):
    the visitor's tab sessions, in the order their activity began, each joins the visit before it when it began at
    most idle_ms after the latest activity of every tab session before it and at most max_ms after the first one of
    that visit began; else it begins a visit of its own. A tab session joins whole, by when it began: it is never
    split between visits. One without a visitor id, or without any time, is a visit of its own.
A visit the collector joined is named after one of its tab sessions, the one it began with; when a late upload joins
two visits, the one made first keeps its id, and a visit that a late upload splits keeps its id where its tab session
is. The visits are a function of the tab sessions' activity, whatever order the uploads came in: an upload that came
late (one that waited in the browser, or another tab's page left before this one's upload was sent) has its visitor's
tab sessions joined again from the start (regroup), when what it brought can change how they join.

    place(con, session_id, browser_session, window, origin, now_ms)   collect, after keeping an upload: the visit of the
                                         tab session it went to, in the caller's transaction (store.LOCK held)
    regroup(con, visitor, now_ms, unplaced=False, also=None)   join a visitor's tab sessions again from the start: those
                                         in a visit already, the one being placed (also), and with unplaced those in
                                         none yet (the upgrade, visit_upgrade.py, which places them after a backup)
    join(tabs) -> [[Tab]]                the rule itself, on Tab tuples (visit_stats.py counts with it too)
    whole_visits(con, ids) -> [id]       delete.py: the tab sessions of every visit one of ids names
"""
from collections import namedtuple

from agentcake import session_split, store, visit_verdict
from agentcake.datafiles import load
from agentcake.site_origin import OTHER

RULES = load("data/cakejs.json")["script"]["session"]
BROWSER, COLLECTOR = "browser", "collector"  # visits.joined_by: named by the uploads' bs, or joined by the visitor id
# A tab session as the rules read it: when its activity began and ended (on the browser's clock: its first and last
# activity, else its first and last record), its visit so far, the server's start and end, and its verdict and
# whether it counts (visit_verdict.py).
Tab = namedtuple("Tab", "id start end visit start_ms end_ms cls counts")
TABS = ("SELECT w.session_id, COALESCE(w.active_from, w.first_t), "
        "COALESCE(w.active_last, w.last_t, w.active_from, w.first_t), w.visit_id, s.start_ms, s.end_ms, "
        "s.verdict_class, s.verdict, s.is_test, s.origin FROM session_web w JOIN sessions s ON s.id = w.session_id")
Visit = namedtuple("Visit", "id joined_by visitor active_from active_last")


def place(con, session_id, browser_session, window, origin, now_ms):
    """Put the tab session an upload went to in its visit (see the module docstring)."""
    con.execute("UPDATE session_web SET browser_session=COALESCE(browser_session, ?), window_id=COALESCE(window_id, ?) "
                "WHERE session_id=?", (browser_session, window, session_id))
    row = con.execute("SELECT w.visitor, w.browser_session FROM session_web w WHERE w.session_id=?",
                      (session_id,)).fetchone()
    if row is None:
        return
    visitor, named = row
    tab = _tab(con, session_id)
    visit = _visit(con, tab.visit)
    if named:
        _place_named(con, tab, named, visitor, visit, now_ms)
    elif visitor is None or tab.start is None:
        _place_alone(con, tab, visitor, visit, now_ms)
    elif not _placed_at_once(con, tab, visitor, visit, now_ms):
        regroup(con, visitor, now_ms, also=session_id)
        return
    if origin == OTHER:  # a tab that turned out to be another site's counts for nothing any more
        visit_verdict.remerge(con, _tab(con, session_id).visit)


def regroup(con, visitor, now_ms, unplaced=False, also=None):
    """Join a visitor's tab sessions (those without a bs) into visits again from the start, keep the ids the module
    docstring says, and write the visits, their tab sessions and their merged verdicts; a visit left without a tab
    session is deleted."""
    tabs = [_read(row) for row in con.execute(
        f"{TABS} WHERE w.visitor = ? AND w.browser_session IS NULL AND (w.visit_id IS NOT NULL OR ? OR "
        "w.session_id = ?)", (visitor, unplaced, also))]
    timed = [tab for tab in tabs if tab.start is not None]
    groups = join(timed) + [[tab] for tab in tabs if tab.start is None]
    before = sorted({tab.visit for tab in tabs if tab.visit})
    made = {}
    for part in store.parts(before):
        made.update(con.execute(f"SELECT id, created_ms FROM visits WHERE id IN ({_marks(part)})", part))
    for group in groups:  # the visit made first keeps its id; a group of tab sessions all in no visit is named anew
        kept = sorted((made[tab.id], _began(tab), tab.id) for tab in group if tab.id in made)
        visit_id = kept[0][-1] if kept else group[0].id
        _write(con, visit_id, COLLECTOR, visitor, group, made.get(visit_id, now_ms))
    for visit_id in before:
        _drop_if_empty(con, visit_id)


def join(tabs):
    """The rule of the module docstring on Tab tuples with a start: [[Tab, ...], ...], each visit's oldest first."""
    groups, reach = [], None
    for tab in sorted(tabs, key=lambda tab: (tab.start, tab.id)):
        if groups and tab.start - reach <= RULES["idle_ms"] and tab.start - groups[-1][0].start <= RULES["max_ms"]:
            groups[-1].append(tab)
        else:
            groups.append([tab])
        reach = tab.end if reach is None else max(reach, tab.end)
    return groups


def whole_visits(con, ids):
    """The ids, then every tab session of each visit one of them names: a visit's id (a browser session id names
    its visit), a tab session's id, or the id a tab's script sent (session_web.tab_id: every session the collector cut
    from it, session_split.py); each once. A visit's own id that is no tab session's is left out: it stands for its
    tab sessions (an id that names nothing stays, to be reported as such)."""
    found = session_split.with_continuations(con, ids)
    visits = []
    for part in store.parts(found):
        visits += [visit_id for (visit_id,) in con.execute(
            f"WITH named(id) AS (VALUES {','.join(['(?)'] * len(part))}) SELECT DISTINCT visit_id FROM session_web "
            "WHERE visit_id IN (SELECT id FROM named) OR session_id IN (SELECT id FROM named)", part)]
    tabs = []
    for visit_id in dict.fromkeys(visit for visit in visits if visit):
        tabs += [tab for (tab,) in con.execute("SELECT session_id FROM session_web WHERE visit_id=? ORDER BY "
                                               "session_id", (visit_id,))]
    named_visits = set(visits) - set(tabs)
    return list(dict.fromkeys([session_id for session_id in found if session_id not in named_visits] + tabs))


def _place_named(con, tab, named, visitor, visit, now_ms):
    """A tab session whose uploads carried a bs: in the visit of that id."""
    if tab.visit == named:
        _widen(con, named, tab)
        return
    con.execute("INSERT OR IGNORE INTO visits(id, joined_by, visitor, created_ms) VALUES(?,?,?,?)",
                (named, BROWSER, visitor, now_ms))
    con.execute("UPDATE session_web SET visit_id=? WHERE session_id=?", (named, tab.id))
    _widen(con, named, tab)
    visit_verdict.remerge(con, named)
    if visit is None:
        return
    if visit.visitor:  # it was in a visit the collector joined: the others of that visit join again without it
        regroup(con, visit.visitor, now_ms)
    else:
        _drop_if_empty(con, visit.id)


def _place_alone(con, tab, visitor, visit, now_ms):
    """A tab session without a visitor id or without a time yet: a visit of its own, named after it."""
    if visit is None:
        _write(con, tab.id, COLLECTOR, visitor, [tab], now_ms)
    else:
        _widen(con, visit.id, tab)


def _placed_at_once(con, tab, visitor, visit, now_ms):
    """Place a tab session of a visitor without a regroup when what its upload brought cannot change how the visitor's
    tab sessions join: a tab session already in a visit of the visitor, which neither began before that visit did
    nor now reaches a visit that began after the latest activity of its own; or a new one that began no earlier
    than the visitor's latest visit, which it joins or follows. False: the visitor's tab sessions join again."""
    if visit is not None:
        if (visit.joined_by != COLLECTOR or visit.visitor != visitor or visit.active_from is None
                or tab.start < visit.active_from):
            return False
        if tab.end > visit.active_last and _starts_between(con, visitor, visit.id, visit.active_last, tab.end):
            return False
        _widen(con, visit.id, tab)
        return True
    latest = con.execute("SELECT id, active_from FROM visits WHERE visitor=? AND joined_by=? AND active_from IS NOT "
                         "NULL ORDER BY active_from DESC LIMIT 1", (visitor, COLLECTOR)).fetchone()
    if latest is None:
        _write(con, tab.id, COLLECTOR, visitor, [tab], now_ms)
        return True
    latest_id, latest_from = latest
    if tab.start < latest_from:
        return False
    reach = con.execute("SELECT MAX(active_last) FROM visits WHERE visitor=? AND joined_by=?",
                        (visitor, COLLECTOR)).fetchone()[0]
    if tab.start - reach <= RULES["idle_ms"] and tab.start - latest_from <= RULES["max_ms"]:
        con.execute("UPDATE session_web SET visit_id=? WHERE session_id=?", (latest_id, tab.id))
        _widen(con, latest_id, tab)
        visit_verdict.remerge(con, latest_id)
    else:
        _write(con, tab.id, COLLECTOR, visitor, [tab], now_ms)
    return True


def _starts_between(con, visitor, own, after, until):
    """Whether another visit of the visitor began more than idle_ms after `after` and at most idle_ms after `until`:
    one the activity up to `until` now reaches."""
    idle = RULES["idle_ms"]
    return con.execute("SELECT 1 FROM visits WHERE visitor=? AND joined_by=? AND id != ? AND active_from > ? AND "
                       "active_from <= ? LIMIT 1", (visitor, COLLECTOR, own, after + idle, until + idle)).fetchone() \
        is not None


def _write(con, visit_id, joined_by, visitor, group, created_ms):
    """A visit made of these tab sessions: its row (bounds and merged verdict from them), and each one's visit_id."""
    starts = [tab.start for tab in group if tab.start is not None]
    ends = [tab.end for tab in group if tab.end is not None]
    con.execute("INSERT INTO visits(id, joined_by, visitor, start_ms, end_ms, active_from, active_last, verdict_class, "
                "created_ms) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET joined_by=excluded.joined_by, "
                "visitor=excluded.visitor, start_ms=excluded.start_ms, end_ms=excluded.end_ms, "
                "active_from=excluded.active_from, active_last=excluded.active_last, "
                "verdict_class=excluded.verdict_class",
                (visit_id, joined_by, visitor, _least(tab.start_ms for tab in group),
                 _most(tab.end_ms for tab in group), min(starts, default=None), max(ends, default=None),
                 visit_verdict.merge(tab.cls for tab in group if tab.counts), created_ms))
    con.executemany("UPDATE session_web SET visit_id=? WHERE session_id=?",
                    [(visit_id, tab.id) for tab in group if tab.visit != visit_id])


def _widen(con, visit_id, tab):
    """A visit's bounds, widened to a tab session's (whose span only grows)."""
    con.execute("UPDATE visits SET start_ms=COALESCE(MIN(start_ms, :start_ms), start_ms, :start_ms), "
                "end_ms=COALESCE(MAX(end_ms, :end_ms), end_ms, :end_ms), "
                "active_from=COALESCE(MIN(active_from, :start), active_from, :start), "
                "active_last=COALESCE(MAX(active_last, :end), active_last, :end) WHERE id=:visit",
                {"visit": visit_id, "start_ms": tab.start_ms, "end_ms": tab.end_ms, "start": tab.start,
                 "end": tab.end})


def _drop_if_empty(con, visit_id):
    con.execute("DELETE FROM visits WHERE id=? AND NOT EXISTS (SELECT 1 FROM session_web WHERE visit_id=?)",
                (visit_id, visit_id))


def _tab(con, session_id):
    return _read(con.execute(f"{TABS} WHERE w.session_id = ?", (session_id,)).fetchone())


def _read(row):
    session_id, start, end, visit, start_ms, end_ms, cls, old, is_test, origin = row
    return Tab(session_id, start, end, visit, start_ms, end_ms, visit_verdict.tab_class(cls, old),
               visit_verdict.counts(is_test, origin))


def _visit(con, visit_id):
    if visit_id is None:
        return None
    row = con.execute("SELECT id, joined_by, visitor, active_from, active_last FROM visits WHERE id=?",
                      (visit_id,)).fetchone()
    return Visit._make(row) if row else None


def _began(tab):
    """When a tab session's activity began, for sorting: one without a time last."""
    return (tab.start is None, tab.start or 0)


def _least(values):
    return min((value for value in values if value is not None), default=None)


def _most(values):
    return max((value for value in values if value is not None), default=None)


def _marks(values):
    return ",".join("?" * len(values))
