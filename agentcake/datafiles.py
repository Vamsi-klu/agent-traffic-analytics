"""The JSON files that ship inside the package (S1.2): defaults.json and data/*.json.

load("data/verdict.json") returns the parsed file, read once per process: these files are part of the release, not of
the user's data, so they cannot change while cake runs. The user's own settings ($CAKE_HOME/config.json) are read by
config.py on every use instead.

read(name) is the file's text, from the package's folder, or from inside agentcake.pyz when the package is imported
from the zip: the .pyz answers --version and help that way, without unpacking into CAKE_HOME (S6.6).
"""
import functools
import json
import os
import zipfile

from agentcake import paths


def read(name):
    path = os.path.join(paths.PACKAGE_DIR, name)
    archive = paths.archive()
    if archive:
        with zipfile.ZipFile(archive) as zipped:
            return zipped.read(os.path.relpath(path, archive).replace(os.sep, "/")).decode("utf-8")
    with open(path, encoding="utf-8") as f:
        return f.read()


@functools.lru_cache(maxsize=None)
def load(name):
    return json.loads(read(name))


def sizes():
    """data/sizes.json: caps on stored fields and the lengths of generated ids and secrets."""
    return load("data/sizes.json")
