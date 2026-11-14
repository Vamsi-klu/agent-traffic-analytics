"""Reading one upload from cake.js (S2.1): agentcake/upload.py, upload format version 1 (docs/collect-format.md).

    python3 -I -m unittest discover -s tests -p test_upload.py -v      (from the Agent Cake folder)

A gzip body is unzipped within its limit; a version 1 batch must carry its dedup key (s, pv, seq); a cake 0.3.4 batch
has none and is still read; records keep their order, their page view and their content; a record without a usable
time is left out and counted; a batch with too many records is refused before anything is read.
"""
import gzip
import json
import os
import sys
import unittest
from http import HTTPStatus

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import upload  # noqa: E402
from agentcake.datafiles import sizes  # noqa: E402

CAPS = sizes()["max_chars"]
T0 = 1794518371300
PV = "c2a8f0e1d2c3b4a5968778695a4b3c2d"
SID = "5b0e6c2f0d8a4a61b7f4c0b1e2d3a4f5"


def v1(**fields):
    """A version 1 batch like the example in docs/collect-format.md."""
    batch = {"v": 1, "k": "ck_test", "s": SID, "pv": PV, "seq": 0, "t": T0 + 0.5, "u": "https://shop.example.com/demo",
             "why": "snapshot", "ua": "Mozilla/5.0", "wd": False,
             "e": [{"type": 4, "data": {"href": "https://shop.example.com/demo", "width": 1280, "height": 900},
                    "timestamp": T0 + 1}],
             "r": [{"t": T0 + 2.4, "ty": "geo", "hf": 1, "vs": 1, "why": "load", "g": [1280, 900, 1280, 987]}],
             "x": [{"t": T0 + 0.1, "ty": "page", "n": 1, "nav": "navigate", "t0": T0 - 288.2}]}
    batch.update(fields)
    return batch


def read(batch, max_records=20000):
    return upload.read_batch(batch, CAPS, max_records)


def refusal(fn, *args):
    with unittest.TestCase().assertRaises(upload.Refused) as caught:
        fn(*args)
    return caught.exception.reason, caught.exception.status, caught.exception.records


