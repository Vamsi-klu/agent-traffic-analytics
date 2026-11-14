"""Structured Field Values (agentcake.detect.sfv): the parsing and serialisation HTTP message signatures need.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

RFC 9421 builds its signature base from Structured Field Values as RFC 8941 defines them: Signature-Input is a
Dictionary of Inner Lists, Signature a Dictionary of Byte Sequences, Signature-Agent a Dictionary of Strings (or, in
its legacy form, one String Item), and a covered Dictionary member (";key") is re-serialised strictly. These tests use
the examples of RFC 9421 section 2.1.2 and the headers of draft-ietf-webbotauth-httpsig-protocol-01 Appendix E.2.
"""
import json, os, sys, unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentcake.detect import sfv  # noqa: E402  (the repository root has to be on sys.path first)

VECTORS_DIR = os.path.join(ROOT, "tests", "vectors", "web-bot-auth")


def draft_vector(name):
    with open(os.path.join(VECTORS_DIR, "draft-ietf-webbotauth-httpsig-protocol-01.json"), encoding="utf-8") as file:
        return json.load(file)[name]


class Rfc9421DictionaryMembers(unittest.TestCase):
    """RFC 9421 section 2.1.2: each member of a Dictionary re-serialised on its own."""

    def setUp(self):
        self.dictionary = sfv.parse_dictionary("a=1, b=2;x=1;y=2, c=(a   b    c), d")

    def test_members_keep_their_order(self):
        self.assertEqual(list(self.dictionary), ["a", "b", "c", "d"])

    def test_each_member_serialises_strictly(self):
        expected = {"a": "1", "b": "2;x=1;y=2", "c": "(a b c)", "d": "?1"}
        for key, serialised in expected.items():
            with self.subTest(key):
                self.assertEqual(sfv.serialize(self.dictionary[key]), serialised)

    def test_values_have_python_types(self):
        self.assertEqual(self.dictionary["a"], sfv.Item(1, {}))
        self.assertEqual(self.dictionary["b"].params, {"x": 1, "y": 2})
        self.assertIsInstance(self.dictionary["c"], sfv.InnerList)
        self.assertEqual([item.value for item in self.dictionary["c"].items], ["a", "b", "c"])
        self.assertIsInstance(self.dictionary["c"].items[0].value, sfv.Token)
        self.assertIs(self.dictionary["d"].value, True)


class WebBotAuthHeaders(unittest.TestCase):
    def setUp(self):
        self.headers = draft_vector("E.2.1")["headers"]

    def test_signature_input_parses_and_reserialises_unchanged(self):
        inputs = sfv.parse_dictionary(self.headers["Signature-Input"])
        member = inputs["sig2"]
        self.assertIsInstance(member, sfv.InnerList)
        self.assertEqual([item.value for item in member.items], ["@authority", "signature-agent"])
        self.assertEqual(member.items[1].params, {"key": "sig2"})
        self.assertEqual(member.params["created"], 1735689600)
        self.assertEqual(member.params["tag"], "web-bot-auth")
        self.assertEqual("sig2=" + sfv.serialize(member), self.headers["Signature-Input"])

    def test_signature_is_a_byte_sequence(self):
        value = sfv.parse_dictionary(self.headers["Signature"])["sig2"].value
        self.assertIsInstance(value, bytes)
        self.assertEqual(len(value), 64)

    def test_signature_agent_dictionary_and_legacy_string(self):
        self.assertEqual(sfv.parse_dictionary(self.headers["Signature-Agent"])["sig2"].value,
                         "https://signature-agent.test")
        legacy = draft_vector("E.2.2")["headers"]["Signature-Agent"]
        self.assertEqual(sfv.parse_item(legacy), sfv.Item("https://signature-agent.test", {}))


