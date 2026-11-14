"""Ed25519 verification (agentcake.detect.ed25519) against RFC 8032.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The five Ed25519 vectors of RFC 8032 section 7.1 verify; changing one bit of the message, the signature or the public
key makes them fail; malformed input (wrong lengths, S out of range, points that are not on the curve or not encoded
canonically) is rejected without an exception. Two signature bases built by other implementations of RFC 9421 (the
signed directory responses of cloudflare/web-bot-auth and of draft-ietf-webbotauth-httpsig-protocol-01) verify too.
"""
import base64, json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentcake.detect import ed25519  # noqa: E402  (the repository root has to be on sys.path first)

VECTORS_DIR = os.path.join(ROOT, "tests", "vectors", "web-bot-auth")

# RFC 8032 section 7.1, "Test Vectors for Ed25519": name -> (public key, message, signature), all hex.
RFC8032_VECTORS = {
    "TEST 1": (
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    "TEST 2": (
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    "TEST 3": (
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
    "TEST 1024": (
        "278117fc144c72340f67d0f2316e8386ceffbf2b2428c9c51fef7c597f1d426e",
        (
            "08b8b2b733424243760fe426a4b54908632110a66c2f6591eabd3345e3e4eb98fa6e264bf09efe12ee50f8f54e9f77b1e355f6c5"
            "0544e23fb1433ddf73be84d879de7c0046dc4996d9e773f4bc9efe5738829adb26c81b37c93a1b270b20329d658675fc6ea534e0"
            "810a4432826bf58c941efb65d57a338bbd2e26640f89ffbc1a858efcb8550ee3a5e1998bd177e93a7363c344fe6b199ee5d02e82"
            "d522c4feba15452f80288a821a579116ec6dad2b3b310da903401aa62100ab5d1a36553e06203b33890cc9b832f79ef80560ccb9"
            "a39ce767967ed628c6ad573cb116dbefefd75499da96bd68a8a97b928a8bbc103b6621fcde2beca1231d206be6cd9ec7aff6f6c9"
            "4fcd7204ed3455c68c83f4a41da4af2b74ef5c53f1d8ac70bdcb7ed185ce81bd84359d44254d95629e9855a94a7c1958d1f8ada5"
            "d0532ed8a5aa3fb2d17ba70eb6248e594e1a2297acbbb39d502f1a8c6eb6f1ce22b3de1a1f40cc24554119a831a9aad6079cad88"
            "425de6bde1a9187ebb6092cf67bf2b13fd65f27088d78b7e883c8759d2c4f5c65adb7553878ad575f9fad878e80a0c9ba63bcbcc"
            "2732e69485bbc9c90bfbd62481d9089beccf80cfe2df16a2cf65bd92dd597b0707e0917af48bbb75fed413d238f5555a7a569d80"
            "c3414a8d0859dc65a46128bab27af87a71314f318c782b23ebfe808b82b0ce26401d2e22f04d83d1255dc51addd3b75a2b1ae078"
            "4504df543af8969be3ea7082ff7fc9888c144da2af58429ec96031dbcad3dad9af0dcbaaaf268cb8fcffead94f3c7ca495e056a9"
            "b47acdb751fb73e666c6c655ade8297297d07ad1ba5e43f1bca32301651339e22904cc8c42f58c30c04aafdb038dda0847dd988d"
            "cda6f3bfd15c4b4c4525004aa06eeff8ca61783aacec57fb3d1f92b0fe2fd1a85f6724517b65e614ad6808d6f6ee34dff7310fdc"
            "82aebfd904b01e1dc54b2927094b2db68d6f903b68401adebf5a7e08d78ff4ef5d63653a65040cf9bfd4aca7984a74d371459867"
            "80fc0b16ac451649de6188a7dbdf191f64b5fc5e2ab47b57f7f7276cd419c17a3ca8e1b939ae49e488acba6b965610b5480109c8"
            "b17b80e1b7b750dfc7598d5d5011fd2dcc5600a32ef5b52a1ecc820e308aa342721aac0943bf6686b64b2579376504ccc493d97e"
            "6aed3fb0f9cd71a43dd497f01f17c0e2cb3797aa2a2f256656168e6c496afc5fb93246f6b1116398a346f1a641f3b041e989f791"
            "4f90cc2c7fff357876e506b50d334ba77c225bc307ba537152f3f1610e4eafe595f6d9d90d11faa933a15ef1369546868a7f3a45"
            "a96768d40fd9d03412c091c6315cf4fde7cb68606937380db2eaaa707b4c4185c32eddcdd306705e4dc1ffc872eeee475a64dfac"
            "86aba41c0618983f8741c5ef68d3a101e8a3b8cac60c905c15fc910840b94c00a0b9d0"
        ),
        "0aab4c900501b3e24d7cdf4663326a3a87df5e4843b2cbdb67cbf6e460fec350"
        "aa5371b1508f9f4528ecea23c436d94b5e8fcd4f681e30a6ac00a9704a188a03",
    ),
    "TEST SHA(abc)": (
        "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
        (
            "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423"
            "643ce80e2a9ac94fa54ca49f"
        ),
        "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
        "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704",
    ),
}


# RFC 8032 section 5.1: the field prime, d, the group order L, and 2^255 for building encodings by hand.
P = 2**255 - 19
D = -121665 * pow(121666, P - 2, P) % P
L = 2**252 + 27742317777372353535851937790883648493
SIGN_BIT = 1 << 255


def vector(name):
    public_key, message, signature = RFC8032_VECTORS[name]
    return bytes.fromhex(public_key), bytes.fromhex(message), bytes.fromhex(signature)


def flip_bit(data, index):
    """The same bytes with one bit of byte index inverted."""
    changed = bytearray(data)
    changed[index] ^= 1
    return bytes(changed)


def encode_y(y, x_sign=0):
    """A 32-byte point encoding with the given y and x-sign bit, without checking that a point exists."""
    return (y | (SIGN_BIT if x_sign else 0)).to_bytes(32, "little")


class Rfc8032Vectors(unittest.TestCase):
    def test_every_section_7_1_vector_verifies(self):
        for name in RFC8032_VECTORS:
            with self.subTest(name):
                self.assertTrue(ed25519.verify(*vector(name)))

    def test_the_1024_vector_has_its_1023_byte_message(self):
        # guards the transcription of the longest vector
        self.assertEqual(len(vector("TEST 1024")[1]), 1023)

    def test_a_changed_message_does_not_verify(self):
        for name in RFC8032_VECTORS:
            public_key, message, signature = vector(name)
            changed = flip_bit(message, len(message) // 2) if message else b"\x00"
            with self.subTest(name):
                self.assertFalse(ed25519.verify(public_key, changed, signature))

    def test_a_changed_signature_does_not_verify(self):
        for name in RFC8032_VECTORS:
            public_key, message, signature = vector(name)
            for index in (0, 31, 32, 63):  # both halves: the point R and the scalar S
                with self.subTest(name, byte=index):
                    self.assertFalse(ed25519.verify(public_key, message, flip_bit(signature, index)))

    def test_a_changed_public_key_does_not_verify(self):
        for name in RFC8032_VECTORS:
            public_key, message, signature = vector(name)
            with self.subTest(name):
                self.assertFalse(ed25519.verify(flip_bit(public_key, 0), message, signature))

    def test_a_signature_from_another_vector_does_not_verify(self):
        public_key, message, _ = vector("TEST 2")
        self.assertFalse(ed25519.verify(public_key, message, vector("TEST 3")[2]))


class MalformedInput(unittest.TestCase):
    def setUp(self):
        self.public_key, self.message, self.signature = vector("TEST 3")

    def test_wrong_lengths_are_rejected(self):
        for public_key, signature in ((self.public_key[:-1], self.signature),
                                      (self.public_key + b"\x00", self.signature),
                                      (self.public_key, self.signature[:-1]),
                                      (self.public_key, self.signature + b"\x00"),
                                      (b"", b"")):
            with self.subTest(public_key=len(public_key), signature=len(signature)):
                self.assertFalse(ed25519.verify(public_key, self.message, signature))

    def test_s_must_be_below_the_group_order(self):
        # S + L satisfies the group equation just like S; RFC 8032 5.1.7 step 1 still requires 0 <= S < L
        s = int.from_bytes(self.signature[32:], "little") + L
        malleated = self.signature[:32] + s.to_bytes(32, "little")
        self.assertTrue(ed25519.verify(self.public_key, self.message, self.signature))
        self.assertFalse(ed25519.verify(self.public_key, self.message, malleated))

    def test_a_public_key_that_is_not_on_the_curve_is_rejected(self):
        y = 2
        x_squared = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
        self.assertEqual(pow(x_squared, (P - 1) // 2, P), P - 1, "Euler: no x exists for this y")
        self.assertFalse(ed25519.is_valid_public_key(encode_y(y)))
        self.assertFalse(ed25519.verify(encode_y(y), self.message, self.signature))

    def test_non_canonical_y_is_rejected(self):
        # y = p + 1 would reduce to y = 1, the neutral point, if decoding did not check y < p (RFC 8032 5.1.3 step 1)
        self.assertFalse(ed25519.is_valid_public_key(encode_y(P + 1)))
        self.assertTrue(ed25519.is_valid_public_key(encode_y(1)))
        non_canonical_r = encode_y(P + 1) + self.signature[32:]
        self.assertFalse(ed25519.verify(self.public_key, self.message, non_canonical_r))

    def test_x_zero_with_the_sign_bit_set_is_rejected(self):
        # y = 1 gives x = 0, and RFC 8032 5.1.3 step 4 fails decoding when x = 0 but the sign bit is 1
        self.assertFalse(ed25519.is_valid_public_key(encode_y(1, x_sign=1)))

    def test_the_vector_keys_are_valid(self):
        for name in RFC8032_VECTORS:
            with self.subTest(name):
                self.assertTrue(ed25519.is_valid_public_key(vector(name)[0]))


class SignatureBasesFromOtherImplementations(unittest.TestCase):
    """Raw Ed25519 over RFC 9421 signature bases that other implementations built and signed."""

    def check(self, public_key_b64url, base, signature_b64):
        public_key = base64.urlsafe_b64decode(public_key_b64url + "=" * (-len(public_key_b64url) % 4))
        signature = base64.b64decode(signature_b64)
        self.assertTrue(ed25519.verify(public_key, base.encode(), signature))
        self.assertFalse(ed25519.verify(public_key, base.encode() + b" ", signature))

    def test_cloudflare_signed_directory_response(self):
        with open(os.path.join(VECTORS_DIR, "web_bot_auth_directory_response_v1.json"), encoding="utf-8") as file:
            vector_ = json.load(file)[0]
        header = vector_["response"]["headers"]["Signature"]
        self.check(vector_["public_key"]["x"], vector_["signature_base"], header.split("=", 1)[1].strip(":"))

    def test_draft_signed_directory_response(self):
        with open(os.path.join(VECTORS_DIR, "draft-ietf-webbotauth-httpsig-protocol-01.json"), encoding="utf-8") as f:
            vector_ = json.load(f)["E.2.3"]
        self.check(vector_["public_key_x"], vector_["signature_base"], vector_["signature"])


if __name__ == "__main__":
    unittest.main()
