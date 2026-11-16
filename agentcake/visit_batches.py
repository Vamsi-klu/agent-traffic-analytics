"""A visit's stored uploads, given back in cake.js's upload format, for the readers built on its batches.

batches(con, session_id) -> one batch per page view, in the order the page views' first records were made:
{"v", "s", "pv", "seq", "t", "u", "e", "r", "x"}, with the page view's header (t, u) from its first batch in the
batches table and its records from the streams in time order, each once (a batch sent twice was stored once).
env_signals.from_cake reads these as it reads cake.js's own batches. A cake 0.3.4 visit has no page views: it
comes back as one batch with pv None and the session's URL. A page view that began in an earlier session of the tab
and went on in this one (a new session begun on the page after 30 minutes without activity, session_split.py) brings
its signal records from that session too: the page record, the environment and the checks were made once, when the
page opened, and they describe the browser this session runs in as well.

collect_requests(con, session_id) -> the network facts of the visit's upload requests (netfacts.request_facts),
oldest first, in from_cake's collect_requests shape: {"headers": [[name, value], ...]}, with "ip_class" when the
address was looked up (no key: unknown). The server half of each page is in the srv table (batches.token_id), and in
the requests rows of source "log" a web server's log added: page requests, which are left out here.
"""
import json

from agentcake import streams
from agentcake.upload import FORMAT_VERSION, RECORD_FIELDS

FIELD_OF_STREAM = {stream: key for key, stream, _ in RECORD_FIELDS}
SIGNALS_STREAM = "env"  # the stream cake.js's signal records ("x") are kept in
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
    _earlier_signals(con, session_id, views)
    url = (con.execute("SELECT url FROM sessions WHERE id=?", (session_id,)).fetchone() or (None,))[0]
    out = []
    for pv, records in views.items():
        made, page_url = heads.get(pv, (None, url))
        out.append({"v": FORMAT_VERSION, "s": session_id, "pv": pv, "seq": 0, "t": made, "u": page_url, **records})
    return out


def _earlier_signals(con, session_id, views):
    """Put before each page view's own signal records those an earlier session of the tab kept for it."""
    shared = [pv for pv in views if pv is not None]
    if not shared:
        return
    marks = ",".join("?" * len(shared))
    earlier = [found for (found,) in con.execute(
        f"SELECT DISTINCT b.session_id FROM batches b JOIN sessions s ON s.id = b.session_id WHERE b.pv IN ({marks}) "
        "AND b.session_id != ? AND s.start_ms <= (SELECT start_ms FROM sessions WHERE id=?)",
        (*shared, session_id, session_id))]
    signals = FIELD_OF_STREAM[SIGNALS_STREAM]
    for other in earlier:
        brought = {}
        for _, _, text, page in streams.read_events(con, other, [SIGNALS_STREAM], with_page=True):
            if page in views:
                brought.setdefault(page, []).append(json.loads(text))
        for page, records in brought.items():
            views[page][signals] = records + views[page][signals]
