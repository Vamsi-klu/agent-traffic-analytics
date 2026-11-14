"""`agentcake delete --session <id> | --visitor <visit id> [--dry-run]`.

A session is one visit: cake keeps a visit under the id cake.js keeps in the visitor's browser (`cake_sid` in
sessionStorage), which is the session id the dashboard shows. --session takes an id read off the dashboard, --visitor
the visit id as a site read it in the visitor's browser (a consent banner can read `cake_sid` before it calls
window.cake.stop() and hand it to the site's server); both name the same rows. Either can be given several times.

run(ids, dry_run) deletes them where it is safe (delete.py says what goes): in this process when no cake runs on this
data folder, else by asking the running cake (POST /api/delete on the local page's own address, which only this
computer can reach), so that one process writes the database and the chunk files. A pid file naming a live process
that does not answer as cake stops it: that cake might be on another port, and two writers would damage the chunk
files. --dry-run only reads, so it runs here either way. The exit code is 0 when something was deleted (or would be),
1 when nothing was recorded under any id, the running cake refused, or traces may be left (the database file could
not be rewritten, or a reader kept its write-ahead log).
"""
import json
import os
import urllib.error
import urllib.request

from agentcake import daemon, delete, paths
from agentcake.config import base_url, load_cfg
from agentcake.datafiles import sizes
from agentcake.responses import JSON
from agentcake.wording import text

FLAGS = ("--session", "--visitor")
DRY_RUN = "--dry-run"


class DeleteFailed(RuntimeError):
    """The running cake answered with an error."""


def parse(args):
    """(ids, dry_run) from the arguments; ValueError with what to print when they are not a delete command."""
    ids, dry_run, rest = [], False, list(args)
    while rest:
        word = rest.pop(0)
        if word == DRY_RUN:
            dry_run = True
        elif word in FLAGS and rest:
            ids.append(rest.pop(0))
        else:
            raise ValueError(text("delete_usage"))
    bad = [i for i in ids if not delete.valid_id(i)]
    if bad:
        raise ValueError(text("delete_bad_id", id=bad[0], max=sizes()["max_chars"]["session_id"]))
    if not ids:
        raise ValueError(text("delete_usage"))
    return ids, dry_run


def run(ids, dry_run=False):
    c = load_cfg()
    here = daemon.running_here()
    if dry_run:
        return report(delete.preview(ids), dry_run=True)
    if not here:
        pid = _live_pid()
        if pid is not None:
            print(text("delete_unsure_running", pid=pid, pid_file=paths.tilde(paths.pid_file()), port=c["port"]))
            return 1
        try:
            return report(delete.delete_sessions(ids))
        except delete.WipeRefused as refused:
            print(text("delete_refused", error=refused))
            return 1
    try:
        return report(ask_running_cake(base_url(c), ids, c["delete_timeout_s"]))
    except DeleteFailed as failed:
        print(text("delete_failed_remote", error=failed))
        return 1


def ask_running_cake(base, ids, timeout):
    """The running cake's answer to POST /api/delete for these ids, sent as this computer's own page would send it."""
    request = urllib.request.Request(base + "/api/delete", data=json.dumps({"sessions": ids}).encode(), method="POST",
                                     headers={"Content-Type": JSON, "Origin": base, "Accept": JSON})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        with error:
            body = error.read()
        try:
            said = json.loads(body).get("error")
        except (ValueError, AttributeError):
            said = None
        raise DeleteFailed(said or f"HTTP {error.code}") from error
    except OSError as error:  # refused, reset, timed out
        raise DeleteFailed(str(error)) from error


def report(result, dry_run=False):
    """Print what was deleted (or would be); returns the exit code."""
    found = False
    for item in result["sessions"]:
        if item["found"]:
            found = True
            entry = "delete_would" if dry_run else "delete_done"
            print(text(entry, id=item["id"], rows=sum(item["rows"].values()), chunks=item["chunks"],
                       bytes=item["chunk_bytes"]))
        else:
            print(text("delete_nothing", id=item["id"]))
    backup_rows = sum(backup["rows"] for backup in result["backups"])
    if backup_rows:
        found = True
        print(text("delete_backups_would" if dry_run else "delete_backups", rows=backup_rows,
                   files=sum(1 for backup in result["backups"] if backup["rows"])))
    if result["log_lines"]:
        found = True
        print(text("delete_log_would" if dry_run else "delete_log", lines=result["log_lines"],
                   log=paths.tilde(paths.log_file())))
    reclaim = result.get("reclaim")
    if reclaim:
        print(text("delete_reclaim", deleted=reclaim["deleted"], compacted=reclaim["compacted"],
                   bytes=reclaim["freed_bytes"]))
    return 0 if found and not _traces_left(result) else 1


def _traces_left(result):
    """True (and why, printed) when the database or a backup could not be rewritten or its log emptied."""
    left = False
    for name, outcome in [(paths.tilde(paths.db_file()), result.get("database"))] + \
                         [(backup["file"], backup) for backup in result["backups"]]:
        if outcome and outcome.get("error"):
            print(text("delete_not_rewritten", file=name, error=outcome["error"]))
            left = True
        elif outcome and not outcome.get("log_cleared", True):
            print(text("delete_wal_busy", file=name))
            left = True
    return left


def _live_pid():
    """The pid in $CAKE_HOME/cake.pid when that process is alive, else None."""
    try:
        with open(paths.pid_file()) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)  # signal 0: no signal, only whether the process exists
    except ProcessLookupError:
        return None
    except PermissionError:  # it exists, run by another user
        return pid
    return pid
