"""GET /api/overview?range=today|7d|30d: the dashboard (S5.1; S5.3 draws it).

First the sessions with data newer than their verdict are judged (judging.catch_up, as the 0.3.4 dashboard did); then,
over the sessions that count (visits.py) in the range (no range: every session):
    counts                  SessionCounts
    agent_last_week         Agent sessions in the same range data/api.json compare_days earlier
    share_by_day            each local day of the range: the shares of human, agent and unsure in the length of that
                            day's sessions (each session's length split by the behaviour model's shares of its segments,
                            the verdict's stored shares: an estimate, as the chart says, not the count of actions a
                            session page gives; counting those needs them kept with each verdict, planned for 0.4.1;
                            whole percents); bots and sessions without input have no share and are left out
    agents_seen             sessions per agent name, Agent sessions only; name null: the agents no name fits (Unnamed)
    top_pages               page views per page (the path and query of its address) in Agent sessions and in Human
                            sessions: the top_pages most visited by each, both tables sort this one list
    latest, latest_agent    the newest sessions of every kind, and of Agent sessions
    average_length          D30: the mean length of Human, Agent only and Human + agent sessions, null for a group
                            without sessions, and how it is measured
    storage                 the disk budget and what cake's data uses of it, whatever the filters (settings.disk: the
                            settings page's numbers; S5.3's Disk bar warns from warn_at_pct, as 0.3.4's dashboard did),
                            and the disk under it with why new replays are stopped, if they are (K2, D34)
    coverage                coverage.py
"""
from agentcake import config, judging
from agentcake.api import answers, coverage, periods, settings, visits
from agentcake.api.visits import AGENT_VERDICT, BEHAVIOR_STATE, LENGTH, TURN, VERDICT, WHO
from agentcake.units import MS_PER_S

LENGTH_GROUPS = ("human", "agent_only", "human_agent")


@answers.view
def view(request):
    range_key = answers.choice(request, "range", tuple(answers.numbers()["range_days"]))
    judging.catch_up()
    numbers, now = answers.numbers(), periods.now_ms()
    start, _ = periods.window(range_key, now)
    everywhere = visits.Scope()
    scope = everywhere.between(start)
    con = visits.connect()
    try:
        latest, _ = visits.page(con, scope, numbers["latest"], now)
        latest_agent, _ = visits.page(con, scope.group(AGENT_VERDICT), numbers["latest_agent"], now)
        week_before = everywhere.between(*periods.earlier(start, now, numbers["compare_days"]))
        body = {"counts": visits.counts(con, scope),
                "agent_last_week": visits.counts(con, week_before)[AGENT_VERDICT],
                "share_by_day": share_by_day(con, scope, start, now),
                "agents_seen": [{"name": name, "sessions": n} for name, n in visits.agents(con, scope)],
                "top_pages": top_pages(con, scope, numbers["top_pages"]),
                "latest": latest, "latest_agent": latest_agent,
                "average_length": average_length(con, scope), "storage": settings.disk(con, config.load_cfg()),
                "coverage": coverage.coverage()}
    finally:
        con.close()
    return answers.ok(body)


def share_by_day(con, scope, start, now):
    if start is None:
        first = con.execute(f"SELECT MIN(s.start_ms) FROM sessions s WHERE {scope.sql()}", scope.args).fetchone()[0]
        start = now if first is None else first
    totals = {day: weights for day, *weights in con.execute(
        f"SELECT date(s.start_ms / {MS_PER_S}, 'unixepoch', 'localtime'), SUM({LENGTH} * s.human_pct), "
        f"SUM({LENGTH} * s.agent_pct), SUM({LENGTH} * s.unsure_pct) FROM sessions s WHERE {scope.sql()} AND "
        f"{VERDICT} != 'bot' AND COALESCE({BEHAVIOR_STATE}, '') != 'off' GROUP BY 1", scope.args)}
    out = []
    for key, label in periods.days(start, now):
        shares = visits.whole_percents([weight or 0 for weight in totals.get(key, (0,) * len(WHO))])
        out.append({"day": label, **dict(zip(WHO, shares))})
    return out


def top_pages(con, scope, per_table):
    """The pages Agent sessions and Human sessions opened most, each counted once per page view."""
    found = {}
    views = con.execute(
        f"SELECT DISTINCT b.session_id, b.pv, b.url, {VERDICT} FROM batches b JOIN sessions s ON s.id = b.session_id "
        f"WHERE {scope.sql()} AND {VERDICT} IN ('human', 'agent') UNION ALL "
        f"SELECT s.id, NULL, s.url, {VERDICT} FROM sessions s WHERE {scope.sql()} AND {VERDICT} IN "
        "('human', 'agent') AND NOT EXISTS (SELECT 1 FROM batches WHERE session_id = s.id)",
        scope.args + scope.args)
    for _, _, url, verdict in views:
        if url:
            counts = found.setdefault(visits.page_path(url), {"agent": 0, "human": 0})
            counts[verdict] += 1
    top = set()
    for who in ("agent", "human"):
        ranked = sorted((path for path, n in found.items() if n[who]), key=lambda path: (-found[path][who], path))
        top.update(ranked[:per_table])
    return [{"path": path, **found[path]}
            for path in sorted(top, key=lambda path: (-found[path]["agent"], -found[path]["human"], path))]


def average_length(con, scope):
    sums = {group: [0, 0] for group in LENGTH_GROUPS}
    for verdict, turns, total, n in con.execute(f"SELECT {VERDICT}, {TURN}, SUM({LENGTH}), COUNT(*) FROM sessions s "
                                                f"WHERE {scope.sql()} GROUP BY 1, 2", scope.args):
        group = turns or verdict
        if group in sums:
            sums[group][0] += total or 0
            sums[group][1] += n
    return {"ms": {group: round(total / n) if n else None for group, (total, n) in sums.items()},
            "about": coverage.average_length_about()}
