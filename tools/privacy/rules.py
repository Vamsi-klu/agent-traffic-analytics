"""What a privacy scan looks for, built from tools/privacy/rules.json.

Rules(canaries, secret, extra_own).find(text) returns the kind of every thing in text that an AgentCake data folder
must never hold, one entry per occurrence, in CATEGORIES' terms; never the text that matched, so that a scan can
only say how many and where. Each kind and what it leaves out (with why) is in rules.json:

    ipv4, ipv6      an address other than cake's own listen addresses (and the scanned folder's public_listen host);
                    not a version number after a product token or in a version field
    canary          a string the test typed into the page (given on the command line), in any letter case
    card_number     Luhn-valid, 13-19 digits, standing alone, in one piece or in printed groups, starting with 2-6
    test_card       the same, when it is a well-known test number (4242 4242 4242 4242)
    key_name        a field naming a pressed key: "key":"a", 'code': 'KeyA', "keyCode": 65
    cookie          a cookie header line or field with a value
    authorization   an authorization header line or field with a value, or a Bearer token
    private_key     a PEM private key block, or a JWK with its private member d
    srv_secret      the value of the scanned folder's server-half secret
    email           an address shape, but not an asset name such as logo@2x.png
"""
import ipaddress
import json
import os
import re

from agentcake import paths

RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")
PRIVACY_FILE = os.path.join(paths.PACKAGE_DIR, "data", "privacy.json")
CATEGORIES = ("ipv4", "ipv6", "canary", "card_number", "test_card", "key_name", "cookie", "authorization",
              "private_key", "srv_secret", "email")

