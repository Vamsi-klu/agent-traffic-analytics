"""Web Bot Auth behind a front door that replaces Host (agentcake.detect.webbotauth.SessionVerifier).

    python3 -I -m unittest discover -s tests -p test_webbotauth_names.py -v      (from the repository root)

nginx's default proxy_set_header Host $proxy_host, CloudFront and Azure Front Door send the request on with the
backend's name, so the @authority the verifier rebuilds is not the one the agent signed. The site's other names
(collect.py: its site_domain with and without www., its public_url) are tried when the request's own Host does not
verify: a signature made for one of them verifies; a forgery verifies with none and stays invalid; a signature that
verifies at once, or a signer that is not bundled, costs no extra verification. Signed with test_webbotauth's signer.
"""
import dataclasses, os, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_webbotauth import AGENT, NOW, SHIPPED, flip_signature_bit, request, sign  # noqa: E402
from agentcake.detect import webbotauth  # noqa: E402
from agentcake.detect.webbotauth import DECLARED, INVALID, VERIFIED  # noqa: E402


class OtherNames(unittest.TestCase):
    def setUp(self):
        self.signed = request(sign([], AGENT, "sig1", ('"@authority"', '"signature-agent"'), "https://agent.example"))
        self.sessions = webbotauth.SessionVerifier({"agent.example": [AGENT.jwk]}, SHIPPED, clock=lambda: NOW + 10)

    def test_a_signature_made_for_another_name_of_the_site_verifies(self):
        """A front door that replaces Host (nginx's default proxy_set_header Host $proxy_host, CloudFront) changes the
        @authority the verifier rebuilds, not the one the agent signed: the site's other names are tried."""
        behind = dataclasses.replace(self.signed, authority="192.0.2.10:8080")
        self.assertEqual(self.sessions.verify("own-name-only", behind).outcome, INVALID)
        names = ("192.0.2.10:8080", "www.shop.example", "shop.example", "cake.shop.example")
        self.assertEqual(self.sessions.verify("other-names", behind, names).outcome, VERIFIED)

    def test_a_forged_signature_fails_with_every_name(self):
        forged = dataclasses.replace(flip_signature_bit(self.signed), authority="192.0.2.10:8080")
        with mock.patch.object(webbotauth.ed25519, "verify", wraps=webbotauth.ed25519.verify) as verify:
            result = self.sessions.verify("forged", forged, ("shop.example", "www.shop.example"))
        self.assertEqual((result.outcome, result.code), (INVALID, "bad-signature"))
        self.assertEqual(verify.call_count, 3, "its own Host, then each other name once")

    def test_other_names_are_tried_only_when_the_signature_does_not_verify(self):
        unknown = request(sign([], AGENT, "sig1", ('"@authority"', '"signature-agent"'), "https://other.example"))
        with mock.patch.object(webbotauth.ed25519, "verify", wraps=webbotauth.ed25519.verify) as verify:
            self.assertEqual(self.sessions.verify("verified", self.signed, ("www.shop.example",)).outcome, VERIFIED)
            self.assertEqual(self.sessions.verify("unknown", unknown, ("www.shop.example",)).outcome, DECLARED)
        self.assertEqual(verify.call_count, 1, "an unknown signer is declared without any arithmetic")


if __name__ == "__main__":
    unittest.main()
