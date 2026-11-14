"""Replay compression: zstd from the standard library when this Python has it, otherwise zlib.

compression.zstd arrived in Python 3.14. On Python 3.11-3.13 (Debian 12 ships 3.11) ZSTD is None: new chunks are
written with zlib, `agentcake doctor` says so, and a zstd chunk read there raises CodecUnavailable. Every chunk names
its codec in its header (replay_chunks.py), so a reader never guesses.

writer_codec(cfg) is the codec new chunks use; level_for(codec, purpose) the level storage.json gives it for live
writes ("live") or for the night recompression ("archive"); compressor() compresses a chunk in pieces;
iter_decompress() gives a chunk's bytes back in blocks of at most read_block_bytes, so a reader never holds a whole
session's replay in memory.
"""
import zlib

from agentcake.storage_config import SETTINGS

try:
    from compression import zstd as ZSTD
except ImportError:  # Python < 3.14
    ZSTD = None


class CodecUnavailable(RuntimeError):
    """A chunk was written with a codec this Python cannot read."""


class CorruptPayload(ValueError):
    """A chunk's compressed bytes do not decompress."""


def available():
    return ("zstd", "zlib") if ZSTD is not None else ("zlib",)


def writer_codec(cfg=SETTINGS):
    """storage.json's codec when this Python has it, else its fallback."""
    return cfg["codec"] if cfg["codec"] in available() else cfg["fallback_codec"]


def level_for(codec, purpose, cfg=SETTINGS):
    return cfg["levels"][codec][purpose]


def _need(codec):
    if codec == "zstd" and ZSTD is None:
        raise CodecUnavailable("this replay chunk is zstd-compressed; reading it needs Python 3.14+ (compression.zstd)")
    if codec not in ("zstd", "zlib"):
        raise CodecUnavailable(f"unknown replay codec {codec!r}")


def compressor(codec, level):
    """An object with compress(bytes) -> bytes and flush() -> bytes that ends the compressed stream."""
    _need(codec)
    return ZSTD.ZstdCompressor(level=level) if codec == "zstd" else zlib.compressobj(level)


def iter_decompress(codec, blob, block):
    """The decompressed bytes of one complete compressed stream, in pieces of at most `block` bytes."""
    _need(codec)
    try:
        yield from (_zstd_blocks(blob, block) if codec == "zstd" else _zlib_blocks(blob, block))
    except (zlib.error, getattr(ZSTD, "ZstdError", zlib.error)) as e:
        raise CorruptPayload(f"{codec}: {e}") from e


def _zstd_blocks(blob, block):
    d = ZSTD.ZstdDecompressor()
    yield d.decompress(blob, block)
    while not d.eof:
        if d.needs_input:
            raise CorruptPayload("zstd: the chunk ends before its frame does")
        yield d.decompress(b"", block)
    if d.unused_data:
        raise CorruptPayload("zstd: bytes after the end of the frame")


def _zlib_blocks(blob, block):
    d = zlib.decompressobj()
    data = blob
    while data and not d.eof:
        yield d.decompress(data, block)
        data = d.unconsumed_tail
    yield d.flush()
    if not d.eof or d.unused_data:
        raise CorruptPayload("zlib: the chunk is cut short or has bytes after its end")
