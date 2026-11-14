"""AgentCake site middleware for Python, the server half, for WSGI and ASGI apps (step S4.3). On each page response it
sets one signed token, byte for byte what the Node middleware (edge/node) makes for the same request:

    Server-Timing: cake;desc="c1.<base64url JSON>.<base64url HMAC-SHA256>"

cake.js reads it from the page's navigation entry and hands it to AgentCake with the visit. CakeEdgeWSGI(app, **options)
mounts it on Flask, Django or any WSGI app, CakeEdgeASGI(app, **options) on FastAPI, Starlette or Django's ASGI app
(README.md); mint_token, network_key and ip_prefix are the format, for the shared vectors. One file and its settings
(cake_edge.json beside it), standard library only, since a site does not install AgentCake. It sets no cookie, stores
nothing, makes no network request, and passes every request through without a secret of at least 32 bytes. The rules are
the Node middleware's (edge/node/lib/), held to tests/vectors/edge_token.json and to cake's own mint()
(agentcake/edge_token.py) by tests/test_edge_python.py. Splitting Server-Timing into entries follows botscent
(src/server/timing.ts, commit 7f948003, MIT) as edge/node/lib/timing.js does. Part of AgentCake, MIT licence.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import time
import urllib.parse

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cake_edge.json")
with open(SETTINGS_FILE, encoding="utf-8") as _settings_file:
    SETTINGS = json.load(_settings_file)
FIXED, HEADERS, OPTIONS = SETTINGS["fixed"], SETTINGS["headers"], SETTINGS["options"]
LOG = logging.getLogger("cake_edge")

CONTROL = re.compile(r"[\x00-\x1f\x7f]")
HEADER_NAME = re.compile(r"[a-z0-9-]+")
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]*", re.IGNORECASE)
VERSION = re.compile(r"[0-9A-Za-z.+-]+")
ABSOLUTE_FORM = re.compile(r"^[a-z][a-z0-9+.-]*://[^/?#]*", re.IGNORECASE)  # "https://shop.example" before a full URL's path
EDGE_WHITESPACE = " \t\r\n"  # protocol: what Fetch's Headers trims from a header value (str.strip() would take more)
OWS = " \t"  # protocol: HTTP's optional whitespace
PATH_SAFE = "/!$&'()*+,;=:@"  # protocol: RFC 3986 pchar and "/": left as they are when a decoded path is encoded again
LATIN_1 = "latin-1"  # protocol: header bytes as text, as PEP 3333, ASGI servers and Node's HTTP parser read them
WSGI_HEADER = "HTTP_"  # protocol: PEP 3333 (CGI) request header keys
NS_PER_MS, MS_PER_S = 1_000_000, 1000  # protocol: units
IPV4, IPV6 = 4, 6  # protocol: IP versions
HEXTET_BYTES, BYTE_BITS = 2, 8  # protocol: an IPv6 group is two bytes


# ---------------------------------------------------------------- settings and the secret
def _is_whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


OPTION_KINDS = {  # what a value of the right kind is, for each option a site may change
    "secret_env": lambda value: isinstance(value, str) and value != "",
    "no_store": lambda value: isinstance(value, bool),
    "max_header_names": lambda value: _is_whole(value, 0),
    "cut": lambda value: isinstance(value, dict) and all(k in OPTIONS["cut"] and _is_whole(n, 1) for k, n in value.items()),
    "skip_extensions": lambda value: isinstance(value, (list, tuple)) and all(isinstance(e, str) for e in value),
}


def _message(key, **values):
    return SETTINGS["messages"][key].format(**values)


def settings_from(options):
    """The values one mounting uses: the "options" of cake_edge.json with the site's choices on top. An option nobody
    knows, or a value of the wrong kind, is named in one warning and changes nothing: a mistake in the site's setup must
    cost the site its token, never its pages. None means "not given"."""
    chosen = {**OPTIONS, "cut": dict(OPTIONS["cut"])}
    unknown, invalid = [], []
    for name, value in options.items():
        if value is None:
            continue
        if name not in OPTION_KINDS:
            unknown.append(name)
        elif not OPTION_KINDS[name](value):
            invalid.append(name)
        elif name == "cut":
            chosen["cut"].update(value)
        else:
            chosen[name] = value
    chosen["skip_extensions"] = tuple(extension.lower() for extension in chosen["skip_extensions"])
    for key, names in (("unknown_options", unknown), ("invalid_options", invalid)):
        if names:
            LOG.warning(_message(key, names=", ".join(names)))
    return chosen


def _as_bytes(secret):
    return secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)


def secret_bytes(secret):
    """The secret's bytes (text is UTF-8), or None when there is none or it is shorter than min_secret_bytes."""
    key = _as_bytes(secret) if isinstance(secret, (str, bytes, bytearray)) else b""
    return key if len(key) >= FIXED["min_secret_bytes"] else None


