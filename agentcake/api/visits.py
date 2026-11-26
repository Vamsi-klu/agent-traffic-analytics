"""The sessions the local pages show: which ones count, the filters, and each one as the lists show it.

A session is a visit (the visits table, visit_join.py): the tab sessions of one browser's tabs while no 30 minutes pass
without activity in any of them, 24 hours at most, as PostHog's sessions span tabs. Each tab session is judged, replayed
and stored on its own; the visit's verdict is merged from its tabs' (visit_verdict.py) and a list reads it as it read a
tab session's, so a session of one tab is listed exactly as it was before sessions spanned tabs. Its tabs are its tab
sessions that count (tabs.py). Lists and counts leave out self-check visits (is_test), uploads from another site (origin
"other") and prefetches the browser never showed (the verdict class "excluded"): a tab session of these is no tab of its
visit, and a visit with no other tab is no session. A visit is read with its first tab session (`s`, the oldest that
counts), whose address, origin and web analytics row describe the visit as its first tab's do (the source and the entry
page are the first tab's). Sessions that an earlier AgentCake's demo shop recorded (origin "demo", until 0.4.0 removed
the shop) are listed and counted as any other and open as they did, marked as the demo shop's (demo_shop), but they
aren't the website's: from_site() leaves them out, so they never say the website is connected (onboarding.py). A session
is sorted as judging.en.json names it:   1 its verdict, the four layers' class as the contract names it (data/api.json
"verdicts"): human, agent (cake's agent     and mixed) or bot; a session cake 0.3.4 judged and nobody opened since keeps
0.3.4's verdict column. A session cake     can't tell (Not sure, Too little data, 0.3.4's unsure, not judged yet) is
human with evidence "thin" (the     reasons say why). An Agent session is Agent only or Human + agent (agent_turns: a
human and an agent took turns,     cake's mixed);   2 its agent: the product's or the automation tool's name and how
sure it is (certainty: verified or likely), or     none when no name fits (the interface says Unnamed; what kind of
agent it is and where it runs are in     its reasons: the Agent row stays inside the verdict). A bot's agent is the
program's name. The names are its     tabs' whose own verdict is the session's, named ones first (agents, when there are
more than one).

A session's length on the lists is its recording's (tabs.clock): from its first recorded event, where its
replay, its timeline and every moment of its page start, to its last action, replay event or segment, whichever is
later: the player's length, as PostHog's replay list shows each recording's; over all its tabs (tabs.clock). Its share
is each actor's share of the actions its page lists under All actions (actions.taken, the function the session page
uses, in each tab), whole percents that add up to 100, all 0 without an action; its segments, when the
behaviour model split it into runs, place each run on its recording's clock; its pages are the pages its page lists
(page_count: each page view, and each new address a single-page app shows in one; a cake 0.3.4 visit has one), in
all its tabs. A session of more than one tab has no segments but tabs: each tab's runs on the session's clock.

SQLite functions registered on each connection keep these rules in Python and the filtering in SQL: cake_verdict(class,
0.3.4 verdict), cake_turns(class, 0.3.4 verdict), cake_evidence(class, 0.3.4 verdict), cake_agent(verdict, detail) and
cake_certainty(verdict, detail).

    connect()                          a database connection with those functions
    Scope()                            the WHERE of a query over SESSIONS (`visits v`, its first tab session `s`),
                                       built with between(), group(), agent(), from_site(), before(); every scope
                                       starts from the sessions that count
    total(con, scope)                  how many sessions a scope holds
    page(con, scope, limit, now, zone) ([SessionSummary], [(start_ms, id)]): newest first, times in AgentCake's
                                       timezone (periods.py)
    counts(con, scope)                 SessionCounts
    agents(con, scope)                 [(agent, sessions)] of the Agent sessions, most first; agent None: Unnamed; a
                                       session two agents acted in counts for each
    tab_counts(alias)                  SQL: the tab session `alias` counts as a visit of the site
    SESSIONS, TABS                     SQL: the sessions with their first tab session `s` (a visit, or a tab session
                                       in none yet); joined to each of their tab sessions that count, `ps`, and its
                                       session_web row `pw`
    EPOCH, RECORDING                   SQL over a tab session `s`: where its recording, and its clock, start (its first
                                       recorded event, else its start), and the epoch and ends tabs.end_of() reads
    addresses(rows)                    {page view: [(t, path)]}: the pages each page view showed (pages.py lists them)
    page_path(url)                     the page an address names, as the lists show it: path and query
    whole_percents(values)             whole percents adding up to 100 (largest remainder), all 0 for nothing
"""
import contextlib
import json
import math
from collections import namedtuple
from urllib.parse import urlsplit

