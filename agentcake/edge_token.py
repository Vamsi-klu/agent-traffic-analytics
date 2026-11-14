"""The server half's token: made, read, and kept once (0.3.3's verify_token and take_token moved here in S1.1; format
S4.1; keeping S4.2).

A site's server (its middleware, edge/: Node, Python, PHP, the WordPress plugin) sends
`Server-Timing: cake;desc="c1.<payload>.<mac>"`: base64url JSON, then HMAC-SHA256 with the shared secret
(edge_secret.py). cake.js forwards it with its batches until collect has answered one of them.

mint() makes a page's token byte for byte as the middleware does for the same request: the format's reference, which the
shared vectors and the browser tests' test site use (cake answers no page of its own since D37 removed the demo shop).
read_token() reads a token by the rules the shared vectors pin (tests/vectors/edge_token.json): strict base64url, the
MAC in its one spelling, a JSON object with this version, an id and an integer time, then the age window. The format's
values and the header names are in data/edge.json, the same as the middleware's; the age window is two settings
(token_max_age_ms, token_max_future_ms in defaults.json, S1.2), and what is kept of a token is in data/sizes.json.
request_path() and skipped_path() read a request target the middleware's way; the log import reads its lines by them too
(log_formats.py, logs.py).

take_token() keeps a good token once, in the srv table, and links the batch that brought it (batches.token_id). A
browser that shows a page from its cache shows the token stored with it: after a 304 (Chromium shows the 304's own new
token; README "Caching and 304" says what each browser does) and when going back to a stored page. So the same token
can come from several page views of one visit: the first keeps it (ok), the same page view again is dup, another page
view of the visit is reuse (counted once per page view in srv.reuses, never a second server half, never a replay).
Another visit bringing it is replay. Collect compares the upload request it sees with the page request the site's
server saw: User-Agent, Accept-Language and network (the day's network key, server mode only). A difference is kept on
the srv row as a signal for the verdict's reasons (ua_match, lang_match, net_match), never a refusal.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from typing import Optional

from agentcake.config import DEFAULTS, load_cfg
from agentcake.datafiles import load, sizes
from agentcake.edge_secret import srv_secret
from agentcake.netfacts import network_key

TOKEN_PARTS = 3  # protocol: <prefix>.<payload>.<mac>
EDGE = load("data/edge.json")
HEADERS = EDGE["headers"]
SKIP_EXTENSIONS = tuple(EDGE["skip_extensions"])

BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
HEADER_NAME = re.compile(r"[a-z0-9-]+")
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]*", re.IGNORECASE)
VERSION = re.compile(r"[0-9A-Za-z.+-]+")
SAFE_INTEGER = 2 ** 53 - 1  # protocol: the integers a JSON number holds exactly in JavaScript, where tokens are made too
EDGE_WHITESPACE = " \t\r\n"  # protocol: what Fetch's Headers trims from a header value
ABSOLUTE_FORM = re.compile(r"[a-z][a-z0-9+.-]*://[^/?#]*", re.IGNORECASE)  # "https://shop.example" before a full URL's path
OWS = " \t"  # protocol: HTTP's optional whitespace (str.strip() would also take other Unicode spaces, unlike JavaScript)


# ---------------------------------------------------------------- the format
def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text):
    """The bytes of base64url text in its one spelling (no padding, spare bits zero), else None."""
    if not BASE64URL.fullmatch(text):
        return None
    try:
        data = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))  # protocol: base64 pads to a multiple of 4
    except ValueError:
        return None
    return data if b64url(data) == text else None


def _mac(secret, text):
    return hmac.new(secret, text.encode("utf-8"), hashlib.sha256).digest()


def sign_payload(secret, payload):
    """The token for a payload: compact JSON in the payload's own key order, UTF-8, base64url, then the MAC."""
    body = b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signed = f"{EDGE['token_prefix']}.{body}"
    return f"{signed}.{b64url(_mac(secret, signed))}"


def entry(token):
    """The Server-Timing entry that carries a token."""
    return f'{EDGE["entry_name"]};desc="{token}"'


def _is_integer(value):
    return type(value) is int and -SAFE_INTEGER <= value <= SAFE_INTEGER


def _payload(body):
    data = b64url_decode(body)
    if data is None:
        return None
    try:
        p = json.loads(data.decode("utf-8"))
    except ValueError:
        return None
    ok = (isinstance(p, dict) and _is_integer(p.get("v")) and p["v"] == EDGE["payload_version"]
          and isinstance(p.get("id"), str) and p["id"] != "" and _is_integer(p.get("t")))
    return p if ok else None


def verify_token(secret, token):
    """The payload of a token this secret signed, in the format the shared vectors pin, else None. No age check."""
    parts = str(token or "").split(".")
    if not secret or len(parts) != TOKEN_PARTS:
        return None
    prefix, body, mac = parts
    if prefix != EDGE["token_prefix"] or not (BASE64URL.fullmatch(body) and BASE64URL.fullmatch(mac)):
        return None
    if not hmac.compare_digest(b64url(_mac(secret, f"{prefix}.{body}")), mac):
        return None
    return _payload(body)