# protocol: shapes of the things looked for. Each needs a non-word character (or the text's edge) on both sides.
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)")
IPV6 = re.compile(r"(?<![\w:.])[0-9A-Fa-f]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?![\w:.])")  # checked by ipaddress
CARD = re.compile(r"(?<![\w.])\d(?:[ -]?\d){12,18}(?!\w|\.\d)")
SEPARATOR = re.compile(r"[ -]")
EMAIL = re.compile(r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.([A-Za-z]{2,})(?![\w-])")
PEM_PRIVATE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
FLAT_OBJECT = re.compile(r"\{[^{}]*\}")  # a JSON object with no object inside, as a JWK is
JWK_KTY = re.compile(r"[\"']kty[\"']\s*:")
OCTET_MAX = 255  # protocol: an IPv4 address is four numbers of 0-255
LUHN_DOUBLE_OVER = 9  # protocol: Luhn subtracts 9 from a doubled digit over 9
DECIMAL = 10


def load_rules():
    with open(RULES_FILE, encoding="utf-8") as f:
        return json.load(f)


def luhn_valid(digits):
    total = 0
    for position, char in enumerate(reversed(digits)):
        digit = int(char)
        if position % 2:  # every second digit from the right is doubled
            digit *= 2
            if digit > LUHN_DOUBLE_OVER:
                digit -= LUHN_DOUBLE_OVER
        total += digit
    return total % DECIMAL == 0


class Rules:
    def __init__(self, canaries=(), secret=None, extra_own=(), data=None):
        self.data = data or load_rules()
        own = list(self.data["own_addresses"]["addresses"]) + [a for a in extra_own if a]
        self.own = {ipaddress.ip_address(a) for a in own if _is_address(a)}
        version = self.data["version_before_address"]
        self.version_before = re.compile(version["pattern"], re.I if "i" in version["flags"] else 0)
        self.look_back = version["look_back"]
        self.canaries = [re.compile(re.escape(c), re.I) for c in canaries if c]
        self.secret = secret or None
        self.key_text, self.key_number = _key_patterns(self.data["key_fields"])
        self.cookie = _header_pattern(self.data["header_fields"]["cookie"])
        self.authorization = _header_pattern(self.data["header_fields"]["authorization"])
        self.bearer = re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{%d,}=*" % self.data["header_fields"]["bearer_min_chars"])
        self.jwk_d = re.compile(r"[\"']d[\"']\s*:\s*[\"'][A-Za-z0-9_-]{%d,}" % self.data["private_key"]["jwk_d_min_chars"])
        self.not_tld = {name.lower() for name in self.data["email"]["not_top_level"]}
        self.test_cards = set(self.data["test_cards"]["numbers"])

    def find(self, text):
        """The kind of each thing found in text (a str), one entry per occurrence."""
        found, lower = [], text.lower()
        if "." in text:
            found += ["ipv4" for m in IPV4.finditer(text) if self._foreign_ipv4(text, m)]
        if "::" in text or text.count(":") > 1:
            found += ["ipv6" for m in IPV6.finditer(text) if self._foreign_ipv6(m.group(0))]
        found += ["canary" for pattern in self.canaries for _ in pattern.finditer(text)]
        found += [kind for m in CARD.finditer(text) for kind in [self._card(m.group(0))] if kind]
        if "key" in lower or "code" in lower or "char" in lower or "which" in lower:
            found += ["key_name"] * (len(self.key_text.findall(text)) + len(self.key_number.findall(text)))
        if "cookie" in lower:
            found += ["cookie"] * len(self.cookie.findall(text))
        if "authorization" in lower:
            found += ["authorization"] * len(self.authorization.findall(text))
        if "bearer" in lower:
            found += ["authorization"] * len(self.bearer.findall(text))
        if "private key" in lower or "kty" in lower:
            found += ["private_key"] * (len(PEM_PRIVATE.findall(text)) + self._jwk_private(text))
        if self.secret:
            found += ["srv_secret"] * text.count(self.secret)
        if "@" in text:
            found += ["email" for m in EMAIL.finditer(text) if m.group(1).lower() not in self.not_tld]
        return found

    def _foreign_ipv4(self, text, match):
        if any(int(part) > OCTET_MAX for part in match.group(0).split(".")):
            return False
        if self.version_before.search(text[max(0, match.start() - self.look_back):match.start()]):
            return False
        return ipaddress.ip_address(match.group(0)) not in self.own

    def _foreign_ipv6(self, candidate):
        if not re.search(r"[0-9A-Fa-f]", candidate):  # "::" alone: CSS's ::-webkit-..., never a visitor
            return False
        try:
            address = ipaddress.IPv6Address(candidate)
        except ValueError:  # a time (20:09:54), a MAC address, a selector
            return False
        return address not in self.own

    def _card(self, written):
        card = self.data["card"]
        digits = SEPARATOR.sub("", written)
        if not card["min_digits"] <= len(digits) <= card["max_digits"] or digits[0] not in card["first_digits"]:
            return None
        separators = set(SEPARATOR.findall(written))
        if len(separators) > 1 or not luhn_valid(digits):
            return None
        if separators:
            groups = [len(group) for group in SEPARATOR.split(written)]
            size = card["group_size"]
            printed = all(n == size for n in groups[:-1]) and 0 < groups[-1] <= size
            if not printed and groups not in card["other_groupings"]:
                return None
        return "test_card" if digits in self.test_cards else "card_number"

    def _jwk_private(self, text):
        if not JWK_KTY.search(text):
            return 0
        return sum(1 for m in FLAT_OBJECT.finditer(text) if JWK_KTY.search(m.group(0)) and self.jwk_d.search(m.group(0)))


def _is_address(text):
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def _key_patterns(fields):
    """("key": one character or a key name) and ("keyCode": a number) patterns, quoted either way."""
    with open(PRIVACY_FILE, encoding="utf-8") as f:
        classes = json.load(f)["page"]["key_classes"]
    names = [re.escape(name) for name in list(classes["named"]) + fields["names"] if name]
    names += [re.escape(prefix) + "[A-Za-z]+" for prefix in classes["prefixes"]] + fields["patterns"]
    one_char = r"[^\"'\\]|\\u[0-9a-fA-F]{4}|\\."
    text_names = "|".join(map(re.escape, fields["text"]))
    number_names = "|".join(map(re.escape, fields["number"]))
    value = "(?:%s|%s)" % ("|".join(names), one_char)
    return (re.compile(r"[\"'](?:%s)[\"']\s*:\s*[\"']%s[\"']" % (text_names, value)),
            re.compile(r"[\"'](?:%s)[\"']\s*:\s*\d+" % number_names))


def _header_pattern(names):
    """A header line ("Cookie: x") or a field with a value ("cookie": "x"), any letter case."""
    alternatives = "|".join(map(re.escape, names))
    return re.compile(r"[\"'](?:%s)[\"']\s*:\s*[\"'][^\"']+|^\s*(?:%s)\s*:\s*\S" % (alternatives, alternatives),
                      re.I | re.M)
