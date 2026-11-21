"""`doctor`, opening a page of the user's website: page_checks(c, url, framework).

doctor asks for the page at url (site_url, or doctor --url) the way a browser opens a page typed into its address bar
(data/doctor.json page_request: Accept and Sec-Fetch-*), with the three Web Bot Auth headers added, holding values that
say they are a test. Four lines: the page loads cake.js with this site key; its response's Server-Timing carries a cake
token that this AgentCake's secret signed, inside the time window tokens count in (edge_token.read_token); the token
holds the Sec-Fetch values doctor sent; and the signature headers doctor sent reached the site's server. Anything in
front of the site's server that removes headers (a proxy, a CDN) shows as the headers that did not arrive. A static
site has no server half, so no token there is a SKIP. A page cache (a WordPress cache plugin, a CDN's full-page cache)
sends a stored page without a token: when a site whose server has the middleware answers without one, doctor asks for
the same page once more with a query parameter of its own and a random value (data/doctor.json "page_cache"), an
address no cache has stored, and a good token there makes the line a WARN that says the page came from a cache
(Cache Enabler on WordPress) instead of a FAIL that sends the owner after a middleware that works. A sandbox that
forbids the connection is named. So is what is wrong with a certificate that Python's default check refuses (out of
date by this computer's clock, self-signed, not for the page's host name or IP address, from an authority Python does
not trust, against a rule of its strict check), which is never taken for a sandbox. Only this command, and only when
told the address, opens the user's site.
"""
import errno
import http.client
import secrets
import socket
import ssl
import urllib.error
import urllib.request
from datetime import timedelta
from http import HTTPStatus
from urllib.parse import urlsplit, urlunsplit

from agentcake import paths
from agentcake.datafiles import load, sizes
from agentcake.doctor_lines import SKIP, WARN
from agentcake.doctor_net import user_agent
from agentcake.doctor_site import script_addresses
from agentcake.edge_secret import srv_secret
from agentcake.edge_token import read_token
from agentcake.site_code import loads_from
from agentcake.storage_config import now_ms
from agentcake.wording import text

# The token's Sec-Fetch fields (edge_token.request_facts): the header's role in data/edge.json, its key in the
# token's "sf", and the role of its length limit in edge.json's "cut".
SEC_FETCH = (("sec_fetch_site", "s", "sec_fetch"), ("sec_fetch_mode", "m", "sec_fetch"),
             ("sec_fetch_dest", "d", "sec_fetch"), ("sec_fetch_user", "u", "sec_fetch_user"))
ONE_MINUTE = timedelta(minutes=1)
# Why a page does not open: no connection (OSError, urllib.error.URLError among them), an address that is no URL
# (ValueError, http.client.InvalidURL among them), or an answer that is not HTTP (http.client.HTTPException).
UNOPENED = (OSError, ValueError, http.client.HTTPException)


def page_checks(c, url, framework):
    token_name, *in_token = [text(name) for name in ("doctor_live_token", "doctor_live_sec_fetch", "doctor_live_signature")]
    sent = request_headers()
    try:
        status, server_timing, body, headers = open_page(url, sent, c["http_timeout_s"])
    except PageNotOpened as failure:
        problem = why_not_opened(failure.error, failure.address)
        opened = (text("doctor_live_script"), False, text("doctor_live_problem", where=url, problem=problem))
        return [opened] + [(name, SKIP, text("doctor_live_not_checked")) for name in [token_name, *in_token]]
    token = cake_token(server_timing)
    if token is None and has_server_half(framework):
        token_line, payload = past_the_cache(c, url, sent, headers, framework)
    else:
        token_line, payload = token_check(c, token, framework)
    checks = [script_check(c, url, status, body), token_line]
    if payload is None:
        return checks + [(name, SKIP, text("doctor_live_not_checked")) for name in in_token]
    return checks + [sec_fetch_check(payload, sent), signature_check(payload, sent)]


def request_headers():
    """A page typed into a browser's address bar, plus the Web Bot Auth headers, and doctor's own User-Agent."""
    return {**load("data/doctor.json")["page_request"], load("data/edge.json")["headers"]["user_agent"]: user_agent()}


class PageNotOpened(Exception):
    """A page that did not open: error says why (one of UNOPENED), address is where (the page's own address, or the
    one a redirect led to)."""

    def __init__(self, error, address):
        super().__init__(error, address)
        self.error, self.address = error, address


