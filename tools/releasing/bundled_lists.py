"""The lists that ship with Agent Cake: refreshed online before a release, checked when it is built.

As PostHog keeps its bot lists in the code and refreshes them with a script before a release
(products/web_analytics/scripts/refresh_bot_ip_ranges.py), Agent Cake's lists, address ranges and signing keys
(tools/build_lists.py) and time zones (tools/build_timezones.py) are rebuilt by `release.py refresh` in the working
tree; the person releasing reads the summary and the diff, runs the tests and commits. `release.py build` then works
offline from that commit, and refuses one whose lists were built more than release.json "lists" -> "max_age_days"
before it: the age counts from the commit's time, not from today, so an old release still builds the same later.
"""
import datetime
import json
import os
import subprocess
import sys

from tools.releasing.settings import ReleaseError


def refresh(repository, settings, run=subprocess.run):
    """Run the refresh scripts (they need the internet) in the repository, then list what they changed."""
    for script in settings["lists"]["refresh"]:
        print(f"release: running {script}", flush=True)
        if run([sys.executable, "-I", os.path.join(repository, script)], cwd=repository).returncode != 0:
            raise ReleaseError(f"{script} failed: nothing else was refreshed; the lists in the commit are unchanged "
                               "unless the script says otherwise")
    changed = run(["git", "-C", repository, "status", "--short", "--", settings["lists"]["data_folder"]],
                  capture_output=True, text=True).stdout.strip()
    return changed


def built_date(tree, settings):
    """The day the lists in a tree were built (names.json "built")."""
    path = os.path.join(tree, settings["lists"]["names_file"])
    try:
        with open(path, encoding="utf-8") as f:
            return datetime.date.fromisoformat(json.load(f)["built"])
    except (OSError, KeyError, ValueError) as error:
        raise ReleaseError(f"cannot read the lists' build date from {settings['lists']['names_file']}: {error}") from None


def check_fresh(tree, settings, epoch):
    """Refuse a tree whose lists are older than max_age_days on the commit's day; returns their age in days."""
    built = built_date(tree, settings)
    committed = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).date()
    age = (committed - built).days
    limit = settings["lists"]["max_age_days"]
    if age > limit:
        raise ReleaseError(f"the lists in this commit were built on {built}, {age} days before it (more than {limit}): "
                           "run `python3 -I tools/release.py refresh`, review and commit the result, then build again")
    return age
