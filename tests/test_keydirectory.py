"""Web Bot Auth key directories (agentcake.detect.keydirectory, S3.2): signer identifiers, JWK thumbprints, key lookup.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Thumbprints follow RFC 7638 (section 3.1 example) and RFC 8037 A.3; Signature-Agent values become the identifiers of
draft-ietf-webbotauth-httpsig-protocol-01 section 5.5 (cloudflare/web-bot-auth signature-agent vectors); a directory
takes a JWK Set, a list of JWKs or raw keys by keyid, and looks keys up per signer, never across signers.
"""
import base64, json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentcake.detect import keydirectory, webbotauth  # noqa: E402  (the repository root has to be on sys.path first)

VECTORS_DIR = os.path.join(ROOT, "tests", "vectors", "web-bot-auth")
SETTINGS = webbotauth.load_settings()
TEST_KEY_X = "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs"  # RFC 9421 B.1.4 test-key-ed25519
TEST_KEY_THUMBPRINT = "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"
RFC8037_X = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"
RFC7638_N = ("0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCi"
             "FV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9"
             "c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1j"
             "F44-csFCur-kEgU8awapJzKnqDKgw")


def okp(x, **extra):
    return {"kty": "OKP", "crv": "Ed25519", "x": x, **extra}


def raw(x):
    return base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))


class Thumbprints(unittest.TestCase):
    def test_rfc_8037_a_3(self):
        self.assertEqual(keydirectory.thumbprint(okp(RFC8037_X, d="ignored", kid="ignored")),
                         "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k")

    def test_rfc_7638_3_1_rsa(self):
        jwk = {"kty": "RSA", "n": RFC7638_N, "e": "AQAB", "alg": "RS256", "kid": "2011-04-29"}
        self.assertEqual(keydirectory.thumbprint(jwk), "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs")

    def test_the_rfc_9421_test_key_has_the_keyid_the_vectors_use(self):
        self.assertEqual(keydirectory.thumbprint(okp(TEST_KEY_X)), TEST_KEY_THUMBPRINT)

    def test_a_jwk_without_its_required_members_has_no_thumbprint(self):
        for jwk in ({"kty": "OKP", "crv": "Ed25519"}, {"kty": "oct", "k": "abc"}, {"x": TEST_KEY_X}):
            with self.subTest(jwk), self.assertRaises(ValueError):
                keydirectory.thumbprint(jwk)


class SignerIdentifiers(unittest.TestCase):
    def identifier(self, value):
        return keydirectory.signer_identifier(value, SETTINGS)

    def test_cloudflare_signature_agent_vectors(self):
        with open(os.path.join(VECTORS_DIR, "web_bot_auth_signature_agent_v2.json"), encoding="utf-8") as file:
            vectors = {vector["name"]: vector["entries"][0]["uri"] for vector in json.load(file)}
        expected = {"origin-default": "signature-agent.test", "directory-default": "signature-agent.test",
                    "jwks-default": "https://signature-agent.test/jwks.json"}
        for name, identifier in expected.items():
            with self.subTest(name):
                self.assertEqual(self.identifier(vectors[name]), identifier)

    def test_urls_are_normalised(self):
        expected = {
            "https://CHATGPT.com:443/": "chatgpt.com",
            "HTTPS://chatgpt.com": "chatgpt.com",
            "https://chatgpt.com:8443": "chatgpt.com:8443",
            "https://a.example/keys/../jwks.json?v=2": "https://a.example/jwks.json",
            "https://a.example/%7euser/%6a%77ks": "https://a.example/~user/jwks",
            "https://a.example/a%2fb": "https://a.example/a%2Fb",
        }
        for value, identifier in expected.items():
            with self.subTest(value):
                self.assertEqual(self.identifier(value), identifier)

    def test_values_that_are_not_https_urls_have_no_identifier(self):
        for value in ("http://chatgpt.com", "chatgpt.com", "https://user@chatgpt.com", "https://chatgpt.com/#a",
                      "https://", "https://exa mple.com", "https://a.example/%zz", "https://[::1]/", ""):
            with self.subTest(value):
                self.assertIsNone(self.identifier(value))


class Directories(unittest.TestCase):
    def test_a_jwk_set_a_list_and_raw_keys_are_the_same_keys(self):
        for keys in ({"keys": [okp(TEST_KEY_X)]}, [okp(TEST_KEY_X)], {"my-label": raw(TEST_KEY_X)}):
            directory = keydirectory.KeyDirectory({"signature-agent.test": keys}, SETTINGS)
            with self.subTest(type(keys).__name__):
                key = directory.find("signature-agent.test", TEST_KEY_THUMBPRINT)
                self.assertEqual(key.public_key, raw(TEST_KEY_X))

    def test_keys_are_found_by_thumbprint_or_kid_within_their_signer_only(self):
        directory = keydirectory.KeyDirectory({"a.example": [okp(TEST_KEY_X, kid="label-1")],
                                               "b.example": [okp(RFC8037_X)]}, SETTINGS)
        self.assertIsNotNone(directory.find("a.example", TEST_KEY_THUMBPRINT))
        self.assertIsNotNone(directory.find("a.example", "label-1"))
        self.assertIsNone(directory.find("b.example", TEST_KEY_THUMBPRINT))
        self.assertIsNone(directory.find("c.example", TEST_KEY_THUMBPRINT))
        self.assertTrue(directory.knows("b.example"))
        self.assertFalse(directory.knows("c.example"))
        self.assertEqual([signer for signer, _ in directory.holders(TEST_KEY_THUMBPRINT)], ["a.example"])

    def test_signer_names_are_normalised_like_signature_agent_values(self):
        directory = keydirectory.KeyDirectory({"https://Signature-Agent.test/": [okp(TEST_KEY_X)],
                                               "https://a.example/jwks.json": [okp(RFC8037_X)]}, SETTINGS)
        self.assertTrue(directory.knows("signature-agent.test"))
        self.assertTrue(directory.knows("https://a.example/jwks.json"))
        with self.assertRaises(ValueError):
            keydirectory.KeyDirectory({"http://a.example": []}, SETTINGS)

    def test_validity_dates_are_kept(self):
        directory = keydirectory.KeyDirectory({"a.example": [okp(TEST_KEY_X, nbf=10, exp=20)]}, SETTINGS)
        key = directory.find("a.example", TEST_KEY_THUMBPRINT)
        self.assertEqual((key.not_before, key.expires), (10, 20))

    def test_malformed_keys_are_left_out_and_other_key_types_kept_without_a_key(self):
        rsa = {"kty": "RSA", "n": RFC7638_N, "e": "AQAB"}
        directory = keydirectory.KeyDirectory({"a.example": [
            okp("not base64url!"), okp(base64.urlsafe_b64encode(bytes(31)).decode()), okp(TEST_KEY_X, exp="soon"),
            {"kty": "OKP", "crv": "X25519", "x": TEST_KEY_X}, rsa, okp(RFC8037_X)]}, SETTINGS)
        self.assertEqual(len(directory.keys("a.example")), 3)
        unsupported = directory.find("a.example", "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs")
        self.assertIsNone(unsupported.public_key)
        self.assertIsNone(directory.find("a.example", TEST_KEY_THUMBPRINT))

    def test_raw_keys_must_be_valid_ed25519_keys(self):
        with self.assertRaises(ValueError):
            keydirectory.KeyDirectory({"a.example": {"k": bytes(31)}}, SETTINGS)


if __name__ == "__main__":
    unittest.main()
