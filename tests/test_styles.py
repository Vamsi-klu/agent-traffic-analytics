"""Each stylesheet stored once: agentcake/styles.py, through agentcake/streams.py.

    python3 -I -m unittest discover -s tests -p test_styles.py -v      (from the cake folder)

rrweb copies a page's CSS into every full snapshot; cake keeps each such text once, by hash, and gives the events
back byte for byte. Small styles, other streams and a switched-off setting leave the text where it is.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import replay_chunks, store, streams, styles  # noqa: E402
from agentcake.storage_config import SETTINGS  # noqa: E402

BASE = 1794517500000
LATER = BASE + 120_000
CSS = ".nav{color:#123}\n.btn::after{content:\"\\u2192 → \\\\\"}\t/* é */ " * 30  # quotes, escapes, non-ASCII
STYLE_TEXT = "h1{margin:0 auto;font:600 2rem/1.2 serif}" * 20


def fresh_db():
    os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
    return store.db()


def snapshot(ts, css=CSS, ascii_only=True):
    node = {"type": 0, "childNodes": [
        {"type": 2, "tagName": "link", "attributes": {"rel": "stylesheet", "_cssText": css}, "childNodes": []},
        {"type": 2, "tagName": "style", "attributes": {}, "childNodes": [
            {"type": 3, "textContent": STYLE_TEXT, "isStyle": True, "id": 9}]},
        {"type": 2, "tagName": "p", "attributes": {"title": "small"}, "childNodes": [
            {"type": 3, "textContent": "Hello", "id": 10}]}]}
    return json.dumps({"type": 2, "data": {"node": node, "initialOffset": {"top": 0, "left": 0}}, "timestamp": ts},
                      ensure_ascii=ascii_only)


def stored_lines(con, sid):
    return [line for line in streams.stored_lines(con, sid, "rrweb")]


class Dedup(unittest.TestCase):
    def setUp(self):
        self.con = fresh_db()
        self.addCleanup(self.con.close)

    def put(self, sid, items, stream="rrweb", cfg=SETTINGS):
        streams.append(self.con, sid, stream, items, BASE, cfg=cfg)
        streams.seal(self.con, LATER, force=True, cfg=cfg)
        self.con.commit()

    def read(self, sid, stream="rrweb"):
        return [t for _, _, t in streams.read_events(self.con, sid, [stream])]

    def test_stylesheets_are_taken_out_and_put_back_byte_for_byte(self):
        for ascii_only in (True, False):
            sid = f"s-{ascii_only}"
            events = [(BASE, snapshot(BASE, ascii_only=ascii_only)), (BASE + 5, '{"type":3,"data":{"source":1}}')]
            self.put(sid, events)
            self.assertEqual(self.read(sid), [t for _, t in events])
            (ts, text, refs), _ = stored_lines(self.con, sid)
            self.assertEqual(len(refs), 2, "the <link> CSS and the <style> text")
            self.assertNotIn("serif", text)
            self.assertIn('"title": "small"', text, "everything else stays in the line")

    def test_a_stylesheet_is_stored_once_for_every_visit_that_sends_it(self):
        for n in range(4):
            self.put(f"visit{n}", [(BASE + n, snapshot(BASE + n))])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM styles").fetchone()[0], 2)
        for n in range(4):
            (_, text, refs), = stored_lines(self.con, f"visit{n}")
            self.assertEqual(len(refs), 2, "every visit's chunk holds only references")
            self.assertNotIn(".nav{", text)
            self.assertEqual(self.read(f"visit{n}"), [snapshot(BASE + n)])

    def test_small_styles_other_streams_and_the_off_switch_keep_text_inline(self):
        small = snapshot(BASE, css="a{b:c}")
        self.put("small", [(BASE, small)])
        self.assertEqual(len(stored_lines(self.con, "small")[0][2]), 1, "only the long <style> text is taken out")
        self.put("raw", [(BASE, snapshot(BASE))], stream="raw")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM chunks c WHERE c.stream='raw' AND styles IS NOT NULL").fetchone()[0], 0)
        self.put("off", [(BASE, snapshot(BASE))], cfg=dict(SETTINGS, css_dedup=False))
        self.assertEqual(stored_lines(self.con, "off")[0][2], [])
        self.assertEqual(self.read("off"), [snapshot(BASE)])

    def test_text_that_only_looks_like_a_stylesheet_is_left_alone(self):
        tricky = json.dumps({"type": 3, "data": {"note": "_cssText isStyle", "adds": []}, "timestamp": BASE})
        self.put("tricky", [(BASE, tricky)])
        self.assertEqual(self.read("tricky"), [tricky])
        self.assertEqual(stored_lines(self.con, "tricky")[0][2], [])

    def test_styles_no_chunk_uses_any_more_are_deleted(self):
        self.put("a", [(BASE, snapshot(BASE))])
        self.put("b", [(BASE, snapshot(BASE, css=CSS + "/* b */"))])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM styles").fetchone()[0], 3)
        streams.drop_replay(self.con, "b")
        self.assertEqual(styles.gc_styles(self.con), 1, "b's own stylesheet; the shared <style> text stays")
        self.con.commit()
        self.assertEqual(self.read("a"), [snapshot(BASE)])

    def test_the_chunk_file_does_not_hold_the_stylesheet(self):
        self.put("one", [(BASE, snapshot(BASE))])
        f, off, n = self.con.execute("SELECT file, byte_offset, byte_length FROM chunks").fetchone()
        _, lines = replay_chunks.read_chunk(f, off, n)
        self.assertNotIn("serif", "".join(lines))


if __name__ == "__main__":
    unittest.main()
