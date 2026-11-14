"""`doctor`, the line about the web server's log import: logs_checks().

No line before the first `agentcake logs import` reached this Agent Cake: most installs never use it. Afterwards one
line on the last import, whose report log_report.py keeps in cake.db (read here without writing): the log format, when
it ran, how many page requests it sent and how many matched a visit, then each recommended header (data/logs.json
"recommended") the format lacks or leaves empty on every page request, by name.
- PASS: the log has every recommended header.
- WARN: some header is missing or always empty. The import works, but the server half has less to say: no Sec-Fetch-*
  values, no signature to verify. The line points at `agentcake logs formats` and docs/*.example.
- FAIL: no line can match, because the uploads carry no visitor's address (trust_lb is off, or the uploads do not
  come through the load balancer that gives it), so log_match has nothing to compare a line's address with.
"""
import time

from agentcake import log_report
from agentcake.doctor_lines import WARN
from agentcake.units import MS_PER_S
from agentcake.wording import text


def logs_checks():
    """[] before any import, else [logs_line(the last import's report)]."""
    report = log_report.stored_report()
    return [] if report is None else [logs_line(report)]


def logs_line(report):
    when = time.strftime(text("doctor_logs_time"), time.gmtime(report["last_ms"] / MS_PER_S))
    info = text("doctor_logs_info", format=report["format"], when=when, records=report["records"],
                matched=report["matched"])
    if report["missing"]:
        info += text("doctor_logs_missing", fields=", ".join(report["missing"]))
    if report["empty"]:
        info += text("doctor_logs_empty", fields=", ".join(report["empty"]))
    if report["views_without_address"] and not report["matched"]:
        return text("doctor_logs"), False, info + text("doctor_logs_no_address")
    if report["missing"] or report["empty"]:
        return text("doctor_logs"), WARN, info + text("doctor_logs_formats")
    return text("doctor_logs"), True, info