from agentcake import store
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

TAB_VERDICT = "cake_verdict(s.verdict_class, s.verdict)"  # a tab session's own, as `s`
TAB_TURN = "cake_turns(s.verdict_class, s.verdict)"
TAB_THIN = "cake_evidence(s.verdict_class, s.verdict)"
VERDICT = "cake_verdict(v.verdict_class, v.old_verdict)"  # a session's (a visit's: its merged class, visit_verdict.py)
TURN = "cake_turns(v.verdict_class, v.old_verdict)"
THIN = "cake_evidence(v.verdict_class, v.old_verdict)"
SHOWN = f"{VERDICT} IS NOT NULL"  # not 'excluded': SESSIONS joins only visits with a tab that counts
DEMO_SHOP = "demo"  # the origin of the sessions an earlier AgentCake's demo shop recorded (until 0.4.0)
FROM_SITE = f"COALESCE(s.origin, 'site') != '{DEMO_SHOP}'"  # of the shown sessions, the website's own
IN_AGENT = f"{VERDICT} = '{AGENT_VERDICT}'"


def tab_counts(alias):
    """SQL: the tab session `alias` counts as a visit of the site: not a self-check, not another site's upload, not a
    prefetch the browser never showed."""
    return (f"{alias}.is_test = 0 AND COALESCE({alias}.origin, 'site') != 'other' AND "
            f"cake_verdict({alias}.verdict_class, {alias}.verdict) IS NOT NULL")


# The sessions, `v`: each visit, and each tab session in no visit yet as a session of its own (alone: its id), as it was
# before sessions spanned tabs: the upgrade places a database an older AgentCake made in the background
# (visit_upgrade.py), and nothing it recorded leaves the lists meanwhile. old_verdict: a lone tab session's cake 0.3.4
# verdict, which its class stands for when it has none.
SESSION_ROWS = ("(SELECT id, start_ms, verdict_class, NULL AS old_verdict, NULL AS alone FROM visits UNION ALL "
                "SELECT o.id, o.start_ms, o.verdict_class, o.verdict, o.id FROM sessions o LEFT JOIN session_web ow "
                "ON ow.session_id = o.id WHERE ow.visit_id IS NULL)")
TAB_IDS = "(SELECT session_id FROM session_web WHERE visit_id = v.id UNION ALL SELECT v.alone)"  # the tabs of `v`
FIRST_TAB = (f"(SELECT t.id FROM sessions t WHERE t.id IN {TAB_IDS} AND {tab_counts('t')} ORDER BY t.start_ms, t.id "
             "LIMIT 1)")
SESSIONS = f"{SESSION_ROWS} v JOIN sessions s ON s.id = {FIRST_TAB}"  # each session that has a tab, with its first
# Each session's tab sessions that count, `ps`, with their web analytics rows, `pw` (what a session adds up, such as
# its page views).
TABS = f"JOIN sessions ps ON ps.id IN {TAB_IDS} AND {tab_counts('ps')} LEFT JOIN session_web pw ON pw.session_id = ps.id"
# The tabs of the session `v` whose own verdict is the session's, `a`: the ones whose agent the session names.
NAMING = f"a.id IN {TAB_IDS} AND {tab_counts('a')} AND cake_verdict(a.verdict_class, a.verdict) = {VERDICT}"
NAMING_TABS = f"JOIN sessions a ON {NAMING}"
TAB_NAME = "cake_agent(cake_verdict(a.verdict_class, a.verdict), a.verdict_detail)"
_RECORDED = ("(SELECT {agg}(t) FROM (SELECT {agg}({chunk}) AS t FROM chunks WHERE session_id = s.id "
             "UNION ALL SELECT {agg}({chunk}) FROM open_chunks WHERE session_id = s.id "
             "UNION ALL SELECT {agg}(ts) FROM events WHERE session_id = s.id))")
