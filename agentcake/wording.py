"""The words AgentCake prints: its name, command and minimum Python from data/product.json, and the
copy of the command line, setup, doctor, ping and the server from data/copy.en.json.

{source} is the repository at this version's tag (product.json "source", with the version filled in): a wheel or a
.pyz carries the package only, so a sentence that names SERVER.md or PRIVACY.md gives it as {source}/SERVER.md.

text(entry, **values) fills a copy entry's {placeholders} ({name}, {command} and {python} always work); an entry that
is a list of lines comes back joined into one string. raw(entry) returns an entry as it is in the file.
"""
from agentcake import __version__, datafiles

COPY_FILE = "data/copy.en.json"


def product():
    """{"name": "AgentCake", "command": "agentcake", "python": "3.11", "source": "https://github.com/…/blob/v<version>"}"""
    facts = datafiles.load("data/product.json")
    return dict(facts, source=facts["source"].format(version=__version__))


def raw(entry):
    return datafiles.load(COPY_FILE)[entry]


def text(entry, /, **values):
    template, fill = raw(entry), dict(product(), **values)
    if isinstance(template, list):
        return "\n".join(line.format(**fill) for line in template)
    return template.format(**fill)
