"""`doctor`: the self-check a coding agent runs after installing, and after connecting a website.

doctor(folder, url) prints one line per check (doctor_lines.py: PASS, FAIL, WARN, SKIP), in three groups:
- Agent Cake itself: it answers on 127.0.0.1 (reach(): nothing listening is "not running, start it"; a connection that
  a sandbox forbids is said to be the sandbox's doing, never "not running"), its local page opens, it serves
  the page script with this installation's site key, a visit arrived: a self-check or a real one (server_checks();
  since 0.4.0 there is no demo shop to check), replays can be stored (replay_storage():
  the replays folder can be written, or made where the nearest existing folder above it can be written, which
  codec, and whether this Python can read the chunks already there; a write refused although the folder's permissions
  allow it is a sandbox's doing, a SKIP that asks for doctor in the user's own terminal, never "storage broken");
- this computer (doctor_machine.py): Python and zstd, free disk space, the lists' age, `agentcake` on PATH;
- the web server's log import, once one has run (doctor_logs.py): how the last went, which headers the log lacks;
- the user's own website, when its folder (--dir, site_dir) or a page of it (--url, site_url) is known: its files
  (doctor_site.py) and that page, opened (doctor_live.py).
Returns 0 when no check failed (a WARN or a SKIP does not fail), else 1. Its words are in data/copy.en.json.
"""
import errno
import json
import os
import platform
import socket
import sqlite3
import stat
import tempfile
from collections import namedtuple
from http import HTTPStatus

from agentcake import codecs, paths, replay_chunks
from agentcake.config import LOCAL_HOST, base_url, load_cfg
from agentcake.datafiles import load
from agentcake.doctor_live import page_checks
from agentcake.doctor_logs import logs_checks
from agentcake.doctor_lines import SKIP, passed, print_checks, summary
from agentcake.doctor_machine import machine_checks
from agentcake.doctor_site import website_checks
from agentcake.ping import http_get
from agentcake.site_code import SiteCode
from agentcake.site_setup import SCRIPT_PATH
from agentcake.wording import text

REFUSED, BLOCKED = "refused", "blocked"  # why Agent Cake did not answer: nothing listens; this process may not connect
Reach = namedtuple("Reach", "health problem error")  # the /api/health answer, else why not and the error's words


def reach(c):
    """Whether Agent Cake answers on 127.0.0.1:<port>. A refused connection means nothing listens there (REFUSED); one
    that fails with an error of data/doctor.json's blocked_errors means this process may not connect at all (BLOCKED:
    a sandbox, such as an AI tool's without network access); any other failure is reported in its own words."""
    try:
        socket.create_connection((LOCAL_HOST, c["port"]), timeout=c["health_timeout_s"]).close()
    except ConnectionRefusedError as error:
        return Reach(None, REFUSED, error.strerror)
    except OSError as error:
        if errno.errorcode.get(error.errno) in load("data/doctor.json")["blocked_errors"]:
            return Reach(None, BLOCKED, error.strerror or str(error))
        return Reach(None, str(error), str(error))
    status, answer = http_get(base_url(c) + "/api/health", c["health_timeout_s"])
    try:
        health = json.loads(answer) if status == HTTPStatus.OK else None
    except ValueError:
        health = None
    if not isinstance(health, dict):
        detail = text("doctor_not_health", base=base_url(c), status=status)
        return Reach(None, detail, detail)
    return Reach(health, None, None)


def replay_storage():
    """("replay storage", verdict, info): the replays folder can be written (before the first start: made, in the
    nearest existing folder above it), which codec new chunks get, and no stored chunk needs a codec this Python lacks
    (zstd chunks copied to a Python older than 3.14). A write that a sandbox refuses is not checked here (SKIP)."""
    folder, codec = replay_chunks.replay_dir(), codecs.writer_codec()
    place = paths.nearest_existing(folder)
    refusal = write_refusal(place)
    if refusal and sandbox_refused(refusal, place):
        return text("doctor_replays"), SKIP, text("doctor_replays_blocked", folder=paths.tilde(place),
                                                  error=refusal.strerror, launcher=paths.launcher())
    info = text("doctor_replays_info", folder=paths.tilde(folder), codec=codec)
    if refusal:
        info += "; " + text("doctor_replays_not_writable", error=refusal.strerror or refusal)
    if codec != "zstd":
        info += " " + text("doctor_replays_zlib", version=platform.python_version())
    unreadable = _chunks_needing_zstd() if "zstd" not in codecs.available() else 0
    if unreadable:
        info += "; " + text("doctor_replays_unreadable", count=unreadable)
    return text("doctor_replays"), not refusal and not unreadable, info


def write_refusal(place):
    """None when this process may make a file in folder place, else the OSError that says why not. os.access answers
    without writing anything; only when it says no is one file made there (and removed at once), for the error."""
    if os.path.isdir(place) and os.access(place, os.W_OK):
        return None
    try:
        with tempfile.TemporaryFile(dir=place):
            return None
    except OSError as error:
        return error


