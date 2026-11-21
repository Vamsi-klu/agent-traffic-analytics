"""The network facts of an upload request (0.3.3's server mode): its headers, and what the visitor's address says.

Per request (the requests table, written by collect_store; the environment layer's env_signals.from_cake reads
"headers" and "ip_class", the verdict the lists.match_ip() fields):
    client_address(headers, c, public) -> address or None   only on the public listener with trust_lb, and only from
                                                             the load balancer's header (data/lb_headers.json) or,
                                                             with proxy_hops, X-Forwarded-For counted from the right
    look_up(address) -> lists.match_ip() result or None     published agent or bot range; relay, CDN, cloud; and the
                                                             country, region and city of the city database
                                                             (geoip.place), when it has them
    request_facts(headers, origin, lb, found) -> facts      the header values data/netfacts.json keeps, as sent and
                                                             cut (data/sizes.json); every header name in order; where
                                                             the upload came from; the load balancer's JA4 and
                                                             protocol; the address's network, its class and its place
    address_hashes(salt, address) -> {ip_hash, net_hash}    the address and its /24 or /48, hashed with the salt of
                                                             ip_salt.py: all that is kept of the address itself
Per session (0.3.3, sessions.net, which the session page shows with the server half, api/server_half.py):
net_facts(headers, c) -> (facts, address): country, region and city (the city database's: no header a client
could write gives a place), published range, TLS JA4, protocol, the Web Bot Auth headers. The
address is returned only so collect can compare networks with the server half and hash it; it is never stored.
ip_prefix() and network_key() compute the day-scoped network key a site's middleware (edge/) signs into its tokens.
"""
import hashlib
import hmac
import ipaddress
import time

from agentcake import geoip
from agentcake.datafiles import load, sizes
from agentcake.detect import lists
from agentcake.units import MS_PER_S

KEEP = load("data/netfacts.json")
# lists.match_ip()'s network kinds, the most specific first: an iCloud Private Relay egress sits in a CDN's ranges
NETWORK_CLASSES = ("relay", "cdn", "cloud")

IPV4, IPV6 = 4, 6  # protocol: IP versions
# The network key's format, shared with the site middleware (edge/, tests/vectors/edge_token.json): the HMAC of an
# address's /24 (IPv4) or /48 (IPv6, its first 3 groups) and the day, cut to 16 hex digits.
IPV4_PREFIX, IPV6_PREFIX, IPV6_PREFIX_GROUPS, NETWORK_KEY_HEX_DIGITS = 24, 48, 3, 16  # protocol: network key format
IPV6_GROUP_BYTES = 2  # protocol: an IPv6 address is written in groups of 2 bytes
SIGNATURE_HEADERS = ("Signature", "Signature-Input", "Signature-Agent")  # RFC 9421, as Web Bot Auth uses it
FORWARDED_FOR = "X-Forwarded-For"  # protocol: the de facto header proxies add the client's address to (proxy_hops)


def lb_headers():
    """data/lb_headers.json: the names of the headers the load balancer sets."""
    return load("data/lb_headers.json")["headers"]


def ranges():
    """When the published ranges in use were built: {"built": date}, or None for the date when the lists cannot be
    read (a broken install). Collecting then goes on without ranges; `agentcake lists` and doctor show the error."""
    try:
        return {"built": lists.current().built}
    except lists.ListsError:
        return {"built": None}


def published_range(ip):
    """(label, kind) of the first published range holding this address, in the lists' priority order; else None."""
    try:
        return lists.current().first_range(ip)
    except lists.ListsError:
        return None


def ip_prefix(ip):
    """The /24 (IPv4) or /48 (IPv6) of an address, written the way the site middleware writes it (edge/)."""
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    if a.version == IPV6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.version == IPV4:
        return str(ipaddress.ip_network(f"{a}/{IPV4_PREFIX}", strict=False).network_address) + f"/{IPV4_PREFIX}"
    # The first three groups from the address's bytes: .exploded raises for an address with a zone ("fe80::1%eth0").
    span = IPV6_PREFIX_GROUPS * IPV6_GROUP_BYTES
    g = [int.from_bytes(a.packed[i:i + IPV6_GROUP_BYTES], "big") for i in range(0, span, IPV6_GROUP_BYTES)]
    return ":".join(format(x, "x") for x in g) + f"::/{IPV6_PREFIX}"


def network_key(secret, ip, now_ms):
    p = ip_prefix(ip)
    if not p:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime(now_ms / MS_PER_S))
    return hmac.new(secret, f"ip|{day}|{p}".encode(), hashlib.sha256).hexdigest()[:NETWORK_KEY_HEX_DIGITS]


def client_address(headers, c, public):
    """The visitor's address as your front door gives it, or None. Only on the public listener with trust_lb (on the
    local listener every visit comes from this computer): with proxy_hops 0, the load balancer's own header
    (data/lb_headers.json "ip"); with proxy_hops N, the N-th entry of X-Forwarded-For from the right.
    No other header (Forwarded, X-Real-IP) ever counts."""
    if not public or not c.get("trust_lb"):
        return None
    hops = c.get("proxy_hops") or 0
    if hops:
        return _forwarded_for(headers, hops)
    return (headers.get(lb_headers()["ip"]) or "").strip() or None


