"""The name and verification lists (S3.1): who a User-Agent says it is, whose published range an address is in, and
which operator a Web Bot Auth signer is, all read from files on this computer.

Like PostHog's bot_definitions.py and bot_ip_networks.py, the lists ship with each release (D23): User-Agent names
from botscent, PostHog, ai.robots.txt and our own (names.json), operators' published address ranges (ip_ranges.json),
Web Bot Auth signers (signers.json) and their key directories (keys.json), all built by lists_build.py from
sources.json. Nothing in this module opens a connection. `agentcake lists update` writes a dated copy under
<CAKE_HOME>/lists/, which is used while it is at least as new as the release's own.

    Lists.load(bundled_dir, user_root) -> the snapshot in use (the release's own folder is parsed once per process)
    current()            -> the same for this CAKE_HOME, cached for this process
    .match_ua(ua)        -> {id, name, operator, category: agent | bot, kind, kind_label, row, evidence, sources,
                             matched} for a declared name, a dict with id None and `conflict` when the User-Agent
                             declares several, or None
    .match_ip(address)   -> {range, range_id, range_kind, operator, verifies, cloud, cdn, relay}; None if not an address
    .signer(host)        -> {host, name, ..., keys, keys_fetched_at} or None; .key_directories() -> {host: [JWK]}
    .status(max_age_days, today) -> {built, age_days, max_age_days, stale, location, sources, skipped}
    network_span(block)  -> (IP version, first address, last address) of a published block, as ipaddress reads it

An address is looked up and dropped: no result, cache or attribute keeps it.

The token, versioned and exact matches follow botscent's contract section 6 and src/server/tokens.ts
(github.com/nalinbhardwaj/botscent, 7f948003, MIT), rewritten here; the boundary characters come from names.json.
"""
import bisect
import copy
import datetime
import functools
import ipaddress
import json
import os
import re
import socket

from agentcake import paths

BUNDLED_DIR = os.path.join(paths.PACKAGE_DIR, "data", "lists")
SOURCES_FILE = os.path.join(BUNDLED_DIR, "sources.json")
KINDS_FILE = os.path.join(BUNDLED_DIR, "kinds.json")
SNAPSHOT_FILES = ("names.json", "ip_ranges.json", "signers.json", "keys.json")
PUBLISHED_KINDS = ("agent", "bot")
NETWORK_KINDS = ("relay", "cdn", "cloud")
DATED_DIR = re.compile(r"\d{4}-\d{2}-\d{2}")
IPV4, IPV6 = ipaddress.IPv4Address(0).version, ipaddress.IPv6Address(0).version
# IP version -> (socket family, address bits): network_span() reads a block without ipaddress
FAMILIES = {IPV4: (socket.AF_INET, ipaddress.IPV4LENGTH), IPV6: (socket.AF_INET6, ipaddress.IPV6LENGTH)}


class ListsError(Exception):
    """A snapshot folder is missing a file or holds one that cannot be read."""


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as error:
        raise ListsError(f"{path}: {error}") from error


class _Pattern:
    """One way a name shows in a User-Agent; find() gives the (start, end) of the match or None."""

    def __init__(self, spec, matching):
        self.mode, self.text = spec["match"], spec["text"]
        self.before, self.after = matching["token_before"], matching["token_after"]
        self.regex = re.compile(self.text) if self.mode == "regex" else None

    def find(self, ua):
        if self.mode == "exact":
            return (0, len(ua)) if ua == self.text else None
        if self.mode == "prefix":
            return (0, len(self.text)) if ua.startswith(self.text) else None
        if self.mode == "regex":
            found = self.regex.search(ua)
            return found.span() if found else None
        at = ua.find(self.text)
        while at != -1:
            end = at + len(self.text)
            if self._bounded(ua[at - 1] if at else "", ua[end] if end < len(ua) else ""):
                return at, end
            at = ua.find(self.text, at + 1)
        return None

    def _bounded(self, previous, following):
        if self.mode == "word":
            return not previous.isalnum()
        if previous and previous not in self.before:
            return False
        if self.mode == "versioned":
            return following == "/"
        return not following or following in self.after


