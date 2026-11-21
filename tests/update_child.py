"""A stand-in for the monthly update's own process, for tests/test_updates_child.py: agentcake/updates.py child() with
test_updates.py's offline downloads (the lists' small world, the city database fixture) at the clock the test gives,
and, as the test asks, a fault in its first download.

    python3 -I tests/update_child.py <mode> <now, ISO> <folder for its notes> <part>...

mode: ok; kill (SIGKILL itself), exit (status 3) or switch (lists_auto_update turned off, as the settings page does)
at its first download; hold (at its first download, wait until the test writes <folder>/go, at most GO_WAIT_S);
say (a line on stdout and one on stderr, then as ok). Notes in <folder>: pid (its process id), sid and pgid (its
session and its process group), and fetched and nice (written at its first download: nice is its CPU priority then,
its nice value).
"""
import datetime
import os
import signal
import sys
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from test_lists_build import fetcher, recipe, world  # noqa: E402
from test_updates import city_database  # noqa: E402
from agentcake import config, updates  # noqa: E402
from agentcake.detect import lists_build  # noqa: E402

EXIT_STATUS = 3
SAID = "update child says"
GO_WAIT_S, POLL_S = 120, 0.05  # hold: how long it waits for the test at most, and how often it looks


def note(name, text=""):
    with open(os.path.join(NOTES, name), "w", encoding="utf-8") as f:
        f.write(text)


def first_download(mode):
    """What the first download does before it answers."""
    note("nice", str(os.getpriority(os.PRIO_PROCESS, 0)))
    note("fetched")
    if mode == "kill":
        os.kill(os.getpid(), signal.SIGKILL)
    elif mode == "exit":
        os._exit(EXIT_STATUS)
    elif mode == "switch":
        config.save_user(**{updates.SETTING: False})
    elif mode == "hold":
        deadline = time.monotonic() + GO_WAIT_S
        while not os.path.exists(os.path.join(NOTES, "go")) and time.monotonic() < deadline:
            time.sleep(POLL_S)


def faulty(fetch, mode, started):
    def answer(*args, **kwargs):
        if not started:
            started.append(True)
            first_download(mode)
        return fetch(*args, **kwargs)
    return answer


if __name__ == "__main__":
    MODE, NOW, NOTES, PARTS = sys.argv[1], datetime.datetime.fromisoformat(sys.argv[2]), sys.argv[3], sys.argv[4:]
    note("pid", str(os.getpid()))
    note("sid", str(os.getsid(0)))
    note("pgid", str(os.getpgid(0)))
    if MODE == "say":
        print(SAID, flush=True)
        print(SAID, file=sys.stderr, flush=True)
    sources, started = recipe(), []
    fetchers = {updates.LISTS: faulty(fetcher(world(sources)), MODE, started),
                updates.PLACES: faulty(city_database, MODE, started)}
    with mock.patch.object(lists_build, "read_recipe", return_value=(sources, lists_build.read_recipe()[1])):
        sys.exit(updates.child(PARTS, now=NOW, fetchers=fetchers))
