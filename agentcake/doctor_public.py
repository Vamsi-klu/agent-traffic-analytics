"""`doctor` on a server: AgentCake the way visitors' browsers reach it, and what sits in front of it.

public_checks(c, health, net) -> [(name, verdict, info)] in server mode; doctor.py prints them under public_header(c).
health is /api/health's answer (None when AgentCake did not answer on 127.0.0.1), net a doctor_net.Network.

The subdomain route (public_url set), seven lines in the order a visit takes:
  1 DNS record         public_url's host resolves; to an address in the bundled lists' CDN ranges (a proxy such as
                       Cloudflare's orange cloud) it is a WARN: it works when Caddy reads the visitor's address from
                       the proxy (deploy/Caddyfile does for Cloudflare), and DNS only is still the better choice;
  2 HTTPS certificate  cake.js from public_url opens under Python's default certificate check (chain and name);
  3 this AgentCake     that cake.js holds this installation's site key, else the address leads to another server;
  4 CORS               OPTIONS of collect with the website's Origin answers 204 and allows that Origin, and so does
                       the upload's answer: else browsers cannot read the answers and send every batch again;
  5 self-check upload  one upload sent with the website's Origin arrives with Accept-Language, User-Agent and Host as
                       sent, the made-up X-Cake-JA4 sent with it is not read as the visitor's, and its answer is not
                       one cake.js would send the upload again on; a changed header is named, with the platform in
                       front (doctor_platforms.py) and what to change there; an upload answered by what is in front
                       (it never arrived) says what to change too: the path rule, or the platform's own setting for that
                       status (CloudFront's 403: the behavior's Allowed HTTP methods);
  6 visitor address    the address AgentCake saw for that upload is not a CDN's (only its network class is kept);
  7 recent visitors    the protection net's state in /api/health, "address_check" (AgentCake's own check that most
                       recent sessions do not come from a CDN's address): failed there, failed here.
An 8th check, the website's pages loading cake.js from public_url, is in the website lines (doctor_site.py's
script_addresses() includes public_url). The same-site path (public_url empty) has lines 5 to 7, the upload going
through https://<site_domain><path_prefix>/collect. A line that needs an earlier one that failed is a SKIP saying
which (no DNS record, no connection, AgentCake not answering on 127.0.0.1, another server at the address).
The self-check never counts as a visit: it goes to collect on 127.0.0.1 first, where a visit may mark itself a test,
and its session keeps that mark (collect_store keeps is_test from a session's first upload); on the public listener
no visit can. What arrived is read from cake.db's requests table, read-only.
"""
import http.client
import json
import os
import sqlite3
import ssl
import urllib.request
from collections import namedtuple
from http import HTTPStatus
from urllib.parse import urlsplit

from agentcake import doctor_platforms, netfacts, paths
from agentcake.address_check import CDN
from agentcake.config import base_url
from agentcake.datafiles import load, sizes
from agentcake.doctor_lines import SKIP, WARN
from agentcake.doctor_net import DEFAULT_PORTS, HTTPS, Network, exchange, header, user_agent, valid_until
from agentcake.ping import selfcheck_upload
from agentcake.site_setup import COLLECT_PATH, SCRIPT_PATH, cake_root
from agentcake.wording import text

SITE_ORIGIN = HTTPS + "://{domain}"  # the website, as its pages' Origin
ALLOW_ORIGIN = "Access-Control-Allow-Origin"  # protocol: CORS (the Fetch standard)
PREFLIGHT = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}  # protocol: CORS
ANY_ORIGIN = "*"  # protocol: CORS's wildcard
# What a reverse proxy answers when the server behind it does not (RFC 9110 15.6): Caddy's 502 for one.
UPSTREAM_DOWN = (HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT)
COMPARED = ("Accept-Language", "User-Agent", "Host")  # what platforms remove or replace, and the judging reads
ADDRESS_CHECK = "address_check"  # /api/health's field of the protection net: {"sessions", "cdn", "misconfigured"}
# A line with several problems (or header changes) says each in a sentence of its own: each ends with its full stop.
BETWEEN_SENTENCES = " "
# The lines after each one that the next ones need: the self-check's two, CORS's, this AgentCake's, the certificate's.
UPLOAD_LINES = ("doctor_public_upload", "doctor_public_address")
AFTER_THIS = ("doctor_public_cors",) + UPLOAD_LINES
AFTER_CERTIFICATE = ("doctor_public_this",) + AFTER_THIS
AFTER_DNS = ("doctor_public_cert",) + AFTER_CERTIFICATE
Upload = namedtuple("Upload", "url sent exchange arrival")  # sent: lower-case names; arrival: collect's facts, or None


