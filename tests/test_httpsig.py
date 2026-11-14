"""The RFC 9421 signature base (agentcake.detect.httpsig, S3.2): component values and the base a verifier rebuilds.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Uses the examples of RFC 9421 sections 2.1, 2.1.2 and 2.2 and checks the whole signature base against RFC 9421 B.2.6
and draft-ietf-webbotauth-httpsig-protocol-01 E.2.1 and E.2.2. Any component that cannot be derived exactly as the
RFC says raises ComponentError, so a signature over it can never be reported as verified or as forged.
"""
import json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentcake.detect import httpsig, sfv  # noqa: E402  (the repository root has to be on sys.path first)

VECTORS_DIR = os.path.join(ROOT, "tests", "vectors", "web-bot-auth")


def load(name):
    with open(os.path.join(VECTORS_DIR, name), encoding="utf-8") as file:
        return json.load(file)


def request(target="/", headers=(), method="GET", authority="www.example.com", scheme="https"):
    return httpsig.Request(method=method, scheme=scheme, authority=authority, target=target, headers=headers)


def identifier(text):
    """A component identifier as it appears in Signature-Input, e.g. '"example-dict";key="a"'."""
    return sfv.parse_item(text)


class DerivedComponents(unittest.TestCase):
    """RFC 9421 section 2.2, with the request of its examples."""

    def setUp(self):
        self.request = request("/path?param=value&foo=bar&baz=bat%2Dman", method="POST")

    def value(self, text, req=None):
        return httpsig.component_value(req or self.request, identifier(text))

    def test_the_examples_of_section_2_2(self):
        expected = {
            '"@method"': "POST",
            '"@target-uri"': "https://www.example.com/path?param=value&foo=bar&baz=bat%2Dman",
            '"@authority"': "www.example.com",
            '"@scheme"': "https",
            '"@request-target"': "/path?param=value&foo=bar&baz=bat%2Dman",
            '"@path"': "/path",
            '"@query"': "?param=value&foo=bar&baz=bat%2Dman",
        }
        for text, value in expected.items():
            with self.subTest(text):
                self.assertEqual(self.value(text), value)

    def test_an_absent_query_is_a_lone_question_mark_and_an_empty_path_a_slash(self):
        self.assertEqual(self.value('"@query"', request("/path")), "?")
        self.assertEqual(self.value('"@path"', request("https://www.example.com")), "/")
        self.assertEqual(self.value('"@target-uri"', request("https://www.example.com")), "https://www.example.com/")

    def test_authority_is_lowercased_without_the_default_port(self):
        self.assertEqual(self.value('"@authority"', request(authority="WWW.Example.COM:443")), "www.example.com")
        self.assertEqual(self.value('"@authority"', request(authority="example.com:8443")), "example.com:8443")
        self.assertEqual(self.value('"@authority"', request(authority="example.com:80", scheme="http")), "example.com")
        self.assertEqual(self.value('"@authority"', request(authority="[2001:DB8::1]:443")), "[2001:db8::1]")

    def test_query_parameters_are_decoded_then_re_encoded(self):
        req = request("/parameters?var=this%20is%20a%20big%0Amultiline%20value&bar=with+plus+whitespace"
                      "&fa%C3%A7ade%22%3A%20=something")
        self.assertEqual(self.value('"@query-param";name="var"', req), "this%20is%20a%20big%0Amultiline%20value")
        self.assertEqual(self.value('"@query-param";name="bar"', req), "with%20plus%20whitespace")
        self.assertEqual(self.value('"@query-param";name="fa%C3%A7ade%22%3A%20"', req), "something")

    def test_query_parameters_of_section_2_2_8(self):
        req = request("/path?param=value&foo=bar&baz=batman&qux=")
        self.assertEqual(self.value('"@query-param";name="baz"', req), "batman")
        self.assertEqual(self.value('"@query-param";name="qux"', req), "")
        self.assertEqual(self.value('"@query-param";name="param"', req), "value")

    def test_a_missing_or_repeated_query_parameter_is_an_error(self):
        req = request("/path?a=1&a=2&b=3")
        for text in ('"@query-param";name="a"', '"@query-param";name="c"', '"@query-param"'):
            with self.subTest(text), self.assertRaises(httpsig.ComponentError):
                self.value(text, req)

    def test_unknown_or_response_only_components_are_errors(self):
        for text in ('"@status"', '"@foo"', '"@signature-params"', '"@method";req', '"@authority";key="a"'):
            with self.subTest(text), self.assertRaises(httpsig.ComponentError):
                self.value(text)


