"""The dashboard's words that come with /api/overview: what counts as a bot (the Bot number's "?").

coverage() is the Coverage of web/src/data/types.ts: the question and answer of data/coverage.en.json "bot". The names
of the categories themselves are judging.en.json's, which the pages read when they are built.
"""
from agentcake.datafiles import load


def _words():
    return load("data/coverage.en.json")


def coverage():
    return {"bot": dict(_words()["bot"])}

