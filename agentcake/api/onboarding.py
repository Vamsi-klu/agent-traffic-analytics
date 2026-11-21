"""GET /api/setup: the home page's ways to connect a website, and its example preview (the home page draws it). Since
0.4.0 there is no demo shop: a fresh AgentCake's home page connects its owner's website, as PostHog 1.0's setup page did.

    sentence          the one sentence for a coding agent, in English, as the page shows it and `agentcake sentence`
                      prints it (copy.en.json site_sentence), with this installation's launcher, ~ for the home folder
    terminal          the commands of the Terminal tab, one per line, placeholders only (api.en.json setup_terminal)
    server            the On a server tab's three things for the subdomain route, each one per line with placeholders
                      only (api.en.json setup_server): install, the two commands that start AgentCake and Caddy from
                      the release folder (docker-compose.yml); dns, the record that points cake.<the site's domain> at
                      the server; settings, what AgentCake on the server is told, public_url among it
    example           made-up sessions and a timeline the page shows as "example data" until real visits arrive
                      (data/example.json); nothing in the database
    recorded          at any time: how many sessions the lists show (visits.py), how many of them the website sent
                      (site: all but those an earlier AgentCake's demo shop recorded) and how many are Agent
                      sessions. The website is connected once it has sent a session: until then the home page shows how
                      to connect it, as PostHog 1.0 asked for its first event (only the owner's own visits answer that;
                      PostHog today keeps demo data in a project of its own), and the dashboard says that the sessions
                      it shows are the demo shop's. The dashboard's top block is the getting-started one until the
                      first Agent session.
"""
from agentcake import paths
from agentcake.api import answers, visits
from agentcake.datafiles import load
from agentcake.wording import product, text


@answers.view
def view(request):
    words, example = answers.words(), load("data/example.json")
    launcher = paths.launcher()
    commands = dict(product(), launcher=paths.tilde(launcher))
    con = visits.connect()
    try:
        counts = visits.counts(con, visits.Scope())
        site = visits.total(con, visits.Scope().from_site())
    finally:
        con.close()
    return answers.ok({
        "sentence": paths.tilde(text("site_sentence", launcher=launcher)),
        "terminal": "\n".join(line.format(**commands) for line in words["setup_terminal"]),
        "server": {part: "\n".join(line.format(**commands) for line in lines)
                   for part, lines in words["setup_server"].items()},
        "example": {"sessions": example["sessions"], "timeline": example["timeline"]},
        "recorded": {"sessions": counts["all"], "site": site, "agent": counts[visits.AGENT_VERDICT]}})
