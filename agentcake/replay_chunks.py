"""Replay chunk files: $CAKE_HOME/replays/<YYYY-MM-DD>/<HH>.bin, named after the UTC date and hour of writing.

A file is a run of chunks, appended and never changed in place. Each chunk describes itself, so a file can be read,
and the chunks table rebuilt, without the database:

    b"CKC1"                    4 bytes    magic, chunk format 1
    header length              4 bytes    big-endian
    header                     JSON       v, session, stream, t0, t1, n (events), codec, level, raw (bytes), crc32
    payload                    codec      compressed lines, `raw` bytes and that crc32 once decompressed

The payload is JSON Lines, one event per line, oldest first: {"t": <ms>, "e": <the event, byte for byte>}, with
"css": [[position, hash], ...] before "e" when styles.py took stylesheets out of the event, and "p": <page view> after
"t" when the event came from a page of cake.js (the page view id of its upload; two tabs of one visit interleave
in time). A reader that does not know "p" still reads the line. The database's chunks table keeps (file,
byte_offset, byte_length) of each chunk (streams.py).

write_chunk(meta, lines, codec, level, now_ms) compresses lines into a chunk at the end of the hour's file and returns
a ChunkRef (build_chunk() and append_chunk() are its two halves, so the slow compression can run unlocked);
read_chunk(file, offset, length) checks the magic and header at once and gives back the header and an
iterator over the lines, decompressed in blocks of read_block_bytes and checked against the header's size and crc32.
copy_chunk() moves a chunk's bytes unchanged into the current file (reclaim in recompress.py).
"""
import json
import os
import struct
import zlib
from collections import namedtuple

from agentcake import codecs, paths
from agentcake.storage_config import SETTINGS, when

MAGIC = b"CKC1"  # protocol: starts every chunk, chunk format 1
FORMAT = 1  # protocol: the chunk format version written into every header
HEADER_LENGTH = struct.Struct(">I")  # protocol: header length, 4 bytes big-endian
PREFIX = len(MAGIC) + HEADER_LENGTH.size
EVENT_KEY = ',"e":'
PAGE_KEY = "p"  # protocol: chunk format 1's optional page view of an event
NEWLINE = "\n"

ChunkRef = namedtuple("ChunkRef", "file offset length raw_bytes")
Line = namedtuple("Line", "t text css page")  # one payload line, decoded


class ChunkError(ValueError):
    """The bytes at (file, offset, length) are not an intact chunk."""


def replay_dir(cfg=SETTINGS):
    return os.path.join(paths.home(), cfg["replay_dir"])


def file_for(ms):
    """The file chunks written at `ms` go to, relative to replay_dir(), with / separators."""
    return when(ms).strftime("%Y-%m-%d/%H.bin")


def encode_line(ts, text, refs=(), page=None):
    """One payload line (without its newline). text is the event's JSON text, kept byte for byte; page is the page
    view the event was recorded on, left out when None."""
    if NEWLINE in text or "\r" in text:
        raise ValueError("an event's JSON text must be one line")
    view = f',"{PAGE_KEY}":{json.dumps(page)}' if page is not None else ""
    css = f',"css":{json.dumps(refs, separators=(",", ":"))}' if refs else ""
    return f'{{"t":{int(ts)}{view}{css}{EVENT_KEY}{text}}}'


def decode_line(line):
    """Line(t, text, css, page) of one payload line: the time, the event's JSON text, its style references, and its
    page view (None for a line written without one)."""
    cut = line.find(EVENT_KEY)
    if cut < 0 or not line.endswith("}"):
        raise ChunkError("not a replay line")
    head = json.loads(line[:cut] + "}")
    return Line(head["t"], line[cut + len(EVENT_KEY):-1], head.get("css", []), head.get(PAGE_KEY))


