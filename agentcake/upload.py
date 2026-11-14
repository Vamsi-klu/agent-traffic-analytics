"""One upload from cake.js, checked and read into a Batch (S2.1; docs/collect-format.md, upload format version 1).

decode_body(body, limit) -> the batch's JSON bytes. cake.js gzips its bigger batches and says so with ?z=gzip, but the
public listener does not read query strings, so the body's first two bytes decide (S1.3 wrote this part). A body that
would unzip to more than `limit` bytes is refused: a small gzip body can hold a huge one.

read_batch(data, caps, max_records) -> Batch. The header is checked and cut to the field caps of data/sizes.json: the
visit id `s`, and for a version 1 batch the page view `pv` and the batch number `seq`, the key a batch sent twice is
known by. A batch without `v` comes from cake 0.3.4's script (k, s, u, ua, wd, e, st): it has neither, and is kept
without that check. Each record becomes (time, JSON text, page view) in its stream (`e` rrweb, `r` raw input, `x`
signals), in the order sent; a record that is not an object or has no time in epoch milliseconds is left out and
counted (bad_records). A batch with more records than max_records, or one that cannot be read, raises
Refused(reason, status, records); collect answers it with that status and counts it.

The site key is not checked here: it is a setting, and collect compares it before the records are read.
"""
from __future__ import annotations

import json
import re
import zlib
from collections import namedtuple
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Optional

from agentcake.datafiles import load

GZIP_MAGIC = b"\x1f\x8b"  # every gzip stream starts with these two bytes; JSON never does
GZIP_WBITS = 16 + zlib.MAX_WBITS  # protocol: zlib's window bits for a gzip header and trailer
# protocol: upload format v1's record arrays, the stream each one is kept in, and the time field of its records
RECORD_FIELDS = (("e", "rrweb", "timestamp"), ("r", "raw", "t"), ("x", "env", "t"))
MAX_SAFE_INTEGER = 2 ** 53 - 1  # protocol: the largest integer a JavaScript number (cake.js's seq and times) holds
NOT_ID = re.compile(r"[^A-Za-z0-9]")  # cake.js's ids are hex; anything else is dropped, as cake 0.3.4 did
FORMAT_VERSION = load("data/cakejs.json")["script"]["format_version"]

Record = namedtuple("Record", "ts text page")


class Refused(Exception):
    """An upload collect does not keep: why (a short word, also the refusals row), the HTTP status, its records."""

    def __init__(self, reason, status, records=0):
        super().__init__(reason)
        self.reason, self.status, self.records = reason, status, records


@dataclass
class Batch:
    session: str
    page_view: Optional[str]          # None for a cake 0.3.4 batch
    seq: Optional[int]
    made_ms: Optional[float]          # `t`, when cake.js made the batch
    url: Optional[str]
    user_agent: Optional[str]
    webdriver: bool
    why: Optional[str]
    token: Optional[str]              # `st`, the server-half token
    dropped: Optional[str]            # `dr`, cake.js's own drop counts so far, as compact JSON
    test: bool                        # a self-check visit (`agentcake ping`)
    records: dict = field(default_factory=dict)   # stream -> [Record], in the order sent
    bad_records: int = 0

    def record_count(self):
        return sum(len(records) for records in self.records.values())


def decode_body(body, limit):
    """The JSON bytes of an upload: the body, or what its gzip stream unzips to (at most limit bytes)."""
    if body[:len(GZIP_MAGIC)] != GZIP_MAGIC:
        return body
    inflater = zlib.decompressobj(GZIP_WBITS)
    try:
        text = inflater.decompress(body, limit)
    except zlib.error:
        raise Refused("bad_body", HTTPStatus.BAD_REQUEST) from None
    if inflater.unconsumed_tail:
        raise Refused("too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    return text


def parse(text):
    """The upload's JSON object."""
    try:
        data = json.loads(text)
    except ValueError:  # also a body that is not UTF-8
        raise Refused("bad_body", HTTPStatus.BAD_REQUEST) from None
    if not isinstance(data, dict):
        raise Refused("bad_body", HTTPStatus.BAD_REQUEST)
    return data


def read_batch(data, caps, max_records):
    """The Batch in an upload's JSON object (see the module docstring)."""
    version = data.get("v")
    if version is not None and version != FORMAT_VERSION:
        raise Refused("version", HTTPStatus.BAD_REQUEST)
    session = _id(data.get("s"), caps["session_id"])
    if not session:
        raise Refused("no_session", HTTPStatus.BAD_REQUEST)
    page_view, seq = None, None
    if version is not None:
        page_view, seq = _id(data.get("pv"), caps["page_view"]), data.get("seq")
        if not page_view or not _is_count(seq):
            raise Refused("bad_batch", HTTPStatus.BAD_REQUEST)
    arrays = {name: data.get(key) for key, name, _ in RECORD_FIELDS}
    if any(array is not None and not isinstance(array, list) for array in arrays.values()):
        raise Refused("bad_batch", HTTPStatus.BAD_REQUEST)
    sent = sum(len(array or []) for array in arrays.values())
    if sent > max_records:
        raise Refused("post_limit", HTTPStatus.REQUEST_ENTITY_TOO_LARGE, sent)
    batch = Batch(session=session, page_view=page_view, seq=seq, made_ms=_number(data.get("t")),
                  url=_text(data.get("u"), caps["url"]), user_agent=_text(data.get("ua"), caps["user_agent"]),
                  webdriver=bool(data.get("wd")), why=_text(data.get("why"), caps["batch_why"]),
                  token=data.get("st") if isinstance(data.get("st"), str) else None,
                  dropped=_drop_counts(data.get("dr"), caps["drop_counts"]), test=bool(data.get("test")))
    for _, name, time_field in RECORD_FIELDS:
        kept = [Record(int(record[time_field]), record_text(record), page_view)
                for record in arrays[name] or [] if isinstance(record, dict) and _is_time(record.get(time_field))]
        batch.bad_records += len(arrays[name] or []) - len(kept)
        if kept:
            batch.records[name] = kept
    return batch


def record_text(record):
    """A record as compact JSON text, UTF-8 as sent; a string with a lone surrogate (half of a cut emoji, which
    JSON.stringify writes as an escape) stays escaped, since such text cannot be stored as UTF-8."""
    text = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    if not text.isascii():
        try:
            text.encode("utf-8")
        except UnicodeEncodeError:
            text = json.dumps(record, separators=(",", ":"))
    return text


def _id(value, cap):
    return NOT_ID.sub("", value)[:cap] if isinstance(value, str) else ""


def _text(value, cap):
    return value[:cap] if isinstance(value, str) else None


def _is_count(value):
    return type(value) is int and 0 <= value <= MAX_SAFE_INTEGER


def _is_time(value):
    """A time in epoch milliseconds: a number (not a bool, not NaN or infinite) from 0 up to MAX_SAFE_INTEGER."""
    return type(value) in (int, float) and 0 <= value <= MAX_SAFE_INTEGER


def _number(value):
    return value if _is_time(value) else None


def _drop_counts(value, cap):
    """cake.js's `dr` ({stream or "b": count}) as compact JSON, or None when it is not that or too long."""
    if not isinstance(value, dict) or not all(isinstance(k, str) and _is_count(v) for k, v in value.items()):
        return None
    text = json.dumps(value, separators=(",", ":"))
    return text if len(text) <= cap else None
