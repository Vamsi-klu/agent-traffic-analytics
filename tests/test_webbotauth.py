"""Web Bot Auth verification (agentcake.detect.webbotauth): verified, invalid, declared or none, with a reason.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Threshold N4: the five published Ed25519 examples verify (four of cloudflare/web-bot-auth 01c0d10a, draft -01 E.2.1),
the same five with one byte changed do not (invalid), five unsigned requests are none. Expired, not yet valid or too
old signatures, a missing key and an expired key are declared, never invalid. One verification stays under
verify_budget_ms (median of 100). Verifying opens no socket. Each session is verified once.
"""
import base64, dataclasses, hashlib, json, os, socket, statistics, sys, time, unittest
from unittest import mock
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentcake.detect import httpsig, keydirectory, sfv, webbotauth  # noqa: E402  (needs the repository root first)
from agentcake.detect.webbotauth import DECLARED, INVALID, NONE, VERIFIED  # noqa: E402

VECTORS_DIR = os.path.join(ROOT, "tests", "vectors", "web-bot-auth")
SHIPPED = webbotauth.load_settings()
VECTOR_SETTINGS = dataclasses.replace(SHIPPED, rejected_key_thumbprints={})  # the vectors use RFC 9421's test key
TEST_KEY = {"kty": "OKP", "crv": "Ed25519", "x": "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs"}
TEST_KEY_THUMBPRINT = "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"
VECTOR_SIGNER = "signature-agent.test"
NOW = 1_800_000_000

# An Ed25519 signer for these tests only (RFC 8032 5.1.5-5.1.6), in affine coordinates and written apart from
# agentcake.detect.ed25519, so that what one signs and the other verifies check each other.
P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
B = (15112221349535400772501151409588531511454012693041857206046113283949847762202,
     46316835694926478169428394003475163141307993866256225615783033603165251855960)


def edwards_add(first, second):
    (x1, y1), (x2, y2) = first, second
    t = D * x1 * x2 * y1 * y2 % P
    return (x1 * y2 + y1 * x2) * pow(1 + t, P - 2, P) % P, (y1 * y2 + x1 * x2) * pow(1 - t, P - 2, P) % P


def edwards_multiply(scalar, point):
    result = (0, 1)
    while scalar:
        if scalar & 1:
            result = edwards_add(result, point)
        point, scalar = edwards_add(point, point), scalar >> 1
    return (result[1] | (result[0] & 1) << 255).to_bytes(32, "little")


