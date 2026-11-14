"""Who a session says it is, and whether that holds (agentcake.detect.verdict_identity).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The name layer reads the User-Agent of each half, navigator.platform and Signature-Agent against the bundled lists;
a tool anyone can run (HeadlessChrome, curl) names no product, and names that disagree name none. The verification
layer: a verified signature or the operator's published range verifies; a name that a range could verify, seen from
outside it, is impersonation, and so is a signature that does not verify, unless it covers what a proxy may rewrite;
a missing or expired key, local mode or no address leave the name self-reported.
"""
import dataclasses, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from verdict_cases import (CHATGPT_USER, CHROME_MAC, GOOGLEBOT, HEADLESS, MANUS, declared, evidence,  # noqa: E402
                           first_address, forged, verified)
from agentcake.detect import verdict_identity  # noqa: E402



def identify(**kwargs):
    return verdict_identity.identify(evidence(**kwargs))


def reason_ids(identity):
    return [r["id"] for r in identity.reasons]


class FromSignals(unittest.TestCase):

    def test_nothing_recorded_gives_no_claims(self):
        self.assertEqual(verdict_identity.claims_from_signals({}),
                         {"user_agents": {"page": [], "collector": [], "server": []}, "platform": None})


class Names(unittest.TestCase):
    def test_declared_agent_without_a_range_is_self_reported(self):
        found = identify(uas=MANUS)
        self.assertEqual((found.entry["id"], found.status, found.evidence), ("manus", "self_reported", ("declared",)))
        self.assertIn("verify.no-range", reason_ids(found))

    def test_tool_anyone_can_run_names_no_product(self):
        found = identify(mode="local", uas=HEADLESS)
        self.assertIsNone(found.entry)
        self.assertEqual([entry["id"] for entry in found.generic], ["headlesschrome"])
        self.assertIn("name.ua-generic", reason_ids(found))

    def test_names_that_disagree_name_none(self):
        found = identify(mode="local", uas={"page": [MANUS], "collector": [], "server": [CHATGPT_USER]})
        self.assertIsNone(found.entry)
        self.assertIn("name.disagree", reason_ids(found))

    def test_platform_claim_is_read(self):
        found = identify(mode="local", platform="Cloudflare Workers")
        self.assertEqual([entry["id"] for entry in found.generic], ["cloudflare-browser-run"])
        self.assertIn("name.platform", reason_ids(found))

    def test_forged_user_agent_shape_is_a_weak_reason_given_once(self):
        found = identify(mode="local", uas="Mozlila/5.0 (Windows NT 10.0) Chrome/157.0.0.0 Safari/537.36")
        self.assertEqual(reason_ids(found).count("name.ua-hint"), 1)

    def test_plain_browser_declares_nothing(self):
        found = identify(uas=CHROME_MAC)
        self.assertEqual((found.entry, found.status, found.generic, found.impersonating), (None, None, (), None))


class Verifying(unittest.TestCase):
    def test_signature_verified_names_the_signer(self):
        found = identify(signatures={"collector": verified("chatgpt.com")})
        self.assertEqual((found.entry["id"], found.status, found.via, found.evidence),
                         ("chatgpt", "verified", "signature", ("signature",)))

    def test_signature_that_does_not_verify_is_impersonation(self):
        found = identify(signatures={"collector": forged("chatgpt.com")})
        self.assertEqual((found.entry, found.status, found.impersonating["id"]), (None, "impersonation", "chatgpt"))

    def test_proxy_rewritable_component_makes_it_unverifiable(self):
        sig = forged("chatgpt.com", covers='"@authority" "@path" "signature-agent"')
        found = identify(signatures={"collector": sig})
        self.assertEqual((found.entry["id"], found.status, found.impersonating), ("chatgpt", "unverifiable", None))

    def test_missing_key_is_self_reported(self):
        found = identify(signatures={"server": declared("chatgpt.com")})
        self.assertEqual((found.entry["id"], found.status, found.impersonating), ("chatgpt", "self_reported", None))

    def test_unknown_signer_is_named_in_the_reasons_only(self):
        found = identify(signatures={"collector": declared("signer.example", code="unknown-signer")})
        self.assertIsNone(found.entry)
        self.assertIn("name.unknown-signer", reason_ids(found))

    def test_signature_naming_no_signer_says_why_and_names_no_one(self):
        incomplete = dataclasses.replace(declared("chatgpt.com", code="incomplete"), signer=None, claimed=None,
                                         facts={"missing": "created"})
        found = identify(signatures={"collector": incomplete})
        self.assertEqual((found.entry, found.status), (None, None))
        self.assertEqual(reason_ids(found), ["verify.signature"])
        self.assertNotIn("unknown", found.reasons[0]["text"])

    def test_signer_mismatch_is_a_reason(self):
        sig = dataclasses.replace(verified("chatgpt.com"), claimed="api.manus.im")
        self.assertIn("name.signer-mismatch", reason_ids(identify(signatures={"collector": sig})))

    def test_published_range_verifies_and_outside_it_is_impersonation(self):
        inside = identify(uas=GOOGLEBOT, address=first_address("google-common-crawlers"))
        self.assertEqual((inside.entry["id"], inside.status, inside.via), ("googlebot", "verified", "ip"))
        outside = identify(uas=GOOGLEBOT)
        self.assertEqual((outside.entry, outside.status, outside.impersonating["id"]),
                         (None, "impersonation", "googlebot"))

    def test_local_mode_and_no_address_cannot_verify(self):
        local = identify(mode="local", uas=GOOGLEBOT)
        self.assertEqual((local.status, local.verify_layer), ("self_reported", {"state": "off", "why": "local"}))
        blind = identify(uas=GOOGLEBOT, address=None)
        self.assertEqual(blind.status, "self_reported")
        self.assertIn("verify.no-address", reason_ids(blind))

    def test_agent_range_without_a_claim_is_infrastructure(self):
        found = identify(address=first_address("openai-chatgpt-user"))
        self.assertIsNone(found.entry)
        self.assertEqual((found.infrastructure["operator"], found.evidence), ("OpenAI", ("ip_range",)))

    def test_candidates_list_every_name_found(self):
        found = identify(uas=CHATGPT_USER, address=first_address("openai-chatgpt-user"))
        methods = {(c["name"], c["layer"], c["method"]) for c in found.candidates}
        self.assertEqual(methods, {("chatgpt-user", "name", "ua"), ("chatgpt-user", "verify", "ip")})


if __name__ == "__main__":
    unittest.main()
