"""Where the dashboard's places come from, as /api/web, /api/health and the session page tell it.

    answer(c) -> {"source", "attribution"}
        source: geoip.source: "none" on an AgentCake that sees no visitor addresses (on this computer every visit is
        127.0.0.1), "missing" on a server whose city database is not downloaded yet, "database" once it is;
        attribution: the credit DB-IP asks for on every page that shows results of its database ({"text", "url"},
        data/geo.json), None while there is no database.
    attribution(c) -> {"text", "url"} or None
    update_command() -> the command that downloads it (`agentcake lists update`, by the path people run it with), which
        /api/health gives with the places (the dashboard names no command: a server downloads it by itself, monthly)
"""
from agentcake import geoip, paths
from agentcake.api import answers


def attribution(c):
    return _credit(geoip.source(c))


def _credit(source):
    if source != geoip.DATABASE:
        return None
    credit = geoip.SETTINGS["attribution"]
    return {"text": credit["text"], "url": credit["url"]}


def update_command():
    return answers.words()["lists_update"].format(launcher=paths.tilde(paths.launcher()))


def answer(c):
    source = geoip.source(c)
    return {"source": source, "attribution": _credit(source)}