# ---------------------------------------------------------------- which requests, and what the token says about them
def _path_of(target):
    """The request target's path as sent, without the query: no URL parsing, since a browser sends its paths resolved
    already and URL parsers resolve odd ones differently (edge/node/lib/request.js)."""
    return re.split(r"[?#]", ABSOLUTE_FORM.sub("", str(target or ""), count=1), maxsplit=1)[0] or "/"


def _request(method, target, header_lines):
    """(method, path, values by lower-case name, names in order). Repeated lines are joined with ", " and values trimmed,
    the way Fetch's Headers.get reads them, so one request makes one token on every runtime."""
    values, names = {}, []
    for name, value in header_lines:
        name, value = str(name).lower(), str(value).strip(EDGE_WHITESPACE)
        values[name] = f"{values[name]}, {value}" if name in values else value
        names.append(name)
    return str(method or "GET").upper(), _path_of(target), values, names


def _media_types(accept):
    return {media_range.split(";")[0].strip(OWS).lower() for media_range in (accept or "").split(",")}


def _is_page(request, settings):
    """A GET of a top-level document: Sec-Fetch-Dest document, or, from a client that sends no fetch metadata, a GET that
    accepts text/html. Never a static file (by extension) or a dot-file. A prefetch or prerender of a page counts: the
    browser shows that very response if the visitor goes to the page, and its Sec-Purpose says so."""
    method, path, values, _ = request
    if method != FIXED["page_method"]:
        return False
    dest = values.get(HEADERS["sec_fetch_dest"])
    if dest is not None:
        is_document = dest.lower() == FIXED["page_dest"]
    else:
        is_document = FIXED["page_type"] in _media_types(values.get(HEADERS["accept"]))
    lower = path.lower()
    skipped = any(segment.startswith(".") for segment in lower.split("/")) or lower.endswith(settings["skip_extensions"])
    return is_document and not skipped


def _cut(value, length):
    return None if value is None else CONTROL.sub("", value)[:length]


def _facts(path, values, names, settings):
    """The payload's fields that describe the request, in the format's order: p, sf, sp, md, al, ch, ua, hn, sg. Headers
    the browser sends anyway, the header names (never their values), whether a Web Bot Auth signature came along."""
    cut = settings["cut"]

    def header(role, length):
        return _cut(values.get(HEADERS[role]), cut[length])
    kept_names = [name for name in names if len(name) <= cut["header_name"] and HEADER_NAME.fullmatch(name)]
    return {"p": _cut(path, cut["path"]),
            "sf": {"s": header("sec_fetch_site", "sec_fetch"), "m": header("sec_fetch_mode", "sec_fetch"),
                   "d": header("sec_fetch_dest", "sec_fetch"), "u": header("sec_fetch_user", "sec_fetch_user")},
            "sp": header("sec_purpose", "sec_purpose"),
            "md": FIXED["markdown_type"] in _media_types(values.get(HEADERS["accept"])),
            "al": header("accept_language", "accept_language"),
            "ch": {"ua": header("sec_ch_ua", "sec_ch_ua"), "pf": header("sec_ch_ua_platform", "sec_ch_ua_platform"),
                   "mb": header("sec_ch_ua_mobile", "sec_ch_ua_mobile")},
            "ua": header("user_agent", "user_agent"),
            "hn": kept_names[:settings["max_header_names"]],
            "sg": {"a": header("signature_agent", "signature_agent"), "s": HEADERS["signature"] in values,
                   "i": HEADERS["signature_input"] in values}}


