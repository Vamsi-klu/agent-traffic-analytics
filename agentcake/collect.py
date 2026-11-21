"""POST /collect: one upload from cake.js (the counterpart of PostHog 1.0's posthog/api/capture.py, which
also writes what it receives within the request).

An upload (docs/collect-format.md, version 1; cake 0.3.4's batches are still taken) is unzipped and read (upload.py),
and its site key must be this cake's. Its session is the one PostHog's time rules give its activity (session_split.py:
a new session after 30 minutes without activity or 24 hours, also for a script that does not cut its own). Where it
came from is read from its Origin and Referer headers (site_origin.py);
the request's network facts (netfacts.py) from its headers and, on server mode's public listener with trust_lb,
from what the load balancer says about the connection: the visitor's address is looked up in the bundled lists and
hashed, never kept (no other forwarding header is ever read). collect_store.py keeps it: the request's facts; the
batch's key, so a batch sent twice is stored once; the visit; the server-half token; each record in its stream with
its page view, within the limits (settings max_events_per_post, max_events_per_session; field caps in
data/sizes.json). A request that carries Web Bot Auth headers is checked here, where the whole request is at hand
(webbotauth.SessionVerifier: the first signed request of a session, once; a signature that does not verify with the
request's Host is tried with the site's other names, which a front door that replaces Host leaves out), and the
result is kept with the request's facts for the verdict (evidence.py). Sessions older than the retention are pruned.
Only after the transaction is committed does judging.on_data decide whether to judge the session now (schedule.py:
every batch on this computer, at most every public_judge_interval_ms on the public listener; the maintenance round
and an opened page do the rest).

Answers 204, also to a copy of a batch already kept (so cake.js stops sending it), with X-Cake-Token when a token was
read: ok | dup | reuse | replay | stale | bad | off (edge_token.take_token; reuse is a stored copy of a page, after a
304 or going back, showing an earlier page view's token). A refused upload gets its status (400 unreadable, 403
another site key, 413 too large or too many records) and is counted in the refusals table. On the public listener a
visit cannot mark itself a test.
"""
import json
from http import HTTPStatus
from urllib.parse import urlencode, urlsplit

from agentcake import collect_store, config, evidence, judging, netfacts, session_split, site_origin, store, upload
from agentcake.datafiles import load, sizes
from agentcake.detect import httpsig, lists, webbotauth
from agentcake.responses import HTML, TEXT, Response
from agentcake.storage_config import now_ms as clock_ms

FETCH_METADATA_PREFIX = "sec-fetch"  # the browser's Sec-Fetch-* request headers (W3C Fetch Metadata)
TOKEN_STATUS_HEADER = "X-Cake-Token"
HEADERS = load("data/edge.json")["headers"]
COLLECT_METHOD = "POST"  # protocol: cake.js uploads with POST (docs/collect-format.md)
HOST = "Host"  # protocol: the request's authority (RFC 9110 7.2), what a Web Bot Auth signature's @authority covers
# The public listener sits behind a TLS-terminating load balancer (SERVER.md); the local one is plain HTTP.
SCHEMES = {True: "https", False: "http"}  # protocol: URI schemes
_verifier = []  # (the lists it was made from, their webbotauth.SessionVerifier): _session_verifier()


def from_local(request):
    return collect(request, public=False)


def from_public(request):
    return collect(request, public=True)


def collect(request, public):
    c, now = config.load_cfg(), clock_ms()
    try:
        batch = read(request.body, c)
    except upload.Refused as refusal:
        _count(refusal, now)
        return Response(refusal.status, refusal.reason, TEXT)
    visit = _visit(request, batch, c, public)
    with store.LOCK:
        con = store.db()
        try:
            batch = session_split.route(con, batch)
            before = judging.state(con, batch.session)
            kept = collect_store.record(con, batch, visit, now, c)
            store.prune(con, c.get("retention_days", 0))
            con.commit()
        finally:
            con.close()
    if not kept.copy:
        judging.on_data(batch.session, before, now, public, c)
    # The token's fate is told to cake.js only as a status: a stale or forged token is not an error for the visitor.
    return Response(HTTPStatus.NO_CONTENT, b"", HTML, {TOKEN_STATUS_HEADER: kept.token} if kept.token else {})


