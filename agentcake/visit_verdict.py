"""A visit's verdict, merged from the verdicts of its tab sessions: the rule the runs of one session are merged by,
applied to the tabs of a visit.

A visit is a session as the dashboard counts one and PostHog defines one: the tab sessions of one browser, joined
while no 30 minutes pass without activity in any of them (visit_join.py). Each tab session is judged on its own, as
before (judging.py), so the behaviour model never sees the actions of two tabs together. A visit's verdict is merged
from the verdicts of its tabs that count:
    a tab with an agent         Agent: class agent (Agent only), or mixed (Human + agent) when a human tab has enough
                                evidence or an agent tab is Human + agent itself
    human tabs only             Human: class human when one of them has enough evidence; a tab on thin evidence (not
                                sure, too little data, cake 0.3.4's unsure, not judged yet) counts for nothing next
                                to it, and next to an agent tab
    thin human tabs only        Human on thin evidence: their class when they all have the same one, else not_sure
    script bot tabs             Script bot only when every tab is one; next to any other tab they decide nothing
A tab that is no visit of the site counts for nothing: a prefetch the browser never showed (class excluded), a
self-check (sessions.is_test) and an upload from another site (sessions.origin other). A visit without any other tab
is no session: its class is excluded.

The class is one that sessions.verdict_class holds, so a visit reads as a tab session does (api/visits.py's
cake_verdict, cake_turns and cake_evidence of the class, with no cake 0.3.4 verdict), and a visit of one tab gets that
tab's class: it reads exactly as the tab session did before visits.

    tab_class(verdict_class, old_verdict) -> class or None   a tab session's class: cake 0.3.4's verdict when it has
                                                             none of its own, None when it was never judged
    merge(classes) -> class or None                          a visit's class, from the classes of its tabs that
                                                             count (tab_class of each)
    counts(is_test, origin) -> bool                          whether a tab session takes part (not a self-check,
                                                             not another site's)
    remerge(con, visit_id) -> class or None                  merge a visit's tabs again and write its verdict_class
    remerge_tab(con, session_id)                             remerge() the visit a tab session belongs to, if any
"""
from agentcake.datafiles import load
from agentcake.detect.verdict import AGENT, BOT, EXCLUDED, HUMAN, MIXED, NOT_SURE
from agentcake.site_origin import OTHER, SITE

CONTRACT = load("data/api.json")  # the classes as the pages read them: the verdict, an Agent's split, thin evidence
VERDICTS, TURNS, EVIDENCE = CONTRACT["verdicts"], CONTRACT["agent_turns"], CONTRACT["evidence"]
NEVER_JUDGED = "unsure"  # how api/visits.py reads a tab session without any verdict: Human on thin evidence
COUNTS = f"s.is_test = 0 AND COALESCE(s.origin, '{SITE}') != '{OTHER}'"  # a tab of a visit of the site
TAB_CLASSES = ("SELECT s.verdict_class, s.verdict FROM session_web w JOIN sessions s ON s.id = w.session_id "
               f"WHERE w.visit_id = ? AND {COUNTS}")


def tab_class(verdict_class, old_verdict):
    """The class a tab session is read by: its own, else the verdict cake 0.3.4 gave it, else None (not judged)."""
    return verdict_class or (old_verdict if old_verdict in VERDICTS else None)


def merge(classes):
    """The class of a visit whose counting tabs have these classes (tab_class of each; see the module docstring)."""
    counted = [cls for cls in classes if _verdict(cls) is not None]
    if not counted:
        return EXCLUDED
    agents = [cls for cls in counted if _verdict(cls) == VERDICTS[AGENT]]
    humans = [cls for cls in counted if _verdict(cls) == VERDICTS[HUMAN]]
    sure = [cls for cls in humans if not _thin(cls)]
    if agents:
        took_turns = bool(sure) or any(TURNS.get(cls) == TURNS[MIXED] for cls in agents)
        return MIXED if took_turns else AGENT
    if sure:
        return HUMAN
    if humans:
        return humans[0] if len(set(humans)) == 1 else NOT_SURE
    return BOT


def counts(is_test, origin):
    """Whether a tab session takes part in its visit's verdict: COUNTS, for a row already read."""
    return not is_test and (origin or SITE) != OTHER


def remerge(con, visit_id):
    """Merge the classes of a visit's counting tabs and write them as its verdict_class; returns the class."""
    found = merge(tab_class(cls, old) for cls, old in con.execute(TAB_CLASSES, (visit_id,)))
    con.execute("UPDATE visits SET verdict_class=? WHERE id=?", (found, visit_id))
    return found


def remerge_tab(con, session_id):
    """remerge() the visit of a tab session whose verdict changed; nothing for a tab session not in a visit yet."""
    row = con.execute("SELECT visit_id FROM session_web WHERE session_id=?", (session_id,)).fetchone()
    if row and row[0]:
        remerge(con, row[0])


def _verdict(cls):
    """The verdict a class reads as (human, agent or bot); None for a class that is no visit (a prefetch)."""
    return VERDICTS.get(cls or NEVER_JUDGED)


def _thin(cls):
    return EVIDENCE.get(cls or NEVER_JUDGED) is not None
