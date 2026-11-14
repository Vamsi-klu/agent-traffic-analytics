"""A visit's stored uploads, given back in cake.js's upload format, for the readers built on its batches.

batches(con, session_id) -> one batch per page view, in the order the page views' first records were made:
{"v", "s", "pv", "seq", "t", "u", "e", "r", "x"}, with the page view's header (t, u) from its first batch in the
batches table and its records from the streams in time order, each once (a batch sent twice was stored once).
env_signals.from_cake reads these as it reads cake.js's own batches. A cake 0.3.4 visit has no page views: it
comes back as one batch with pv None and the session's URL.

collect_requests(con, session_id) -> the network facts of the visit's upload requests (netfacts.request_facts),
oldest first, in from_cake's collect_requests shape: {"headers": [[name, value], ...]}, with "ip_class" when the
address was looked up (no key: unknown). The server half of each page is in the srv table (batches.token_id), and in
the requests rows of source "log" a web server's log added: page requests, which are left out here.
"""
import json

from agentcake import streams
from agentcake.upload import FORMAT_VERSION, RECORD_FIELDS

FIELD_OF_STREAM = {stream: key for key, stream, _ in RECORD_FIELDS}
LOG_SOURCE = "log"  # log_match.SOURCE: the requests rows `agentcake logs import` adds


def collect_requests(con, session_id):
    out = []
    for (text,) in con.execute("SELECT facts FROM requests WHERE session_id=? ORDER BY recv_ms, rowid", (session_id,)):
        facts = json.loads(text)
        if facts.get("source") == LOG_SOURCE:  # a page request from the web server's log, not an upload
            continue
        out.append({"headers": facts["headers"], **({"ip_class": facts["ip_class"]} if "ip_class" in facts else {})})
    return out


def batches(con, session_id):
    heads = {}
    for pv, t, url in con.execute("SELECT pv, t, url FROM batches WHERE session_id=? ORDER BY pv, seq", (session_id,)):
        heads.setdefault(pv, (t, url))
    views = {}
    for _, stream, text, page in streams.read_events(con, session_id, with_page=True):
        view = views.setdefault(page, {key: [] for key in FIELD_OF_STREAM.values()})
        view[FIELD_OF_STREAM[stream]].append(json.loads(text))
    if not views:
        return []
    url = (con.execute("SELECT url FROM sessions WHERE id=?", (session_id,)).fetchone() or (None,))[0]
    out = []
    for pv, records in views.items():
        made, page_url = heads.get(pv, (None, url))
        out.append({"v": FORMAT_VERSION, "s": session_id, "pv": pv, "seq": 0, "t": made, "u": page_url, **records})
    return out
