"""The monthly update of the agent lists and IP ranges and, on a server, of the city database: when it runs, the
run itself, and the record of the last one, whichever way it ran.

`agentcake lists update` runs every part at once (run(MANUAL)). `agentcake serve` calls start(): a daemon thread that
checks first at a random moment soon after the start (sources.json "update" -> "auto": first_check_s), then once every
check_every_s, and has the parts that are due run while lists_auto_update is on (defaults.json, on by default; the
settings page switches it), in a process of its own: child_command() starts this installation's Python on child().
So serve never loads the code that downloads and converts, the update's memory goes back to the system when it ends
(converting the city database takes some 70 MB of Python objects, and freed memory stays with the process that used
it), it never holds serve's GIL, and when it is killed (a memory limit's OOM kill takes the largest process) serve goes
on (deploy/cake.service: OOMPolicy=continue). The child runs at the lowest CPU priority (sources.json child_nice): on
a server with one CPU, converting the city database takes the whole CPU for minutes, and serve's answers and the
container's health check come first. The child takes the update lock and writes the record itself; serve uses what it
wrote at the next lookup (detect/lists.py and geoip.py notice a new copy). A child that ends with another status, or
is killed, is a failed run of the parts that were due, recorded as any failure. It runs in a process group of its own,
so a Ctrl-C meant for serve in a terminal doesn't cut it short, but in serve's session: on Linux a new session is a new
scheduler autogroup, where its nice value would count only against its own threads, not against serve (sched(7)). It
writes where serve writes (cake.log, the journal, the container's log).

A part is due once its last success is every_days old: the lists counted from the day they were built, so a new
release's own lists are fresh, and the city database from when it was downloaded or last found current. A server without
a city database gets one at once, within minutes of its first start. A part that fails leaves what is in use as it was
and waits retry_after_s before it is tried again, restarts included; the daily checks never hammer a source that is
down. The random first moment and each installation's own dates spread the downloads of many installations over time.
PostHog came to do the same for its city database (its server downloads GeoLite2 and again once it is 45 days old, with
no setting; posthog#33123), and Matomo's "automatic updates" of its GeoIP database have a switch: here both, on by
default.

Only the public addresses in data/lists/sources.json and data/geo.json are fetched, by detect/lists_build.py and
geoip_build.py with their own User-Agent; nothing about the site, its visits or this installation is sent. Both are
imported only when a part runs, in the child or in `agentcake lists update`, never in serve.

    run(how, c=None, now=None, parts=PARTS, fetchers=None) -> the record of the run, with "details" (each part's folder,
                                     answer or error, for the command line); None for a background run while another
                                     update holds the lock (`agentcake lists update` waits for it instead). A
                                     background run reads the setting again before each part: switched off on the
                                     settings page, no further part starts (one downloading ends), and a run that
                                     started none records nothing (None)
    due(c, now) -> the parts due now, in PARTS order; [] while the setting is off
    check(c=None, now=None, command=None) -> serve's daily check: the parts due now, run by command(parts) (default
                                     child_command) in a process of its own; the failure it recorded for a child that
                                     ended with another status than 0, else None (the child recorded its run, or
                                     nothing was due)
    child_command(parts) -> [python, -I, -c, code, part...]: child() of this installation, which is the folder that
                                     holds the agentcake package put first on sys.path (a wheel's site-packages, the
                                     release folder or checkout, or the .pyz itself), so it runs the same AgentCake as
                                     serve whichever way it was installed
    child(parts=None, now=None, fetchers=None) -> 0: run(AUTO, ...) of the parts named (default: sys.argv[1:]), at nice
                                     value child_nice
    status(c=None) -> {"auto", "last", "failures", "failing"}: what /api/settings, /api/health and doctor show
    untried(part) -> whether no update has recorded the part here yet, neither done nor failed (a skipped part leaves
                                     no mark): on a new server, the city database before serve's first check
    start() -> a threading.Event that ends the checks (serve sets it when it stops)
    loop(stop, first_s, every_s, once), first_wait(rng)    the thread's body and its first wait (the tests drive them)
    exclusive(wait) -> context manager: whether this process holds the update lock

The record, <CAKE_HOME>/updates.json: "last" {at, how: auto | manual, ok, error, parts: {part: updated | current |
skipped | failed}}, "failures" (failed runs in a row) and each part's last success and last failure ("parts", as ISO
times). fetchers: {part: fetch} in place of the downloads, which the tests pass to stay offline.
"""
import contextlib
import datetime
import fcntl
import json
import os
import random
import subprocess
import sys
import threading
import traceback

