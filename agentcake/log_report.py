"""The report of the last log import (S4.4), for doctor (doctor_logs.py) and the settings page (S5.5).

update(con, envelope, counts, now_ms) adds one /edge request's counts (log_match.COUNTS) to the report of its import
run, which the database's settings table keeps under "log_import": the run's id, the log format, the recommended
fields the format lacks and those empty on every page request (as `logs import` found them), first_ms and last_ms,
and the counts summed over the run. A request of another run starts a new report. The caller holds store.LOCK and
commits. last(con) reads the report.

stored_report() reads the same report straight from cake.db without writing to it, for doctor (doctor_logs.py, whose
line says how the last import went and which recommended headers the log lacks) and the settings page (S5.5); None
when there is no database, no settings table yet, or no import.
"""
import json
import os
import sqlite3

from agentcake import paths, store
from agentcake.log_match import COUNTS

SETTING = "log_import"


def update(con, envelope, counts, now_ms):
    report = store.setting(con, SETTING)
    if not report or report.get("run") != envelope["run"]:
        report = {"run": envelope["run"], "first_ms": now_ms, **dict.fromkeys(COUNTS, 0)}
    report.update(format=envelope["format"], missing=envelope["fields"]["missing"],
                  empty=envelope["fields"]["empty"], last_ms=now_ms)
    for name in COUNTS:
        report[name] = report.get(name, 0) + counts.get(name, 0)
    store.set_setting(con, SETTING, report, now_ms)


def last(con):
    return store.setting(con, SETTING)


def stored_report():
    """The report in cake.db, read without writing; None when there is no database, no settings table, no import."""
    if not os.path.exists(paths.db_file()):
        return None
    con = sqlite3.connect(f"file:{paths.db_file()}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT value FROM settings WHERE key=?", (SETTING,)).fetchone()
    except sqlite3.OperationalError:  # a database older than the settings table
        return None
    finally:
        con.close()
    return json.loads(row[0]) if row else None
