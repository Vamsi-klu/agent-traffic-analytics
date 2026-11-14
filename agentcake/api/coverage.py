"""The dashboard's note on what Agent Cake records and how it decides (S5.3's wording, served by S5.1).

coverage() is the Coverage of web/src/data/types.ts: the words of data/coverage.en.json, each row's "how it's decided"
the sentence data/judging.en.json gives its class (the same words the verdicts use, S3.4), or "named": how an agent's
name is found (D39: a name is level 3, no class of its own). The names of the categories themselves (D39's three
levels) are judging.en.json's too, which the pages read when they are built. average_length_about() says how a
session's length is measured (D30).
"""
from agentcake.datafiles import load
from agentcake.detect import verdict_text
from agentcake.wording import product

NAMED = "named"


def _words():
    return load("data/coverage.en.json")


def _how(key):
    judged = verdict_text.judging()
    return judged[NAMED]["how"] if key == NAMED else judged["classes"][key]["how"]


def coverage():
    words, name = _words(), product()["name"]
    return {"title": words["title"].format(name=name), "lead": words["lead"].format(name=name),
            "columns": dict(words["columns"]),
            "rows": [{"what": row["what"], "verdict": row["verdict"], "shown_as": row["shown_as"],
                      "how": _how(row["class"])} for row in words["rows"]],
            "bot": dict(words["bot"])}


def average_length_about():
    return _words()["average_length"]