class BareItems(unittest.TestCase):
    def roundtrip(self, text):
        return sfv.serialize(sfv.parse_item(text))

    def test_integers_and_their_limits(self):
        self.assertEqual(sfv.parse_item("-999999999999999").value, -999999999999999)
        with self.assertRaises(sfv.ParseError):
            sfv.parse_item("1000000000000000")

    def test_decimals_serialise_without_trailing_zeros(self):
        self.assertEqual(sfv.parse_item("1.50").value, Decimal("1.50"))
        self.assertEqual(self.roundtrip("1.50"), "1.5")
        self.assertEqual(self.roundtrip("-0.0"), "0.0")
        self.assertEqual(self.roundtrip("12.000"), "12.0")
        for bad in ("1.2345", "1.", "1234567890123.1"):
            with self.subTest(bad), self.assertRaises(sfv.ParseError):
                sfv.parse_item(bad)

    def test_strings_escape_quote_and_backslash_only(self):
        self.assertEqual(sfv.parse_item(r'"a \"b\" \\c"').value, 'a "b" \\c')
        self.assertEqual(self.roundtrip(r'"a \"b\" \\c"'), r'"a \"b\" \\c"')
        for bad in (r'"a\nb"', '"unterminated', '"tab\there"'):
            with self.subTest(bad), self.assertRaises(sfv.ParseError):
                sfv.parse_item(bad)

    def test_tokens_may_hold_colons_and_slashes(self):
        item = sfv.parse_item("text/html;q=1")
        self.assertEqual(item.value, sfv.Token("text/html"))
        self.assertEqual(sfv.serialize(item), "text/html;q=1")

    def test_byte_sequences_accept_missing_padding(self):
        self.assertEqual(sfv.parse_item(":aGVsbG8=:").value, b"hello")
        self.assertEqual(sfv.parse_item(":aGVsbG8:").value, b"hello")
        self.assertEqual(self.roundtrip(":aGVsbG8:"), ":aGVsbG8=:")
        for bad in (":aGVs*G8=:", ":aGVsbG8="):
            with self.subTest(bad), self.assertRaises(sfv.ParseError):
                sfv.parse_item(bad)

    def test_booleans(self):
        self.assertIs(sfv.parse_item("?0").value, False)
        self.assertEqual(self.roundtrip("?1"), "?1")
        with self.assertRaises(sfv.ParseError):
            sfv.parse_item("?2")

    def test_types_added_after_rfc_8941_are_not_parsed(self):
        # RFC 9421 refers to RFC 8941, which has no Date (@) or Display String (%"") items
        for text in ("@1659578233", '%"caf%c3%a9"'):
            with self.subTest(text), self.assertRaises(sfv.ParseError):
                sfv.parse_item(text)


class DictionarySyntax(unittest.TestCase):
    def test_whitespace_rules(self):
        self.assertEqual(list(sfv.parse_dictionary("  a=1,\tb=2  ")), ["a", "b"])
        self.assertEqual(sfv.parse_dictionary("a=1; x=2")["a"].params, {"x": 2})

    def test_a_repeated_key_keeps_its_place_and_takes_the_last_value(self):
        dictionary = sfv.parse_dictionary("a=1, b=2, a=3")
        self.assertEqual(list(dictionary), ["a", "b"])
        self.assertEqual(dictionary["a"].value, 3)

    def test_malformed_dictionaries_are_rejected(self):
        for bad in ("a=1,", "a=1,,b=2", "A=1", "a=1 b=2", "a=(1 2", "a=(1,2)", "a=1;", "a=é", "a=\"x\" trailing"):
            with self.subTest(bad), self.assertRaises(sfv.ParseError):
                sfv.parse_dictionary(bad)

    def test_an_empty_dictionary_is_valid_and_an_empty_item_is_not(self):
        self.assertEqual(sfv.parse_dictionary(""), {})
        with self.assertRaises(sfv.ParseError):
            sfv.parse_item("")

    def test_inner_list_with_parameters_on_items_and_list(self):
        member = sfv.parse_dictionary('sig=("@method" "x";key="a";req);created=1')["sig"]
        self.assertEqual(member.items[1].params, {"key": "a", "req": True})
        self.assertEqual(sfv.serialize(member), '("@method" "x";key="a";req);created=1')

    def test_an_empty_inner_list(self):
        self.assertEqual(sfv.serialize(sfv.parse_dictionary("sig=();created=5")["sig"]), "();created=5")


if __name__ == "__main__":
    unittest.main()
