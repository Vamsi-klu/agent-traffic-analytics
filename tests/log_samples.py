"""Made-up web server access logs for the log import tests (S4.4), with the truth every line was written from.

    requests(count, seed, start_ms) -> [Truth]          a mix of page views, static files, uploads, redirects
    LINE_WRITERS[name](truth) -> one log line            as nginx, Apache and Caddy write it, escaping included
    parsed_view(name, truth) -> what a parser must read  the truth seen through that format (fields, precision)

No real visitor is in here: addresses come from the documentation ranges of RFC 5737 (192.0.2.0/24, 198.51.100.0/24,
203.0.113.0/24), IPv6 ones are the first address of a range the release's lists publish (no visitor's address), and
the User-Agents are the generic strings of current browsers. Some requests carry a Web Bot Auth signature made with
the test signer of test_webbotauth.py, so that the import can verify them against a test key directory. It covers
@authority and Signature-Agent, not the path, and is valid from SIGNED_FROM_S for SIGNED_FOR_S, so one signature
(made once: the test signer is slow on purpose) serves every signed request of the samples.
"""
import base64
import datetime
import functools
import ipaddress
import json
import os
import random
import re
from dataclasses import dataclass, field, replace
from typing import Optional

from agentcake.detect import httpsig, keydirectory, sfv
from test_webbotauth import AGENT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_NETS = ("192.0.2.", "198.51.100.", "203.0.113.")  # RFC 5737
SIGNER_HOST = "agent.example"
SITE_HOST = "shop.example"
CHROME_HINT = '"Chromium";v="149", "Google Chrome";v="149", "Not)A;Brand";v="24"'
USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 "
    "Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 "
    "Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 "
    "Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 "
    "Edg/149.0.0.0",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/149.0.0.0 Safari/537.36",
    'Mozilla/5.0 (compatible; "Quoted" Tester/1.0; back\\slash)',
)
LANGUAGES = ("en-US,en;q=0.9", "de-DE,de;q=0.9,en;q=0.8", "fr-FR,fr;q=0.9", "ja,en-US;q=0.9", "es-ES,es;q=0.9")
PAGES = ("/", "/shop", "/shop?page=2", "/product/17", "/product/42?color=red&size=m", "/cart", "/checkout",
         "/search?q=red+shoes", "/caf%C3%A9", "/about", "/blog/hello-world/")
STATIC = ("/static/app.css", "/static/app.js", "/img/logo.png", "/favicon.ico", "/fonts/body.woff2")
UPLOAD = "/cake/collect"
SIGNED_FROM_S = 1794499000  # before every sample's first request
SIGNED_FOR_S = 4 * 3600
LOG_OFFSET = datetime.timezone(datetime.timedelta(hours=-8))  # the web server's local time in $time_local and %t
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
FORMATS = ("nginx-combined", "nginx-agentcake", "apache-combined", "apache-agentcake", "caddy-json")
FORMAT_OF_SAMPLE = {"nginx-combined": "combined", "apache-combined": "combined"}  # both servers write combined alike
WHOLE_SECONDS = {"nginx-combined", "apache-combined"}  # $time_local and %t have no fraction of a second
LOGGED_HEADERS = {
    "nginx-combined": ("user-agent", "referer"),
    "apache-combined": ("user-agent", "referer"),
    "nginx-agentcake": ("user-agent", "accept-language", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
                        "sec-fetch-user", "sec-ch-ua", "signature-agent", "signature-input", "signature"),
}
LOGGED_HEADERS["apache-agentcake"] = LOGGED_HEADERS["nginx-agentcake"]


@dataclass(frozen=True)
class Truth:
    """One request as the web server saw it. headers: lower-case name -> value, only those sent."""
    t_ms: int
    ip: str
    method: str
    target: str
    protocol: str
    status: int
    host: str
    scheme: str
    headers: dict = field(default_factory=dict)
    referer: Optional[str] = None


@functools.lru_cache(maxsize=None)
def published_ipv6():
    """The first address of the first IPv6 range in the release's lists: published, so no visitor's address."""
    with open(os.path.join(ROOT, "agentcake", "data", "lists", "ip_ranges.json"), encoding="utf-8") as f:
        ranges = json.load(f)["ranges"]
    block = next(r["v6"][0] for r in ranges if r.get("v6"))
    return str(ipaddress.ip_network(block, strict=False).network_address)


def doc_address(rng):
    return rng.choice(DOC_NETS) + str(rng.randrange(1, 255))