class _Range:
    """One published list: sorted, merged [start, end] integers per IP version, for bisect."""

    def __init__(self, spec):
        self.id, self.label, self.kind = spec["id"], spec["label"], spec["kind"]
        self.operator, self.verifies = spec.get("operator"), list(spec.get("verifies", []))
        spans = {}
        for block in spec.get("v4", []) + spec.get("v6", []):
            version, first, last = network_span(block)
            spans.setdefault(version, []).append((first, last))
        self.blocks = {}
        for version, pairs in spans.items():
            merged = []
            for start, end in sorted(pairs):
                if merged and start <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            self.blocks[version] = ([s for s, _ in merged], [e for _, e in merged])

    def contains(self, version, number):
        starts, ends = self.blocks.get(version, ((), ()))
        i = bisect.bisect_right(starts, number) - 1
        return i >= 0 and ends[i] >= number


def network_span(block):
    """(IP version, first address, last address as integers) of a network block: what ipaddress.ip_network(block)
    gives. A block written the way ipaddress writes one ("<address>/<prefix>", no host bits) is read with inet_pton,
    several times faster, which counts with over 20,000 blocks in a release; any other spelling goes to ipaddress
    itself, so the result and the errors stay its own."""
    span = _written_span(block) if isinstance(block, str) else None
    if span is None:
        network = ipaddress.ip_network(block)
        span = network.version, int(network.network_address), int(network.broadcast_address)
    return span


def _written_span(block):
    """network_span() of a block in ipaddress's own spelling, or None for anything else."""
    text, _, prefix = block.partition("/")
    version = IPV6 if ":" in text else IPV4
    family, bits = FAMILIES[version]
    try:
        packed = socket.inet_pton(family, text)
    except OSError:
        return None
    if not (prefix.isascii() and prefix.isdigit()) or str(int(prefix)) != prefix or int(prefix) > bits:
        return None
    if socket.inet_ntop(family, packed) != text:
        return None
    first, host = int.from_bytes(packed, "big"), (1 << (bits - int(prefix))) - 1
    return None if first & host else (version, first, first | host)


def _inside(span, other):
    return span != other and other[0] <= span[0] and span[1] <= other[1]


def _address(value):
    """The address, with an IPv4-mapped IPv6 one (::ffff:a.b.c.d) read as the IPv4 it carries; None if not one."""
    try:
        address = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None
    return getattr(address, "ipv4_mapped", None) or address