def public_header(c):
    if c.get("public_url"):
        return text("doctor_public_header", url=c["public_url"])
    site = SITE_ORIGIN.format(domain=c["site_domain"]) if c.get("site_domain") else ""
    return text("doctor_public_header_path", url=site + (c.get("path_prefix") or "") + "/")


def public_checks(c, health, net=None):
    net = net or Network()
    lines = subdomain_checks(c, health, net) if c.get("public_url") else path_checks(c, health, net)
    return lines + [visitors_check(c, health)]


def fix_values(c, url):
    """What the sentences that say what to change are filled with: the host of url, and path_prefix."""
    return {"host": urlsplit(url).hostname, "prefix": c.get("path_prefix") or ""}


def subdomain_checks(c, health, net):
    """Lines 1 to 6 of the subdomain route, each after the ones it needs."""
    root, timeout = cake_root(c), load("data/doctor.json")["public_timeout_s"]
    parts, values = urlsplit(root), fix_values(c, root)
    dns_line, addresses = dns_check(net, parts.hostname, parts.port or DEFAULT_PORTS[parts.scheme], values)
    if not addresses:
        return [dns_line] + skipped(AFTER_DNS, text("doctor_public_why_dns"))
    script = exchange(net, root + SCRIPT_PATH, "GET", {"User-Agent": user_agent()}, timeout=timeout)
    lines = [dns_line, certificate_check(root, script, values)]
    if script.answer is None:
        return lines + skipped(AFTER_CERTIFICATE, text("doctor_public_why_https"))
    if not health:  # the public listener is the same process: what answers there now is Caddy's 502, not another server
        return lines + skipped(AFTER_CERTIFICATE, text("doctor_public_why_down"))
    this = this_check(c, root + SCRIPT_PATH, script.answer, values)
    lines.append(this)
    if this[1] is not True:
        return lines + skipped(AFTER_THIS, text("doctor_public_why_other", url=root))
    if not c.get("site_domain"):
        return lines + [(text(key), SKIP, no_site_domain()) for key in AFTER_THIS]
    origin = SITE_ORIGIN.format(domain=c["site_domain"])
    preflight = exchange(net, root + COLLECT_PATH, "OPTIONS", dict(PREFLIGHT, Origin=origin), timeout=timeout)
    upload = send_self_check(c, health, net, root + COLLECT_PATH, origin)
    return lines + [cors_check(origin, preflight, upload)] + upload_lines(c, upload, path=False)


def path_checks(c, health, net):
    """Lines 5 and 6 of the same-site path."""
    if not c.get("site_domain"):
        return [(text(key), SKIP, no_site_domain()) for key in UPLOAD_LINES]
    origin = SITE_ORIGIN.format(domain=c["site_domain"])
    upload = send_self_check(c, health, net, origin + (c.get("path_prefix") or "") + COLLECT_PATH, origin)
    return upload_lines(c, upload, path=True)


def skipped(keys, why):
    return [(text(key), SKIP, text("doctor_public_not_checked", why=why)) for key in keys]


def no_site_domain():
    return text("doctor_public_no_site_domain", launcher=paths.launcher())


def said(error):
    """An error's own words: its strerror, else what it says."""
    return getattr(error, "strerror", None) or str(error)


# 1 to 4 ---------------------------------------------------------------------------------------------------------------

def dns_check(net, host, port, values):
    """(the line, the addresses host resolves to: [] when none)."""
    name = text("doctor_public_dns")
    try:
        addresses = net.resolve(host, port)
    except OSError as error:  # socket.gaierror: no record
        return (name, False, text("doctor_public_dns_none", host=host, error=said(error))), []
    for address in addresses:
        cdn = (netfacts.look_up(address) or {}).get(CDN)
        if cdn:
            fix = doctor_platforms.dns_fix(doctor_platforms.by_range(cdn), **values)
            return (name, WARN, text("doctor_public_dns_cdn", host=host, address=address, cdn=cdn, fix=fix)), addresses
    return (name, True, text("doctor_public_dns_info", host=host, addresses=", ".join(addresses))), addresses


def certificate_check(root, script, values):
    name, host = text("doctor_public_cert"), values["host"]
    hint, error = text("doctor_public_cert_hint", host=host), script.error
    if isinstance(error, ssl.SSLCertVerificationError):  # before SSLError, of which it is one
        return name, False, text("doctor_public_cert_bad", reason=error.verify_message or error.reason, hint=hint)
    if isinstance(error, ssl.SSLError):  # no certificate for the name at all, for one
        return name, False, text("doctor_public_cert_bad", reason=error.reason or said(error), hint=hint)
    if error is not None:
        return name, False, text("doctor_public_cert_no_connection", host=host, error=said(error), hint=hint)
    if urlsplit(root).scheme != HTTPS:
        return name, WARN, text("doctor_public_cert_http", url=root, host=host)
    return name, True, text("doctor_public_cert_info", host=host, until=valid_until(script.certificate))