def read_token(secret, token, now_ms, c=None):
    """('ok' | 'stale' | 'bad', payload or None): the MAC and format, then the age window around now_ms. c: the
    settings (load_cfg()); without them the shipped defaults, the window the shared vectors pin."""
    c = c or DEFAULTS
    p = verify_token(secret, token)
    if p is None:
        return "bad", None
    if p["t"] > now_ms + c["token_max_future_ms"] or now_ms - p["t"] > c["token_max_age_ms"]:
        return "stale", p
    return "ok", p


# ---------------------------------------------------------------- the request and its facts (edge/node/lib/facts.js)
def request_path(target):
    """The request target's path as sent, without the query (as edge/node/lib/request.js reads it): no URL parsing,
    since a browser sends its paths resolved already and URL parsers resolve odd ones differently."""
    text = str(target or "")
    absolute = ABSOLUTE_FORM.match(text)
    if absolute:
        text = text[absolute.end():]
    return re.split(r"[?#]", text, maxsplit=1)[0] or "/"


def skipped_path(path):
    """A dot-file (a segment starting with ".") or a static file by its extension (data/edge.json skip_extensions):
    never a page, whatever the request asked for."""
    lower = path.lower()
    return any(segment.startswith(".") for segment in lower.split("/")) or lower.endswith(SKIP_EXTENSIONS)


def _request(method, target, header_lines):
    """(method, path, values by lower-case name, names in order). Repeated lines are joined with ", " and values
    trimmed, the way Fetch's Headers.get reads them."""
    values, names = {}, []
    for name, value in header_lines:
        name, value = str(name).lower(), str(value).strip(EDGE_WHITESPACE)
        values[name] = f"{values[name]}, {value}" if name in values else value
        names.append(name)
    return str(method or "GET").upper(), request_path(target), values, names


def _media_types(accept):
    return {media_range.split(";")[0].strip(OWS).lower() for media_range in (accept or "").split(",")}


def _cut(value, length):
    return None if value is None else CONTROL.sub("", str(value))[:length]


def is_page_request(method, path, values):
    """A GET of a top-level document (Sec-Fetch-Dest: document, or accepting text/html without fetch metadata), not a
    static file by its extension and not a dot-file."""
    if method != EDGE["page_method"]:
        return False
    dest = values.get(HEADERS["sec_fetch_dest"])
    if dest is not None:
        is_document = dest.lower() == EDGE["page_dest"]
    else:
        is_document = EDGE["page_type"] in _media_types(values.get(HEADERS["accept"]))
    return is_document and not skipped_path(path)


def request_facts(path, values, names):
    """The payload's fields that describe the request, in the format's order: p, sf, sp, md, al, ch, ua, hn, sg."""
    cut = EDGE["cut"]

    def header(role, length):
        return _cut(values.get(HEADERS[role]), length)
    kept_names = [n for n in names if len(n) <= cut["header_name"] and HEADER_NAME.fullmatch(n)]
    return {"p": _cut(path, cut["path"]),
            "sf": {"s": header("sec_fetch_site", cut["sec_fetch"]), "m": header("sec_fetch_mode", cut["sec_fetch"]),
                   "d": header("sec_fetch_dest", cut["sec_fetch"]), "u": header("sec_fetch_user", cut["sec_fetch_user"])},
            "sp": header("sec_purpose", cut["sec_purpose"]),
            "md": EDGE["markdown_type"] in _media_types(values.get(HEADERS["accept"])),
            "al": header("accept_language", cut["accept_language"]),
            "ch": {"ua": header("sec_ch_ua", cut["sec_ch_ua"]), "pf": header("sec_ch_ua_platform", cut["sec_ch_ua_platform"]),
                   "mb": header("sec_ch_ua_mobile", cut["sec_ch_ua_mobile"])},
            "ua": header("user_agent", cut["user_agent"]),
            "hn": kept_names[:EDGE["max_header_names"]],
            "sg": {"a": header("signature_agent", cut["signature_agent"]), "s": HEADERS["signature"] in values,
                   "i": HEADERS["signature_input"] in values}}


def _identifier(value):
    ok = isinstance(value, str) and len(value) <= EDGE["verdict_id_max"] and IDENTIFIER.fullmatch(value)
    return value if ok else None


def _verdict_fields(verdict):
    """botscent's verdict ({type, agent_name, reasons}) as {t, a, r}, short identifiers only; None when there is none."""
    if not isinstance(verdict, dict) or verdict.get("type") not in EDGE["verdict_types"]:
        return None
    reasons = verdict.get("reasons") if isinstance(verdict.get("reasons"), list) else []
    kept = [r for r in map(_identifier, reasons) if r][:EDGE["verdict_reasons_max"]]
    return {"t": verdict["type"], "a": _identifier(verdict.get("agent_name")), "r": kept}