def write_chunk(meta, lines, codec, level, now_ms, cfg=SETTINGS):
    """Compress lines (an iterable of str, without newlines) into one chunk at the end of the current hour's file.

    meta gives session, stream, t0, t1 and n. The file is flushed to disk before this returns, so a chunks row that
    points at it is never ahead of the bytes."""
    return append_chunk(*build_chunk(meta, lines, codec, level), now_ms, cfg)


def build_chunk(meta, lines, codec, level):
    """(chunk bytes, raw payload size): the compression half of write_chunk, which needs no lock (recompress.py)."""
    comp = codecs.compressor(codec, level)
    parts, raw, crc = [], 0, 0
    for line in lines:
        piece = (line + NEWLINE).encode("utf-8")
        raw += len(piece)
        crc = zlib.crc32(piece, crc)
        parts.append(comp.compress(piece))
    parts.append(comp.flush())
    header = json.dumps(dict(meta, v=FORMAT, codec=codec, level=level, raw=raw, crc32=crc),
                        separators=(",", ":")).encode()
    return b"".join([MAGIC, HEADER_LENGTH.pack(len(header)), header] + parts), raw


def append_chunk(blob, raw_bytes, now_ms, cfg=SETTINGS):
    """Append a built chunk to the current hour's file (the caller holds store.LOCK)."""
    rel, offset = _append(blob, now_ms, cfg)
    return ChunkRef(rel, offset, len(blob), raw_bytes)


def copy_chunk(rel, offset, length, now_ms, cfg=SETTINGS):
    """Append a stored chunk's bytes, unchanged, to the current hour's file; returns the new (file, offset)."""
    with open(os.path.join(replay_dir(cfg), rel), "rb") as f:
        blob = _read_at(f, offset, length)
    _parse(blob)
    return _append(blob, now_ms, cfg)


def read_chunk(rel, offset, length, cfg=SETTINGS, fileobj=None):
    """(header, iterator over the payload's lines) of the chunk at (rel, offset, length).

    The header is checked now; the payload is decompressed while the iterator is read and checked at its end. Pass an
    open fileobj to read from a file opened earlier (streams.py opens a session's files before it reads them)."""
    if fileobj is None:
        with open(os.path.join(replay_dir(cfg), rel), "rb") as f:
            blob = _read_at(f, offset, length)
    else:
        blob = _read_at(fileobj, offset, length)
    header, payload = _parse(blob)
    return header, _lines(header, payload, cfg["read_block_bytes"])


def _append(blob, now_ms, cfg):
    rel = file_for(now_ms)
    path = os.path.join(replay_dir(cfg), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "ab") as f:
        f.seek(0, os.SEEK_END)
        offset = f.tell()
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    return rel, offset


def _read_at(f, offset, length):
    f.seek(offset)
    blob = f.read(length)
    if len(blob) != length:
        raise ChunkError("the file ends inside this chunk")
    return blob


def _parse(blob):
    if blob[:len(MAGIC)] != MAGIC:
        raise ChunkError("no chunk starts at this offset")
    (size,) = HEADER_LENGTH.unpack(blob[len(MAGIC):PREFIX])
    try:
        header = json.loads(blob[PREFIX:PREFIX + size])
    except ValueError as e:
        raise ChunkError(f"unreadable chunk header: {e}") from e
    if header.get("v") != FORMAT:
        raise ChunkError(f"chunk format {header.get('v')!r}; this cake reads format {FORMAT}")
    return header, blob[PREFIX + size:]


def _lines(header, payload, block):
    """The payload's lines; raises ChunkError at the end when the size or crc32 differ from the header."""
    raw, crc, rest = 0, 0, b""
    try:
        for piece in codecs.iter_decompress(header["codec"], payload, block):
            raw += len(piece)
            crc = zlib.crc32(piece, crc)
            *done, rest = (rest + piece).split(NEWLINE.encode())
            for line in done:
                yield line.decode("utf-8")
    except codecs.CorruptPayload as e:
        raise ChunkError(str(e)) from e
    if rest or raw != header["raw"] or crc != header["crc32"]:
        raise ChunkError("the chunk's payload does not match its header (size or crc32)")
