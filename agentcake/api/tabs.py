"""A session's tabs: the tab sessions of one visit, numbered as the session's row and page name them.

A session is a visit (the visits table, visit_join.py): the tab sessions of one browser's tabs, joined while no 30
minutes pass without activity in any of them, 24 hours at most, as PostHog's sessions are. Each tab session is still
judged, replayed and stored on its own. A visit's tabs are its tab sessions that count as a visit of the site (not a
self-check, another site's upload or a prefetch the browser never showed: visits.tab_counts()), oldest first. They are
numbered by the tab cake.js named (session_web.window_id, its w), in the order each tab first opened: a tab that went
quiet for 30 minutes while another was in use, and then went on, is one tab in two tab sessions, which share its number;
a tab session without a w (an older cake.js, another script, a session recorded before 0.6.2) is a tab of its own.

A tab session in no visit yet (the upgrade places an older AgentCake's in the background: visit_upgrade.py) is a
session of its own, its id the session's, as it was before sessions spanned tabs (visits.py).

The session's clock starts at the first recorded event of any of its tab sessions and runs to the latest end of any
of them (each one's end as end_of() measures it), so every tab's segments, pages, actions and replay
sit on one clock; a session of one tab keeps the clock it always had.

    Part                                      one tab session of a visit (see PART_COLUMNS), with its tab number
    parts(con, session_ids) -> {session id: [Part]}   each session's tab sessions that count, oldest first,
                                              numbered
    clock(parts) -> (epoch, length)           the session's clock: where it starts (epoch ms) and how long it runs
    end_of(part) -> epoch ms                  where a tab session's recording ends
    resolve(con, address_id) -> (session id, tab session id or None) or None
                                              the session an address names: a visit's id, or a tab session's (an
                                              address from before a session spanned tabs), which also names that tab;
                                              a tab session in no visit yet is its own session
"""
from collections import namedtuple

from agentcake.api import visits

PART_COLUMNS = (f"s.id, w.window_id, s.start_ms, s.origin, s.verdict_class, s.verdict, {visits.TAB_VERDICT}, "
                f"{visits.TAB_TURN}, {visits.TAB_THIN}, s.verdict_detail, {visits.RECORDING}")
Part = namedtuple("Part", "visit id window start_ms origin verdict_class old_verdict verdict turns evidence detail "
                          "epoch last_action replay_end segments_end tab", defaults=(None,))


def parts(con, session_ids):
    """{session id: [Part]}: each session's tab sessions that count, oldest first (start_ms, then id), numbered by
    tab: a visit's, or a tab session in no visit yet itself."""
    found = {}
    if session_ids:
        marks, ids = ",".join("?" * len(session_ids)), tuple(session_ids)
        for row in con.execute(f"SELECT w.visit_id, {PART_COLUMNS} FROM session_web w JOIN sessions s ON "
                               f"s.id = w.session_id WHERE w.visit_id IN ({marks}) AND {visits.tab_counts('s')} "
                               f"UNION ALL SELECT s.id, {PART_COLUMNS} FROM sessions s LEFT JOIN session_web w ON "
                               f"w.session_id = s.id WHERE s.id IN ({marks}) AND w.visit_id IS NULL AND "
                               f"{visits.tab_counts('s')} ORDER BY visit_id, start_ms, id", ids + ids):
            found.setdefault(row[0], []).append(Part(*row))
    return {session_id: _numbered(listed) for session_id, listed in found.items()}


def _numbered(listed):
    """The parts with their tab numbers: 1 for the first tab to open, each tab session with the window it shares with
    another, or its own when it names none."""
    numbers = {}
    out = []
    for part in listed:
        key = part.window if part.window is not None else ("", part.id)
        numbers.setdefault(key, len(numbers) + 1)
        out.append(part._replace(tab=numbers[key]))
    return out


def end_of(part):
    """Where a tab session's recording ends, in epoch ms: its last action, replay event or segment, whichever is
    later, never before it starts (stored times keep the fractions of a millisecond cake.js sends)."""
    return max([part.epoch] + [t for t in (part.last_action, part.replay_end, part.segments_end) if t is not None])


def clock(listed):
    """(epoch, length) of the session these parts make: from the first one's start to the latest end of any, in whole
    ms: a session of one tab has that tab's own clock."""
    epoch = min(part.epoch for part in listed)
    return epoch, int(max(end_of(part) for part in listed) - epoch)


def resolve(con, address_id):
    """(visit id, None) for a visit's id; (its visit id, address_id) for a tab session's id; (address_id, None) for a
    tab session in no visit yet, a session of its own; None for none of these."""
    if con.execute("SELECT 1 FROM visits WHERE id=?", (address_id,)).fetchone():
        return address_id, None
    row = con.execute("SELECT w.visit_id FROM sessions s LEFT JOIN session_web w ON w.session_id = s.id WHERE s.id=?",
                      (address_id,)).fetchone()
    if row is None:
        return None
    return (row[0], address_id) if row[0] else (address_id, None)