class Lists:
    """One snapshot of the lists: the release's own folder or one dated update."""

    def __init__(self, files, kinds, location):
        names, ranges = files["names.json"], files["ip_ranges.json"]
        self.built, self.schema, self.location, self.skipped = names["built"], names["schema"], location, []
        self._kinds = kinds["kinds"]
        self._names = {entry["id"]: entry for entry in names["names"]}
        self._matchers = [(entry, [_Pattern(p, names["matching"]) for p in entry["patterns"]])
                          for entry in names["names"] if entry["patterns"]]
        self._hints = [(hint, re.compile(hint["pattern"])) for hint in names["hints"]]
        self._platforms, self._sources = names["platforms"], names["sources"]
        self._raw_ranges = ranges["ranges"]
        self._ranges = [_Range(spec) for spec in ranges["ranges"]]
        self._signers = files["signers.json"]["signers"]
        keys = files["keys.json"]
        self._keys, self._responses, self._keys_fetched_at = keys["directories"], keys["responses"], keys["fetched_at"]

    @classmethod
    def from_dir(cls, directory, location):
        files = {name: _read_json(os.path.join(directory, name)) for name in SNAPSHOT_FILES}
        try:
            return cls(files, _read_json(KINDS_FILE), location)
        except (KeyError, TypeError, ValueError, re.error) as error:
            raise ListsError(f"{directory}: {error!r}") from error

    @classmethod
    def load(cls, bundled_dir=BUNDLED_DIR, user_root=None):
        """The release's lists, or the newest update under user_root when it is at least as new and readable."""
        bundled = _bundled(bundled_dir)
        if not user_root or not os.path.isdir(user_root):
            return bundled
        skipped = []
        for name in sorted(os.listdir(user_root), reverse=True):
            folder = os.path.join(user_root, name)
            if not DATED_DIR.fullmatch(name) or not os.path.isdir(folder):
                continue
            try:
                candidate = cls.from_dir(folder, folder)
            except ListsError as error:
                skipped.append(str(error))
                continue
            if candidate.schema == bundled.schema and candidate.built >= bundled.built:
                candidate.skipped = skipped
                return candidate
            break
        bundled.skipped = skipped
        return bundled

    # names ---------------------------------------------------------------------------------------------------------

    def _describe(self, entry, matched=None):
        kind = self._kinds[entry["kind"]]
        return {"id": entry["id"], "name": entry["name"], "operator": entry.get("operator"),
                "category": kind["category"], "kind": entry["kind"], "kind_label": kind["label"],
                "row": kind.get("row"), "evidence": entry.get("evidence", "listed"), "sources": list(entry["sources"]),
                "matched": matched}

    def _conflict(self, entries):
        """Several names declared at once name none; category and kind stay when they all agree."""
        kinds = {entry["kind"] for entry in entries}
        categories = {self._kinds[kind]["category"] for kind in kinds}
        kind = kinds.pop() if len(kinds) == 1 else None
        return {"id": None, "name": None, "operator": None,
                "category": categories.pop() if len(categories) == 1 else None, "kind": kind,
                "kind_label": self._kinds[kind]["label"] if kind else None,
                "row": self._kinds[kind].get("row") if kind else None, "evidence": "conflict",
                "sources": sorted({s for entry in entries for s in entry["sources"]}), "matched": None,
                "conflict": sorted(entry["id"] for entry in entries)}

    def match_ua(self, ua):
        """The name a User-Agent declares. A match inside a longer one gives way to it (Googlebot-Image over
        Googlebot), and a tool anyone runs (HeadlessChrome, curl) gives way to a named product."""
        if not ua:
            return None
        hits = []
        for entry, patterns in self._matchers:
            spans = [span for span in (p.find(ua) for p in patterns) if span]
            if spans:
                hits.append((max(spans, key=lambda s: s[1] - s[0]), entry))
        hits = [(span, entry) for span, entry in hits if not any(_inside(span, other) for other, _ in hits)]
        specific = [hit for hit in hits if not self._kinds[hit[1]["kind"]].get("generic")]
        hits = specific or hits
        if not hits:
            return None
        if len({entry["id"] for _, entry in hits}) == 1:
            span, entry = hits[0]
            return self._describe(entry, ua[span[0]:span[1]])
        return self._conflict([entry for _, entry in hits])

    def name(self, list_id):
        """What a list id stands for, whichever layer found it (User-Agent, signer, page rule)."""
        entry = self._names.get(list_id)
        return self._describe(entry) if entry else None

    def match_platform(self, platform):
        """The name a page's navigator.platform declares (botscent page.json), or None."""
        return self.name(self._platforms.get(platform or ""))

    def ua_hints(self, ua):
        """Shapes of a malformed or forged User-Agent: weak signals for the reasons, never a name."""
        return [{"id": hint["id"], "name": hint["name"]} for hint, regex in self._hints if regex.search(ua or "")]

    def sources(self):
        return self._sources

    # addresses -----------------------------------------------------------------------------------------------------

    def match_ip(self, value):
        """The first agent or bot range holding the address, and whether it is a relay, a CDN or a cloud."""
        address = _address(value)
        if address is None:
            return None
        number = int(address)
        found = {"range": None, "range_id": None, "range_kind": None, "operator": None, "verifies": [],
                 "cloud": None, "cdn": None, "relay": None}
        for block in self._ranges:
            if not block.contains(address.version, number):
                continue
            if block.kind in PUBLISHED_KINDS and found["range"] is None:
                found.update(range=block.label, range_id=block.id, range_kind=block.kind, operator=block.operator,
                             verifies=list(block.verifies))
            elif block.kind in NETWORK_KINDS and found[block.kind] is None:
                found[block.kind] = block.label
        return found

    def first_range(self, value):
        """(label, kind) of the first range of any kind holding the address: 0.3.3's published_range()."""
        address = _address(value)
        if address is None:
            return None
        number = int(address)
        return next(((b.label, b.kind) for b in self._ranges if b.contains(address.version, number)), None)

    def raw_ranges(self):
        return self._raw_ranges

    # signers -------------------------------------------------------------------------------------------------------

    def signer_hosts(self):
        return sorted(self._signers)

    def signer(self, host):
        """A Web Bot Auth signer host (exact, as botscent compares it) with its name and bundled keys."""
        info = self._signers.get((host or "").lower())
        if not info:
            return None
        named = self.name(info["name"]) or {}
        response = self._responses.get(host.lower()) or {}
        return {"host": host.lower(), "name": info["name"], "display": named.get("name"),
                "operator": named.get("operator"), "category": named.get("category"), "kind": named.get("kind"),
                "directory": info["directory"], "keys": list(self._keys.get(host.lower(), [])),
                "keys_fetched_at": response.get("fetched_at") or self._keys_fetched_at}

    def key_directories(self):
        """{signer host: [Ed25519 JWK]}: what the Web Bot Auth check (S3.2) verifies against."""
        return {host: list(keys) for host, keys in self._keys.items()}

    def directory_response(self, host):
        """The signer's directory response as fetched: status, signature headers and body, or None."""
        return self._responses.get((host or "").lower())

    # age -----------------------------------------------------------------------------------------------------------

    def status(self, max_age_days=None, today=None):
        """How old the lists in use are against the I4 limit (sources.json "update", unless given)."""
        if max_age_days is None:
            max_age_days = update_settings()["max_age_days"]
        today = today or datetime.datetime.now(datetime.timezone.utc).date()
        age = (today - datetime.date.fromisoformat(self.built)).days
        return {"built": self.built, "age_days": age, "max_age_days": max_age_days, "stale": age > max_age_days,
                "location": self.location, "sources": self._sources, "skipped": list(self.skipped)}


