"""`doctor`, the lines about this computer: machine_checks(c).

python_check(): the Python that runs Agent Cake and whether it has compression.zstd (without it replays are stored
with zlib and take more disk). disk_check(c): the free space on the disk of the data folder (or of the folder it
will be made in) against disk_min_free_mb (space.disk_space): below it the oldest replays are deleted to
make room, a WARN; with auto_free off, or when deleting every old replay would not make room because other files fill
the disk (none is deleted; space.disk_room, read from the database without changing it), new replays are not
stored until there is room, a FAIL; the line gives the floor and the free space and says how to lower the floor.
lists_check(): the age of the name and address lists in use (detect/lists.py) against max_age_days:
older is a WARN naming `agentcake lists update`, the one command that goes online, or an upgrade. path_check():
every `agentcake` on PATH, as `which -a` lists them: when the first is not this installation, typing the command runs
another program, which is a WARN (the instructions run this one by its full path).
"""
import os
import pathlib
import platform
import sqlite3
import sys

from agentcake import codecs, paths
from agentcake.detect import lists
from agentcake.doctor_lines import WARN
from agentcake.space import disk_room, disk_space
from agentcake.units import BYTES_PER_MB
from agentcake.wording import product, text

SHEBANG = "#!"  # protocol: the first bytes of a script that names its interpreter


def machine_checks(c):
    return [python_check(), disk_check(c), lists_check(), path_check()]


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
    if not disk["low"]:
        below = text("doctor_disk_frees") if c["auto_free"] else text("doctor_disk_replays_stop")
        return text("doctor_disk"), True, text("doctor_disk_ok", below=below, **values)
    launcher, stop = paths.launcher(), text("doctor_disk_replays_stop")
    if not c["auto_free"]:
        return text("doctor_disk"), False, text("doctor_disk_low", why=text("doctor_disk_auto_free_off"), replays_stop=stop,
                                                fix=text("doctor_disk_fix_auto_free", launcher=launcher), **values)
    if _room_left(c, disk):
        return text("doctor_disk"), WARN, text("doctor_disk_freeing", frees=text("doctor_disk_frees"),
                                               launcher=launcher, **values)
    return text("doctor_disk"), False, text("doctor_disk_full_other",
                                            other_files=text("doctor_disk_other_files", floor=values["floor"]),
                                            replays_stop=stop, resume=text("doctor_disk_replays_resume"),
                                            fix=text("doctor_disk_fix", launcher=launcher), **values)


def _room_left(c, disk):
    """Whether deleting old replays can make room (space.disk_room), read from the database without changing it: not
    before there is a database."""
    if not os.path.exists(paths.db_file()):
        return False
    con = sqlite3.connect(pathlib.Path(paths.db_file()).as_uri() + "?mode=ro", uri=True)
    try:
        return disk_room(con, c, disk)
    except sqlite3.OperationalError:  # a cake 0.3.4 database the running cake has not opened yet: it decides then
        return True
    finally:
        con.close()


def lists_check(today=None):
    status = lists.current().status(today=today)
    values = {"built": status["built"], "age": status["age_days"], "max_age": status["max_age_days"]}
    if status["stale"]:
        return text("doctor_lists"), WARN, text("doctor_lists_stale", launcher=paths.launcher(), **values)
    return text("doctor_lists"), True, text("doctor_lists_info", location=paths.tilde(status["location"]), **values)


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
    """The commands that run this Agent Cake: bin/agentcake of its release folder or checkout, and the installed wheel's
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
