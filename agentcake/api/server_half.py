"""The "Server half" table of a session (the session page draws it): what the site's server saw of each page request.

One row per server-half token the session brought (the srv table), in the order the pages were served:
when (the token's time, on the site's server's clock, in ms from the session's start, never before it), the path, the
Sec-Fetch-* headers, a signature's Signature-Agent (the token carries no signature to check, so it is never verified
here: collect checks the signatures of cake.js's own requests), and how cake.js's uploads compare with the page
request: the same network, User-Agent and Accept-Language (null when either side did not say), and how many more page
views brought the same token again because the browser showed them a stored copy (reuses). network is what the
load balancer said about cake.js's uploads and where their address is (server mode with trust_lb; null on this
computer), with the credit DB-IP asks for when it shows a country of its database (places.attribution). note says
why page views have no row, when some have none (api.en.json server_half).

    table(con, session_id, net_json, epoch, page_views) -> ServerHalf
"""
import json

from agentcake import config
from agentcake.api import places
from agentcake.api.answers import words

FETCH = {"site": "s", "mode": "m", "dest": "d", "user": "u"}  # protocol: the token's Sec-Fetch fields (edge_token)
SIGNATURE, SIGNED, SIGNED_INPUT, SIGNATURE_AGENT = "sg", "s", "i", "a"  # protocol: the token's signature fields
NETWORK = {"country": "country", "range": "range", "ja4": "ja4", "protocol": "proto"}  # protocol: sessions.net keys


def table(con, session_id, net_json, epoch, page_views):
    pages = [_page(epoch, *row) for row in con.execute(
        "SELECT page_ms, path, body, net_match, ua_match, lang_match, reuses FROM srv WHERE session_id=? "
        "ORDER BY page_ms, recv_ms", (session_id,))]
    said = words()["server_half"]
    missing = page_views - len(pages)
    note = said["none"] if not pages else said["some"].format(missing=missing, pages=page_views) if missing > 0 else None
    return {"pages": pages, "network": _network(net_json), "note": note}


def _page(epoch, page_ms, path, body, net_match, ua_match, lang_match, reuses):
    payload = json.loads(body) if body else {}
    fetch, signature = payload.get("sf") or {}, payload.get(SIGNATURE) or {}
    signed = signature.get(SIGNED) or signature.get(SIGNED_INPUT) or signature.get(SIGNATURE_AGENT)
    return {"at_ms": max(0, (page_ms or epoch) - epoch), "path": path or "/",
            "fetch": {name: _text(fetch.get(field)) for name, field in FETCH.items()},
            "signature": {"agent": _text(signature.get(SIGNATURE_AGENT)), "verified": False} if signed else None,
            "same_network": _same(net_match), "same_user_agent": _same(ua_match), "same_language": _same(lang_match),
            "reuses": reuses or 0}


def _network(net_json):
    net = json.loads(net_json) if net_json else None
    if not net:
        return None
    shown = {name: _text(net.get(key)) for name, key in NETWORK.items()}
    return dict(shown, attribution=places.attribution(config.load_cfg()) if shown["country"] else None)


def _same(match):
    return None if match is None else bool(match)


def _text(value):
    """A value as the page shows it: text, or null for none (the contract never holds an empty text)."""
    return str(value) if value not in (None, "") else None