def read(body, c):
    """The Batch of an upload, or upload.Refused. A gzipped upload may unzip to as much as the local listener reads."""
    data = upload.parse(upload.decode_body(body, c["local_max_body_bytes"]))
    if not c.get("site_key") or data.get("k") != c["site_key"]:
        raise upload.Refused("site_key", HTTPStatus.FORBIDDEN)
    return upload.read_batch(data, sizes()["max_chars"], c["max_events_per_post"])


def _visit(request, batch, c, public):
    headers = request.headers
    cap = sizes()["max_chars"]["sec_fetch_value"]
    sec_fetch = json.dumps({k: v[:cap] for k, v in headers.items() if k.lower().startswith(FETCH_METADATA_PREFIX)})
    origin = site_origin.classify(headers, batch.url, c, public)
    net, address = netfacts.net_facts(headers, c) if public else (None, None)
    facts = netfacts.request_facts(headers, origin, net is not None, netfacts.look_up(address))
    checked = _web_bot_auth(request, batch.session, c, public)
    if checked:
        facts[evidence.WEB_BOT_AUTH] = checked
    return collect_store.Visit(origin=origin, sec_fetch=sec_fetch, net=net, address=address, public=public, facts=facts)


def _web_bot_auth(request, session_id, c, public):
    """The Web Bot Auth result of a request carrying Signature-Input or Signature-Agent, as evidence.py reads it;
    None for a request without them, or when the bundled lists cannot be read (doctor says why). The target is
    rebuilt from what the listener kept, so a signature over the path or query may not verify: verdict.json's
    signature_proxy_components then make it "could not verify", never impersonation. The authority is the request's
    Host, then the site's other names (site_authorities)."""
    headers = request.headers
    if not (headers.get(HEADERS["signature_input"]) or headers.get(HEADERS["signature_agent"])):
        return None
    try:
        verifier = _session_verifier()
    except lists.ListsError:
        return None
    query = urlencode(request.query, doseq=True)
    target = ((c.get("path_prefix") or "") if public else "") + request.path + ("?" + query if query else "")
    signed = httpsig.Request(COLLECT_METHOD, SCHEMES[public], headers.get(HOST) or "", target, list(headers.items()))
    result = verifier.verify(session_id, signed, site_authorities(c))
    return {name: getattr(result, name) for name in evidence.VERIFICATION_FIELDS}


def _session_verifier():
    """The verifier of the key directories in the lists in use, made on first use and again once an update replaced
    the lists (lists.current() is then another snapshot); raises lists.ListsError when they cannot be read."""
    snapshot = lists.current()
    if not _verifier or _verifier[0][0] is not snapshot:
        _verifier[:] = [(snapshot, webbotauth.SessionVerifier(snapshot.key_directories()))]
    return _verifier[0][1]


def site_authorities(c):
    """The names an agent may have signed a request to the site for: its site_domain with and without
    www., then the host of public_url (the subdomain route's address, cake.example.com), each once; none unset."""
    names = []
    domain = (c.get("site_domain") or "").strip().lower()
    if domain:
        www = site_origin.WWW  # the label a site's main name is also served under (www.example.com)
        names += [domain, domain[len(www):] if domain.startswith(www) else www + domain]
    public_host = urlsplit(c.get("public_url") or "").netloc.lower()  # an origin: config.py refuses anything else
    if public_host and public_host not in names:
        names.append(public_host)
    return names


def _count(refusal, now):
    with store.LOCK:
        con = store.db()
        try:
            collect_store.count(con, refusal.reason, refusal.records, now)
            con.commit()
        finally:
            con.close()
