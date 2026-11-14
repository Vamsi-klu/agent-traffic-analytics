"""The signature on POST /edge: what `agentcake logs import` signs each batch
with (logs.py) and what Agent Cake checks before it reads one (edge_api.py), one implementation for both ends.

The header HEADER holds <prefix>.<time in ms>.<base64url HMAC-SHA256 of "<prefix>.<time>." followed by the body>,
keyed with the server half's secret (edge_secret.py); the header's name and the prefix are in data/logs.json "edge".
sign() makes the value. verified() takes it only for this secret and this body, at a time inside the page tokens'
window around now (the settings token_max_age_ms and token_max_future_ms).
"""
import hashlib
import hmac
import re

from agentcake.datafiles import load
from agentcake.edge_token import BASE64URL, b64url

EDGE = load("data/logs.json")["edge"]
HEADER = EDGE["header"]
SIGNATURE_PARTS = 3  # protocol: <prefix>.<time>.<mac>
DIGITS = re.compile(r"[0-9]+")


def sign(secret, body, now_ms):
    """The Cake-Edge-Signature value for this body, sent at now_ms."""
    return f"{EDGE['prefix']}.{now_ms}.{b64url(_mac(secret, now_ms, body))}"


def verified(secret, header, body, now_ms, c):
    """Whether header signs body with secret, at a time inside the page tokens' window around now_ms."""
    parts = str(header or "").split(".")
    if not secret or len(parts) != SIGNATURE_PARTS:
        return False
    prefix, sent, mac = parts
    if prefix != EDGE["prefix"] or not DIGITS.fullmatch(sent) or not BASE64URL.fullmatch(mac):
        return False
    sent_ms = int(sent)
    if sent_ms > now_ms + c["token_max_future_ms"] or now_ms - sent_ms > c["token_max_age_ms"]:
        return False
    return hmac.compare_digest(b64url(_mac(secret, sent_ms, body)), mac)


def _mac(secret, sent_ms, body):
    return hmac.new(secret, f"{EDGE['prefix']}.{sent_ms}.".encode("ascii") + body, hashlib.sha256).digest()