def open_page(url, headers, timeout):
    """(status, the Server-Timing values joined, the page's text, the response's headers) of one GET; an HTTP error
    status is an answer too. No answer raises PageNotOpened."""
    try:
        request = urllib.request.Request(url, headers=headers)
    except ValueError as error:  # an address that is no URL
        raise PageNotOpened(error, url) from error
    try:
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            server_timing = response.headers.get_all(load("data/edge.json")["headers"]["server_timing"]) or []
            body = response.read().decode("utf-8", "replace")
            return response.getcode(), ", ".join(server_timing), body, response.headers
    except UNOPENED as error:
        raise PageNotOpened(error, last_address(request)) from error


def last_address(request):
    """The address urllib asked for last for request: where the last redirect led, else the request's own. urllib
    notes each address a redirect leads to, in order, in the first request's redirect_dict (its loop check)."""
    return next(reversed(getattr(request, "redirect_dict", None) or {}), request.full_url)


def past_the_cache(c, url, sent, first_headers, framework):
    """The token line of a page that came without a token from a site whose server has the middleware: the page asked
    for once more at an address no page cache has stored. A good token there is a WARN (the first answer came from a
    cache, named by its header when it had one), with the token's payload for the lines after it; a token that is bad
    or stale there is that FAIL; no answer within http_timeout_s is a WARN that the server half was not checked; none
    at all, or another failure, is the first answer's line."""
    cache = load("data/doctor.json")["page_cache"]
    seen = cache_seen(first_headers, cache["headers"])
    try:
        _, server_timing, _, _ = open_page(with_parameter(url, cache["query"], secrets.token_hex(cache["value_bytes"])),
                                           sent, c["http_timeout_s"])
    except PageNotOpened as failure:
        if timed_out(failure.error):  # a page the site's server makes itself can take longer than one a cache sends
            return (text("doctor_live_token"), WARN, text("doctor_live_token_cache_timeout", seen=seen,
                                                          seconds=c["http_timeout_s"], launcher=paths.launcher())), None
        return token_check(c, None, framework)
    token = cake_token(server_timing)
    if token is None:
        return token_check(c, None, framework)
    (name, ok, info), payload = token_check(c, token, framework)
    if ok is not True:
        return (name, ok, info), payload
    option = cache["no_store"].get(middleware_of(framework).get("edge"), "")
    return (name, WARN, text("doctor_live_token_cached", seen=seen, option=option)), payload


def timed_out(error):
    """Whether a request ran out of time: while reading the answer (TimeoutError) or while connecting (urllib's
    URLError around one)."""
    return isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)


def with_parameter(url, name, value):
    """url with name=value added to its query (doctor's own parameter: no page cache has that address stored)."""
    parts = urlsplit(url)
    query = "&".join(part for part in (parts.query, f"{name}={value}") if part)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, parts.fragment))


def cache_seen(headers, names):
    """The first of names (headers page caches add) the answer has, as doctor_live_cache_seen writes it; else ""."""
    cap = sizes()["max_chars"]["header_value"]
    for name in names:
        value = headers.get(name)
        if value:
            return text("doctor_live_cache_seen", header=name, value=value[:cap])
    return ""


def why_not_opened(error, address):
    """Why a page did not open at address (the page's own, or where a redirect led). A certificate Python's default
    check refused is that certificate's problem (certificate_problem), named with the address's host. A connection the
    system refused with an errno of data/doctor.json's blocked_errors is a sandbox's doing; only the system's own
    errors count, as an ssl.SSLError carries the TLS library's code in errno (SSL_ERROR_SSL is 1: EPERM's number) and
    a socket.gaierror the resolver's. Anything else in its own words."""
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return certificate_problem(reason, urlsplit(address).hostname)
    from_system = isinstance(reason, OSError) and not isinstance(reason, (ssl.SSLError, socket.gaierror))
    if from_system and errno.errorcode.get(reason.errno) in load("data/doctor.json")["blocked_errors"]:
        return text("doctor_live_blocked")
    return text("doctor_live_open_failed", error=reason)


