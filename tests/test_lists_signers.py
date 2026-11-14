"""S3.1 and S3.2: the bundled Web Bot Auth signers, read on this computer without any network.

    python3 -I -m unittest discover -s tests -v      (from the cake folder)

Signers resolve to names with their bundled Ed25519 keys; a rolling expiry is not bundled as a fixed one; keys are
kept per signer, as the verifier takes them; every stored directory response still verifies with the keys it carries
(draft -01 section 5.5.3), which for muse.ai are signatures Meta made itself; Meta's Muse resolves from
Signature-Agent "https://muse.ai" to its keys; a signer that stopped signing keeps its keys and says so.
Split from test_lists.py (signers-update, 2026-11-13).
"""
import base64, hashlib, json, os, sys, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from agentcake.detect import ed25519, keydirectory, lists, sfv, webbotauth  # noqa: E402

BUNDLED = os.path.join(HERE, "agentcake", "data", "lists")


class SignersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = lists.Lists.load(BUNDLED)

    def test_signers_resolve_to_names_with_ed25519_keys(self):
        for host, name in [("chatgpt.com", "chatgpt"), ("api.manus.im", "manus"), ("agent.bot.goog", "google-agent")]:
            with self.subTest(host=host):
                signer = self.snapshot.signer(host)
                self.assertEqual(signer["name"], name)
                self.assertTrue(signer["keys"])
                self.assertTrue(all(k["kty"] == "OKP" and k["crv"] == "Ed25519" and k["x"] for k in signer["keys"]))
                self.assertTrue(signer["keys_fetched_at"])

    def test_rolling_expiry_is_not_bundled_as_a_fixed_expiry(self):
        # chatgpt.com answers every fetch with "now plus seven days"; bundling that would end verification a week
        # after each release, so the key carries the rolling lifetime instead.
        key = self.snapshot.signer("chatgpt.com")["keys"][0]
        self.assertNotIn("exp", key)
        self.assertGreater(key["rolling_expiry_s"], 0)

    def test_key_directories_use_the_per_signer_format_the_verifier_takes(self):
        # Web Bot Auth draft -01 section 5.4: keys are looked up per signer, never by keyid alone.
        directories = self.snapshot.key_directories()
        self.assertEqual(set(directories), set(self.snapshot.signer_hosts()))
        self.assertTrue(all(isinstance(keys, list) and keys for keys in directories.values()))

    def test_signed_directory_responses_are_kept_for_checking_later(self):
        # Draft -01 section 5.5.3 and appendix B: bundled keys are tied to the signer only through the signed
        # directory response, so its signature, the signed headers and the body are stored as they arrived.
        response = self.snapshot.directory_response("chatgpt.com")
        self.assertIn('tag="http-message-signatures-directory"', response["headers"]["signature-input"])
        self.assertTrue(response["headers"]["signature"])
        self.assertEqual(json.loads(response["body"])["keys"][0]["x"],
                         self.snapshot.signer("chatgpt.com")["keys"][0]["x"])

    def test_muse_signs_as_muse_ai_with_the_keys_its_directory_names(self):
        # Meta's Muse signs with Signature-Agent "https://muse.ai" since 2026-11-07. Meta publishes no example
        # request, so the check is that the directory reads and its keyids line up: each bundled key's RFC 7638
        # thumbprint is the kid Meta gives it, and the keyids that signed the directory response are those keys.
        signer = self.snapshot.signer("muse.ai")
        self.assertEqual((signer["name"], signer["display"], signer["operator"], signer["kind"]),
                         ("muse", "Muse", "Meta", "cloud-agent"))
        thumbprints = {keydirectory.thumbprint(key) for key in signer["keys"]}
        self.assertEqual(thumbprints, {key["kid"] for key in signer["keys"]})
        signed_with = {member.params["keyid"] for member in self.directory_signatures("muse.ai")[0].values()}
        self.assertEqual(signed_with, thumbprints)
        settings = webbotauth.default_settings()
        directory = keydirectory.KeyDirectory(self.snapshot.key_directories(), settings)
        named = keydirectory.signer_identifier("https://muse.ai", settings)
        self.assertTrue(all(directory.find(named, keyid) for keyid in thumbprints))

    def test_every_bundled_directory_response_verifies_with_the_keys_it_carries(self):
        # Draft -01 section 5.5.3: a directory signs its response with its own keys over "@authority";req, which
        # ties the bundled keys to the host they came from. For muse.ai these are signatures Meta made itself.
        for host in self.snapshot.signer_hosts():
            with self.subTest(host=host):
                inputs, values = self.directory_signatures(host)
                response = self.snapshot.directory_response(host)
                bundled = self.snapshot.signer(host)["keys"]
                keys = {**{keydirectory.thumbprint(key): key for key in bundled},
                        **{key["kid"]: key for key in bundled if "kid" in key}}  # agent.bot.goog signs by kid
                self.assertTrue(inputs)
                if "content-digest" in response["headers"]:
                    digest = sfv.parse_dictionary(response["headers"]["content-digest"])["sha-256"].value
                    self.assertEqual(digest, hashlib.sha256(response["body"].encode("utf-8")).digest())
                for label, member in inputs.items():
                    x = keys[member.params["keyid"]]["x"]
                    public_key = base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))
                    base = directory_signature_base(host, response["headers"], member)
                    self.assertTrue(ed25519.verify(public_key, base, values[label].value), label)

    def test_a_signer_that_stopped_signing_keeps_its_keys_and_says_so(self):
        # Grok Bot's signer: requests arrive unsigned since October 2026 (botscent, Fingerprint, Verisoul; xAI has
        # said nothing). Its keys stay bundled, so a signature verifies again if it ever signs again.
        with open(os.path.join(BUNDLED, "signers.json"), encoding="utf-8") as f:
            signer = json.load(f)["signers"]["cursorusercontent.com"]
        self.assertEqual((signer["name"], signer["signing"]["state"]), ("grok-bot", "stopped"))
        self.assertTrue(signer["signing"]["since"] and signer["signing"]["note"])
        self.assertTrue(self.snapshot.signer("cursorusercontent.com")["keys"])

    def directory_signatures(self, host):
        headers = self.snapshot.directory_response(host)["headers"]
        return sfv.parse_dictionary(headers["signature-input"]), sfv.parse_dictionary(headers["signature"])

    def test_unknown_signer(self):
        self.assertIsNone(self.snapshot.signer("example.com"))
        self.assertIsNone(self.snapshot.directory_response("example.com"))


def directory_signature_base(host, headers, member):
    """The RFC 9421 signature base of a stored directory response: "@authority";req is the host that was asked, any
    other covered component is a stored response header (chatgpt.com covers content-digest)."""
    lines = [f"{sfv.serialize(item)}: {host}" if item.value == "@authority"
             else f'"{item.value}": {headers[item.value]}' for item in member.items]
    lines.append(f'"@signature-params": {sfv.serialize(member)}')
    return "\n".join(lines).encode("ascii")