def _forwarded_for(headers, hops):
    """The address the first of your `hops` proxies added to X-Forwarded-For, or None. Each proxy adds the address it
    was reached from at the right, so that is the hops-th entry from the right, over every line of the header in
    order; what is left of it came with the request and can be anything (PostHog 1.0's capture.py takes the
    leftmost, and checks no crawler against it). Fewer entries than proxies gives None, never another entry. A port
    some proxies write after the address (203.0.113.7:51234, [2001:db8::7]:443) is dropped."""
    lines = headers.get_all(FORWARDED_FOR) if hasattr(headers, "get_all") else [headers.get(FORWARDED_FOR)]
    entries = [entry.strip() for line in lines or () if line for entry in line.split(",")]
    if len(entries) < hops:
        return None
    entry = entries[-hops]
    if entry.startswith("["):
        entry = entry[1:].partition("]")[0]
    elif entry.count(":") == 1:
        entry = entry.partition(":")[0]
    try:
        return str(ipaddress.ip_address(entry))
    except ValueError:
        return None


def look_up(address):
    """lists.match_ip() of the address, with the country, region and city the city database gives it when it gives
    one (geoip.place: the weak signals compare the country with the browser's time zone and languages); None for no
    address, text that is not one, or lists that cannot be read (`agentcake lists` and doctor say why; collecting goes
    on without them)."""
    if not address:
        return None
    try:
        found = lists.current().match_ip(address)
    except lists.ListsError:
        return None
    return dict(found, **(geoip.place(address) or {})) if found is not None else None


def network_class(found):
    """relay, cdn or cloud: the most specific network kind the address is in; None when it is in none."""
    return next((kind for kind in NETWORK_CLASSES if found.get(kind)), None)


def request_facts(headers, origin, lb, found):
    """One upload request's facts (see the module docstring); lb: the load balancer's headers count; found:
    look_up() of the address (None when there was none to look up: then there is no ip_class, which reads as
    unknown, not as "in no network")."""
    cap, kept, names = sizes()["max_chars"], [], []
    for name, value in headers.items():
        key = name.lower()
        names.append(key)
        limit = _value_cap(key)
        if limit:
            kept.append([name, value[:cap[limit]]])
    facts = {"headers": kept, "names": names[:cap["header_names"]], "origin": origin}
    if lb:
        facts.update(_load_balancer(headers, cap))
    if found is not None:
        facts.update(found, ip_class=network_class(found))
    return facts


def address_hashes(salt, address):
    """{"ip_hash", "net_hash"}: HMAC-SHA256 with the salt of the address and of its /24 or /48 (ip_prefix), cut to
    ip_hash_hex hex digits; an IPv4-mapped IPv6 address hashes as its IPv4. {} for text that is not an address."""
    try:
        ip = ipaddress.ip_address(str(address).strip())
    except ValueError:
        return {}
    ip = getattr(ip, "ipv4_mapped", None) or ip
    digits = sizes()["ip_hash_hex"]

    def digest(kind, text):
        return hmac.new(salt, f"{kind}|{text}".encode(), hashlib.sha256).hexdigest()[:digits]

    return {"ip_hash": digest("ip", ip), "net_hash": digest("net", ip_prefix(str(ip)))}


def _value_cap(name):
    """The data/sizes.json cap of a header whose value is kept, or None when only its name is kept."""
    if name in KEEP["keep_values"]:
        return KEEP["keep_values"][name]
    return next((limit for prefix, limit in KEEP["keep_value_prefixes"].items() if name.startswith(prefix)), None)


def _load_balancer(headers, cap):
    """What the load balancer says about the connection itself: the TLS JA4 fingerprint and the protocol. The place
    is never read from a header: the city database gives it (geoip.py)."""
    names = lb_headers()
    return {"ja4": (headers.get(names["ja4"]) or "")[:cap["ja4"]] or None,
            "proto": (headers.get(names["proto"]) or "")[:cap["proto"]] or None}


def net_facts(headers, c):
    """sessions.net (0.3.3): where the visitor's address is (the city database), what the load balancer says about
    the connection, and the published range of the address. Only on the public listener (the caller's choice) with
    trust_lb. The address is returned for the caller to compare networks with the server half and to hash; it is not
    in the facts and never stored."""
    if not c.get("trust_lb"):
        return None, None
    ip, cap = client_address(headers, c, public=True), sizes()["max_chars"]
    pr = published_range(ip) if ip else None
    facts = dict((geoip.place(ip) if ip else None) or {}, **_load_balancer(headers, cap), range=pr[0] if pr else None,
                 range_kind=pr[1] if pr else None,
                 # Web Bot Auth on cake.js's own request (does an agent sign the page's fetches too?), kept as sent, cut
                 sig={k: (headers.get(k) or "")[:cap["signature_header"]] or None for k in SIGNATURE_HEADERS},
                 ranges_built=ranges()["built"])
    return facts, ip