FIRST_EVENT = _RECORDED.format(agg="MIN", chunk="t_start")
EPOCH = f"COALESCE({FIRST_EVENT}, s.start_ms)"  # where a session's recording, and its clock, start
REPLAY_END = (f"(SELECT MAX(t) FROM (SELECT MAX(t_end) AS t FROM chunks WHERE session_id = s.id AND stream = '{STREAM}' "
              f"UNION ALL SELECT MAX(t_end) FROM open_chunks WHERE session_id = s.id AND stream = '{STREAM}'))")
SEGMENTS_END = "(SELECT MAX(t_end) FROM segments WHERE session_id = s.id)"
RECORDING = f"{EPOCH}, s.last_action_ms, {REPLAY_END}, {SEGMENTS_END}"  # tabs.end_of()'s epoch and ends
COLUMNS = f"v.id, v.start_ms, s.origin, {VERDICT}, {TURN}, {THIN}"
Row = namedtuple("Row", "id start_ms origin verdict turns evidence")


@contextlib.contextmanager
def snapshot(con):
    """Every statement inside reads the database as the first one found it (one read transaction; in WAL mode no writer
    waits for it): the upgrade and late uploads place tab sessions in visits between two statements of one answer.
    Inside a transaction already (a snapshot, or writes not committed yet), that one."""
    if con.in_transaction:
        yield con
        return
    con.execute("BEGIN")
    try:
        yield con
    finally:
        con.rollback()


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
    """Conditions over SESSIONS (a visit `v` and its first tab `s`) and their arguments; each method returns a narrower
    scope."""

    def __init__(self, conditions=(SHOWN,), args=()):
        self.conditions, self.args = tuple(conditions), tuple(args)

    def where(self, condition, *args):
        return Scope(self.conditions + (condition,), self.args + args)

    def sql(self):
        return " AND ".join(self.conditions)

    def between(self, start, end=None):
        scope = self if start is None else self.where("v.start_ms >= ?", start)
        return scope if end is None else scope.where("v.start_ms < ?", end)

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
        """The sessions with a tab that names this agent, of the session's own verdict (an agent's name in an Agent
        session, a bot's in a Script bot one)."""
        if not name:
            return self
        return self.where(f"EXISTS (SELECT 1 FROM sessions a WHERE {NAMING} AND {TAB_NAME} = ?)", name)

    def from_site(self):
        """Only the website's own sessions: not those an earlier AgentCake's demo shop recorded."""
        return self.where(FROM_SITE)

    def before(self, key):
        """After the row (start_ms, id) in newest-first order: the next page."""
        start_ms, session_id = key
        return self.where("(v.start_ms < ? OR (v.start_ms = ? AND v.id < ?))", start_ms, start_ms, session_id)


def page(con, scope, limit, now, zone):
    with snapshot(con):
        rows = [Row._make(row) for row in con.execute(f"SELECT {COLUMNS} FROM {SESSIONS} WHERE {scope.sql()} ORDER BY "
                                                       "v.start_ms DESC, v.id DESC LIMIT ?", scope.args + (limit,))]
        from agentcake.api import rows as listed  # it reads this module's helpers: imported when first needed
        return listed.summaries(con, rows, now, zone), [(row.start_ms, row.id) for row in rows]


def counts(con, scope):
    out = dict.fromkeys(GROUPS, 0)
    for verdict, turns, evidence, n in con.execute(f"SELECT {VERDICT}, {TURN}, {THIN}, COUNT(*) FROM {SESSIONS} WHERE "
                                                   f"{scope.sql()} GROUP BY 1, 2, 3", scope.args):
        out["all"] += n
        out[verdict] += n
        for group in (turns, evidence):
            if group:
                out[group] += n
    return out


def total(con, scope):
    return con.execute(f"SELECT COUNT(*) FROM {SESSIONS} WHERE {scope.sql()}", scope.args).fetchone()[0]


def agents(con, scope):
    return con.execute(f"SELECT {TAB_NAME}, COUNT(DISTINCT v.id) FROM {SESSIONS} {NAMING_TABS} WHERE {scope.sql()} "
                       f"AND {IN_AGENT} GROUP BY 1 ORDER BY 2 DESC, 1", scope.args).fetchall()


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


def relative(runs, origin, length):
    """Stored runs (t_start, t_end, actor) as contract segments: ms from origin, inside 0 … length."""
    out = []
    for t_start, t_end, who in runs:
        start = min(max(0, t_start - origin), length)
        out.append({"who": who, "start_ms": int(start), "end_ms": int(min(max(start, t_end - origin), length))})
    return out
