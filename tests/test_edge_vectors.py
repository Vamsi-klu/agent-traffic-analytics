"""Shared server-half token vectors (S4.1): the Node middleware and cake make and read the same tokens, byte for byte.

    python3 -I -m unittest discover -s tests -v      (from the cake folder)

tests/vectors/edge_token.json is shared with the Node middleware (edge/node/test/vectors.test.js). SharedVectors checks
the file with the standard library alone (hmac, hashlib, base64, json, ipaddress), so the format does not rest on
either implementation. AgentcakeEdgeToken checks cake's own code against it: agentcake/edge_token.py makes every
vector's token from the vector's request and reads every token as the file says, and netfacts.py computes the same
network keys. CrossLanguage has cake make tokens for 300 more requests and the Node middleware verify and remake each.
"""
import base64, hashlib, hmac, ipaddress, json, os, random, re, shutil, subprocess, sys, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from agentcake import config, edge_token, netfacts  # noqa: E402  (the repository root first, so no wheel is needed)

with open(os.path.join(HERE, "vectors", "edge_token.json"), encoding="utf-8") as f:
    VECTORS = json.load(f)
RULES = VECTORS["rules"]
BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
SAFE_INTEGER = 2 ** 53 - 1  # protocol: the integers JSON numbers hold exactly in JavaScript, where tokens are made
HEXTET_BYTES = 2  # protocol: an IPv6 group
BYTE_BITS = 8  # protocol


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text):
    """base64url without padding, in its one spelling (spare bits zero), else ValueError."""
    if not BASE64URL.fullmatch(text):
        raise ValueError("not base64url")
    data = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if b64url(data) != text:
        raise ValueError("not the canonical spelling")
    return data


def mac(secret, text):
    return hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).digest()


def sign(secret, payload):
    """The token for a payload: compact JSON (keys in their order, no ASCII escaping), base64url, HMAC-SHA256."""
    body = b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signed = f"{RULES['token_prefix']}.{body}"
    return f"{signed}.{b64url(mac(secret, signed))}"


def is_payload(payload):
    def integer(value):
        return type(value) is int and -SAFE_INTEGER <= value <= SAFE_INTEGER
    return (isinstance(payload, dict) and integer(payload.get("v")) and payload["v"] == RULES["payload_version"]
            and isinstance(payload.get("id"), str) and payload["id"] != "" and integer(payload.get("t")))


def verify(secret, token, now_ms):
    """('ok' | 'stale' | 'bad', payload or None), by the rules cake applies to a token it receives."""
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != RULES["token_prefix"] or not all(BASE64URL.fullmatch(p) for p in parts[1:]):
        return "bad", None
    if not hmac.compare_digest(b64url(mac(secret, f"{parts[0]}.{parts[1]}")), parts[2]):
        return "bad", None
    try:
        payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
    except ValueError:
        return "bad", None
    if not is_payload(payload):
        return "bad", None
    if payload["t"] > now_ms + RULES["max_future_ms"] or now_ms - payload["t"] > RULES["max_age_ms"]:
        return "stale", payload
    return "ok", payload


