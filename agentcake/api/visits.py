"""The sessions the local pages show: which ones count, the filters, and each one as the lists show it.

Lists and counts leave out self-check visits (is_test), uploads from another site (origin "other") and prefetches
the browser never showed (the verdict class "excluded"). Sessions that an earlier AgentCake's demo shop recorded
(origin "demo", until 0.4.0 removed the shop) are listed and counted as any other and open as they did, marked as the
demo shop's (demo_shop), but they aren't the website's: from_site() leaves them out, so they never say the website is
connected (onboarding.py). A session is sorted as judging.en.json names it:
  1 its verdict, the four layers' class as the contract names it (data/api.json "verdicts"): human, agent (cake's agent
    and mixed) or bot; a session cake 0.3.4 judged and nobody opened since keeps 0.3.4's verdict column. A session cake
    can't tell (Not sure, Too little data, 0.3.4's unsure, not judged yet) is human with evidence "thin" (the
    reasons say why). An Agent session is Agent only or Human + agent (agent_turns: a human and an agent took turns,
    cake's mixed);
  2 its agent: the product's or the automation tool's name and how sure it is (certainty: verified or likely), or
    none when no name fits (the interface says Unnamed; what kind of agent it is and where it runs are in
    its reasons: the Agent row stays inside the verdict). A bot's agent is the program's name.

A session's length on the lists is its recording's (recording_length): from its first recorded event, where its
replay, its timeline and every moment of its page start, to its last action, replay event or segment, whichever is
later: the player's length, as PostHog's replay list shows each recording's. Its share is each actor's share of the actions its page lists under Every action (actions.session_share, the
function the session page uses), whole percents that add up to 100, all 0 without an action; its segments, when the
behaviour model split it into runs, place each run on its recording's clock; its pages are the pages its page lists
(page_count: each page view, and each new address a single-page app shows in one; a cake 0.3.4 visit has one).

SQLite functions registered on each connection keep these rules in Python and the filtering in SQL: cake_verdict(class,
0.3.4 verdict), cake_turns(class, 0.3.4 verdict), cake_evidence(class, 0.3.4 verdict), cake_agent(verdict, detail) and
cake_certainty(verdict, detail).

    connect()                          a database connection with those functions
    Scope()                            the WHERE of a query over `sessions s`, built with between(), group(), agent(),
                                       from_site(), before(); every scope starts from the sessions that count
    total(con, scope)                  how many sessions a scope holds
    page(con, scope, limit, now, zone) ([SessionSummary], [(start_ms, id)]): newest first, times in AgentCake's
                                       timezone (periods.py)
    counts(con, scope)                 SessionCounts
    agents(con, scope)                 [(agent, sessions)] of the Agent sessions, most first; agent None: Unnamed
    first_event(con, session_id)       when the session's first recorded event happened (events' clock), or None
    recording(con, session_id)         (epoch, length) of the session's recording: where its clock starts, how long
    addresses(rows)                    {page view: [(t, path)]}: the pages each page view showed (pages.py lists them)
    page_path(url)                     the page an address names, as the lists show it: path and query
    whole_percents(values)             whole percents adding up to 100 (largest remainder), all 0 for nothing
"""
import json
import math
from collections import namedtuple
from urllib.parse import urlsplit

from agentcake import store
from agentcake.api import periods
from agentcake.api.answers import numbers
from agentcake.session_replay import STREAM
from agentcake.units import PERCENT

WHO = ("human", "agent", "unsure")
VERDICTS = ("human", "agent", "bot")  # judging.en.json's verdicts
TURNS = ("agent_only", "human_agent")  # an Agent session's split
EVIDENCE = ("thin",)  # a Human session cake could not tell: marked
GROUPS = ("all",) + VERDICTS + TURNS + EVIDENCE  # the session list's filters and counts
AGENT_VERDICT, BOT = "agent", "bot"
NAMED_VERDICTS = (AGENT_VERDICT, BOT)

VERDICT = "cake_verdict(s.verdict_class, s.verdict)"
TURN = "cake_turns(s.verdict_class, s.verdict)"
THIN = "cake_evidence(s.verdict_class, s.verdict)"
AGENT = f"cake_agent({VERDICT}, s.verdict_detail)"
CERTAINTY = f"cake_certainty({VERDICT}, s.verdict_detail)"
SHOWN = f"s.is_test = 0 AND COALESCE(s.origin, 'site') != 'other' AND {VERDICT} IS NOT NULL"
DEMO_SHOP = "demo"  # the origin of the sessions an earlier AgentCake's demo shop recorded (until 0.4.0)
FROM_SITE = f"COALESCE(s.origin, 'site') != '{DEMO_SHOP}'"  # of the shown sessions, the website's own
IN_AGENT = f"{VERDICT} = '{AGENT_VERDICT}'"
_RECORDED = ("(SELECT {agg}(t) FROM (SELECT {agg}({chunk}) AS t FROM chunks WHERE session_id = s.id "
             "UNION ALL SELECT {agg}({chunk}) FROM open_chunks WHERE session_id = s.id "
             "UNION ALL SELECT {agg}(ts) FROM events WHERE session_id = s.id))")
