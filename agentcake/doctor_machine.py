"""`doctor`, the lines about this computer: machine_checks(c).

python_check(): the Python that runs AgentCake and whether it has compression.zstd (without it replays are stored
with zlib and take more disk). disk_check(c): the free space on the disk of the data folder (or of the folder it
will be made in) against disk_min_free_mb (space.disk_space): below it new replays are not stored until there is
room, and none is deleted for it, a FAIL; the line gives the floor and the free space and says how to free space or
lower the floor.
lists_check(): the age of the name and address lists in use (detect/lists.py) against max_age_days:
older is a WARN naming `agentcake lists update`, which downloads them now, or an upgrade. places_check(c), on a
server only (geoip.sees_addresses: on this computer every visit is 127.0.0.1 and there is no line): the city database
the visitors' places are looked up in (geoip.py); none yet, one that cannot be read, or one older than
data/geo.json's max_months_old is a WARN naming the same command. While the updates are on and none has been
downloaded or failed to be (updates.untried), the WARN says instead when serve's first check, minutes after it starts,
downloads it: a new server, the Docker image's included, has none until then. updates_check(c): whether `serve`
updates both once a month (lists_auto_update, updates.py), when the last update ran (in AgentCake's time zone, as the
log import's line writes it) and how it went; warn_after_failures failed updates in a row are a WARN naming the same
command, and with the setting off the line names it too. path_check():
every `agentcake` on PATH, as `which -a` lists them: when the first is not this installation, typing the command runs
another program, which is a WARN (the instructions run this one by its full path).
"""
import datetime
import os
import platform
import sys

from agentcake import codecs, geoip, paths, timezone, updates
from agentcake.detect import lists
from agentcake.doctor_lines import WARN
from agentcake.space import disk_space
from agentcake.units import BYTES_PER_MB, MS_PER_S, S_PER_MIN
from agentcake.wording import product, text

SHEBANG = "#!"  # protocol: the first bytes of a script that names its interpreter
SENTENCE_ENDS = (".", "!", "?")  # an update's error ends one sentence of the line, before the next one starts


def machine_checks(c, today=None):
    places = [places_check(c, today)] if geoip.sees_addresses(c) else []
    return [python_check(), disk_check(c), lists_check(today)] + places + [updates_check(c), path_check()]


def python_check():
    zstd = text("doctor_python_zstd") if "zstd" in codecs.available() else text("doctor_python_no_zstd")
    return text("doctor_python"), True, text("doctor_python_info", version=platform.python_version(),
                                             executable=paths.tilde(sys.executable), zstd=zstd)