def sandbox_refused(error, place):
    """Whether a refused write is a sandbox's doing (an AI tool's, which lets it write only in its own folder): the
    error is one of data/doctor.json's write_blocked_errors, and place is a folder whose owner, group and mode let
    this user write in it, as the file system alone would decide (os.access asks the sandbox too)."""
    if errno.errorcode.get(error.errno) not in load("data/doctor.json")["write_blocked_errors"]:
        return False
    try:
        folder = os.stat(place)
    except OSError:
        return False
    if not stat.S_ISDIR(folder.st_mode):
        return False
    if os.geteuid() == 0:  # root may write in any folder whatever its mode
        return True
    if folder.st_uid == os.geteuid():  # the owner's bits decide for the owner, whatever the group's say
        needed = stat.S_IWUSR | stat.S_IXUSR
    elif folder.st_gid == os.getegid() or folder.st_gid in os.getgroups():
        needed = stat.S_IWGRP | stat.S_IXGRP
    else:
        needed = stat.S_IWOTH | stat.S_IXOTH
    return folder.st_mode & needed == needed


def _chunks_needing_zstd():
    """How many stored chunks are zstd (read-only look at cake.db; 0 when there is no database or chunks table)."""
    if not os.path.exists(paths.db_file()):
        return 0
    con = sqlite3.connect(f"file:{paths.db_file()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM chunks WHERE codec='zstd'").fetchone()[0]
    except sqlite3.OperationalError:  # a 0.3.4 database: no chunks table yet
        return 0
    finally:
        con.close()


def not_reached(reached, base):
    """The four server lines when Agent Cake did not answer: what happened, and the three lines that needed it."""
    needed = [text(check) for check in ("doctor_page", "doctor_script", "doctor_visit")]
    if reached.problem == BLOCKED:
        return [(text("doctor_running"), False, text("doctor_blocked", base=base, error=reached.error))] + \
               [(check, SKIP, text("doctor_not_checked_blocked")) for check in needed]
    if reached.problem == REFUSED:
        down = text("doctor_not_running")
        return [(text("doctor_running"), False, text("doctor_start_it", launcher=paths.launcher()))] + \
               [(check, False, down) for check in needed]
    return [(text("doctor_running"), False, text("doctor_reach_error", base=base, error=reached.error))] + \
           [(check, SKIP, text("doctor_not_checked")) for check in needed]


def server_checks(c, reached, base):
    """(check, verdict, info) for the running server, its local page, the page script it serves (with this
    installation's site key in it) and a visit received, a self-check or a real one (a server that records its site's
    visits never needs a ping); reached is reach()'s answer."""
    if not reached.health:
        return not_reached(reached, base)
    timeout, health = c["http_timeout_s"], reached.health
    page_status, _ = http_get(base + "/", timeout)
    script_status, script = http_get(base + SCRIPT_PATH, timeout)
    site_key = c.get("site_key")
    script_ok = script_status == HTTPStatus.OK and bool(site_key) and site_key in script
    selfcheck, real = health.get("selfcheck_visits", 0), health.get("real_sessions", 0)
    return [(text("doctor_running"), True, f"{base}/"),
            (text("doctor_page"), page_status == HTTPStatus.OK,
             text("doctor_page_info", base=base, status=page_status)),
            (text("doctor_script"), script_ok, text("doctor_script_info", base=base, status=script_status)),
            (text("doctor_visit"), selfcheck + real > 0, text("doctor_visit_info", selfcheck=selfcheck, real=real))]


def site_checks(c, folder, url):
    """The website's files (when its folder is known) and one of its pages (when its address is known)."""
    code = SiteCode(folder) if folder else None
    checks = website_checks(c, folder, code) if code else []
    if not url:
        return checks + [(text("doctor_live_script"), SKIP, text("doctor_live_no_url", launcher=paths.launcher()))]
    return checks + page_checks(c, url, code.framework if code else c.get("framework") or "unknown")


def doctor(d=None, url=None):
    c = load_cfg()
    base, reached = base_url(c), reach(c)
    checks = server_checks(c, reached, base) + [replay_storage()] + machine_checks(c) + logs_checks()
    folder, url = d or c.get("site_dir") or None, url or c.get("site_url") or None
    site = site_checks(c, folder, url) if folder or url else []  # optional: the user's own website
    print_checks(checks)
    if site:
        print(text("doctor_site_header"))
        print_checks(site)
    else:
        print(text("doctor_site_none"))
    if reached.problem == BLOCKED:
        print(text("doctor_blocked_next", launcher=paths.launcher()))
    elif not reached.health:
        print(text("doctor_sandbox_note"))
    print(summary(checks + site, base))
    return 0 if passed(checks + site) else 1