def ip_prefix(ip):
    """The /24 of an IPv4 address or the /48 of an IPv6 one, written as cake 0.3.3's ip_prefix writes it."""
    try:
        address = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.version == 4:
        bits = RULES["ipv4_prefix_bits"]
        return f"{ipaddress.ip_network(f'{address}/{bits}', strict=False).network_address}/{bits}"
    # The groups from the address's bytes: .exploded raises for an address with a zone ("fe80::1%eth0").
    bits = RULES["ipv6_prefix_bits"]
    packed = address.packed
    groups = [int.from_bytes(packed[i:i + HEXTET_BYTES], "big") for i in range(0, bits // BYTE_BITS, HEXTET_BYTES)]
    return ":".join(format(group, "x") for group in groups) + f"::/{bits}"


def network_key(secret, ip, now_ms):
    prefix = ip_prefix(ip)
    if prefix is None:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime(now_ms / 1000))
    digest = hmac.new(secret.encode("utf-8"), f"{RULES['network_key_label']}|{day}|{prefix}".encode(), hashlib.sha256)
    return digest.hexdigest()[:RULES["network_key_hex_chars"]]


class SharedVectors(unittest.TestCase):
    def secret(self, name):
        return VECTORS["secrets"][name]

    def test_every_page_token_verifies_to_its_payload(self):
        pages = [v for v in VECTORS["mint"] if v["token"]]
        self.assertTrue(pages)
        for v in pages:
            with self.subTest(v["name"]):
                self.assertEqual(verify(self.secret(v["secret"]), v["token"], v["now_ms"]), ("ok", v["payload"]))

    def test_python_makes_the_same_token_from_the_same_payload(self):
        for v in VECTORS["mint"]:
            if v["token"]:
                with self.subTest(v["name"]):
                    self.assertEqual(sign(self.secret(v["secret"]), v["payload"]), v["token"])

    def test_every_verify_vector_gives_its_result(self):
        for v in VECTORS["verify"]:
            with self.subTest(v["name"]):
                result, payload = verify(self.secret(v["secret"]), v["token"], v["now_ms"])
                self.assertEqual(result, v["result"])
                if result == "ok":
                    self.assertEqual(payload, v["payload"])

    def test_network_keys_and_prefixes_match(self):
        for v in VECTORS["network_keys"]:
            with self.subTest(v["name"]):
                self.assertEqual(ip_prefix(v["ip"]), v["prefix"])
                self.assertEqual(network_key(self.secret(v["secret"]), v["ip"], v["now_ms"]), v["key"])

    def test_page_tokens_carry_the_network_key_of_their_client(self):
        for v in VECTORS["mint"]:
            if v["token"]:
                with self.subTest(v["name"]):
                    expected = network_key(self.secret(v["secret"]), v["client_ip"], v["now_ms"]) if v["client_ip"] else None
                    self.assertEqual(v["payload"]["ik"], expected)

    def test_no_token_holds_the_client_address_or_its_prefix(self):
        for v in VECTORS["mint"]:
            if v["token"] and v["client_ip"]:
                with self.subTest(v["name"]):
                    text = b64url_decode(v["token"].split(".")[1]).decode("utf-8")
                    network = ip_prefix(v["client_ip"]).split("/")[0].removesuffix("::").removesuffix(".0")
                    self.assertNotIn(v["client_ip"].strip(), text)
                    self.assertNotIn(network, text)


def secret_bytes(name):
    return VECTORS["secrets"][name].encode("utf-8")


class AgentcakeEdgeToken(unittest.TestCase):
    def test_mint_makes_every_vector_token_from_its_request(self):
        for v in VECTORS["mint"]:
            with self.subTest(v["name"]):
                r = v["request"]
                token = edge_token.mint(secret_bytes(v["secret"]), r["method"], r["path"], r["headers"], v["now_ms"],
                                        ip=v["client_ip"], token_id=v["id"], verdict=v["verdict"], version=v["version"])
                self.assertEqual(token, v["token"])

    def test_read_token_gives_every_verify_vector_its_result(self):
        for v in VECTORS["verify"]:
            with self.subTest(v["name"]):
                result, payload = edge_token.read_token(secret_bytes(v["secret"]), v["token"], v["now_ms"])
                self.assertEqual(result, v["result"])
                if result == "ok":
                    self.assertEqual(payload, v["payload"])

    def test_the_age_window_is_the_vectors_window(self):
        self.assertEqual(config.DEFAULTS["token_max_age_ms"], RULES["max_age_ms"])  # settings since S1.2 (defaults.json)
        self.assertEqual(config.DEFAULTS["token_max_future_ms"], RULES["max_future_ms"])

    def test_netfacts_computes_every_network_key(self):
        for v in VECTORS["network_keys"]:
            with self.subTest(v["name"]):
                self.assertEqual(netfacts.ip_prefix(v["ip"]), v["prefix"])
                self.assertEqual(netfacts.network_key(secret_bytes(v["secret"]), v["ip"], v["now_ms"]), v["key"])

    def test_cake_and_the_node_middleware_hold_the_same_values(self):
        with open(os.path.join(ROOT, "edge", "node", "defaults.json"), encoding="utf-8") as f:
            node = json.load(f)
        with open(os.path.join(ROOT, "edge", "node", "headers.json"), encoding="utf-8") as f:
            node_headers = json.load(f)
        edge = edge_token.EDGE
        for key in ("token_prefix", "payload_version", "entry_name", "token_id_bytes", "page_method", "page_dest", "page_type",
                    "markdown_type", "verdict_types", "verdict_id_max", "verdict_reasons_max", "version_max"):
            self.assertEqual(edge[key], node["fixed"][key], key)
        for key in ("cut", "max_header_names", "skip_extensions"):
            self.assertEqual(edge[key], node["options"][key], key)
        for role, name in edge["headers"].items():
            self.assertEqual(name, node_headers[role], role)

    def test_a_minted_token_reads_back_and_rides_its_entry(self):
        secret = secret_bytes("main")
        now = VECTORS["mint"][0]["now_ms"]
        lines = [("Accept", "text/html"), ("Sec-Fetch-Dest", "document")]
        first, second = (edge_token.mint(secret, "GET", "/demo", lines, now, ip="203.0.113.9") for _ in range(2))
        self.assertEqual(edge_token.read_token(secret, first, now)[0], "ok")
        self.assertNotEqual(first, second, "a fresh random id each time")
        self.assertEqual(edge_token.entry(first), f'cake;desc="{first}"')
        self.assertIsNone(edge_token.mint(None, "GET", "/demo", lines, now), "no secret: no token")


# ---------------------------------------------------------------- many more requests, in both languages
NAMES = ["Host", "Connection", "User-Agent", "Accept", "Accept-Language", "Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-Dest",
         "Sec-Fetch-User", "Sec-Purpose", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "Signature-Agent", "Signature",
         "Signature-Input", "Cookie", "Referer", "X_Under_Score", "X.Dot", "X-" + "n" * 70, "\u00dcber"]
CHOICES = {
    "accept": ["text/html", "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8", "*/*", "text/markdown, text/html;q=0.9",
               "application/json", " TEXT/HTML ; q=1 ", "", "text/html\u0085"],
    "sec-fetch-dest": ["document"] * 6 + ["DOCUMENT", "iframe", "script", "empty", " document\t", "document\u0085", "doc ument"],
}
PAGE_LIKE = ["Sec-Fetch-Dest", "Accept"]  # most requests carry one, so that many of them are pages
PATH_PARTS = ["products", "cake", "shop", "about"] * 4 + ["", ".", "..", "...", ".env", "a.b", "x.html", "logo.PNG", "app.js",
                                                         "%41b", "~u", "a;b", "c@d", "e:f", "%", "Q?x=1", "R#frag", "s.css?v=2"]
ADDRESSES = ["203.0.113.77", "198.51.100.1", "2001:db8::5", "::ffff:203.0.113.7", "fe80::1%eth0", "300.1.1.1", "", None,
             "unknown", " 203.0.113.8 "]
VERDICTS = [None, {"type": "agent", "agent_name": "chatgpt-agent", "reasons": ["web-bot-auth"]}, {"type": "human", "reasons": []},
            {"type": "maybe"}, {"type": "agent", "agent_name": "x" * 90, "reasons": ["ok", "bad id!", 5, "a.b-c_d"]}]
NOISE = [chr(c) for c in range(0x20, 0x7f)] + ["\u00e9", "\u00fc", "\u00ff", "\u00a0", "\x01", "\x07", "\x7f", "\t", "\u0085"]


def noise(rng):
    text = "".join(rng.choice(NOISE) for _ in range(rng.choice([0, 3, 30, 300])))
    return rng.choice(["", " ", "\t"]) + text + rng.choice(["", " ", "\t "])


def random_case(rng, n):
    """One request built from the parts above; the seed makes the same 300 requests on every run."""
    lines = []
    names = rng.sample(NAMES, rng.randrange(len(NAMES)))
    names += [name for name in PAGE_LIKE if name not in names and rng.random() < 0.9]
    for name in names:
        pool = CHOICES.get(name.lower())
        lines.append([name, rng.choice(pool) if pool and rng.random() < 0.8 else noise(rng)])
    if lines and rng.random() < 0.2:
        lines.append(list(rng.choice(lines)))  # a line sent twice
    path = "/" + "/".join(rng.choice(PATH_PARTS) for _ in range(rng.randrange(1, 4)))
    return {"secret": rng.choice(["main", "other"]), "request": {"method": rng.choice(["GET"] * 6 + ["POST", "HEAD", "get"]),
            "path": path, "headers": lines}, "now_ms": VECTORS["mint"][0]["now_ms"] + rng.randrange(10 * 86400000),
            "id": f"cross-{n}", "client_ip": rng.choice(ADDRESSES), "verdict": rng.choice(VERDICTS),
            "version": rng.choice([None, "1.2.0", "bad version!", "9" * 50])}


@unittest.skipUnless(shutil.which("node"), "node is not installed: the Node half of the check cannot run")
class CrossLanguage(unittest.TestCase):
    def test_node_verifies_and_remakes_every_token_cake_makes(self):
        rng = random.Random(4110)
        cases = [random_case(rng, n) for n in range(300)]
        for c in cases:
            r = c["request"]
            c["token"] = edge_token.mint(secret_bytes(c["secret"]), r["method"], r["path"], r["headers"], c["now_ms"],
                                         ip=c["client_ip"], token_id=c["id"], verdict=c["verdict"], version=c["version"])
            c["secret"] = VECTORS["secrets"][c["secret"]]
        self.assertGreater(sum(1 for c in cases if c["token"]), 80, "enough of them are pages (97 with this seed)")
        script = os.path.join(ROOT, "edge", "node", "scripts", "cross-check.js")
        run = subprocess.run(["node", script], input=json.dumps(cases), capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        for c, node in zip(cases, json.loads(run.stdout)):
            with self.subTest(c["id"]):
                self.assertEqual(node["token"], c["token"], "the same token from the same request")
                self.assertEqual(node["result"], "ok" if c["token"] else None)


if __name__ == "__main__":
    unittest.main()