def _version(version):
    ok = isinstance(version, str) and len(version) <= EDGE["version_max"] and VERSION.fullmatch(version)
    return version if ok else None


def mint(secret, method, target, header_lines, now_ms, ip=None, token_id=None, verdict=None, version=None):
    """The token for a request cake answers itself, or None (not a page, or no secret). header_lines are the request's
    (name, value) lines in the order they came, e.g. BaseHTTPRequestHandler's self.headers.items(); ip is the visitor's
    address, used for the network key only and never put in the token."""
    if not secret:
        return None
    method, path, values, names = _request(method, target, header_lines)
    if not is_page_request(method, path, values):
        return None
    payload = {"v": EDGE["payload_version"], "id": token_id or b64url(secrets.token_bytes(EDGE["token_id_bytes"])),
               "t": now_ms, **request_facts(path, values, names),
               "ik": network_key(secret, ip, now_ms) if ip else None,
               "bs": _verdict_fields(verdict), "bsv": _version(version)}
    return sign_payload(secret, payload)


# ---------------------------------------------------------------- keeping tokens
@dataclass(frozen=True)
class Delivery:
    """A token as collect received it: the visit, page view and batch that brought it, and what collect saw of that
    upload request, to compare with what the site's server saw of the page request."""
    session: str
    page_view: Optional[str] = None   # None for a cake 0.3.4 batch, which has no page views
    seq: Optional[int] = None         # the batch's number in its page view
    user_agent: Optional[str] = None  # the upload request's User-Agent header
    language: Optional[str] = None    # its Accept-Language header
    address: Optional[str] = None     # the visitor's address (server mode, from the load balancer); never written


def take_token(con, token, came, now_ms, c=None):
    """Verify a server-half token and keep it once (see the module docstring); came: its Delivery. Returns 'ok' (kept
    now), 'dup' (this page view brought it already), 'reuse' (another page view of this visit brought it first),
    'replay' (another visit brought it first), 'stale', 'bad' or 'off' (no secret). On ok, dup and reuse the batch's
    row is linked to the token. c: the settings (load_cfg())."""
    c = c or load_cfg()
    secret = srv_secret()
    if not secret:
        return "off"
    result, payload = read_token(secret, token, now_ms, c)
    if result != "ok":
        return result
    token_id = payload["id"][:sizes()["max_chars"]["token_id"]]
    kept = con.execute("SELECT session_id, pv FROM srv WHERE id=?", (token_id,)).fetchone()
    if kept is None:
        _keep(con, secret, token_id, payload, came, now_ms)
        state = "ok"
    elif kept[0] != came.session:
        return "replay"
    elif came.page_view is None or came.page_view == kept[1] or _linked(con, token_id, came):
        state = "dup"
    else:
        con.execute("UPDATE srv SET reuses = reuses + 1 WHERE id=?", (token_id,))
        state = "reuse"
    if came.page_view is not None:  # a cake 0.3.4 batch has no row of its own
        con.execute("UPDATE batches SET token_id=? WHERE session_id=? AND pv=? AND seq=?",
                    (token_id, came.session, came.page_view, came.seq))
    return state


def _keep(con, secret, token_id, payload, came, now_ms):
    """The srv row of a token kept now: its payload without the network key, and how the upload request compares."""
    cap, cut = sizes()["max_chars"], EDGE["cut"]
    network = payload.pop("ik", None)
    mine = network_key(secret, came.address, payload["t"]) if came.address else None
    con.execute("""INSERT INTO srv(id, session_id, recv_ms, page_ms, path, body, net_match, pv, ua_match, lang_match)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (token_id, came.session, now_ms, payload["t"], str(payload.get("p"))[:cap["token_path"]],
                 json.dumps(payload)[:cap["token_body"]], _same(network, mine), came.page_view,
                 _same(payload.get("ua"), _as_cut(came.user_agent, cut["user_agent"])),
                 _same(payload.get("al"), _as_cut(came.language, cut["accept_language"]))))


def _linked(con, token_id, came):
    """Whether a batch of this page view is linked to the token already (a page view that reused it, sending again)."""
    found = con.execute("SELECT 1 FROM batches WHERE session_id=? AND pv=? AND token_id=? LIMIT 1",
                        (came.session, came.page_view, token_id)).fetchone()
    return found is not None


def _as_cut(value, length):
    """A header value collect saw, trimmed, cleaned and cut the way the token's own copy was (request_facts)."""
    return None if value is None else _cut(str(value).strip(EDGE_WHITESPACE), length)


def _same(theirs, mine):
    """1 when both sides say the same, 0 when they differ, None when either does not say: nothing to compare."""
    return None if theirs is None or mine is None else int(theirs == mine)
