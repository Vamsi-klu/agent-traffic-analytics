"""Where a privacy scan reads from: every file of a data folder, as the text it holds.

Folder(root, data).texts() walks root (or reads one file) and yields (location, text):

- each cell of each table of each SQLite database (cake.db, backups/...), opened read-only; a compressed BLOB (the
  styles table keeps stylesheets zstd- or zlib-compressed) is decompressed first;
- the header and each line of every replay chunk, found by its magic and decompressed (zstd or zlib, as its header
  says) without asking the database where chunks are, so that a dead chunk a reclaim has not removed yet is read too;
  zeros (what `agentcake delete` leaves where a chunk was) are passed over;
- each line of every other file (logs, JSON exports, config.json), a gzip- or zstd-compressed file decompressed first.

Locations are relative to root and hold no content: "<file> <table>.<column> row <n>", "<file> chunk@<offset> line
<n>", "<file> line <n>". counts says how much was read; skipped lists what rules.json says to leave out, with why;
unreadable lists what could not be read (a chunk in a codec this Python lacks, bytes that are not a chunk), which a
scan must not pass as clean.
"""
import gzip
import json
import mmap
import os
import sqlite3
import struct
import urllib.parse
import zlib
from collections import Counter

from agentcake import codecs, replay_chunks
from agentcake.storage_config import SETTINGS

SQLITE_MAGIC = b"SQLite format 3\x00"  # protocol: the first bytes of every SQLite 3 database file
GZIP_MAGIC = b"\x1f\x8b"  # protocol: RFC 1952
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"  # protocol: RFC 8878, a zstd frame
ZLIB_METHOD = 0x78  # protocol: RFC 1950, deflate with a 32 KiB window: the first byte of every zlib stream cake writes
ZLIB_CHECK = 31  # protocol: RFC 1950, the first two bytes read as a number are a multiple of 31
ZSTD_ERROR = getattr(codecs.ZSTD, "ZstdError", zlib.error)
HEAD_BYTES = len(SQLITE_MAGIC)
NEWLINE = b"\n"


class Truncated(ValueError):
    """A compressed stream ends before it is complete."""


class Folder:
    def __init__(self, root, data, name=None):
        self.root, self.data, self.name = os.path.abspath(root), data, name
        self.block = SETTINGS["read_block_bytes"]
        self.counts, self.skipped, self.unreadable = Counter(), [], []

    def texts(self):
        if os.path.isfile(self.root):  # one file given on the command line
            yield from self._file(self.root, self.name or os.path.basename(self.root))
            return
        for folder, dirs, names in os.walk(self.root):
            dirs.sort()
            for name in list(dirs):
                rel = self._rel(os.path.join(folder, name))
                if rel in self.data["skip_folders"]:
                    self.skipped.append((rel + "/", self.data["skip_folders"][rel]))
                    dirs.remove(name)
            for name in sorted(names):
                path = os.path.join(folder, name)
                why = self._skip_why(name)
                if why:
                    self.skipped.append((self._rel(path), why))
                elif os.path.isfile(path) and not os.path.islink(path):
                    yield from self._file(path, self._rel(path))

    def _rel(self, path):
        rel = os.path.relpath(path, self.root).replace(os.sep, "/")
        return f"{self.name}/{rel}" if self.name else rel

    def _skip_why(self, name):
        if name in self.data["skip_files"]:
            return self.data["skip_files"][name]
        return next((why for suffix, why in self.data["skip_suffixes"].items() if name.endswith(suffix)), None)

    def _file(self, path, rel):
        with open(path, "rb") as f:
            head = f.read(HEAD_BYTES)
        in_replays = self.name is None and rel.startswith(SETTINGS["replay_dir"] + "/") and rel.endswith(".bin")
        if head.startswith(SQLITE_MAGIC):
            yield from self._database(path, rel)
        elif head.startswith(replay_chunks.MAGIC) or in_replays:  # a chunk file can start with a wiped chunk's zeros
            yield from self._chunks(path, rel)
        else:
            yield from self._lines(path, rel, head)

    # ------------------------------------------------------------------ databases
    def _database(self, path, rel):
        self.counts["databases"] += 1
        con = sqlite3.connect("file:%s?mode=ro" % urllib.parse.quote(path), uri=True)
        try:
            for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
                self.counts["tables"] += 1
                yield from self._table(con, table, rel)
        finally:
            con.close()

    def _table(self, con, table, rel):
        quoted = '"%s"' % table.replace('"', '""')
        columns = [row[1] for row in con.execute(f"PRAGMA table_info({quoted})")]
        try:
            rows, has_rowid = con.execute(f"SELECT rowid, * FROM {quoted}"), True
        except sqlite3.OperationalError:  # a WITHOUT ROWID table: rows are numbered in the order they are read
            rows, has_rowid = con.execute(f"SELECT * FROM {quoted}"), False
        for number, row in enumerate(rows, 1):
            if has_rowid:
                number, row = row[0], row[1:]
            for column, value in zip(columns, row):
                if value is not None:
                    self.counts["cells"] += 1
                    yield f"{rel} {table}.{column} row {number}", _cell_text(value)

    # ------------------------------------------------------------------ replay chunks
    def _chunks(self, path, rel):
        self.counts["chunk files"] += 1
        size = os.path.getsize(path)
        if not size:
            return
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
            at = 0
            while at < size:
                start = data.find(replay_chunks.MAGIC, at)
                end = size if start < 0 else start
                if data[at:end].strip(b"\x00"):
                    self.unreadable.append((f"{rel} @{at}", f"{end - at} bytes that are not a chunk"))
                if start < 0:
                    break
                at = yield from self._chunk(data, start, rel)

    def _chunk(self, data, start, rel):
        """Yield one chunk's header and lines; return where the next chunk may start."""
        header, header_end = _header(data, start)
        where = f"{rel} chunk@{start}"
        if header is None:  # the magic by chance, or a damaged chunk: the bytes up to the next magic are reported
            return start + 1
        codec = header.get("codec")
        if codec not in codecs.available():
            self.unreadable.append((where, f"codec {codec!r}: this Python cannot read it"))
            return _next_magic(data, header_end)
        self.counts["chunks"] += 1
        yield f"{where} header", json.dumps(header)
        stream = _Inflate(data, header_end, codec, self.block)
        try:
            for number, line in enumerate(_split_lines(stream.pieces()), 1):
                self.counts["chunk lines"] += 1
                yield f"{where} line {number}", line.decode("utf-8", "replace")
        except (Truncated, zlib.error, ZSTD_ERROR) as e:
            self.unreadable.append((where, f"its payload does not decompress ({e})"))
            return _next_magic(data, header_end)
        return stream.end

    # ------------------------------------------------------------------ other files
    def _lines(self, path, rel, head):
        self.counts["files"] += 1
        if head.startswith(ZSTD_MAGIC) and codecs.ZSTD is None:
            self.unreadable.append((rel, "zstd-compressed: this Python cannot read it"))
            return
        opener = gzip.open if head.startswith(GZIP_MAGIC) else codecs.ZSTD.open if head.startswith(ZSTD_MAGIC) else open
        try:
            with opener(path, "rb") as f:
                for number, line in enumerate(f, 1):
                    self.counts["lines"] += 1
                    yield f"{rel} line {number}", line.decode("utf-8", "replace")
        except (OSError, EOFError, ZSTD_ERROR) as e:  # a compressed file that is cut short or damaged
            self.unreadable.append((rel, f"does not decompress ({e})"))


