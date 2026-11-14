"""Replay chunk files and their compression (S2.2): agentcake/replay_chunks.py and agentcake/codecs.py.

    python3 -I -m unittest tests.test_replay_chunks -v      (from the cake folder)

A chunk survives compression byte for byte with either codec; its header names the codec it was written with; a
Python without compression.zstd writes zlib chunks and can read them, and says clearly that it cannot read a zstd one;
chunks are appended to replays/<UTC date>/<UTC hour>.bin and found again by (file, offset, length).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import codecs, replay_chunks  # noqa: E402
from agentcake.storage_config import SETTINGS  # noqa: E402

# 2026-11-12 21:05:00 UTC, in epoch milliseconds
WRITE_MS = 1794517500000


def fresh_home():
    home = tempfile.mkdtemp(prefix="cake-test-")
    os.environ["CAKE_HOME"] = home
    return home


def sample_lines(n=300):
    """rrweb-like lines: a snapshot with CSS and non-ASCII text, then many small mouse events."""
    snap = {"type": 2, "data": {"node": {"type": 0, "childNodes": [{"type": 2, "tagName": "style", "attributes": {
        "_cssText": "body{font-family:system-ui}" * 40}, "childNodes": [{"type": 3, "textContent": "Café ☕  "}]}]}},
        "timestamp": WRITE_MS}
    lines = [replay_chunks.encode_line(WRITE_MS, json.dumps(snap))]
    for i in range(1, n):
        ev = {"type": 3, "data": {"source": 1, "positions": [{"x": i, "y": 2 * i, "id": 7, "timeOffset": -i}]},
              "timestamp": WRITE_MS + i}
        lines.append(replay_chunks.encode_line(WRITE_MS + i, json.dumps(ev, separators=(",", ":"))))
    return lines


def meta(n):
    return {"session": "s1", "stream": "rrweb", "t0": WRITE_MS, "t1": WRITE_MS + n - 1, "n": n}


class Lines(unittest.TestCase):
    def test_a_line_gives_back_its_time_text_and_style_references_exactly(self):
        text = '{"type": 3, "data": {"text": "\\u00e9\\n\\"q\\""}, "timestamp": 5}'
        self.assertEqual(replay_chunks.decode_line(replay_chunks.encode_line(5, text)), (5, text, [], None))
        refs = [[12, "ab" * 16], [40, "cd" * 16]]
        self.assertEqual(replay_chunks.decode_line(replay_chunks.encode_line(-7, text, refs)), (-7, text, refs, None))

    def test_a_line_keeps_the_page_view_its_event_was_recorded_on(self):
        text = '{"t":5.5,"ty":"click"}'
        line = replay_chunks.decode_line(replay_chunks.encode_line(5, text, [[2, "ab"]], "c2a8f0"))
        self.assertEqual((line.t, line.text, line.css, line.page), (5, text, [[2, "ab"]], "c2a8f0"))

    def test_every_line_is_json(self):
        line = replay_chunks.encode_line(9, '{"a": [1, 2]}', [[3, "ff"]])
        self.assertEqual(json.loads(line), {"t": 9, "css": [[3, "ff"]], "e": {"a": [1, 2]}})
        with_page = replay_chunks.encode_line(9, '{"a": 1}', page="pv7")
        self.assertEqual(json.loads(with_page), {"t": 9, "p": "pv7", "e": {"a": 1}})


class RoundTrip(unittest.TestCase):
    def setUp(self):
        fresh_home()

    def roundtrip(self, codec):
        lines = sample_lines()
        level = codecs.level_for(codec, "live")
        ref = replay_chunks.write_chunk(meta(len(lines)), lines, codec, level, WRITE_MS)
        header, got = replay_chunks.read_chunk(ref.file, ref.offset, ref.length)
        self.assertEqual(list(got), lines)
        self.assertEqual(header["codec"], codec)
        self.assertEqual(header["level"], level)
        self.assertEqual(header["raw"], len(("\n".join(lines) + "\n").encode("utf-8")))
        self.assertEqual(ref.raw_bytes, header["raw"])
        self.assertLess(ref.length, header["raw"], "compressed")
        return ref

    def test_zstd_chunk_decompresses_byte_for_byte(self):
        if codecs.ZSTD is None:
            self.skipTest("this Python has no compression.zstd")
        self.roundtrip("zstd")

    def test_zlib_chunk_decompresses_byte_for_byte(self):
        self.roundtrip("zlib")

    def test_decompression_is_streamed_in_blocks_and_lines_survive_block_edges(self):
        lines = sample_lines(2000)
        ref = replay_chunks.write_chunk(meta(len(lines)), lines, "zlib", codecs.level_for("zlib", "live"), WRITE_MS)
        small = dict(SETTINGS, read_block_bytes=97)  # far smaller than one line: every line crosses block edges
        _, got = replay_chunks.read_chunk(ref.file, ref.offset, ref.length, cfg=small)
        self.assertEqual(list(got), lines)

    def test_chunks_of_one_hour_share_a_file_at_growing_offsets(self):
        a = self.roundtrip("zlib")
        b = replay_chunks.write_chunk(meta(1), ["x"], "zlib", codecs.level_for("zlib", "live"), WRITE_MS + 60_000)
        self.assertEqual(a.file, "2026-11-12/21.bin")
        self.assertEqual(b.file, a.file)
        self.assertEqual(b.offset, a.offset + a.length)
        self.assertTrue(os.path.isfile(os.path.join(replay_chunks.replay_dir(), "2026-11-12", "21.bin")))
        c = replay_chunks.write_chunk(meta(1), ["x"], "zlib", codecs.level_for("zlib", "live"), WRITE_MS + 3600_000)
        self.assertEqual(c.file, "2026-11-12/22.bin", "the next hour starts a new file")

    def test_a_damaged_chunk_is_refused(self):
        ref = self.roundtrip("zlib")
        path = os.path.join(replay_chunks.replay_dir(), ref.file)
        with open(path, "r+b") as f:
            f.seek(ref.offset + ref.length - 3)
            f.write(b"\x00\x00\x00")
        with self.assertRaises(replay_chunks.ChunkError):
            list(replay_chunks.read_chunk(ref.file, ref.offset, ref.length)[1])
        with self.assertRaises(replay_chunks.ChunkError):
            replay_chunks.read_chunk(ref.file, ref.offset + 1, ref.length - 1)


class WithoutZstd(unittest.TestCase):
    """Python 3.11-3.13 (Debian 12's 3.11): no compression.zstd, so zlib."""

    def setUp(self):
        fresh_home()

    def test_new_chunks_use_zlib_and_say_so_in_their_header(self):
        with mock.patch.object(codecs, "ZSTD", None):
            self.assertEqual(codecs.writer_codec(), "zlib")
            lines = sample_lines()
            codec = codecs.writer_codec()
            ref = replay_chunks.write_chunk(meta(len(lines)), lines, codec, codecs.level_for(codec, "live"), WRITE_MS)
            header, got = replay_chunks.read_chunk(ref.file, ref.offset, ref.length)
            self.assertEqual(header["codec"], "zlib")
            self.assertEqual(list(got), lines)

    def test_a_zstd_chunk_says_it_needs_compression_zstd(self):
        if codecs.ZSTD is None:
            self.skipTest("this Python has no compression.zstd")
        lines = sample_lines(10)
        ref = replay_chunks.write_chunk(meta(len(lines)), lines, "zstd", codecs.level_for("zstd", "live"), WRITE_MS)
        with mock.patch.object(codecs, "ZSTD", None):
            with self.assertRaises(codecs.CodecUnavailable) as caught:
                list(replay_chunks.read_chunk(ref.file, ref.offset, ref.length)[1])
            self.assertIn("compression.zstd", str(caught.exception))

    def test_the_preferred_codec_comes_from_the_settings(self):
        self.assertEqual(codecs.writer_codec(dict(SETTINGS, codec="zlib")), "zlib")
        if codecs.ZSTD is not None:
            self.assertEqual(codecs.writer_codec(), "zstd")


if __name__ == "__main__":
    unittest.main()
