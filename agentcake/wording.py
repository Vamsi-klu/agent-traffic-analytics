"""The words Agent Cake prints: its name, command and minimum Python from data/product.json, and the
copy of the command line, setup, doctor, ping and the server from data/copy.en.json (data/copy.zh.json holds the two
texts written for a coding agent that are also offered in Chinese).

text(entry, **values) fills a copy entry's {placeholders} ({name}, {command} and {python} always work); an entry that
is a list of lines comes back joined into one string. raw(entry) returns an entry as it is in the file.
"""
from agentcake import datafiles


def product():
    """{"name": "Agent Cake", "command": "agentcake", "python": "3.11"}"""
    return datafiles.load("data/product.json")


def raw(entry, /, lang="en"):
    return datafiles.load(f"data/copy.{lang}.json")[entry]


def text(entry, /, lang="en", **values):
    template, fill = raw(entry, lang), dict(product(), **values)
    if isinstance(template, list):
        return "\n".join(line.format(**fill) for line in template)
    return template.format(**fill)