FETCH_MODES = {"document": "navigate", "image": "no-cors", "empty": "cors"}


@functools.lru_cache(maxsize=None)
def signature_headers():
    """Signature-Agent, Signature-Input and Signature of a request to SITE_HOST by the test agent."""
    agent = f'sig1="https://{SIGNER_HOST}"'
    signature_input = (f'sig1=("@authority" "signature-agent");created={SIGNED_FROM_S};'
                       f'expires={SIGNED_FROM_S + SIGNED_FOR_S};keyid="{keydirectory.thumbprint(AGENT.jwk)}";'
                       'alg="ed25519";tag="web-bot-auth"')
    request = httpsig.Request("GET", "https", SITE_HOST, "/", [("Signature-Agent", agent),
                                                                ("Signature-Input", signature_input)])
    base = httpsig.signature_base(request, sfv.parse_dictionary(signature_input)["sig1"])
    signature = f"sig1=:{base64.b64encode(AGENT.sign(base.encode())).decode()}:"
    return {"signature-agent": agent, "signature-input": signature_input, "signature": signature}


def browser_headers(rng, ua, language, dest="document", signed=False):
    """The headers a browser sends on a page request (dest document) or another request; some left out at random."""
    headers = {"user-agent": ua}
    if rng.random() < 0.9:
        headers["accept-language"] = language
    if rng.random() < 0.85:  # browsers before Safari 16.4 send no Sec-Fetch-*
        headers.update({"sec-fetch-site": rng.choice(("none", "same-origin", "cross-site")),
                        "sec-fetch-mode": FETCH_MODES[dest], "sec-fetch-dest": dest})
        if dest == "document" and rng.random() < 0.6:
            headers["sec-fetch-user"] = "?1"
    if "Chrome/" in ua:
        headers["sec-ch-ua"] = CHROME_HINT
    if signed:
        headers.update(signature_headers())
    return headers


def requests(count, seed, start_ms):
    """count requests over about an hour from start_ms: mostly page views, then static files, uploads to Agent Cake,
    redirects, 404s and HEADs, a few signed, a few from IPv6."""
    rng, ipv6, out, t = random.Random(seed), published_ipv6(), [], start_ms
    for _ in range(count):
        t += rng.randrange(50, 40_000)
        kind = rng.choices(("page", "static", "upload", "redirect", "missing", "head"), (60, 20, 8, 5, 4, 3))[0]
        ip = ipv6 if rng.random() < 0.05 else doc_address(rng)
        ua, language = rng.choice(USER_AGENTS), rng.choice(LANGUAGES)
        method, status, target = "GET", 200, rng.choice(PAGES)
        signed = kind == "page" and rng.random() < 0.08
        dest = {"static": "image", "upload": "empty"}.get(kind, "document")
        headers = browser_headers(rng, ua, language, dest, signed)
        if kind == "static":
            target, status = rng.choice(STATIC), rng.choice((200, 304))
        elif kind == "upload":
            method, target, status = "POST", UPLOAD, 204
        elif kind == "redirect":
            status = rng.choice((301, 302, 308))
        elif kind == "missing":
            target, status = "/old-page", 404
        elif kind == "head":
            method = "HEAD"
        elif rng.random() < 0.1:
            status = 304
        out.append(Truth(t, ip, method, target, rng.choice(("HTTP/1.1", "HTTP/2.0")), status, SITE_HOST,
                         rng.choice(("https", "https", "http")), headers,
                         referer=f"https://{SITE_HOST}/" if rng.random() < 0.5 else None))
    return out


# ---------------------------------------------------------------- how each web server writes a line
PLAIN = re.compile(r'[ !#-\[\]-~]*')  # printable ASCII but " and \\: what neither server escapes


def nginx_escape(value):
    """nginx's escape=default: ", \\ and bytes below 32 or above 126 as \\xXX."""
    if PLAIN.fullmatch(value):
        return value
    return "".join(chr(b) if 32 <= b <= 126 and b not in b'"\\' else f"\\x{b:02X}" for b in value.encode("utf-8"))


def apache_escape(value):
    """Apache's ap_escape_logitem: \\" and \\\\, \\n \\r \\t \\b \\v, other bytes that are not printable as \\xhh."""
    if PLAIN.fullmatch(value):
        return value
    named = {ord('"'): '\\"', ord("\\"): "\\\\", 10: "\\n", 13: "\\r", 9: "\\t", 8: "\\b", 11: "\\v"}
    return "".join(named.get(b) or (chr(b) if 32 <= b <= 126 else f"\\x{b:02x}") for b in value.encode("utf-8"))


