"""GET /api/setup: the home page's ways to connect a website, and its example preview (the home page draws it). Since
0.4.0 there is no demo shop: a fresh AgentCake's home page connects its owner's website, as PostHog 1.0's setup page did.

    sentence          the one sentence for a coding agent, in English and Chinese (copy.en.json and copy.zh.json
                      site_sentence: the sentence is for an AI, so both stay), with this installation's launcher, ~ for
                      the home folder
    terminal, server  the commands of the Terminal and On a server tabs, one per line, placeholders only (api.en.json)
    example           made-up sessions and a timeline the page shows as "example data" until real visits arrive
                      (data/example.json); nothing in the database
    recorded          how many sessions the lists show (visits.py), and how many of them are Agent sessions, at any
                      time: the home page is the dashboard from the first session on (like 0.3.4's page), and
                      the dashboard's top block is the getting-started one until the first Agent session
"""
from agentcake import paths
from agentcake.api import answers, visits
from agentcake.datafiles import load
from agentcake.wording import product, text

LANGUAGES = ("en", "zh")


@answers.view
def view(request):
    words, example = answers.words(), load("data/example.json")
    launcher = paths.launcher()
    commands = dict(product(), launcher=paths.tilde(launcher))
    con = visits.connect()
    try:
        counts = visits.counts(con, visits.Scope())
    finally:
        con.close()
    return answers.ok({
        "sentence": {lang: paths.tilde(text("site_sentence", lang=lang, launcher=launcher)) for lang in LANGUAGES},
        "terminal": "\n".join(line.format(**commands) for line in words["setup_terminal"]),
        "server": "\n".join(line.format(**commands) for line in words["setup_server"]),
        "example": {"sessions": example["sessions"], "timeline": example["timeline"]},
        "recorded": {"sessions": counts["all"], "agent": counts[visits.AGENT_VERDICT]}})
