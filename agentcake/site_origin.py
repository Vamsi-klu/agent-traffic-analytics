"""Where an upload came from (S2.1): the website, or another site.

classify(headers, batch_url, c, public) -> "site" | "other". The page an upload came from is its Origin header (browsers
send it with every POST, cake.js's included), else its Referer, else the batch's own URL (what cake.js read from
location; all a non-browser sender shows). On the local listener, any page on this computer counts as the site: a dev
server. The site is site_domain (a leading "www." left out) and its subdomains; without a site_domain there is nothing
to check against and every upload counts as the site. (Until D37, a page under /demo on cake's own port was cake's demo
shop, "demo"; the sessions it recorded keep that origin and are shown like the site's, api/visits.py.) An upload from
anywhere else (another domain, an opaque "null" origin, no page at all) is "other": collect still records it, and the
dashboard leaves it out (someone else's copy of the page script, a staging site, a forged upload). A sender that is not
a browser can claim any origin; this check is about browsers on other sites, not about forgery.
"""
from urllib.parse import urlsplit

SITE, OTHER = "site", "other"
LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")  # protocol: this computer's names in a URL
LOOPBACK_SUFFIX = ".localhost"  # protocol: RFC 6761, every name below localhost is this computer
WWW = "www."


def classify(headers, batch_url, c, public):
    host = _place(page_of(headers, batch_url))[0]
    if not public and _is_loopback(host):
        return SITE
    domain = site_host(c)
    if domain is None:
        return SITE
    return SITE if host is not None and (host == domain or host.endswith("." + domain)) else OTHER


def page_of(headers, batch_url):
    """The page an upload says it came from: the Origin header, else the Referer, else the batch's URL (or None)."""
    for value in (headers.get("Origin"), headers.get("Referer"), batch_url):
        if value:
            return value
    return None


def site_host(c):
    """The site's host name from site_domain, lower case, without a leading www. (None when it is not set)."""
    host = _place("//" + c["site_domain"])[0] if c.get("site_domain") else None
    return host[len(WWW):] if host and host.startswith(WWW) else host


def _place(url):
    """(host, port) of a URL, host lower case without a trailing dot; (None, None) for a URL without a usable host
    (no host, an unclosed IPv6 bracket, a port out of range)."""
    try:
        parts = urlsplit(str(url or ""))
        host, port = parts.hostname, parts.port
    except ValueError:
        return None, None
    return (host.rstrip(".") or None, port) if host else (None, None)


def _is_loopback(host):
    return host is not None and (host in LOOPBACK_NAMES or host.endswith(LOOPBACK_SUFFIX))