def certificate_problem(error, host):
    """What is wrong with a certificate Python's check refused, by the check's code (verify_code, OpenSSL's
    X509_V_ERR_*) in data/doctor.json certificate_errors, for the OpenSSL Python runs on (OpenSSL 3 numbers its strict
    checks' codes differently from 1.1.1); a code not listed there in the check's own words."""
    code, words = getattr(error, "verify_code", None), getattr(error, "verify_message", None) or str(error)
    for spec in load("data/doctor.json")["certificate_errors"]:
        if code in spec["codes"] and ssl.OPENSSL_VERSION_INFO[0] >= spec.get("openssl", 0):
            return text(spec["entry"], host=host, reason=words)
    return text("doctor_live_cert_other", host=host, reason=words)


def cake_token(server_timing):
    """The desc of the cake entry in a Server-Timing value (entries joined by commas, parameters by semicolons)."""
    for entry in server_timing.split(","):
        name, *parameters = [part.strip() for part in entry.split(";")]
        if name != load("data/edge.json")["entry_name"]:
            continue
        for parameter in parameters:
            key, _, value = parameter.partition("=")
            if key.strip().lower() == "desc":
                return value.strip().strip('"') or None
    return None


def script_check(c, url, status, body):
    opened = text("doctor_live_opened", url=url, status=status)
    if status != HTTPStatus.OK:
        return text("doctor_live_script"), False, text("doctor_live_problem", where=opened, problem=text("doctor_live_not_ok"))
    site_key = c.get("site_key")
    if site_key and site_key in body and any(loads_from(body, address) for address in script_addresses(c)):
        return text("doctor_live_script"), True, opened
    return text("doctor_live_script"), False, text("doctor_live_problem", where=opened, problem=text("doctor_live_script_none"))


def token_check(c, token, framework):
    """(the token's line, its payload when it is good, else None)."""
    name = text("doctor_live_token")
    if not token:
        if not has_server_half(framework):
            return (name, SKIP, text("doctor_live_token_optional")), None
        return (name, False, text("doctor_live_token_none", env=load("data/frameworks.json")["secret_env"])), None
    secret = srv_secret()
    if not secret:
        return (name, False, text("doctor_live_no_secret", launcher=paths.launcher())), None
    now = now_ms()
    result, payload = read_token(secret, token, now, c)
    if result == "bad":
        return (name, False, text("doctor_live_token_bad", launcher=paths.launcher())), None
    off = timedelta(milliseconds=abs(now - payload["t"]))
    if result == "stale":
        return (name, False, text("doctor_live_token_stale", minutes=round(off / ONE_MINUTE))), None
    return (name, True, text("doctor_live_token_ok", age=round(off.total_seconds()))), payload


def middleware_of(framework):
    """The framework's middleware entry in data/frameworks.json ({} for a framework without one, or unknown)."""
    spec = next((f for f in load("data/frameworks.json")["frameworks"] if f["name"] == framework), None)
    return (spec or {}).get("middleware") or {}


def has_server_half(framework):
    return bool(middleware_of(framework))


def sec_fetch_check(payload, sent):
    edge = load("data/edge.json")
    values = payload.get("sf") or {}
    roles = [(edge["headers"][role], key, edge["cut"][cut]) for role, key, cut in SEC_FETCH]
    lost = [display(header) for header, key, length in roles if values.get(key) != sent[header][:length]]
    if lost:
        return text("doctor_live_sec_fetch"), False, text("doctor_live_lost", headers=", ".join(lost))
    return text("doctor_live_sec_fetch"), True, text("doctor_live_arrived",
                                                    headers=", ".join(display(header) for header, _, _ in roles))


def signature_check(payload, sent):
    edge = load("data/edge.json")
    headers, signature = edge["headers"], payload.get("sg") or {}
    agent = sent[headers["signature_agent"]][:edge["cut"]["signature_agent"]]
    arrived = {headers["signature_agent"]: signature.get("a") == agent, headers["signature"]: signature.get("s") is True,
               headers["signature_input"]: signature.get("i") is True}
    lost = [display(header) for header, came in arrived.items() if not came]
    if lost:
        return text("doctor_live_signature"), False, text("doctor_live_lost", headers=", ".join(lost))
    return text("doctor_live_signature"), True, text("doctor_live_arrived", headers=", ".join(map(display, arrived)))


def display(header):
    """A header name the way people write it: sec-fetch-site -> Sec-Fetch-Site."""
    return "-".join(part.capitalize() for part in header.split("-"))