@functools.cache
def update_settings():
    """sources.json "update": part of the package, so read once per process."""
    return _read_json(SOURCES_FILE)["update"]


def user_root():
    """<CAKE_HOME>/lists: where `agentcake lists update` puts its dated copies."""
    return os.path.join(paths.home(), update_settings()["user_dir"])


_BUNDLED = {}  # folder -> (signature of its files, the Lists parsed from them)


def _bundled(directory):
    """The snapshot in a release's folder, parsed once per process: parsing is the slow part of reading the lists,
    and every CAKE_HOME (each test's, `agentcake serve`, every command) starts from the same files. Parsed again when
    they change (tools/build_lists.py rewrites them). Each caller gets its own shallow copy, so that load() can set
    `skipped` on it; the parsed tables are shared and never changed."""
    signature = _signature(directory)
    kept = _BUNDLED.get(directory)
    if signature is None or kept is None or kept[0] != signature:
        kept = (signature, Lists.from_dir(directory, "bundled"))  # a missing file raises ListsError here
        _BUNDLED[directory] = kept
    return copy.copy(kept[1])


def _signature(directory):
    """(size, modification time) of each file a snapshot is parsed from, or None when one cannot be read."""
    files = [os.path.join(directory, name) for name in SNAPSHOT_FILES] + [KINDS_FILE]
    try:
        return tuple((stat.st_size, stat.st_mtime_ns) for stat in map(os.stat, files))
    except OSError:
        return None


_CURRENT = {}


def current():
    """The lists in use for this CAKE_HOME, read once per process (reload() after an update)."""
    root = user_root()
    if root not in _CURRENT:
        _CURRENT[root] = Lists.load(BUNDLED_DIR, root)
    return _CURRENT[root]


def reload():
    _CURRENT.clear()