class FieldComponents(unittest.TestCase):
    """RFC 9421 sections 2.1 and 2.1.2."""

    def setUp(self):
        self.request = request(headers=[
            ("Host", "www.example.com"),
            ("Date", "Tue, 20 Apr 2021 02:07:56 GMT"),
            ("X-OWS-Header", "   Leading and trailing whitespace.   "),
            ("X-Obs-Fold-Header", "Obsolete\r\n    line folding."),
            ("Cache-Control", "max-age=60"),
            ("Cache-Control", "   must-revalidate"),
            ("Example-Dict", " a=1,    b=2;x=1;y=2,   c=(a   b   c), d"),
            ("X-Empty-Header", ""),
        ])

    def value(self, text):
        return httpsig.component_value(self.request, identifier(text))

    def test_the_field_examples_of_section_2_1(self):
        expected = {
            '"host"': "www.example.com",
            '"date"': "Tue, 20 Apr 2021 02:07:56 GMT",
            '"x-ows-header"': "Leading and trailing whitespace.",
            '"x-obs-fold-header"': "Obsolete line folding.",
            '"cache-control"': "max-age=60, must-revalidate",
            '"example-dict"': "a=1,    b=2;x=1;y=2,   c=(a   b   c), d",
            '"x-empty-header"': "",
        }
        for text, value in expected.items():
            with self.subTest(text):
                self.assertEqual(self.value(text), value)

    def test_dictionary_members_of_section_2_1_2(self):
        expected = {"a": "1", "d": "?1", "b": "2;x=1;y=2", "c": "(a b c)"}
        for key, value in expected.items():
            with self.subTest(key):
                self.assertEqual(self.value(f'"example-dict";key="{key}"'), value)

    def test_headers_can_be_given_as_a_mapping(self):
        req = request(headers={"Cache-Control": ["max-age=60", "must-revalidate"], "Date": "today"})
        self.assertEqual(httpsig.component_value(req, identifier('"cache-control"')), "max-age=60, must-revalidate")
        self.assertEqual(httpsig.component_value(req, identifier('"date"')), "today")

    def test_field_errors(self):
        for text in ('"x-absent"', '"Date"', '"example-dict";key="z"', '"date";key="a"', '"date";sf', '"date";bs',
                     '"date";tr', '"date";req'):
            with self.subTest(text), self.assertRaises(httpsig.ComponentError):
                self.value(text)

    def test_values_that_cannot_go_into_a_base_are_errors(self):
        for value in ("café", "a\nb", "a\rb"):
            req = request(headers=[("X-Bad", value)])
            with self.subTest(value), self.assertRaises(httpsig.ComponentError):
                httpsig.component_value(req, identifier('"x-bad"'))


class SignatureBase(unittest.TestCase):
    def build(self, vector, request_fields, header_name, label):
        req = httpsig.Request(method=request_fields["method"], scheme=request_fields["scheme"],
                              authority=request_fields["authority"], target=request_fields["target"],
                              headers=list(map(tuple, request_fields["headers"])) + list(vector["headers"].items()))
        covered = sfv.parse_dictionary(vector["headers"][header_name])[label]
        return httpsig.signature_base(req, covered)

    def test_rfc_9421_b_2_6(self):
        rfc = load("rfc9421.json")
        self.assertEqual(self.build(rfc["B.2.6"], rfc["request"], "Signature-Input", "sig-b26"),
                         rfc["B.2.6"]["signature_base"])

    def test_draft_e_2_1_and_e_2_2(self):
        draft = load("draft-ietf-webbotauth-httpsig-protocol-01.json")
        for name in ("E.2.1", "E.2.2"):
            with self.subTest(name):
                self.assertEqual(self.build(draft[name], draft["request"], "Signature-Input", "sig2"),
                                 draft[name]["signature_base"])

    def test_a_covered_signature_member_is_its_serialised_byte_sequence(self):
        req = request(headers=[("Signature", "inner=:aGVsbG8:, outer=:d29ybGQ=:")])
        covered = sfv.parse_dictionary('outer=("signature";key="inner");created=1')["outer"]
        expected = '"signature";key="inner": :aGVsbG8=:\n"@signature-params": ("signature";key="inner");created=1'
        self.assertEqual(httpsig.signature_base(req, covered), expected)

    def test_a_component_listed_twice_is_an_error_whatever_the_parameter_order(self):
        req = request(headers=[("Example-Dict", "a=1")])
        for text in ('x=("@method" "@method")', 'x=("example-dict";key="a" "example-dict";key="a")',
                     'x=("@query-param";name="a" "@query-param";name="a")'):
            covered = sfv.parse_dictionary(text)["x"]
            with self.subTest(text), self.assertRaises(httpsig.ComponentError):
                httpsig.signature_base(req, covered)

    def test_a_component_identifier_must_be_a_string(self):
        covered = sfv.parse_dictionary("x=(method)")["x"]
        with self.assertRaises(httpsig.ComponentError):
            httpsig.signature_base(request(), covered)


if __name__ == "__main__":
    unittest.main()