def _mb(size_bytes):
    return format(size_bytes // BYTES_PER_MB, ",")


def disk_check(c, usage=None):
    """usage stands in for shutil.disk_usage (space.disk_space's)."""
    disk = disk_space(c, usage)
    values = {"free": _mb(disk["free"]), "floor": _mb(disk["min_free"]), "folder": paths.tilde(paths.home())}
    if not disk["min_free"]:
        return text("doctor_disk"), True, text("doctor_disk_off_info", off=text("doctor_disk_off"), **values)
    stop = text("doctor_disk_replays_stop")
    if not disk["low"]:
        return text("doctor_disk"), True, text("doctor_disk_ok", below=stop, **values)
    return text("doctor_disk"), False, text("doctor_disk_low", replays_stop=stop, resume=text("doctor_disk_replays_resume"),
                                            fix=text("doctor_disk_fix", launcher=paths.launcher()), **values)


def lists_check(today=None):
    status = lists.current().status(today=today)
    values = {"built": status["built"], "age": status["age_days"], "max_age": status["max_age_days"]}
    if status["stale"]:
        return text("doctor_lists"), WARN, text("doctor_lists_stale", launcher=paths.launcher(), **values)
    return text("doctor_lists"), True, text("doctor_lists_info", location=paths.tilde(status["location"]), **values)


def places_check(c, today=None):
    status, launcher = geoip.status(today=today) or {}, paths.launcher()
    if "month" not in status:
        if status.get("errors"):
            return text("doctor_places"), WARN, text("doctor_places_unreadable", error=status["errors"][0],
                                                     launcher=launcher)
        return text("doctor_places"), WARN, " ".join([text("doctor_places_missing"), _places_coming(c, launcher)])
    values = {"month": status["month"], "months": status["months_old"], "folder": status["folder"]}
    if status["stale"]:
        return text("doctor_places"), WARN, text("doctor_places_stale", launcher=launcher, **values)
    return text("doctor_places"), True, text("doctor_places_info", **values)


def _places_coming(c, launcher):
    """How a server without a city database gets one: before any update has tried, serve's first check downloads it
    (when that comes, from sources.json); with the updates off, or after a download failed (the next try waits for a
    later daily check), the command that downloads it now."""
    if c.get(updates.SETTING) and updates.untried(updates.PLACES):
        first, last = (seconds // S_PER_MIN for seconds in updates.settings()["first_check_s"])
        return text("doctor_places_first_update", first=first, last=last)
    return text("doctor_places_command", launcher=launcher)


def updates_check(c):
    found = updates.status(c)
    last = found["last"]
    if found["auto"]:
        said = [text("doctor_updates_on_server" if geoip.sees_addresses(c) else "doctor_updates_on",
                     days=updates.settings()["every_days"])]
    else:
        said = [text("doctor_updates_off")]
    command = text("doctor_updates_command", launcher=paths.launcher())
    if found["failing"]:
        return text("doctor_updates"), WARN, " ".join(said + [text("doctor_updates_failing", count=found["failures"],
                                                                    error=_ended(last["error"])), command])
    if last:
        when = _clock(last["at"], c)
        said.append(text("doctor_updates_last_ok", when=when) if last["ok"]
                    else text("doctor_updates_last_failed", when=when, error=_ended(last["error"])))
    if not found["auto"]:
        said.append(command)
    elif last and not last["ok"]:
        said.append(text("doctor_updates_retry"))
    return text("doctor_updates"), True, " ".join(said)


def _ended(error):
    """An update's error (a URL and urllib's reason, as a rule) with a full stop, so the next sentence starts anew."""
    error = (error or "").rstrip()
    return error if error.endswith(SENTENCE_ENDS) else error + SENTENCE_ENDS[0]


def _clock(at, c):
    """A recorded ISO time in AgentCake's time zone, written as the log import's line writes its time."""
    zone, moment = timezone.chosen(c), datetime.datetime.fromisoformat(at)
    shown = moment.astimezone(zone)
    return shown.strftime(text("doctor_logs_time", zone=timezone.short(zone, moment.timestamp() * MS_PER_S)))


def path_check(path=None, ours=None):
    """path: the PATH to look through (default $PATH); ours: the commands that run this installation (default
    this_installation())."""
    found = commands_on_path(product()["command"], os.environ.get("PATH", "") if path is None else path)
    mine = {os.path.realpath(command) for command in (this_installation() if ours is None else ours)}
    if not found:
        return text("doctor_path"), True, text("doctor_path_none", launcher=paths.launcher())
    first, others = found[0], found[1:]
    also = text("doctor_path_also", paths=", ".join(map(paths.tilde, others))) if others else ""
    if os.path.realpath(first) in mine or _runs_this_python(first):
        return text("doctor_path"), True, text("doctor_path_this", path=paths.tilde(first)) + also
    return text("doctor_path"), WARN, text("doctor_path_other", path=paths.tilde(first), launcher=paths.launcher()) + also


def commands_on_path(name, path):
    """Every executable file called name in the folders of path, in order, each real file once (`which -a`)."""
    found, seen = [], set()
    for folder in path.split(os.pathsep):
        candidate = os.path.join(folder or os.curdir, name)  # an empty entry is the current folder
        real = os.path.realpath(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK) and real not in seen:
            seen.add(real)
            found.append(candidate)
    return found


def this_installation():
    """The commands that run this AgentCake: bin/agentcake of its release folder or checkout, and the installed wheel's
    `agentcake` this process was started as (paths.running_command)."""
    return [command for command in (paths.bin_script(), paths.running_command()) if command]


def _runs_this_python(command):
    """Whether command is a script whose interpreter is the Python running now: an installed wheel's `agentcake`, run
    here as `python -m agentcake` from the same environment."""
    try:
        with open(command, "rb") as f:
            first_line = f.readline().decode("utf-8", "replace").strip()
    except OSError:
        return False
    words = first_line[len(SHEBANG):].split() if first_line.startswith(SHEBANG) else []
    return bool(words) and os.path.realpath(words[0]) == os.path.realpath(sys.executable)