def _short(value, longest, pattern):
    return value if isinstance(value, str) and len(value) <= longest and pattern.fullmatch(value) else None


def _verdict_fields(verdict):
    """botscent's verdict ({type, agent_name, reasons}) as {t, a, r}, short identifiers only; None when there is none."""
    if not isinstance(verdict, dict) or verdict.get("type") not in FIXED["verdict_types"]:
        return None
    reasons = verdict.get("reasons") if isinstance(verdict.get("reasons"), list) else []
    kept = [reason for reason in reasons if _short(reason, FIXED["verdict_id_max"], IDENTIFIER)]
    return {"t": verdict["type"], "a": _short(verdict.get("agent_name"), FIXED["verdict_id_max"], IDENTIFIER),
            "r": kept[:FIXED["verdict_reasons_max"]]}


# ---------------------------------------------------------------- the network key and the token
def ip_prefix(ip):
    """"203.0.113.0/24" or "2001:db8:0::/48": the /24 of an IPv4 address, the /48 of an IPv6 one (an IPv4-mapped IPv6
    address counts as its IPv4), by the rules of Python's ipaddress, which the Node middleware follows too; else None."""
    try:
        address = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    if address.version == IPV6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.version == IPV4:
        bits = FIXED["ipv4_prefix_bits"]
        return f"{ipaddress.ip_network(f'{address}/{bits}', strict=False).network_address}/{bits}"
    bits, packed = FIXED["ipv6_prefix_bits"], address.packed  # packed, since .exploded fails for "fe80::1%eth0"
    groups = [int.from_bytes(packed[i:i + HEXTET_BYTES], "big") for i in range(0, bits // BYTE_BITS, HEXTET_BYTES)]
    return ":".join(format(group, "x") for group in groups) + f"::/{bits}"


def network_key(secret, ip, now_ms):
    """The first 16 hex characters of HMAC-SHA256(secret, "ip|<UTC day>|<prefix>"), or None for no address. cake computes
    the same from cake.js's own request and keeps only whether the two match: no side keeps the address."""
    prefix = ip_prefix(ip) if ip else None
    if prefix is None:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime(now_ms / MS_PER_S))
    text = f"{FIXED['network_key_label']}|{day}|{prefix}"
    return hmac.new(_as_bytes(secret), text.encode("utf-8"), hashlib.sha256).hexdigest()[:FIXED["network_key_hex_chars"]]


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(key, payload):
    """c1.<base64url of compact JSON, keys in the payload's order, UTF-8>.<base64url HMAC-SHA256 of what comes before>."""
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signed = f"{FIXED['token_prefix']}.{body}"
    return f"{signed}.{_b64url(hmac.new(key, signed.encode('ascii'), hashlib.sha256).digest())}"


def _mint(key, request, now_ms, token_id, ip, verdict, version, settings):
    _, path, values, names = request
    return _sign(key, {"v": FIXED["payload_version"], "id": token_id, "t": now_ms, **_facts(path, values, names, settings),
                       "ik": network_key(key, ip, now_ms), "bs": _verdict_fields(verdict),
                       "bsv": _short(version, FIXED["version_max"], VERSION)})


def mint_token(secret, method, target, header_lines, now_ms, token_id, ip=None, verdict=None, version=None, **options):
    """The token for a request with everything that varies given, or None (not a page, or no usable secret): what the
    shared vectors are checked with. header_lines: (name, value) in the order sent. verdict and version: botscent's,
    which only the vectors carry here, since botscent is a JavaScript library."""
    key = secret_bytes(secret)
    if key is None:
        return None
    settings, request = settings_from(options), _request(method, target, header_lines)
    return _mint(key, request, now_ms, token_id, ip, verdict, version, settings) if _is_page(request, settings) else None


# ---------------------------------------------------------------- the response head
def _entries(value):
    """A Server-Timing value split into its entries at the commas outside quoted strings."""
    entries, start, quoted, i = [], 0, False, 0
    while i < len(value):
        if quoted and value[i] == "\\":
            i += 1
        elif value[i] == '"':
            quoted = not quoted
        elif value[i] == "," and not quoted:
            entries.append(value[start:i])
            start = i + 1
        i += 1
    entries.append(value[start:])
    return [entry.strip() for entry in entries if entry.strip()]


def with_cake_entry(values, token):
    """One Server-Timing value from the header's values so far: the site's own entries, any cake entry (from a proxy, a
    second copy of the middleware or a stored response) dropped, and this request's entry last: exactly one per response."""
    name = FIXED["entry_name"]
    kept = [entry for value in values for entry in _entries(value) if entry.split(";", 1)[0].strip().lower() != name]
    return ", ".join(kept + [f'{name};desc="{token}"'])


def head_with_entry(headers, token, no_store=False):
    """A response's header lines as text pairs, with one Server-Timing that carries cake's entry and, under no_store, an
    HTML response made private and unstored. The other lines keep their order; the changed ones go last."""
    timing, cache, kind = HEADERS["server_timing"], HEADERS["cache_control"], HEADERS["content_type"]
    named = [(name.lower(), name, value) for name, value in headers]
    content_type = next((value for low, _, value in named if low == kind), "")
    no_store = no_store and content_type.split(";")[0].strip().lower() in FIXED["html_types"]
    dropped = {timing, cache} if no_store else {timing}
    out = [(name, value) for low, name, value in named if low not in dropped]
    out.append((timing, with_cake_entry([value for low, _, value in named if low == timing], token)))
    return out + [(cache, FIXED["no_store_value"])] if no_store else out


# ---------------------------------------------------------------- the mountings
class CakeEdge:
    """What both mountings share: settings, secret, the token for a request. Wiring: secret (default: the variable named by
    secret_env), client_ip(subject) (the visitor's address from the WSGI environ or ASGI scope, as the site knows it; without
    it no network key), now / random_id for tests. Options: no_store, max_header_names, cut, skip_extensions, secret_env."""

    def __init__(self, secret=None, client_ip=None, now=None, random_id=None, **options):
        self.settings = settings_from(options)
        given = os.environ.get(self.settings["secret_env"]) if secret is None else secret
        self.key = secret_bytes(given)
        if given and self.key is None:
            LOG.warning(_message("short_secret", min=FIXED["min_secret_bytes"]))
        self.enabled = self.key is not None
        self.client_ip = client_ip
        self.now = now or (lambda: time.time_ns() // NS_PER_MS)
        self.random_id = random_id or (lambda: _b64url(secrets.token_bytes(FIXED["token_id_bytes"])))
        self._said = set()

    def warn_once(self, key, error):
        """Name a failure once, by its kind only: a misconfigured site would otherwise log it on every page."""
        line = _message(key, error=type(error).__name__)
        if line not in self._said:
            self._said.add(line)
            LOG.warning(line)

    def address(self, subject):
        """The visitor's address from the site's client_ip(subject), or None (no client_ip, no text, or it failed)."""
        if self.client_ip is None:
            return None
        try:
            ip = self.client_ip(subject)
        except Exception as error:  # the site's own code: whatever it raises costs the network key, never the page
            self.warn_once("client_ip_failed", error)
            return None
        return ip if isinstance(ip, str) else None

    def token(self, method, target, header_lines, subject):
        """The token for a page request, or None (not a page, no secret, or a request that cannot be read)."""
        if not self.enabled:
            return None
        try:
            request = _request(method, target, header_lines)
            if not _is_page(request, self.settings):
                return None
            return _mint(self.key, request, self.now(), self.random_id(), self.address(subject), None, None, self.settings)
        except Exception as error:  # the server half must never break a page: a token that cannot be made is not sent
            self.warn_once("token_failed", error)
            return None

    def head(self, headers, token, binary=False):
        """The response's header lines with cake's entry (ASGI's are bytes: binary); as given if they cannot be read."""
        try:
            pairs = [(name.decode(LATIN_1), value.decode(LATIN_1)) if binary else (name, value) for name, value in headers]
            out = head_with_entry(pairs, token, self.settings["no_store"])
            return [(name.encode(LATIN_1), value.encode(LATIN_1)) for name, value in out] if binary else out
        except Exception as error:  # the server half must never break a page: the head goes out as the app wrote it
            self.warn_once("head_failed", error)
            return headers


def _wsgi_target(environ):
    """The request target as sent: REQUEST_URI or RAW_URI where the server keeps it (Gunicorn, uWSGI, Werkzeug, mod_wsgi),
    else SCRIPT_NAME + PATH_INFO percent-encoded again (wsgiref hands them over decoded, as PEP 3333 text)."""
    raw = environ.get("REQUEST_URI") or environ.get("RAW_URI")
    path = environ.get("SCRIPT_NAME", "") + environ.get("PATH_INFO", "")
    return raw or urllib.parse.quote(path.encode(LATIN_1), safe=PATH_SAFE)


def _wsgi_lines(environ):
    """The header lines from the HTTP_ keys in the order the server put them in (the order sent, for wsgiref, Gunicorn,
    uWSGI and Werkzeug), names lower-cased with "-" for "_"; the server has joined any repeated line its own way."""
    return [(key[len(WSGI_HEADER):].replace("_", "-").lower(), value) for key, value in environ.items()
            if key.startswith(WSGI_HEADER)]


class _Mounting:
    def __init__(self, app, secret=None, client_ip=None, now=None, random_id=None, **options):
        self.app, self.edge = app, CakeEdge(secret, client_ip, now, random_id, **options)
        self.enabled = self.edge.enabled


class CakeEdgeWSGI(_Mounting):
    """WSGI middleware. Flask: app.wsgi_app = CakeEdgeWSGI(app.wsgi_app); Django: around get_wsgi_application(). The entry
    goes into the headers the app hands to start_response, before any of the body is written, so the app's own
    Server-Timing stays and a streamed body is never held back."""

    def __call__(self, environ, start_response):
        token = self.edge.token(environ.get("REQUEST_METHOD"), _wsgi_target(environ), _wsgi_lines(environ), environ)
        if token is None:
            return self.app(environ, start_response)

        def start_response_with_entry(status, headers, exc_info=None):
            return start_response(status, self.edge.head(headers, token), exc_info)
        return self.app(environ, start_response_with_entry)


def _asgi_target(scope):
    """The path as sent: raw_path where the server gives it (Uvicorn, Hypercorn, Daphne), else path encoded again."""
    raw = scope.get("raw_path")
    return raw.decode(LATIN_1) if raw else urllib.parse.quote(scope.get("path", "").encode("utf-8"), safe=PATH_SAFE)


def _asgi_lines(scope):
    return [(bytes(name).decode(LATIN_1), bytes(value).decode(LATIN_1)) for name, value in scope.get("headers", ())]


class CakeEdgeASGI(_Mounting):
    """ASGI middleware. FastAPI and Starlette: app.add_middleware(CakeEdgeASGI); Django: around get_asgi_application().
    The entry goes into the http.response.start message, which a server sends before the first chunk of the body, so a
    streaming response carries it and nothing is held back. Other scopes (lifespan, websocket) pass through untouched."""

    async def __call__(self, scope, receive, send):
        token = None
        if scope.get("type") == "http":
            token = self.edge.token(scope.get("method"), _asgi_target(scope), _asgi_lines(scope), scope)
        if token is None:
            return await self.app(scope, receive, send)

        async def send_with_entry(message):
            if message.get("type") == "http.response.start":
                message = {**message, "headers": self.edge.head(message.get("headers", []), token, binary=True)}
            await send(message)
        return await self.app(scope, receive, send_with_entry)
