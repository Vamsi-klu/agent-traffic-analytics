"""Where visits come from, for the settings page (S5.5): each source's state and when it last sent something, where the
website's visits arrive, and what the server half says about the site's server.

    sources(con, c, now_ms) -> {"sources", "last_seen", "route", "server_half"}, the Settings fields of these names

The sources are the website and its server half (D37 removed the demo shop; the sessions it recorded are not a source
any more). A source is receiving when something arrived in the last data/api.json receiving_days, waiting when it is
set up and nothing came lately, and not connected otherwise: the website once site_domain or site_dir is set or a visit
came, the server half once server mode has the secret it shares with the site's server, or a token or a log import
came. A first visit is receiving in the very next answer, and the open page
asks again every refresh_ms (I3). last_seen is each source's latest moment in words (periods.when), None before any.
route says where the website's visits arrive: this computer's local listener, or in server mode the public listener
under path_prefix on the site's own domain (SERVER.md).
server_half: missing names the request headers (written as people write them) that none of the website's latest
server_half_tokens tokens carried, though a browser sends them with every page request over HTTPS: something in front
of the site's server (a proxy, a CDN) removes them, as doctor's live check finds for one test page (doctor_live.py);
empty when no such token came or one had them. logs is the last log import (log_report.py): when, the log's format,
and the recommended fields its log lacks or leaves empty; None before the first.
"""
import json

from agentcake import log_report
from agentcake.api import answers, periods
from agentcake.datafiles import load
from agentcake.doctor_live import display
from agentcake.edge_secret import srv_secret
from agentcake.units import MS_PER_DAY

RECEIVING, WAITING, NOT_CONNECTED = "receiving", "waiting", "not_connected"
THIS_COMPUTER, SERVER = "this_computer", "server"
FETCH = "sf"  # protocol: the token's Sec-Fetch fields (edge_token.request_facts)


def sources(con, c, now_ms):
    numbers = answers.numbers()
    since = now_ms - numbers["receiving_days"] * MS_PER_DAY
    site_ms = con.execute("SELECT MAX(end_ms) FROM sessions WHERE is_test = 0 AND origin = 'site'").fetchone()[0]
    token_ms = con.execute("SELECT MAX(r.recv_ms) FROM srv r JOIN sessions s ON s.id = r.session_id "
                           "WHERE s.origin = 'site'").fetchone()[0]
    logs = log_report.last(con)
    half_ms = max((ms for ms in (token_ms, logs and logs.get("last_ms")) if ms is not None), default=None)
    server_mode = bool(c.get("public_listen"))
    seen = {"site": site_ms, "server_half": half_ms}
    set_up = {"site": bool(c.get("site_domain") or c.get("site_dir")), "server_half": server_mode and bool(srv_secret())}
    return {"sources": {name: _state(ms, set_up[name], since) for name, ms in seen.items()},
            "last_seen": {name: None if ms is None else periods.when(ms, now_ms) for name, ms in seen.items()},
            "route": SERVER if server_mode else THIS_COMPUTER,
            "server_half": {"missing": _missing(con, numbers["settings"]), "logs": _logs(logs, now_ms)}}


def _state(last_ms, set_up, since):
    if last_ms is not None and last_ms >= since:
        return RECEIVING
    return WAITING if set_up or last_ms is not None else NOT_CONNECTED


def _missing(con, settings):
    """The headers none of the website's latest tokens had, in data/api.json's order; [] without tokens."""
    bodies = [body for (body,) in con.execute(
        "SELECT r.body FROM srv r JOIN sessions s ON s.id = r.session_id WHERE s.origin = 'site' "
        "ORDER BY r.recv_ms DESC LIMIT ?", (settings["server_half_tokens"],))]
    fetched = [(json.loads(body) if body else {}).get(FETCH) or {} for body in bodies]
    headers = load("data/edge.json")["headers"]
    return [display(headers[role]) for role, field in settings["server_half_headers"].items()
            if fetched and not any(values.get(field) for values in fetched)]


def _logs(report, now_ms):
    if not report:
        return None
    return {"last": periods.when(report["last_ms"], now_ms), "format": report["format"],
            "missing": [display(name) for name in report.get("missing") or []],
            "empty": [display(name) for name in report.get("empty") or []]}
