"""`doctor`, opening a page of the user's website: page_checks(c, url, framework).

doctor asks for the page at url (site_url, or doctor --url) the way a browser opens a page typed into its address bar
(data/doctor.json page_request: Accept and Sec-Fetch-*), with the three Web Bot Auth headers added, holding values that
say they are a test. Four lines: the page loads cake.js with this site key; its response's Server-Timing carries a cake
token that this AgentCake's secret signed, inside the time window tokens count in (edge_token.read_token); the token
holds the Sec-Fetch values doctor sent; and the signature headers doctor sent reached the site's server. Anything in
front of the site's server that removes headers (a proxy, a CDN) shows as the headers that did not arrive. A static
site has no server half, so no token there is a SKIP. A sandbox that forbids the connection is named.
Only this command, and only when told the address, opens the user's site.
"""
import errno
import http.client
import urllib.error
import urllib.request
from datetime import timedelta
from http import HTTPStatus

from agentcake import __version__, paths
from agentcake.datafiles import load
from agentcake.doctor_lines import SKIP
from agentcake.doctor_site import script_addresses
from agentcake.edge_secret import srv_secret
from agentcake.edge_token import read_token
from agentcake.storage_config import now_ms
from agentcake.wording import product, text

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
        status, server_timing, body = open_page(url, sent, c["http_timeout_s"])
    except UNOPENED as error:
        opened = (text("doctor_live_script"), False, text("doctor_live_problem", where=url, problem=why_not_opened(error)))
        return [opened] + [(name, SKIP, text("doctor_live_not_checked")) for name in [token_name, *in_token]]
    token_line, payload = token_check(c, cake_token(server_timing), framework)
    checks = [script_check(c, url, status, body), token_line]
    if payload is None:
        return checks + [(name, SKIP, text("doctor_live_not_checked")) for name in in_token]
    return checks + [sec_fetch_check(payload, sent), signature_check(payload, sent)]


def request_headers():
    """A page typed into a browser's address bar, plus the Web Bot Auth headers, and doctor's own User-Agent."""
    doctor = load("data/doctor.json")
    user_agent = doctor["user_agent"].format(command=product()["command"], version=__version__)
    return {**doctor["page_request"], load("data/edge.json")["headers"]["user_agent"]: user_agent}


def open_page(url, headers, timeout):
    """(status, the Server-Timing values joined, the page's text) of one GET; an HTTP error status is an answer too."""
    try:
        response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        server_timing = response.headers.get_all(load("data/edge.json")["headers"]["server_timing"]) or []
        return response.getcode(), ", ".join(server_timing), response.read().decode("utf-8", "replace")


def why_not_opened(error):
    reason = getattr(error, "reason", error)
    if isinstance(reason, OSError) and errno.errorcode.get(reason.errno) in load("data/doctor.json")["blocked_errors"]:
        return text("doctor_live_blocked")
    return text("doctor_live_open_failed", error=reason)


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
    if site_key and site_key in body and any(address in body for address in script_addresses(c)):
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


def has_server_half(framework):
    spec = next((f for f in load("data/frameworks.json")["frameworks"] if f["name"] == framework), None)
    return bool(spec and spec.get("middleware"))


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
