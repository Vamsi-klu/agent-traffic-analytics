"""The release settings (tools/releasing/release.json) and the error every step of a release raises.

load() reads release.json once per call; nothing is cached, so a test can hand any step its own settings. Each step
takes the parts of the settings it needs and the folder it works in (the repository, or the exported commit).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SETTINGS_FILE = os.path.join(HERE, "release.json")


class ReleaseError(Exception):
    """A release cannot be built; the message says why and what to do."""


def load(path=SETTINGS_FILE):
    return read_json(path)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def setting(tree, rule, what):
    """The value a data file of the commit holds: rule["settings_file"] (a JSON file), read along rule["settings_key"];
    what says what the value is for, in the error when the file is missing."""
    path = os.path.join(tree, rule["settings_file"])
    if not os.path.isfile(path):
        raise ReleaseError(f"{rule['settings_file']} is not in this commit, so it does not say {what}")
    value = read_json(path)
    try:
        for key in rule["settings_key"]:
            value = value[key]
    except (KeyError, TypeError):
        raise ReleaseError(f"{rule['settings_file']} has no {' -> '.join(rule['settings_key'])}") from None
    return value


def package_folder(tree, settings, rule):
    """The folder inside the package that a data file of the commit names (setting()). AgentCake looks there at run
    time, so the release reads the name from the same place."""
    value = setting(tree, rule, f"where in the package {rule['folder']}/ goes")
    return os.path.join(tree, settings["package"], value)


def modes(settings):
    """release.json "modes" as numbers: {"file": 0o644, "executable": 0o755, "folder": 0o755}."""
    return {kind: int(text, 8) for kind, text in settings["modes"].items()}


def file_name(settings, kind, name, version):
    """The name of a release file that release.json "files" names (pyz, checksums), for this name and version."""
    return settings["files"][kind].format(name=name, version=version)
