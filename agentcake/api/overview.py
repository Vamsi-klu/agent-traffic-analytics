"""GET /api/overview?range=today|7d|30d: the dashboard (the dashboard page draws it).

First the sessions with data newer than their verdict are judged (judging.catch_up, as the 0.3.4 dashboard did); then,
over the sessions that count (visits.py) in the range (no range: every session):
    counts                  SessionCounts
    agent_last_week         Agent sessions in the same range data/api.json compare_days earlier; null for all time,
                            which has no earlier range
    agents_seen             sessions per agent name, Agent sessions only; name null: the agents no name fits (Unnamed)
    page_views              the range's page views as PostHog counts $pageview (web_time.py: each page load and each
                            new path within it, not a new query string alone); all of them, and by the session's
                            verdict; the sessions recorded before these were counted are filled in first (api/web.py)
    pages_per_session       page views divided by sessions: of all sessions and of each verdict's; null for a group
                            without sessions
    latest_agent            the newest Agent sessions (the top block)
    storage                 the disk budget and what cake's data uses of it, whatever the filters (settings.disk: the
                            settings page's numbers; the dashboard shows only the warning, from warn_at_pct, as 0.3.4's did),
                            and the disk under it with why new replays are stopped, if they are
    coverage                what counts as a bot, the Bot number's "?" (coverage.py)
"""
from agentcake import config, judging
from agentcake.api import answers, coverage, periods, settings, visits, web
from agentcake.api.visits import AGENT_VERDICT, VERDICT

ALL = "all"


@answers.view
def view(request):
    range_key = answers.choice(request, "range", periods.range_keys())
    judging.catch_up()
    numbers, now = answers.numbers(), periods.now_ms()
    start, _ = periods.window(range_key, now)
    everywhere = visits.Scope()
    scope = everywhere.between(start)
    con = visits.connect()
    try:
        latest_agent, _ = visits.page(con, scope.group(AGENT_VERDICT), numbers["latest_agent"], now)
        week_before = everywhere.between(*periods.earlier(start, now, numbers["compare_days"]))
        counts, views = visits.counts(con, scope), page_views(con, scope)
        body = {"counts": counts,
                "agent_last_week": None if start is None else visits.counts(con, week_before)[AGENT_VERDICT],
                "agents_seen": [{"name": name, "sessions": n} for name, n in visits.agents(con, scope)],
                "page_views": views,
                "pages_per_session": pages_per_session(views, counts),
                "latest_agent": latest_agent,
                "storage": settings.disk(con, config.load_cfg()),
                "coverage": coverage.coverage()}
    finally:
        con.close()
    return answers.ok(body)


def page_views(con, scope):
    """{"all", and each verdict}: the page views of the scope's sessions as PostHog counts them (web_time.py's
    web_paths: each page load and each new path), in all and by their session's verdict; sessions recorded before page
    views were counted by path are filled in first, as /api/web does (web.fill)."""
    web.fill(con, scope)
    counted = dict.fromkeys((ALL,) + visits.VERDICTS, 0)
    for verdict, views in con.execute(f"SELECT {VERDICT}, SUM(p.views) FROM web_paths p JOIN sessions s "
                                      f"ON s.id = p.session_id WHERE {scope.sql()} GROUP BY 1", scope.args):
        counted[ALL] += views
        counted[verdict] += views
    return counted


def pages_per_session(views, counts):
    """{"all", and each verdict: page views / sessions}; None for a group without sessions."""
    return {group: views[group] / counts[group] if counts[group] else None for group in (ALL,) + visits.VERDICTS}