def clf_time(t_ms):
    moment = datetime.datetime.fromtimestamp(t_ms // 1000, LOG_OFFSET)
    return moment.strftime("%d/") + MONTHS[moment.month - 1] + moment.strftime("/%Y:%H:%M:%S %z")


def nginx_value(value):
    return "-" if value is None else nginx_escape(value)


def apache_value(value):
    return "-" if value is None else apache_escape(value)


def request_line(truth):
    return f"{truth.method} {truth.target} {truth.protocol}"


def nginx_combined(truth):
    size = "0" if truth.status in (204, 304) or truth.method == "HEAD" else "5120"
    return (f'{truth.ip} - - [{clf_time(truth.t_ms)}] "{nginx_escape(request_line(truth))}" {truth.status} {size} '
            f'"{nginx_value(truth.referer)}" "{nginx_value(truth.headers.get("user-agent"))}"')


def apache_combined(truth):
    size = "-" if truth.status in (204, 304) or truth.method == "HEAD" else "5120"
    return (f'{truth.ip} - - [{clf_time(truth.t_ms)}] "{apache_escape(request_line(truth))}" {truth.status} {size} '
            f'"{apache_value(truth.referer)}" "{apache_value(truth.headers.get("user-agent"))}"')


def nginx_agentcake(truth):
    seconds, millis = divmod(truth.t_ms, 1000)
    names = LOGGED_HEADERS["nginx-agentcake"]
    quoted = " ".join(f'"{nginx_value(truth.headers.get(name))}"' for name in names)
    return (f'{truth.ip} [{seconds}.{millis:03d}] "{nginx_escape(request_line(truth))}" {truth.status} '
            f'{truth.scheme} "{nginx_escape(truth.host)}" {quoted}')


def apache_agentcake(truth):
    names = LOGGED_HEADERS["apache-agentcake"]
    quoted = " ".join(f'"{apache_value(truth.headers.get(name))}"' for name in names)
    return (f'{truth.ip} [{truth.t_ms}] "{apache_escape(request_line(truth))}" {truth.status} '
            f'"{apache_escape(truth.host)}" {quoted}')


def caddy_json(truth):
    canonical = {name: ["-".join(part.capitalize() for part in name.split("-"))] for name in truth.headers}
    headers = {canonical[name][0]: [value] for name, value in truth.headers.items()}
    headers["Cookie"] = ["REDACTED"]  # Caddy logs every header; cookies are redacted unless log_credentials is on
    if truth.referer:
        headers["Referer"] = [truth.referer]
    request = {"remote_ip": truth.ip, "remote_port": "51234", "client_ip": truth.ip, "proto": truth.protocol,
               "method": truth.method, "host": truth.host, "uri": truth.target, "headers": headers}
    if truth.scheme == "https":
        request["tls"] = {"resumed": False, "version": 772, "cipher_suite": 4865, "proto": "h2",
                          "server_name": truth.host}
    entry = {"level": "info", "ts": truth.t_ms / 1000, "logger": "http.log.access.log0", "msg": "handled request",
             "request": request, "bytes_read": 0, "user_id": "", "duration": 0.0021, "size": 5120,
             "status": truth.status, "resp_headers": {"Content-Type": ["text/html; charset=utf-8"]}}
    return json.dumps(entry, separators=(",", ":"))


LINE_WRITERS = {"nginx-combined": nginx_combined, "nginx-agentcake": nginx_agentcake,
                "apache-combined": apache_combined, "apache-agentcake": apache_agentcake, "caddy-json": caddy_json}


def parsed_view(sample, truth):
    """The truth as a parser reads it from this sample format's line: whole seconds where the format has no fraction,
    the headers the format logs, no Host or scheme where the format has none."""
    t_ms = truth.t_ms // 1000 * 1000 if sample in WHOLE_SECONDS else truth.t_ms
    if sample == "caddy-json":
        headers = dict(truth.headers, cookie="REDACTED", **({"referer": truth.referer} if truth.referer else {}))
        return replace(truth, t_ms=t_ms, headers=headers)
    logged = LOGGED_HEADERS[sample]
    headers = {name: value for name, value in truth.headers.items() if name in logged}
    if "referer" in logged and truth.referer:
        headers["referer"] = truth.referer
    host = truth.host if "agentcake" in sample else None
    scheme = truth.scheme if sample == "nginx-agentcake" else None
    return replace(truth, t_ms=t_ms, headers=headers, host=host, scheme=scheme)
