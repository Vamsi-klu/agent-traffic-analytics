"""GET /api/overview?range=24h|7d|30d|all: the dashboard (the dashboard page draws it).

First the sessions with data newer than their verdict are judged (judging.catch_up, as the 0.3.4 dashboard did); then,
over the sessions that count (visits.py) in the range (no range: every session):
    counts                  SessionCounts
    agent_earlier           Agent sessions of the range's previous period, PostHog's (periods.earlier): as long as
                            the range runs to the end of its current hour or day, right before it (25 hours, 8 days,
                            31 days); null for all time, which has no earlier range
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
    address_check           on a server, whether the visitor's address it reads is a CDN's own, whatever the filters
                            (address_check.current): the dashboard warns while it is
"""
from agentcake import address_check, config, judging, timezone
from agentcake.api import answers, coverage, periods, settings, visits, web
from agentcake.api.visits import AGENT_VERDICT, VERDICT

ALL = "all"


@answers.view
def view(request):
    range_key = answers.choice(request, "range", periods.range_keys())
    judging.catch_up()
    numbers, now, zone = answers.numbers(), periods.now_ms(), timezone.chosen(config.load_cfg())
    start, _ = periods.window(range_key, now, zone)
    before = periods.earlier(range_key, now, zone)
    everywhere = visits.Scope()
    scope = everywhere.between(start)
    con = visits.connect()
    try:
        latest_agent, _ = visits.page(con, scope.group(AGENT_VERDICT), numbers["latest_agent"], now, zone)
        counts, views = visits.counts(con, scope), page_views(con, scope)
        agent_earlier = None if before is None else visits.counts(con, everywhere.between(*before))[AGENT_VERDICT]
        body = {"counts": counts,
                "agent_earlier": agent_earlier,
                "agents_seen": [{"name": name, "sessions": n} for name, n in visits.agents(con, scope)],
                "page_views": views,
                "pages_per_session": pages_per_session(views, counts),
                "latest_agent": latest_agent,
                "storage": settings.disk(con, config.load_cfg()),
                "coverage": coverage.coverage(),
                "address_check": address_check.current(con)}
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