class Body(unittest.TestCase):
    def test_a_plain_body_is_read_as_it_is(self):
        self.assertEqual(upload.decode_body(b'{"a":1}', 100), b'{"a":1}')

    def test_a_gzip_body_is_unzipped_by_its_first_bytes(self):
        text = json.dumps(v1()).encode()
        self.assertEqual(upload.decode_body(gzip.compress(text), len(text)), text)

    def test_a_gzip_body_that_unzips_past_the_limit_is_refused(self):
        bomb = gzip.compress(b" " * 100_000)  # about 100 bytes on the wire
        self.assertEqual(refusal(upload.decode_body, bomb, 99_999)[:2], ("too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE))

    def test_a_broken_gzip_stream_or_text_that_is_not_json_is_a_bad_body(self):
        self.assertEqual(refusal(upload.decode_body, b"\x1f\x8bnot gzip", 100)[0], "bad_body")
        for text in (b"not json", b"[1, 2]", b'"text"', b"\xff\xfe"):
            self.assertEqual(refusal(upload.parse, text)[:2], ("bad_body", HTTPStatus.BAD_REQUEST), text)


class Header(unittest.TestCase):
    def test_a_version_1_batch_gives_its_key_and_header(self):
        batch = read(v1(seq=7, st="c1.e30.mac", dr={"e": 2, "b": 1}))
        self.assertEqual((batch.session, batch.page_view, batch.seq), (SID, PV, 7))
        self.assertEqual((batch.made_ms, batch.url, batch.why, batch.token), (T0 + 0.5, "https://shop.example.com/demo",
                                                                              "snapshot", "c1.e30.mac"))
        self.assertEqual(json.loads(batch.dropped), {"e": 2, "b": 1})
        self.assertFalse(batch.webdriver)

    def test_a_version_1_batch_without_its_page_view_or_number_is_refused(self):
        for broken in ({"pv": None}, {"pv": "!!"}, {"seq": None}, {"seq": -1}, {"seq": True}, {"seq": 1.5},
                       {"seq": 2 ** 60}):
            self.assertEqual(refusal(read, v1(**broken))[:2], ("bad_batch", HTTPStatus.BAD_REQUEST), broken)

    def test_a_cake_034_batch_has_no_key_and_is_still_read(self):
        batch = read({"k": "ck_test", "s": "sessA", "u": "https://tartini.ai/", "ua": "Mozilla/5.0", "wd": True,
                      "e": [{"type": 4, "timestamp": T0, "data": {}}], "st": "c1.x.y"})
        self.assertEqual((batch.session, batch.page_view, batch.seq), ("sessA", None, None))
        self.assertEqual([r.page for r in batch.records["rrweb"]], [None])
        self.assertTrue(batch.webdriver)

    def test_an_unknown_format_version_is_refused(self):
        self.assertEqual(refusal(read, v1(v=2))[0], "version")

    def test_the_visit_id_keeps_only_letters_and_digits_and_must_be_there(self):
        self.assertEqual(read(v1(s="ab-12/cd")).session, "ab12cd")
        for missing in (None, "", "---", 42):
            self.assertEqual(refusal(read, v1(s=missing))[0], "no_session", missing)

    def test_fields_are_cut_to_their_caps_and_wrong_types_dropped(self):
        batch = read(v1(u="https://x.example/" + "a" * 2000, ua=7, why=["timer"], dr={"e": "many"}))
        self.assertEqual(len(batch.url), CAPS["url"])
        self.assertEqual((batch.user_agent, batch.why, batch.dropped), (None, None, None))
        self.assertEqual(len(read(v1(s="f" * 100)).session), CAPS["session_id"])


class Records(unittest.TestCase):
    def test_records_keep_their_stream_order_page_view_and_content(self):
        sent = v1(e=[{"type": 3, "timestamp": T0 + i, "data": {"x": i}} for i in range(5)])
        batch = read(sent)
        self.assertEqual([json.loads(r.text) for r in batch.records["rrweb"]], sent["e"])
        self.assertEqual([json.loads(r.text) for r in batch.records["raw"]], sent["r"])
        self.assertEqual([json.loads(r.text) for r in batch.records["env"]], sent["x"])
        self.assertEqual({r.page for records in batch.records.values() for r in records}, {PV})
        self.assertEqual([r.ts for r in batch.records["raw"]], [int(T0 + 2.4)], "the stream's time is whole ms")
        self.assertEqual(batch.record_count(), 7)

    def test_text_is_compact_utf8_json_and_odd_characters_survive(self):
        record = {"t": T0, "ty": "err", "msg": "Café ☕ line sep\r\nend \U0001F600 \ud83d"}
        text = upload.record_text(record)
        self.assertEqual(json.loads(text), record)
        self.assertNotIn("\n", text)
        text.encode("utf-8")  # storable: the lone surrogate stays an escape
        self.assertEqual(upload.record_text({"a": "é", "b": [1, 2.5]}), '{"a":"é","b":[1,2.5]}')

    def test_records_without_a_usable_time_are_left_out_and_counted(self):
        odd = [{"type": 3}, {"type": 3, "timestamp": "soon"}, {"type": 3, "timestamp": True},
               {"type": 3, "timestamp": -5}, {"type": 3, "timestamp": float("nan")}, "text", 7, None,
               {"type": 3, "timestamp": T0}]
        batch = read(v1(e=odd, r=[], x=[]))
        self.assertEqual(len(batch.records["rrweb"]), 1)
        self.assertEqual(batch.bad_records, len(odd) - 1)
        self.assertNotIn("raw", batch.records)

    def test_record_arrays_must_be_lists(self):
        self.assertEqual(refusal(read, v1(e={"type": 3}))[0], "bad_batch")

    def test_too_many_records_are_refused_before_they_are_read(self):
        sent = v1(e=[{"type": 3, "timestamp": T0}] * 6, r=[], x=[])
        self.assertEqual(refusal(read, sent, 5), ("post_limit", HTTPStatus.REQUEST_ENTITY_TOO_LARGE, 6))
        self.assertEqual(read(sent, 6).record_count(), 6)


if __name__ == "__main__":
    unittest.main()