from agentcake import config, geoip, paths
from agentcake.detect import lists

SETTING = "lists_auto_update"
LISTS, PLACES = PARTS = ("lists", "places")
AUTO, MANUAL = "auto", "manual"
UPDATED, CURRENT, SKIPPED, FAILED = "updated", "current", "skipped", "failed"
PLACE_RESULTS = (UPDATED, CURRENT, SKIPPED)  # the keys of geoip_build.update's answer, each its part's result
MARKS = ("ok_at", "failed_at")  # each part's last success and last failure in the record
UTC = datetime.timezone.utc


def settings():
    return lists.update_settings()["auto"]


def _path(name):
    return os.path.join(paths.home(), settings()[name])


def _now():
    return datetime.datetime.now(UTC)


def _time(text):
    """A recorded ISO time as an aware datetime (one written without a zone is UTC); None for none, and for anything
    else that is not an ISO time, such as a city database's about.json edited by hand (it is then downloaded again)."""
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def read_state():
    """What updates.json holds; {} before the first update, and for a file that cannot be read or holds what no run
    writes (edited by hand, or by another version), which the next run writes again from the start."""
    try:
        with open(_path("state_file"), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {}
    return state if _as_written(state) else {}


def _as_written(state):
    """Whether a record holds what _record() writes, with the types its readers use: failures a count, each part's
    marks readable times, and the last run (if any) with its time, way, result, error and parts."""
    if not isinstance(state, dict):
        return False
    failures, marks, last = state.get("failures", 0), state.get("parts", {}), state.get("last")
    return (type(failures) is int and failures >= 0 and isinstance(marks, dict)
            and all(isinstance(mark, dict) and all(_time(mark[key]) for key in MARKS if key in mark)
                    for mark in marks.values())
            and (last is None or isinstance(last, dict) and _time(last.get("at")) is not None
                 and last.get("how") in (AUTO, MANUAL) and isinstance(last.get("ok"), bool)
                 and isinstance(last.get("parts"), dict) and "error" in last
                 and (last["error"] is None or isinstance(last["error"], str))))


def _write_state(state):
    path = _path("state_file")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    staged = path + ".incoming"
    with open(staged, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=config.JSON_INDENT)
    os.replace(staged, path)


@contextlib.contextmanager
def exclusive(wait):
    """One update at a time, across processes: the background one and `agentcake lists update` would otherwise clear
    each other's half-written downloads. wait: block until the other one ends; else yield False at once."""
    path = _path("lock_file")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _lock_file(path) as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _lock_file(path):
    """The lock file, made when it is missing. One this user may not write (another user's: root running `agentcake
    lists update` on the data folder) is opened to read, as flock() needs no write access: the update still runs and
    records what it could not write, instead of failing before it starts and recording nothing."""
    try:
        return open(path, "a")
    except PermissionError:
        return open(path, "rb")


def _update_lists(c, now, fetch):
    """The lists' part: (UPDATED, the folder written) or (FAILED, the error); the lists in use stay when it fails."""
    from agentcake.detect import lists_build

    try:
        return UPDATED, lists_build.update(fetch=fetch, now=now)
    except (lists_build.BuildError, OSError) as error:  # OSError: a full or read-only disk while writing the snapshot
        return FAILED, error


def _update_places(c, now, fetch):
    """The city database's part: (its result, geoip_build.update's answer) or (FAILED, the error)."""
    from agentcake import geoip_build

    try:
        found = geoip_build.update(c, fetch=fetch, now=now)
    except (geoip_build.BuildError, OSError) as error:
        return FAILED, error
    return next(result for result in PLACE_RESULTS if result in found), found


RUNNERS = {LISTS: _update_lists, PLACES: _update_places}


def run(how, c=None, now=None, parts=PARTS, fetchers=None):
    c, now, fetchers = (config.load_cfg() if c is None else c), now or _now(), fetchers or {}
    with exclusive(wait=how == MANUAL) as held:
        if not held:
            return None
        outcomes = {}
        for part in (part for part in PARTS if part in parts):
            if how == AUTO and not config.load_cfg().get(SETTING):
                break  # switched off since the check, or while a part downloaded: no further part starts
            outcomes[part] = RUNNERS[part](c, now, fetchers.get(part))
        if not outcomes:
            return None
        record = _record(how, outcomes, now)
    return dict(record, details={part: detail for part, (_, detail) in outcomes.items()})


def _record(how, outcomes, now):
    """Write the run into updates.json: the last run, the failed runs in a row, each part's last success or failure."""
    state, at = read_state(), now.isoformat(timespec="seconds")
    marks = state.setdefault("parts", {})
    errors = [str(detail) for result, detail in outcomes.values() if result == FAILED]
    for part, (result, _) in outcomes.items():
        mark = marks.setdefault(part, {})
        if result == FAILED:
            mark["failed_at"] = at
        elif result != SKIPPED:  # skipped: on this computer the city database is never downloaded, nor due
            mark["ok_at"] = at
            mark.pop("failed_at", None)
    ok = not errors
    state["last"] = {"at": at, "how": how, "ok": ok, "error": errors[0][:settings()["error_chars"]] if errors else None,
                     "parts": {part: result for part, (result, _) in outcomes.items()}}
    state["failures"] = 0 if ok else state.get("failures", 0) + 1
    _write_state(state)
    return state["last"]


def due(c, now):
    if not c.get(SETTING):
        return []
    marks, every = read_state().get("parts", {}), datetime.timedelta(days=settings()["every_days"])
    built = datetime.datetime.combine(datetime.date.fromisoformat(lists.current().built), datetime.time(), tzinfo=UTC)
    found = [LISTS] if _part_due(marks.get(LISTS, {}), built, now, every) else []
    if geoip.sees_addresses(c):
        database = geoip.database()
        downloaded = _time(database.built_at) if database else None
        if _part_due(marks.get(PLACES, {}), downloaded, now, every, missing=database is None):
            found.append(PLACES)
    return found


def _part_due(mark, in_use_at, now, every, missing=False):
    """in_use_at: when what is in use was made (the lists' day, the database's download), counted as a success."""
    failed = _time(mark.get("failed_at"))
    if failed and now - failed < datetime.timedelta(seconds=settings()["retry_after_s"]):
        return False
    if missing:
        return True
    successes = [moment for moment in (_time(mark.get("ok_at")), in_use_at) if moment]
    return not successes or now - max(successes) >= every


def check(c=None, now=None, command=None):
    c, now = (config.load_cfg() if c is None else c), now or _now()
    parts = due(c, now)
    if not parts:
        return None
    try:
        ended = subprocess.run((command or child_command)(parts), process_group=0).returncode
    except OSError as error:  # this Python could not be started again
        failure = str(error)
    else:
        if ended == 0:
            return None
        failure = str(subprocess.CalledProcessError(ended, __name__))  # Python's own words: exit status, or signal
    with exclusive(wait=True):
        return _record(AUTO, {part: (FAILED, failure) for part in parts}, now)


def child_command(parts):
    root = os.path.dirname(paths.PACKAGE_DIR)
    code = f"import sys; sys.path.insert(0, {root!r}); from agentcake import updates; sys.exit(updates.child())"
    return [sys.executable, "-I", "-c", code, *parts]


def child(parts=None, now=None, fetchers=None):
    _yield_cpu()
    run(AUTO, parts=sys.argv[1:] if parts is None else parts, now=now, fetchers=fetchers)
    return 0


def _yield_cpu():
    """This process, before it downloads or converts anything, at nice value child_nice. Never above the priority it
    started with: an unprivileged process may lower its own priority, not raise it."""
    started = os.getpriority(os.PRIO_PROCESS, 0)
    os.setpriority(os.PRIO_PROCESS, 0, max(started, settings()["child_nice"]))


def status(c=None):
    c, state = (config.load_cfg() if c is None else c), read_state()
    failures = state.get("failures", 0)
    return {"auto": bool(c.get(SETTING)), "last": state.get("last"), "failures": failures,
            "failing": failures >= settings()["warn_after_failures"]}


def untried(part):
    return not read_state().get("parts", {}).get(part)


def first_wait(rng=random):
    low, high = settings()["first_check_s"]
    return rng.uniform(low, high)


def loop(stop, first_s, every_s, once):
    """Wait first_s, then check every every_s until stop is set; each check reads the settings again, so turning the
    setting off or on takes effect at the next one without a restart."""
    wait = first_s
    while not stop.wait(wait):
        try:
            once()
        except Exception:  # an unforeseen failure must not end the checks: it goes to cake.log, and the next one runs
            traceback.print_exc()
        wait = every_s


def start():
    stop = threading.Event()
    threading.Thread(target=loop, args=(stop, first_wait(), settings()["check_every_s"], check), name="cake-updates",
                     daemon=True).start()
    return stop