class _Inflate:
    """The decompressed pieces of the compressed stream that starts at `start` in data, read block by block; `end` is
    where the stream ended (where the next chunk can start), known once pieces() is exhausted."""

    def __init__(self, data, start, codec, block):
        self.data, self.start, self.codec, self.block, self.end = data, start, codec, block, None

    def pieces(self):
        return self._zstd() if self.codec == "zstd" else self._zlib()

    def _next_block(self, fed):
        piece = self.data[fed:fed + self.block]
        if not piece:
            raise Truncated("the file ends before the stream does")
        return piece

    def _zstd(self):
        stream, fed = codecs.ZSTD.ZstdDecompressor(), self.start
        while not stream.eof:
            if stream.needs_input:
                piece = self._next_block(fed)
                fed += len(piece)
                out = stream.decompress(piece, self.block)
            else:
                out = stream.decompress(b"", self.block)
            if out:
                yield out
        self.end = fed - len(stream.unused_data)

    def _zlib(self):
        stream, fed, pending = zlib.decompressobj(), self.start, b""
        while not stream.eof:
            if not pending:
                pending = self._next_block(fed)
                fed += len(pending)
            out = stream.decompress(pending, self.block)
            pending = stream.unconsumed_tail
            if out:
                yield out
        self.end = fed - len(stream.unused_data) - len(pending)


def _header(data, start):
    """(header dict, where its payload starts) of the chunk at start, or (None, None)."""
    try:
        (size,) = replay_chunks.HEADER_LENGTH.unpack_from(data, start + len(replay_chunks.MAGIC))
        end = start + replay_chunks.PREFIX + size
        header = json.loads(data[start + replay_chunks.PREFIX:end])
    except (struct.error, ValueError):
        return None, None
    return (header, end) if isinstance(header, dict) else (None, None)


def _next_magic(data, after):
    found = data.find(replay_chunks.MAGIC, after)
    return found if found >= 0 else len(data)


def _split_lines(pieces):
    rest = b""
    for piece in pieces:
        *lines, rest = (rest + piece).split(NEWLINE)
        yield from lines
    if rest:
        yield rest


def _cell_text(value):
    """A cell as text: a compressed BLOB decompressed, other bytes as UTF-8, anything else as str()."""
    if not isinstance(value, bytes):
        return str(value)
    try:
        if value.startswith(ZSTD_MAGIC) and codecs.ZSTD is not None:
            value = codecs.ZSTD.decompress(value)
        elif value.startswith(GZIP_MAGIC):
            value = gzip.decompress(value)
        elif len(value) > 1 and value[0] == ZLIB_METHOD and int.from_bytes(value[:2], "big") % ZLIB_CHECK == 0:
            value = zlib.decompress(value)
    except (zlib.error, OSError, EOFError, ZSTD_ERROR):
        pass  # not compressed after all: read as it is
    return value.decode("utf-8", "replace")
