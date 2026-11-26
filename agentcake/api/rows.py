"""Each session as the lists show it (SessionSummary in web/src/data/types.ts): the session list's rows, the
dashboard's latest Agent sessions and the summary at the top of a session's page.

A session is a visit and its tabs (tabs.py); visits.py's docstring says what a row holds. A session of one tab is the
row its tab session always was, key for key. A session of more than one tab is read over all of them: its length runs
from the first recorded event of any tab to the latest end of any (tabs.clock), its pages and its actions are all its
tabs', each tab's actions told by the tab's own verdict (actions.taken), and instead of segments it has tabs, one for
each tab in the order it opened, with who acted when in it on the session's clock (the row draws a line per tab). Its
agent is named by its tabs whose own verdict is the session's (an Agent session's agent tabs, a Script bot session's
bots): the first named one, else Unnamed; agents lists them all, named ones first in the order of their tabs, when there
are more than one.

    summaries(con, rows, now, zone) -> [SessionSummary]   rows: visits.Row of each session, in their order
    runs(con, ids) -> {tab session id: [(t_start, t_end, actor)]}   the stored segments of tab sessions, oldest first
    names(parts, verdict) -> [(name, certainty)]          the agents a session's tabs name: named ones first, in the
                                                          order of their tabs, then None (Unnamed) if one is unnamed
    tracks(parts, stored, epoch, length) -> [TabTrack]    each tab's stretch and runs, on the session's clock
"""
from agentcake.api import periods, tabs, visits

VERIFIED = "verified"  # data/api.json certainty: a name checked by a signature or a published address range


def summaries(con, rows, now, zone):
    from agentcake.api import actions  # it reads visits.py, which imports this module when first needed
    found = tabs.parts(con, [row.id for row in rows])
    ids = [part.id for listed in found.values() for part in listed]
    stored, pages = runs(con, ids), _addresses(con, ids)
    out = []
    for row in rows:
        listed = found[row.id]
        epoch, length = tabs.clock(listed)
        taken = [action for part in listed
                 for action in actions.taken(con, part.id, part.verdict, part.turns, stored.get(part.id, []))]
        named = names(listed, row.verdict)
        agent, certainty = named[0] if named else (None, None)
        summary = {"id": row.id, "verdict": row.verdict, "evidence": row.evidence, "agent_turns": row.turns,
                   "agent": agent, "certainty": certainty, "when": periods.when(row.start_ms, now, zone),
                   "duration_ms": length,
                   "pages": sum(visits.page_count(pages.get(part.id, {})) for part in listed),
                   "share": actions.share(taken)}
        if len(listed) == 1 and stored.get(listed[0].id):
            summary["segments"] = visits.relative(stored[listed[0].id], epoch, length)
        if row.origin == visits.DEMO_SHOP:
            summary["demo_shop"] = True
        if len(listed) > 1:
            summary["tabs"] = tracks(listed, stored, epoch, length)
        if len(named) > 1:
            summary["agents"] = [{"name": name, "certainty": sure} for name, sure in named]
        out.append(summary)
    return out


def names(listed, verdict):
    """The agents the parts name (see the module docstring); a name read verified in any of its tabs is verified."""
    found = {}
    for part in listed:
        if part.verdict == verdict and verdict in visits.NAMED_VERDICTS:
            name = visits.agent_of(part.verdict, part.detail)
            sure = visits.certainty_of(part.verdict, part.detail)
            if name not in found or sure == VERIFIED:
                found[name] = sure
    named = [(name, sure) for name, sure in found.items() if name is not None]
    return named + ([(None, None)] if None in found else [])


def tracks(listed, stored, epoch, length):
    """[{"start_ms", "end_ms", "segments"}]: each tab, Tab 1 first, from its first part's first recorded event to its
    last part's end, with the runs of all its parts, on the session's clock (0 … length)."""
    out = {}
    for part in listed:
        start = int(min(max(0, part.epoch - epoch), length))
        end = int(min(length, tabs.end_of(part) - epoch))
        track = out.setdefault(part.tab, {"start_ms": start, "end_ms": end, "segments": []})
        track["start_ms"], track["end_ms"] = min(track["start_ms"], start), max(track["end_ms"], end)
        track["segments"] += visits.relative(stored.get(part.id, []), epoch, length)
    return [out[number] for number in sorted(out)]


def runs(con, ids):
    out = {}
    if ids:
        for session_id, t_start, t_end, actor in con.execute(f"SELECT session_id, t_start, t_end, actor FROM segments "
                                                             f"WHERE session_id IN ({_in(ids)}) ORDER BY session_id, "
                                                             "t_start", ids):
            out.setdefault(session_id, []).append((t_start, t_end, actor))
    return out


def _addresses(con, ids):
    """{session id: visits.addresses()} of the tab sessions, in one query."""
    found = {}
    if ids:
        for session_id, pv, t, url in con.execute(f"SELECT session_id, pv, t, url FROM batches WHERE session_id IN "
                                                  f"({_in(ids)}) AND url IS NOT NULL ORDER BY session_id, pv, seq", ids):
            found.setdefault(session_id, []).append((pv, t, url))
    return {session_id: visits.addresses(rows) for session_id, rows in found.items()}


def _in(ids):
    return ",".join("?" * len(ids))
