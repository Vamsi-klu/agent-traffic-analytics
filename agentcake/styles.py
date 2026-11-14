"""Each stylesheet stored once (S2.2): the CSS rrweb copies into its snapshots, kept once per hash.

rrweb inlines a page's stylesheets into every full snapshot (`_cssText` of a <link> or <style>, and the text of a
<style> marked isStyle), which is most of a snapshot (note 5: snapshots are 56-100% of a replay), and every visit to
a site sends the same text again. Measured on note 5's public-site recordings: 43% less disk over three visits per
site, 87% for a repeat visit of github.com (S2.2's measurement).

cut_styles(con, text, now_ms) works on an event's JSON text, never re-serialising it: each stylesheet string of at
least css_min_length characters is found as it is written in the text, its inside is stored in the styles table
(compressed, keyed by a hash of those exact characters) and left out of the line, which records [position, hash];
restore() puts the same characters back at the same positions, so an event is read back byte for byte. A text that
cannot be found as written (an unusual JSON encoder) simply stays in the line. Cutting happens when a 10-second
chunk is sealed (streams.py), for the streams in css_dedup_streams. gc_styles() deletes stylesheets no chunk
refers to any more.
"""
import hashlib
import json

from agentcake import codecs
from agentcake.storage_config import SETTINGS

MARKERS = ('"_cssText"', '"isStyle"')


def cut_styles(con, text, now_ms, cfg=SETTINGS):
    """(text with its long stylesheets left out, [[position, hash], ...] in position order)."""
    if not any(marker in text for marker in MARKERS):
        return text, []
    try:
        event = json.loads(text)
    except ValueError:
        return text, []
    pieces, refs, cursor, removed = [], [], 0, 0
    for value in _style_values(event):
        if len(value) < cfg["css_min_length"]:
            continue
        found = _find_string(text, value, cursor)
        if found is None:
            continue
        inside_from, inside_to = found
        pieces.append(text[cursor:inside_from])
        refs.append([inside_from - removed, _keep(con, text[inside_from:inside_to], now_ms, cfg)])
        removed += inside_to - inside_from
        cursor = inside_to
    pieces.append(text[cursor:])
    return "".join(pieces), refs


def restore(text, refs, lookup):
    """The event text again: lookup(hash) gives each stylesheet's characters, put back at their positions."""
    if not refs:
        return text
    pieces, cursor = [], 0
    for position, digest in refs:
        pieces += [text[cursor:position], lookup(digest)]
        cursor = position
    pieces.append(text[cursor:])
    return "".join(pieces)


class Lookup:
    """Stylesheet characters by hash, decompressed once per read. rows: {hash: (body, codec)}, what fetch() gave
    inside the read's snapshot."""

    def __init__(self, rows, cfg=SETTINGS):
        self.rows, self.block, self.cache = rows, cfg["read_block_bytes"], {}

    def __call__(self, digest):
        if digest not in self.cache:
            row = self.rows.get(digest)
            if row is None:
                raise KeyError(f"stylesheet {digest} is missing from the styles table")
            body, codec = row
            self.cache[digest] = b"".join(codecs.iter_decompress(codec, body, self.block)).decode("utf-8")
        return self.cache[digest]


def fetch(con, hashes):
    """{hash: (body, codec)} of the given stylesheets, for a Lookup taken inside a read snapshot."""
    rows = {}
    for digest in hashes:
        row = con.execute("SELECT body, codec FROM styles WHERE hash=?", (digest,)).fetchone()
        if row is not None:
            rows[digest] = row
    return rows


def gc_styles(con):
    """Delete the stylesheets no chunk refers to; returns how many. Caller holds store.LOCK."""
    used = set()
    for (names,) in con.execute("SELECT styles FROM chunks WHERE styles IS NOT NULL"):
        used.update(names.split())
    dead = [(digest,) for (digest,) in con.execute("SELECT hash FROM styles") if digest not in used]
    con.executemany("DELETE FROM styles WHERE hash=?", dead)
    return len(dead)


def _style_values(node):
    """Stylesheet strings in an rrweb event, in the order they are written in its JSON text."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and (key == "_cssText" or (key == "textContent" and node.get("isStyle"))):
                yield value
            elif isinstance(value, (dict, list)):
                yield from _style_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _style_values(value)


def _find_string(text, value, cursor):
    """(start, end) of the inside of the JSON string `value` as written in text at or after cursor, or None."""
    best = None
    for written in {json.dumps(value), json.dumps(value, ensure_ascii=False)}:
        at = text.find(written, cursor)
        if at >= 0 and (best is None or at < best[0]):
            best = (at, written)
    if best is None:
        return None
    at, written = best
    return at + len('"'), at + len(written) - len('"')


def _keep(con, inside, now_ms, cfg):
    data = inside.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()[:cfg["css_hash_chars"]]
    if con.execute("SELECT 1 FROM styles WHERE hash=?", (digest,)).fetchone() is None:
        codec = codecs.writer_codec(cfg)
        comp = codecs.compressor(codec, codecs.level_for(codec, "live", cfg))
        con.execute("INSERT INTO styles(hash, body, codec, raw_bytes, created_ms) VALUES(?,?,?,?,?)",
                    (digest, comp.compress(data) + comp.flush(), codec, len(data), now_ms))
    return digest