def this_check(c, url, answer, values):
    name, site_key = text("doctor_public_this"), c.get("site_key")
    if answer.status == HTTPStatus.OK and site_key and site_key in answer.body.decode("utf-8", "replace"):
        return name, True, text("doctor_public_this_info", url=url)
    if answer.status in UPSTREAM_DOWN:
        return name, False, text("doctor_public_this_upstream", url=url, status=answer.status,
                                 listen=c.get("public_listen"), **values)
    return name, False, text("doctor_public_this_other", url=url, status=answer.status, **values)


def cors_check(origin, preflight, upload):
    """Both answers allow origin: the preflight's (with 204) and, when it was sent, the upload's."""
    name, allowed, none = text("doctor_public_cors"), (origin, ANY_ORIGIN), text("doctor_public_cors_none")
    options, problems = preflight.answer, []
    if options is None or options.status != HTTPStatus.NO_CONTENT or header(options, ALLOW_ORIGIN) not in allowed:
        problems.append(text("doctor_public_cors_options", status=options.status if options else none,
                             allow=header(options, ALLOW_ORIGIN) or none))
    answered = upload.exchange.answer if upload else None
    if answered is not None and header(answered, ALLOW_ORIGIN) not in allowed:
        problems.append(text("doctor_public_cors_upload", allow=header(answered, ALLOW_ORIGIN) or none))
    if problems:
        return name, False, text("doctor_public_cors_bad", problems=BETWEEN_SENTENCES.join(problems), origin=origin)
    return name, True, text("doctor_public_cors_info", origin=origin)


# 5 and 6: the self-check upload -----------------------------------------------------------------------------------

def send_self_check(c, health, net, url, origin):
    """The Upload of one self-check through url; None when AgentCake did not answer on 127.0.0.1 or did not take it
    there, where it is registered first (the module docstring)."""
    if not health:
        return None
    session_id, body = selfcheck_upload(c, origin)
    if not register(c, body):
        return None
    doctor = load("data/doctor.json")
    sent = dict(doctor["upload_request"], origin=origin, **{"user-agent": user_agent(),
                                                            made_up_header().lower(): made_up_value()})
    answer = exchange(net, url, "POST", sent, body, doctor["public_timeout_s"])
    arrived = arrivals(session_id)[1:]  # the first is the registration
    return Upload(url, dict(sent, host=urlsplit(url).netloc), answer, arrived[-1] if arrived else None)


def register(c, body):
    request = urllib.request.Request(base_url(c) + COLLECT_PATH, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=c["http_timeout_s"]) as answer:
            return answer.status == HTTPStatus.NO_CONTENT
    except (OSError, ValueError, http.client.HTTPException):  # urllib.error.HTTPError is an OSError
        return False


def arrivals(session_id):
    """The facts collect kept of each upload request of the session, oldest first (cake.db, read-only)."""
    database = paths.db_file()
    if not os.path.exists(database):
        return []
    con = sqlite3.connect("file:" + urllib.request.pathname2url(database) + "?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT facts FROM requests WHERE session_id=? ORDER BY rowid", (session_id,)).fetchall()
    finally:
        con.close()
    return [json.loads(facts) for (facts,) in rows]


def made_up_header():
    return netfacts.lb_headers()["ja4"]


def made_up_value():
    return load("data/doctor.json")["made_up_ja4"]


def upload_lines(c, upload, path):
    """The self-check's line and the visitor address's line."""
    name = text("doctor_public_upload")
    if upload is None:
        return skipped(UPLOAD_LINES, text("doctor_public_why_local"))
    values = fix_values(c, upload.url)
    answer, not_arrived = upload.exchange.answer, skipped(("doctor_public_address",), text("doctor_public_why_upload"))
    if answer is None:
        return [(name, False, text("doctor_public_upload_failed", url=upload.url,
                                   error=said(upload.exchange.error)))] + not_arrived
    found = doctor_platforms.identify(answer.headers, (upload.arrival or {}).get("names", ()))
    through = text("doctor_public_through", platforms=doctor_platforms.names(found)) if found else ""
    if upload.arrival is None and answer.status == HTTPStatus.NO_CONTENT:
        return [(name, False, text("doctor_public_upload_lost", url=upload.url, status=answer.status, through=through,
                                   **values))] + not_arrived
    if upload.arrival is None:  # something in front answered for AgentCake: its path rule, or a platform's own refusal
        fix = doctor_platforms.status_fix(found, answer.status, **values)
        return [(name, False, text("doctor_public_upload_status", url=upload.url, status=answer.status,
                                   through=through, fix=fix))] + not_arrived
    return [arrival_check(c, upload, found, through, path, values),
            address_check(c, upload.arrival, found, path, values)]