FIRST_EVENT = _RECORDED.format(agg="MIN", chunk="t_start")
EPOCH = f"COALESCE({FIRST_EVENT}, s.start_ms)"  # where a session's recording, and its clock, start
REPLAY_END = (f"(SELECT MAX(t) FROM (SELECT MAX(t_end) AS t FROM chunks WHERE session_id = s.id AND stream = '{STREAM}' "
              f"UNION ALL SELECT MAX(t_end) FROM open_chunks WHERE session_id = s.id AND stream = '{STREAM}'))")
SEGMENTS_END = "(SELECT MAX(t_end) FROM segments WHERE session_id = s.id)"
RECORDING = f"{EPOCH}, s.last_action_ms, {REPLAY_END}, {SEGMENTS_END}"  # recording_length()'s epoch and ends
COLUMNS = f"s.id, s.start_ms, s.origin, {VERDICT}, {TURN}, {THIN}, {AGENT}, {CERTAINTY}, {RECORDING}"
Row = namedtuple("Row", "id start_ms origin verdict turns evidence agent certainty epoch last_action replay_end "
                 "segments_end")


def connect():
    con = store.db()
    for name, function in (("cake_verdict", verdict_of), ("cake_turns", turns_of), ("cake_evidence", evidence_of),
                           ("cake_agent", agent_of), ("cake_certainty", certainty_of)):
        con.create_function(name, -1, function, deterministic=True)  # -1: SQLite passes the arguments as given
    return con


def verdict_of(verdict_class, old_verdict):
    """The contract's verdict (level 1); None for a prefetch that was no visit."""
    verdicts = numbers()["verdicts"]
    if verdict_class:
        return verdicts.get(verdict_class)
    return verdicts[old_verdict] if old_verdict in verdicts else verdicts["unsure"]


def turns_of(verdict_class, old_verdict):
    """An Agent session's split: agent_only, or human_agent for cake's mixed; None for any other session."""
    return numbers()["agent_turns"].get(verdict_class or old_verdict)


def evidence_of(verdict_class, old_verdict):
    """thin for a session cake could not tell, which the contract counts as human; None for any other."""
    return numbers()["evidence"].get(verdict_class or old_verdict or "unsure")


def _named(verdict, detail):
    """The verdict's detail when it names an agent or a bot, else None."""
    if verdict not in NAMED_VERDICTS or not detail:
        return None
    found = json.loads(detail)
    return found if found.get("display_name") else None


def agent_of(verdict, detail):
    """The agent's or the bot's name; None when no product name fits (Unnamed) or the session has no agent."""
    named = _named(verdict, detail)
    return named["display_name"] if named else None


def certainty_of(verdict, detail):
    """How sure the name is (level 3): verified or likely; None without a name."""
    named = _named(verdict, detail)
    return numbers()["certainty"].get(named.get("name_certainty")) if named else None


class Scope:
    """Conditions on `sessions s` and their arguments; each method returns a narrower scope."""

    def __init__(self, conditions=(SHOWN,), args=()):
        self.conditions, self.args = tuple(conditions), tuple(args)

    def where(self, condition, *args):
        return Scope(self.conditions + (condition,), self.args + args)

    def sql(self):
        return " AND ".join(self.conditions)

    def between(self, start, end=None):
        scope = self if start is None else self.where("s.start_ms >= ?", start)
        return scope if end is None else scope.where("s.start_ms < ?", end)

    def group(self, group):
        """One of the session list's groups (GROUPS): a verdict, a split of Agent, or Human on thin evidence."""
        if group in (None, "all"):
            return self
        if group in TURNS:
            return self.where(f"{TURN} = ?", group)
        if group in EVIDENCE:
            return self.where(f"{THIN} = ?", group)
        return self.where(f"{VERDICT} = ?", group)

    def agent(self, name):
        return self.where(f"{AGENT} = ?", name) if name else self

    def from_site(self):
        """Only the website's own sessions: not those an earlier AgentCake's demo shop recorded."""
        return self.where(FROM_SITE)

    def before(self, key):
        """After the row (start_ms, id) in newest-first order: the next page."""
        start_ms, session_id = key
        return self.where("(s.start_ms < ? OR (s.start_ms = ? AND s.id < ?))", start_ms, start_ms, session_id)


def page(con, scope, limit, now, zone):
    rows = [Row._make(row) for row in con.execute(f"SELECT {COLUMNS} FROM sessions s WHERE {scope.sql()} ORDER BY "
                                                   "s.start_ms DESC, s.id DESC LIMIT ?", scope.args + (limit,))]
    return _summaries(con, rows, now, zone), [(row.start_ms, row.id) for row in rows]