def b64url(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class Signer:
    def __init__(self, seed):
        digest = hashlib.sha512(seed).digest()
        self.scalar = int.from_bytes(digest[:32], "little") & ((1 << 254) - 8) | (1 << 254)
        self.prefix = digest[32:]
        self.public_key = edwards_multiply(self.scalar, B)
        self.jwk = {"kty": "OKP", "crv": "Ed25519", "x": b64url(self.public_key)}

    def sign(self, message):
        r = int.from_bytes(hashlib.sha512(self.prefix + message).digest(), "little") % L
        encoded_r = edwards_multiply(r, B)
        k = int.from_bytes(hashlib.sha512(encoded_r + self.public_key + message).digest(), "little") % L
        return encoded_r + ((r + k * self.scalar) % L).to_bytes(32, "little")


AGENT, BROWSER = Signer(b"agentcake test agent"), Signer(b"agentcake test browser")


def sign(headers, signer, label, components, url=None, created=NOW, target="/", authority="shop.example"):
    """``headers`` plus one more Web Bot Auth signature (and its Signature-Agent member when ``url`` is given)."""
    headers = list(headers) + ([("Signature-Agent", f'{label}="{url}"')] if url else [])
    keyid = keydirectory.thumbprint(signer.jwk)
    signature_input = (f'{label}=({" ".join(components)});created={created};expires={created + 60};keyid="{keyid}"'
                       ';alg="ed25519";tag="web-bot-auth"')
    headers.append(("Signature-Input", signature_input))
    request = httpsig.Request("GET", "https", authority, target, headers)
    base = httpsig.signature_base(request, sfv.parse_dictionary(signature_input)[label])
    headers.append(("Signature", f"{label}=:{base64.b64encode(signer.sign(base.encode())).decode()}:"))
    return headers


def request(headers, target="/", authority="shop.example", method="GET"):
    return httpsig.Request(method, "https", authority, target, headers)


def load(name):
    with open(os.path.join(VECTORS_DIR, name), encoding="utf-8") as file:
        return json.load(file)


def published_examples():
    """The five published Ed25519 Web Bot Auth requests as (name, request, created)."""
    examples = []
    for file in ("web_bot_auth_architecture_v1.json", "web_bot_auth_architecture_v2.json"):
        for vector in load(file):
            if vector["key"]["kty"] == "OKP":
                headers = [("Signature", vector["signature"]), ("Signature-Input", vector["signature_input"])]
                headers += [("Signature-Agent", vector["signature_agent"])] if "signature_agent" in vector else []
                url = urlsplit(vector["target_url"])
                examples.append((f"{file} {vector['label']}", request(headers, url.path, url.netloc),
                                 vector["created_ms"] // 1000))
    draft = load("draft-ietf-webbotauth-httpsig-protocol-01.json")
    fields = draft["request"]
    headers = [tuple(header) for header in fields["headers"]] + list(draft["E.2.1"]["headers"].items())
    examples.append(("draft-01 E.2.1", request(headers, fields["target"], fields["authority"], fields["method"]),
                     int(sfv.parse_dictionary(draft["E.2.1"]["headers"]["Signature-Input"])["sig2"].params["created"])))
    return examples


def replace_header(req, name, change):
    return dataclasses.replace(req, headers=[(n, change(v) if n == name else v) for n, v in req.headers])


def flip_signature_bit(req):
    def change(value):
        label, encoded = value.split("=", 1)
        signature = bytearray(base64.b64decode(encoded.strip(":")))
        signature[10] ^= 1
        return f"{label}=:{base64.b64encode(signature).decode()}:"
    return replace_header(req, "Signature", change)


def change_authority(req):
    return dataclasses.replace(req, authority=req.authority.replace("a", "b", 1))


def edit_signature_input(req, old, new):
    return replace_header(req, "Signature-Input", lambda value: value.replace(old, new, 1))


def change_nonce(req):
    return edit_signature_input(req, 'nonce="', 'nonce="A')


def change_created(req):
    """created one second later: still inside the window, but not what was signed."""
    return edit_signature_input(req, ";created=1735689600;", ";created=1735689601;")


def change_expires(req):
    return edit_signature_input(req, ";expires=4889289600;", ";expires=4889289601;")


ONE_BYTE_CHANGES = (flip_signature_bit, change_authority, change_nonce, change_created, change_expires)


class N4(unittest.TestCase):
    def setUp(self):
        self.directory = webbotauth.KeyDirectory({VECTOR_SIGNER: [TEST_KEY]}, VECTOR_SETTINGS)
        self.examples = published_examples()

    def verify(self, req, now, directory=None, settings=VECTOR_SETTINGS):
        return webbotauth.verify_request(req, directory or self.directory, now, settings)

    def test_the_five_published_examples_verify(self):
        self.assertEqual(len(self.examples), 5)
        for name, req, created in self.examples:
            with self.subTest(name):
                result = self.verify(req, created + 30)
                self.assertEqual((result.outcome, result.signer, result.keyid),
                                 (VERIFIED, VECTOR_SIGNER, TEST_KEY_THUMBPRINT))
                # sig1 covers no Signature-Agent, so its key names the signer (draft -01 4.3)
                self.assertEqual(result.via, "key" if result.label == "sig1" else "signature-agent")

    def test_the_same_five_with_one_byte_changed_do_not_verify(self):
        for (name, req, created), change in zip(self.examples, ONE_BYTE_CHANGES):
            with self.subTest(name, change=change.__name__):
                result = self.verify(change(req), created + 30)
                self.assertEqual((result.outcome, result.code, result.signer),
                                 (INVALID, "bad-signature", VECTOR_SIGNER))

    def test_five_unsigned_requests_have_no_signature(self):
        unsigned = [
            request([("User-Agent", "Mozilla/5.0"), ("Accept", "text/html")]),
            request([("Content-Type", "application/json"), ("Origin", "https://shop.example")], "/collect",
                    method="POST"),
            request([("Accept-Language", "en")], "/products?page=2"),
            request([("Sec-Fetch-Site", "cross-site"), ("Sec-Fetch-Mode", "navigate")], "/", method="HEAD"),
            request([], "/cart", "Shop.Example:443"),
        ]
        for req in unsigned:
            with self.subTest(req.target, headers=req.headers):
                result = self.verify(req, NOW)
                self.assertEqual((result.outcome, result.code), (NONE, "unsigned"))

    def test_other_signatures_and_unreadable_headers_are_not_web_bot_auth(self):
        other_protocol = [("Signature-Input", 'sig1=("@authority");created=1;tag="other"'),
                          ("Signature", "sig1=:AA==:")]
        for headers in (other_protocol,
                        [("Signature-Input", "this is not a dictionary"), ("Signature", "garbage")],
                        [("Signature-Agent", "(not a signer")]):
            with self.subTest(headers):
                self.assertEqual(self.verify(request(headers), NOW).code, "unsigned")

    def test_outside_the_time_window_is_declared(self):
        _, legacy, created = self.examples[1]  # expires = created + 3600
        _, far, far_created = self.examples[3]  # expires in 2124
        skew, max_age = VECTOR_SETTINGS.clock_skew_s, VECTOR_SETTINGS.max_age_s
        for req, now, code in ((legacy, created + 3600 + skew + 1, "expired"),
                               (legacy, created - skew - 1, "not-yet-valid"),
                               (far, far_created + max_age + skew + 1, "too-old")):
            with self.subTest(code):
                result = self.verify(req, now)
                self.assertEqual((result.outcome, result.code), (DECLARED, code))
        self.assertEqual(self.verify(legacy, created + 3600 + skew - 1).outcome, VERIFIED, "inside the clock skew")

    def test_a_missing_or_expired_key_is_declared_even_when_the_request_was_changed(self):
        _, req, created = self.examples[4]
        directories = {
            "key-missing": {VECTOR_SIGNER: [AGENT.jwk]},
            "key-expired": {VECTOR_SIGNER: [dict(TEST_KEY, exp=created - 1)]},
            "key-not-yet-valid": {VECTOR_SIGNER: [dict(TEST_KEY, nbf=created + 1)]},
            "unknown-signer": {"other.example": [AGENT.jwk]},
        }
        for code, keys in directories.items():
            directory = webbotauth.KeyDirectory(keys, VECTOR_SETTINGS)
            for changed in (req, flip_signature_bit(req)):
                with self.subTest(code, changed=changed is not req):
                    result = self.verify(changed, created + 30, directory)
                    self.assertEqual((result.outcome, result.code), (DECLARED, code))

    def test_the_shipped_settings_reject_the_published_test_key(self):
        name, req, created = self.examples[4]
        result = self.verify(req, created + 30, settings=SHIPPED)
        self.assertEqual((result.outcome, result.code), (DECLARED, "test-key"))

    def test_rsa_signatures_are_declared_unsupported(self):
        vector = load("web_bot_auth_architecture_v2.json")[1]
        req = request([("Signature", vector["signature"]), ("Signature-Input", vector["signature_input"]),
                       ("Signature-Agent", vector["signature_agent"])], "/path/to/resource", "example.com")
        result = self.verify(req, vector["created_ms"] // 1000 + 30)
        self.assertEqual((result.outcome, result.code), (DECLARED, "unsupported-algorithm"))


class Attribution(unittest.TestCase):
    def setUp(self):
        self.directory = webbotauth.KeyDirectory({"agent.example": [AGENT.jwk], "browser.example": [BROWSER.jwk]},
                                                 SHIPPED)

    def verify(self, headers, target="/"):
        return webbotauth.verify_request(request(headers, target), self.directory, NOW + 10, SHIPPED)

    def test_a_fresh_signature_over_more_components_verifies(self):
        components = ('"@method"', '"@authority"', '"@path"', '"@query-param";name="q"', '"accept"',
                      '"signature-agent";key="sig1"')
        headers = sign([("Accept", "text/html")], AGENT, "sig1", components, "https://agent.example",
                       target="/s?q=cake")
        result = self.verify(headers, "/s?q=cake")
        self.assertEqual((result.outcome, result.code, result.signer), (VERIFIED, "verified", "agent.example"))
        self.assertEqual(self.verify(headers, "/s?q=pie").outcome, INVALID)

    def test_a_key_never_vouches_for_another_signer(self):
        # signed by agent.example's key, but the covered Signature-Agent names browser.example
        headers = sign([], AGENT, "sig1", ('"@authority"', '"signature-agent";key="sig1"'), "https://browser.example")
        result = self.verify(headers)
        self.assertEqual((result.outcome, result.code, result.signer), (DECLARED, "key-missing", "browser.example"))

    def test_an_uncovered_signature_agent_is_only_a_claim(self):
        headers = sign([("Signature-Agent", 'sig1="https://browser.example"')], AGENT, "sig1", ('"@authority"',))
        result = self.verify(headers)
        self.assertEqual((result.outcome, result.signer, result.via, result.claimed),
                         (VERIFIED, "agent.example", "key", "browser.example"))

    def test_a_signature_agent_without_a_signature_is_a_claim(self):
        result = self.verify([("Signature-Agent", '"https://chatgpt.com"')])
        self.assertEqual((result.outcome, result.code, result.claimed), (DECLARED, "claim-only", "chatgpt.com"))

    def test_a_covered_field_that_is_absent_cannot_be_judged(self):
        headers = sign([("Accept", "*/*")], AGENT, "sig1", ('"@authority"', '"accept"', '"signature-agent"'),
                       "https://agent.example")
        result = self.verify([header for header in headers if header[0] != "Accept"])
        self.assertEqual((result.outcome, result.code), (DECLARED, "unrebuildable"))

    def test_an_agent_behind_a_remote_browser_both_verify(self):
        # draft -01 D.2: the browser's signature covers the agent's Signature-Agent, Signature-Input and Signature
        headers = sign([], AGENT, "agent", ('"@method"', '"@authority"', '"@path"', '"signature-agent";key="agent"'),
                       "https://agent.example")
        headers = sign(headers, BROWSER, "browser", ('"@method"', '"@authority"', '"@path"',
                                                    '"signature-agent";key="browser"', '"signature-agent";key="agent"',
                                                    '"signature-input";key="agent"', '"signature";key="agent"'),
                       "https://browser.example", created=NOW + 1)
        result = self.verify(headers)
        self.assertEqual([(check.label, check.outcome, check.signer) for check in result.checks],
                         [("agent", VERIFIED, "agent.example"), ("browser", VERIFIED, "browser.example")])

    def test_a_verified_signature_wins_over_a_broken_one_and_both_are_listed(self):
        good = sign([], AGENT, "a", ('"@authority"', '"signature-agent";key="a"'), "https://agent.example")
        bad = sign([], BROWSER, "b", ('"@authority"', '"signature-agent";key="b"'), "https://browser.example",
                   authority="elsewhere.example")
        result = self.verify(good + bad)
        self.assertEqual((result.outcome, result.signer), (VERIFIED, "agent.example"))
        self.assertEqual([check.outcome for check in result.checks], [VERIFIED, INVALID])

    def test_only_max_signatures_are_checked(self):
        headers = []
        for label in ("a", "b", "c"):
            headers = sign(headers, AGENT, label, ('"@authority"', f'"signature-agent";key="{label}"'),
                           "https://agent.example")
        settings = dataclasses.replace(SHIPPED, max_signatures=2)
        result = webbotauth.verify_request(request(headers), self.directory, NOW + 10, settings)
        self.assertEqual((len(result.checks), result.skipped), (2, 1))


class SettingsAndReasons(unittest.TestCase):
    def test_the_settings_cannot_drop_the_parameters_the_checks_read(self):
        with self.assertRaises(ValueError):
            dataclasses.replace(SHIPPED, required_parameters=("keyid",))

    def test_every_code_has_a_reason_and_explains(self):
        self.assertEqual(set(SHIPPED.reasons) - {"$missing"}, set(webbotauth.CODES))
        result = webbotauth.verify_request(request([("Signature-Agent", '"https://chatgpt.com"')]), {}, NOW)
        self.assertEqual(webbotauth.explain(result), "The request names a signer but has no signature to verify, so the name is self-reported.")
        self.assertEqual(webbotauth.words(webbotauth.as_facts(result))[1],
                         "Signature-Agent names chatgpt.com, but the request carries no Web Bot Auth signature.")
        self.assertEqual(set(SHIPPED.details), set(webbotauth.CODES) - {"unsigned"})

    def test_the_test_signer_reproduces_rfc_8032_test_1(self):
        # so the signatures it makes for these tests are real Ed25519 signatures
        signer = Signer(bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"))
        self.assertEqual(signer.public_key.hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        self.assertEqual(signer.sign(b"").hex()[:32], "e5564300c360ac729086e2cc806e828a")


class CostAndNetwork(unittest.TestCase):
    def setUp(self):
        self.directory = webbotauth.KeyDirectory({VECTOR_SIGNER: [TEST_KEY]}, VECTOR_SETTINGS)

    def test_one_verification_is_within_the_budget(self):
        name, req, created = published_examples()[4]
        durations = []
        for _ in range(100):
            start = time.perf_counter()
            result = webbotauth.verify_request(req, self.directory, created + 30, VECTOR_SETTINGS)
            durations.append((time.perf_counter() - start) * 1000)
            self.assertEqual(result.outcome, VERIFIED)
        self.assertLess(statistics.median(durations), SHIPPED.verify_budget_ms)

    def test_verifying_opens_no_socket(self):
        def refuse(*args, **kwargs):
            raise AssertionError("verification tried to use the network")
        with mock.patch.object(socket, "socket", refuse), mock.patch.object(socket, "create_connection", refuse), \
                mock.patch.object(socket, "getaddrinfo", refuse):
            settings = dataclasses.replace(webbotauth.load_settings(), rejected_key_thumbprints={})
            directory = webbotauth.KeyDirectory({VECTOR_SIGNER: [TEST_KEY]}, settings)
            for (name, req, created), change in zip(published_examples(), ONE_BYTE_CHANGES):
                with self.subTest(name):
                    original = webbotauth.verify_request(req, directory, created + 30, settings)
                    self.assertEqual(original.outcome, VERIFIED)
                    changed = webbotauth.verify_request(change(req), directory, created + 30, settings)
                    self.assertEqual(changed.outcome, INVALID)


class Sessions(unittest.TestCase):
    def setUp(self):
        self.signed = request(sign([], AGENT, "sig1", ('"@authority"', '"signature-agent"'), "https://agent.example"))
        self.sessions = webbotauth.SessionVerifier({"agent.example": [AGENT.jwk]}, SHIPPED, clock=lambda: NOW + 10)

    def test_a_session_is_verified_once(self):
        with mock.patch.object(webbotauth.ed25519, "verify", wraps=webbotauth.ed25519.verify) as verify:
            first = self.sessions.verify("s1", self.signed)
            again = self.sessions.verify("s1", request([]))
        self.assertEqual(verify.call_count, 1)
        self.assertIs(again, first)
        self.assertEqual(first.outcome, VERIFIED)

    def test_an_unsigned_request_is_not_remembered(self):
        self.assertEqual(self.sessions.verify("s2", request([])).outcome, NONE)
        self.assertEqual(self.sessions.verify("s2", self.signed).outcome, VERIFIED)

    def test_a_forgotten_session_is_verified_again(self):
        with mock.patch.object(webbotauth.ed25519, "verify", wraps=webbotauth.ed25519.verify) as verify:
            self.sessions.verify("s3", self.signed)
            self.sessions.forget("s3")
            self.sessions.verify("s3", self.signed)
        self.assertEqual(verify.call_count, 2)

    def test_the_oldest_session_leaves_the_cache_first(self):
        small = dataclasses.replace(SHIPPED, session_cache_size=2)
        sessions = webbotauth.SessionVerifier({"agent.example": [AGENT.jwk]}, small, clock=lambda: NOW + 10)
        with mock.patch.object(webbotauth.ed25519, "verify", wraps=webbotauth.ed25519.verify) as verify:
            for session in ("a", "b", "c", "a"):
                sessions.verify(session, self.signed)
        self.assertEqual(verify.call_count, 4, "a was dropped when c came, so it is verified again")


if __name__ == "__main__":
    unittest.main()