def arrival_check(c, upload, found, through, path, values):
    changes = header_changes(upload.sent, upload.arrival, urlsplit(upload.url).scheme)
    problems = [text("doctor_public_upload_changed", changes=BETWEEN_SENTENCES.join(changes), through=through,
                     fix=doctor_platforms.headers_fix(found, **values))] if changes else []
    status = upload.exchange.answer.status
    if sent_again(status):  # AgentCake kept it, but something in front answered for it (a proxy that gave up waiting)
        problems.append(text("doctor_public_upload_retried", url=upload.url, status=status, through=through))
    if c.get("trust_lb") and upload.arrival.get("ja4") == made_up_value()[:sizes()["max_chars"]["ja4"]]:
        fix = text("doctor_public_made_up_fix_path" if path else "doctor_public_made_up_fix", header=made_up_header())
        problems.append(text("doctor_public_made_up", header=made_up_header(), fix=fix))
    if problems:
        return text("doctor_public_upload"), False, BETWEEN_SENTENCES.join(problems)
    return text("doctor_public_upload"), True, text("doctor_public_upload_info", url=upload.url,
                                                     origin=upload.sent["origin"], through=through)


def sent_again(status):
    """Whether cake.js sends an upload again after an answer with this status (data/cakejs.json retry_statuses)."""
    return status in load("data/cakejs.json")["script"]["batch"]["retry_statuses"]


def header_changes(sent, arrival, scheme):
    """How each of COMPARED reached AgentCake: removed, or replaced (with what came instead); [] when as sent."""
    came = {name.lower(): value for name, value in arrival.get("headers", ())}
    changes = []
    for name in COMPARED:
        value = came.get(name.lower())
        if value is None:
            changes.append(text("doctor_public_removed", header=name))
        elif not same_value(name.lower(), sent[name.lower()], value, scheme):
            changes.append(text("doctor_public_replaced", header=name, value=value))
    return changes


def same_value(name, sent, came, scheme):
    """Whether a header came as it was sent: as collect keeps it (cut, data/netfacts.json); Host by name and port."""
    if name == "host":
        return host_and_port(sent, scheme) == host_and_port(came, scheme)
    limit = load("data/netfacts.json")["keep_values"].get(name)
    return came == (sent[:sizes()["max_chars"][limit]] if limit else sent)


def host_and_port(value, scheme):
    try:
        parts = urlsplit("//" + value)
        return (parts.hostname or "").rstrip("."), parts.port or DEFAULT_PORTS[scheme]
    except ValueError:  # a port that is no number
        return value, None


def address_check(c, arrival, found, path, values):
    name = text("doctor_public_address")
    if not c.get("trust_lb"):
        if path:
            return name, SKIP, text("doctor_public_address_off_path")
        return name, WARN, text("doctor_public_address_off", launcher=paths.launcher())
    if "ip_hash" not in arrival:  # collect hashes an address only when one came (collect_store.py)
        fix = text("doctor_public_address_none_fix_path" if path else "doctor_public_address_none_fix")
        return name, WARN, text("doctor_public_address_none", fix=fix)
    kind = arrival.get("ip_class")
    if kind == CDN:
        platform = doctor_platforms.by_range(arrival.get(CDN))
        fix = doctor_platforms.address_fix([platform] if platform else found, path, **values)
        return name, False, text("doctor_public_address_cdn", cdn=arrival.get(CDN), fix=fix)
    label = arrival.get(kind) if kind else None
    kind_words = text("doctor_public_address_cloud", label=label) if label else text("doctor_public_address_unlisted")
    return name, True, text("doctor_public_address_info", kind=kind_words)


# 7 ----------------------------------------------------------------------------------------------------------------

def visitors_check(c, health):
    name = text("doctor_public_visitors")
    if not health:
        return name, SKIP, text("doctor_public_not_checked", why=text("doctor_public_why_down"))
    state = health.get(ADDRESS_CHECK)
    if not isinstance(state, dict):  # an AgentCake from before the protection net
        return name, SKIP, text("doctor_public_visitors_unknown")
    sessions, cdn = state.get("sessions") or 0, state.get("cdn") or 0
    if state.get("misconfigured"):
        path = not c.get("public_url")
        url = SITE_ORIGIN.format(domain=c.get("site_domain") or "") if path else cake_root(c)
        fix = doctor_platforms.address_fix([], path, **fix_values(c, url))
        return name, False, text("doctor_public_visitors_cdn", cdn=cdn, sessions=sessions, fix=fix)
    if not sessions:
        return name, True, text("doctor_public_visitors_none")
    return name, True, text("doctor_public_visitors_info", cdn=cdn, sessions=sessions)
