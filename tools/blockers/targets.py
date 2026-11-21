"""What the content-blocker check looks at: AgentCake's requests from a visitor's browser, and each blocker's lists.

requests() reads them from AgentCake's own code, so a new or renamed route is checked without editing this file: every
route of the public listener (agentcake/routes.py PUBLIC) that a browser asks for, under the path SERVER.md tells a site
to use (`agentcake config set path_prefix …`) on SERVER.md's example site, and the same routes on the local page's
address from a site on this computer; the upload also with cake.js's gzip query (data/cakejs.json). Routes only servers
call (blockers.json "not_from_browsers") are left out.

lists_of(blocker, catalog) picks a blocker's default lists from its catalog: uBlock Origin's assets.json, Brave's
list_catalog.json, or a fixed list (AdGuard). Each list is (name, url, applies_to_first_party_in_standard_mode).
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)  # run as a script under python3 -I, the repository root is not on sys.path
from agentcake import config, routes  # noqa: E402
from agentcake.datafiles import load  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(HERE, "blockers.json")
SERVER_MD = os.path.join(REPO, "SERVER.md")
LOCAL_SITE = "http://localhost:3000/"  # protocol: a site's dev server on this computer, another origin than cake's
SCRIPT, UPLOAD = "script", "xmlhttprequest"  # protocol: the request types filter lists name (cake.js uploads by fetch)


def settings():
    with open(SETTINGS, encoding="utf-8") as f:
        return json.load(f)


def documented_prefix(server_md=SERVER_MD):
    """The path_prefix SERVER.md tells a site to set."""
    with open(server_md, encoding="utf-8") as f:
        found = re.search(r"agentcake config set path_prefix (\S+)", f.read())
    if not found:
        raise ValueError("SERVER.md has no `agentcake config set path_prefix …` line")
    return config.coerce("path_prefix", found.group(1))


def browser_routes(conf):
    """(method, path) of each public route a visitor's browser asks for."""
    skip = set(conf["not_from_browsers"])
    return [(r.method, r.path) for r in routes.PUBLIC if not r.is_prefix and r.path not in skip]


def requests(conf=None, prefix=None):
    """Every request to check: {label, url, type, page}."""
    conf = conf or settings()
    prefix = documented_prefix() if prefix is None else prefix
    gzip = load("data/cakejs.json")["script"]["gzip_query"]
    host = conf["site"]["page_host"]
    places = [("server", f"https://{host}{prefix}", f"https://{host}/"),
              ("local", config.base_url(config.DEFAULTS), LOCAL_SITE)]
    out = []
    for where, base, page in places:
        for method, path in browser_routes(conf):
            kind = UPLOAD if method == "POST" else SCRIPT
            for query in ("", gzip) if kind == UPLOAD else ("",):
                out.append({"label": f"{where} {method} {path}{query}", "url": base + path + query, "type": kind,
                            "page": page})
    return out


def first_party(url, page):
    """Same site, as blockers count it: the same host, or the same last two labels of a name (not of an address)."""
    def site(u):
        host = re.sub(r"^\w+://", "", u).split("/")[0].split(":")[0]
        return host if re.fullmatch(r"[\d.]+", host) else ".".join(host.split(".")[-2:])
    return site(url) == site(page)


def _http(urls):
    urls = urls if isinstance(urls, list) else [urls]
    return next((u for u in urls if u.startswith(("https://", "http://"))), None)


def lists_of(blocker, catalog, conf=None):
    """[(name, url, in_standard_first_party)] of a blocker's default lists. in_standard_first_party says whether a
    first-party request is checked against the list in the blocker's default mode (only Brave makes the difference)."""
    conf = conf or settings()
    spec = conf["blockers"][blocker]
    if spec["kind"] == "fixed":
        return [(name, url, True) for name, url in spec["lists"].items()]
    if spec["kind"] == "ubo-assets":
        return [(entry.get("title", key), _http(entry.get("contentURL")) or _http(entry.get("cdnURLs")), True)
                for key, entry in catalog.items() if entry.get("content") == "filters" and not entry.get("off")]
    if spec["kind"] == "brave-catalog":
        out = []
        for entry in catalog:
            platforms = entry.get("platforms")
            if not entry.get("default_enabled") or (platforms and not set(platforms) & set(conf["brave_platforms"])):
                continue
            for n, source in enumerate(entry["sources"], 1):
                out.append((f"{entry['title']} ({n})", source["url"], not entry.get("first_party_protections")))
        return out
    raise ValueError(f"unknown catalog kind {spec['kind']!r} for {blocker}")


def hosts_format(text):
    """True for a hosts file (`0.0.0.0 name` lines), which matchers read differently from filter syntax."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", "!"))][:20]
    return bool(lines) and all(re.match(r"^(?:\d{1,3}\.){3}\d{1,3}\s+\S", ln) for ln in lines)


def line_of(rule, text):
    """1-based line numbers where the rule is written, as the list has it."""
    return [n for n, line in enumerate(text.splitlines(), 1) if line.strip() == rule]
