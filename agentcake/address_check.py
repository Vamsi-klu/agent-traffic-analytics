"""Is the visitor's address really the visitor's? The safety net under the verification layer.

On a server the visitor's address is what the front door says it is (netfacts.client_address). Set up wrong, it is the
front door's own address: Cloudflare's when the DNS record of the subdomain route is proxied (the orange cloud), or a
CDN's in front of a same-site path. Then a real Googlebot seen from a Cloudflare address looks like an impersonator
(verdict_identity: a name its operator's published ranges could verify, from an address outside them), and every
visitor gets "many sessions from one address". AgentCake keeps no address, but it keeps the network class of each
upload's address (netfacts.request_facts' ip_class): when most of the latest sessions with an address came from a
CDN's published ranges, the address is the front door's.

    check(con, at_ms, settings=None) -> {"sessions", "cdn", "misconfigured"}
        the latest `sessions` sessions with a visitor's address in the window before at_ms (data/verdict.json
        "address_check"; self-checks and uploads from other sites left out), how many of them came from a CDN's ranges
        (a relay's, such as iCloud Private Relay's, are visitors), and whether that is at least cdn_share of them;
        fewer sessions say nothing. evidence.py checks at each session's own last upload, so a session is judged the
        same when it is judged again after the setup was fixed; the latest sessions rather than the whole window, so
        that a fix shows within a few sessions.
    current(con, c=None, now_ms=None) -> the same for now on a server that reads addresses (geoip.sees_addresses:
        public_listen and trust_lb), else nothing to say: what /api/health (doctor) and the dashboard's warning read.

A session judged as if it had no address only loses what the address would have said (verification by a published
range, the address weak signals): this never makes anyone an Agent.
"""
from agentcake import datafiles, geoip
from agentcake.config import load_cfg
from agentcake.storage_config import now_ms as clock_ms
from agentcake.units import MS_PER_S

SETTINGS_FILE = "data/verdict.json"
CDN = "cdn"  # netfacts.network_class() of an address in a CDN's published ranges (lists.NETWORK_KINDS)
NOTHING = {"sessions": 0, "cdn": 0, "misconfigured": False}
# The upload requests that carried a visitor's address (look_up gave a range_id key, null or not), newest first, of the
# sessions that count: not self-checks, not uploads from another site (api/visits.py's SHOWN, without the verdict).
LATEST = ("SELECT r.session_id, json_extract(r.facts, '$.ip_class') FROM requests r JOIN sessions s "
          "ON s.id = r.session_id WHERE r.recv_ms BETWEEN ? AND ? AND json_type(r.facts, '$.range_id') IS NOT NULL "
          "AND s.is_test = 0 AND COALESCE(s.origin, 'site') != 'other' ORDER BY r.recv_ms DESC")


def check(con, at_ms, settings=None):
    """What the latest sessions with an address before at_ms say about the address source (see the docstring)."""
    rule = (settings or datafiles.load(SETTINGS_FILE))["address_check"]
    latest = {}
    for session_id, ip_class in con.execute(LATEST, (at_ms - rule["window_s"] * MS_PER_S, at_ms)):
        latest.setdefault(session_id, ip_class)  # the class of the session's newest upload with an address
        if len(latest) == rule["sessions"]:
            break
    cdn = sum(1 for ip_class in latest.values() if ip_class == CDN)
    enough = len(latest) >= rule["sessions"]
    return {"sessions": len(latest), "cdn": cdn, "misconfigured": enough and cdn / len(latest) >= rule["cdn_share"]}


def current(con, c=None, now_ms=None):
    """check() for now, on a server that reads the visitor's address; NOTHING where no address is read."""
    if not geoip.sees_addresses(c or load_cfg()):
        return dict(NOTHING)
    return check(con, clock_ms() if now_ms is None else now_ms)
