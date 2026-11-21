"""The page script over HTTP: gzipped for a client that accepts gzip, and with an ETag, so that a browser whose copy
is still current gets a 304 instead of the script again.

cake.js is the one large file that every page of the website loads. answer(request, script) answers a GET of it, on
both listeners (assets.cake_js):
  - gzipped, with Content-Encoding: gzip, when the request's Accept-Encoding allows gzip (RFC 9110 12.5.3: gzip or
    x-gzip listed, or else "*", with a weight above 0; every browser sends it); as it is otherwise, which any client
    can read;
  - with Vary: Accept-Encoding either way, so that a cache between the browser and AgentCake keeps the two apart;
  - with one weak ETag of the script's text on both: they carry the same script in different bytes, which is what a
    weak tag says (RFC 9110 8.8.1). A request whose If-None-Match names it gets 304 and no content (RFC 9110 13.1.2,
    the weak comparison). The cache time stays short (public_script_cache_s), so that a changed setting reaches
    the visitors' browsers soon; after it, a browser asks again, and the 304 spares it the whole script. That needs
    the HTTP/1.1 of a front such as Caddy or a load balancer: these listeners answer in HTTP/1.0 (http.server), and
    Chromium sends back no ETag it got in HTTP/1.0 (net/http/http_cache_transaction.cc).
The text changes only with a release or a setting (assets.served_script fills in the site key and the parts of pages
never to record), so the latest text's tag and gzip are made once and kept. The gzip is the standard library's at
its default level, 9, the smallest; its header carries no time, so the bytes depend on the text alone.

AgentCake compresses the script itself because that reaches every route: on the subdomain route Caddy compresses
nothing unless its Caddyfile says `encode` (deploy/Caddyfile does not), a load balancer in front of the path option
may not compress at all, and both pass an answer that is already compressed on as it is. PostHog 1.0.0 served its
page script, /static/array.js, the same way through WhiteNoise 5.0.1 (MIT): gzipped once at level 9 with no time when
the static files were collected, then answered with Vary: Accept-Encoding, an ETag and 304 (PostHog's
posthog/settings.py STATICFILES_STORAGE; WhiteNoise's compress.py and responders.py). The approach, not its code.
"""
import functools
import gzip
import hashlib
import re
from collections import namedtuple
from http import HTTPStatus

from agentcake.responses import JS, Response

ACCEPT_ENCODING, CONTENT_ENCODING, VARY = "Accept-Encoding", "Content-Encoding", "Vary"  # protocol: RFC 9110 headers
ETAG, IF_NONE_MATCH = "ETag", "If-None-Match"  # protocol: RFC 9110 8.8.3 and 13.1.2
GZIP = "gzip"  # protocol: a content coding of RFC 9110 8.4.1
GZIP_NAMES = (GZIP, "x-gzip")  # protocol: RFC 9110 8.4.1, where x-gzip names the same coding
ANY = "*"  # protocol: any coding not listed (Accept-Encoding), any current copy (If-None-Match)
QVALUE = re.compile(r"0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?")  # protocol: RFC 9110 12.4.2's qvalue
ENTITY_TAG = re.compile(r'(?:W/)?"[^"]*"')  # protocol: RFC 9110 8.8.3's entity-tag
WEAK = "W/"  # protocol: RFC 9110 8.8.3, the mark of a weak entity-tag

Coded = namedtuple("Coded", "etag gzipped")


def answer(request, script):
    """The Response to a GET of the page script, whose bytes are `script`, for this request's headers."""
    coded = coded_forms(script)
    headers = {VARY: ACCEPT_ENCODING, ETAG: coded.etag}
    if names_current(request.headers.get(IF_NONE_MATCH), coded.etag):
        return Response(HTTPStatus.NOT_MODIFIED, b"", JS, headers)
    if accepts_gzip(request.headers.get(ACCEPT_ENCODING)):
        return Response(HTTPStatus.OK, coded.gzipped, JS, {**headers, CONTENT_ENCODING: GZIP})
    return Response(HTTPStatus.OK, script, JS, headers)


@functools.lru_cache(maxsize=1)
def coded_forms(script):
    """The ETag and the gzipped bytes of one text of the script. Only the latest text is kept: there is one script."""
    return Coded(f'{WEAK}"{hashlib.sha256(script).hexdigest()}"', gzip.compress(script, mtime=0))


def accepts_gzip(value):
    """Whether an Accept-Encoding value allows gzip: no header, or one that names neither gzip nor "*", does not."""
    weights = {}
    for item in (value or "").split(","):
        coding, *parameters = [part.strip() for part in item.split(";")]
        if coding:
            weights[coding.lower()] = weight(parameters)
    listed = [weights[name] for name in GZIP_NAMES if name in weights]
    return (max(listed) if listed else weights.get(ANY, 0)) > 0


def weight(parameters):
    """An item's q (RFC 9110 12.4.2): 1 without one, 0 for one that cannot be read, so that a doubtful item never
    gets a coding the client may not read."""
    for parameter in parameters:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "q":
            return float(value.strip()) if QVALUE.fullmatch(value.strip()) else 0
    return 1


def names_current(value, etag):
    """Whether an If-None-Match value names this ETag, compared weakly (RFC 9110 13.1.2), or is "*"."""
    if value is None:
        return False
    if value.strip() == ANY:
        return True
    return any(tag.removeprefix(WEAK) == etag.removeprefix(WEAK) for tag in ENTITY_TAG.findall(value))