def counts(con, scope):
    out = dict.fromkeys(GROUPS, 0)
    for verdict, turns, evidence, n in con.execute(f"SELECT {VERDICT}, {TURN}, {THIN}, COUNT(*) FROM sessions s WHERE "
                                                   f"{scope.sql()} GROUP BY 1, 2, 3", scope.args):
        out["all"] += n
        out[verdict] += n
        for group in (turns, evidence):
            if group:
                out[group] += n
    return out


def total(con, scope):
    return con.execute(f"SELECT COUNT(*) FROM sessions s WHERE {scope.sql()}", scope.args).fetchone()[0]


def agents(con, scope):
    return con.execute(f"SELECT {AGENT}, COUNT(*) FROM sessions s WHERE {scope.sql()} AND {IN_AGENT} "
                       "GROUP BY 1 ORDER BY 2 DESC, 1", scope.args).fetchall()


def first_event(con, session_id):
    return con.execute(f"SELECT {FIRST_EVENT} FROM sessions s WHERE s.id = ?", (session_id,)).fetchone()[0]


def recording(con, session_id):
    """(epoch, length) of a session's recording (recording_length), read as the lists read it."""
    epoch, *ends = con.execute(f"SELECT {RECORDING} FROM sessions s WHERE s.id = ?", (session_id,)).fetchone()
    return epoch, recording_length(epoch, ends)


def recording_length(epoch, ends):
    """How long a recording that starts at epoch runs: to the latest of ends (its last action, last replay event and
    last segment's end), in whole ms (stored times keep the fractions of a millisecond cake.js sends)."""
    return int(max([epoch] + [t for t in ends if t is not None]) - epoch)


def addresses(rows):
    """{page view: [(t, path)]} from batch rows (page view, t, url) in the order cake.js numbered them: each page view's
    first address, then each address that differs from the batch before it (a single-page app's new page; a change
    without a time can't be placed)."""
    out = {}
    for pv, t, url in rows:
        path, history = page_path(url), out.setdefault(pv, [])
        if not history or (path != history[-1][1] and t is not None):
            history.append((t, path))
    return out


def page_count(found):
    """How many pages a session's page lists, from its addresses(): one at least (its own address)."""
    return max(1, sum(len(history) for history in found.values()))


def page_path(url):
    """The path and query of an address (no scheme, host or fragment); an address that cannot be read, as it is."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    return (parts.path or "/") + ("?" + parts.query if parts.query else "")


def whole_percents(values):
    total = sum(values)
    if not total:
        return [0] * len(values)
    exact = [value * PERCENT / total for value in values]
    whole = [math.floor(share) for share in exact]
    for index in sorted(range(len(values)), key=lambda i: whole[i] - exact[i])[:PERCENT - sum(whole)]:
        whole[index] += 1
    return whole


def _summaries(con, rows, now, zone):
    from agentcake.api import actions  # it reads this module's helpers: imported when first needed
    runs = _runs(con, [row.id for row in rows])
    pages = _addresses(con, [row.id for row in rows])
    out = []
    for row in rows:
        length = recording_length(row.epoch, (row.last_action, row.replay_end, row.segments_end))
        summary = {"id": row.id, "verdict": row.verdict, "evidence": row.evidence, "agent_turns": row.turns,
                   "agent": row.agent, "certainty": row.certainty, "when": periods.when(row.start_ms, now, zone),
                   "duration_ms": length, "pages": page_count(pages.get(row.id, {})),
                   "share": actions.session_share(con, row.id, row.verdict, row.turns, runs.get(row.id, []))}
        if runs.get(row.id):
            summary["segments"] = relative(runs[row.id], row.epoch, length)
        if row.origin == DEMO_SHOP:
            summary["demo_shop"] = True
        out.append(summary)
    return out


def _addresses(con, ids):
    """{session id: addresses()} of the sessions, in one query."""
    found = {}
    if ids:
        for session_id, pv, t, url in con.execute(f"SELECT session_id, pv, t, url FROM batches WHERE session_id IN "
                                                  f"({_in(ids)}) AND url IS NOT NULL ORDER BY session_id, pv, seq", ids):
            found.setdefault(session_id, []).append((pv, t, url))
    return {session_id: addresses(rows) for session_id, rows in found.items()}


def relative(runs, origin, length):
    """Stored runs (t_start, t_end, actor) as contract segments: ms from origin, inside 0 … length."""
    out = []
    for t_start, t_end, who in runs:
        start = min(max(0, t_start - origin), length)
        out.append({"who": who, "start_ms": int(start), "end_ms": int(min(max(start, t_end - origin), length))})
    return out


def _in(ids):
    return ",".join("?" * len(ids))


def _runs(con, ids):
    out = {}
    if ids:
        for session_id, t_start, t_end, actor in con.execute(f"SELECT session_id, t_start, t_end, actor FROM segments "
                                                             f"WHERE session_id IN ({_in(ids)}) ORDER BY session_id, "
                                                             "t_start", ids):
            out.setdefault(session_id, []).append((t_start, t_end, actor))
    return out
