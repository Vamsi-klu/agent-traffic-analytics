"""POST /edge: a web server's page requests from its access log, signed with the server half's secret.

`agentcake logs import` (logs.py) reads a log where it lies and sends its page requests here in batches, each an
envelope {"v", "run", "format", "fields", "records"} (data/logs.json "edge"). Only a sender holding this AgentCake's
server-half secret ($CAKE_HOME/srv_secret, the one a site's middleware signs page tokens with) is heard: the header
Cake-Edge-Signature signs the request's time and body with it (edge_signature.py says how).
No signature, another secret, a body changed after signing, a time outside the page tokens' window (the settings
token_max_age_ms and token_max_future_ms), or no secret here: 403, before the body is read. A signed body that is no
envelope: 400. Otherwise log_match.record() matches and keeps the records, log_report.update() adds them to the
import's report, and the answer is their counts as JSON; then the sessions they were kept for are judged again
(judging.on_log_lines), so that a final verdict takes its log lines in.

Both listeners answer it (routes.py). The web server that writes the log is usually the load balancer in front of
AgentCake (SERVER.md), the one host the firewall lets reach the public port, and the load balancer's path rules never
forward /edge from the internet; on one machine, `logs import` sends to the local page's port. The records hold
visitors' addresses: log_match looks them up and hashes them, and nothing here keeps or prints them.
"""
import json
from http import HTTPStatus

from agentcake import config, judging, log_match, log_report, store
from agentcake.datafiles import load
from agentcake.edge_secret import srv_secret
from agentcake.edge_signature import HEADER, verified
from agentcake.responses import JSON, TEXT, Response
from agentcake.storage_config import now_ms as clock_ms

SPEC = load("data/logs.json")
EDGE = SPEC["edge"]
ROUTE = EDGE["route"]
MAX_RECORDS = EDGE["max_records"]
REPORTED_FIELDS = ("missing", "empty")


def receive(request):
    c, now_ms = config.load_cfg(), clock_ms()
    if not verified(srv_secret(), request.headers.get(HEADER), request.body, now_ms, c):
        return Response(HTTPStatus.FORBIDDEN, "forbidden", TEXT)
    envelope = read_envelope(request.body)
    if envelope is None:
        return Response(HTTPStatus.BAD_REQUEST, "not an envelope of log records", TEXT)
    with store.LOCK:
        con = store.db()
        try:
            before = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM requests").fetchone()[0]
            counts = log_match.record(con, envelope, now_ms, c)
            log_report.update(con, envelope, counts, now_ms)
            matched = [session for (session,) in con.execute(  # the rows record() added: one per matched line
                "SELECT DISTINCT session_id FROM requests WHERE rowid > ?", (before,))]
            con.commit()
        finally:
            con.close()
    judging.on_log_lines(matched, now_ms, c)
    return Response(HTTPStatus.OK, json.dumps(counts), JSON)


def read_envelope(body):
    """The envelope in a body ({"run", "format", "fields", "records"}), or None. Its records are checked one by one
    in log_match; here only that they are a list of at most max_records."""
    try:
        data = json.loads(body)
    except ValueError:  # also a body that is not UTF-8
        return None
    if not isinstance(data, dict) or data.get("v") != EDGE["version"]:
        return None
    records, run, name, caps = data.get("records"), data.get("run"), data.get("format"), EDGE["max_chars"]
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        return None
    if not (log_match.short_text(run, caps["run"]) and log_match.short_text(name, caps["format"])):
        return None
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    return {"run": run, "format": name, "records": records,
            "fields": {kind: _field_names(fields.get(kind)) for kind in REPORTED_FIELDS}}


def _field_names(value):
    """The recommended fields named in a report, in data/logs.json's order; anything else is left out."""
    named = {name for name in value if isinstance(name, str)} if isinstance(value, list) else set()
    return [name for name in SPEC["recommended"]["fields"] if name in named]
