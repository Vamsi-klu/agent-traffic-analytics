"""Builds signers.json and keys.json (S3.1): the Web Bot Auth signers cake can name, and each one's key directory as
fetched, for the verification layer (S3.2).

    build_signers(recipe, botscent_signers, fetch, previous, now) -> (signers, directories, responses)

Signers are botscent's signers.json plus sources.json "signers.extra"; a "signers.signing" note (a signer reported to
have stopped signing requests, which its directory cannot show) is copied onto the signer, whose keys stay bundled so
that its signatures verify again if it signs again. Keys stay grouped by signer host: the architecture draft
(draft-meunier-web-bot-auth-architecture-01, section 5.4) looks a key up by signer and key, never by keyid alone. Each
directory response is kept with its signature headers and body (section 5.5.3, appendix B), so whether a signer really
published these keys can be checked later. A key whose expiry only rolls forward (every fetch answers "now plus N
days", as chatgpt.com does) is bundled with rolling_expiry_s instead of exp, following botscent's key watch
(scripts/keys.ts, MIT, 7f948003): bundling that exp would end verification a few days after each release.
"""
import json


def _real(mapping):
    return {key: value for key, value in mapping.items() if not key.startswith("$")}


def roll_expiry(fresh, previous, previous_fetched, now, tolerance):
    """The fresh keys of one signer, with a rolling expiry replaced by rolling_expiry_s (times in epoch seconds).

    A key keeps rolling when the previous snapshot had it rolling with the same nbf and the fresh exp is again about
    now plus that lifetime; it starts rolling when its exp moved by exactly the time between the two fetches."""
    out = []
    for key in fresh:
        old = next((k for k in previous if k.get("x") == key["x"]), None)
        expiry = key.get("exp")

        def rolls(lifetime):
            return expiry is not None and abs(expiry - now - lifetime) < tolerance

        if old and "rolling_expiry_s" in old and old.get("nbf") == key.get("nbf") and rolls(old["rolling_expiry_s"]):
            lifetime = old["rolling_expiry_s"]
        elif (old and old.get("exp") is not None and expiry is not None and old["exp"] != expiry
              and previous_fetched is not None and rolls(old["exp"] - previous_fetched)):
            lifetime = round(expiry - now)
        else:
            out.append(key)
            continue
        out.append({**{k: v for k, v in key.items() if k != "exp"}, "rolling_expiry_s": lifetime})
    return out


def ed25519_keys(body, fields):
    """The Ed25519 OKP keys of a directory body, with only the fields the verifier reads."""
    keys = json.loads(body).get("keys") or []
    return [{field: key[field] for field in fields if field in key} for key in keys
            if key.get("kty") == "OKP" and key.get("crv") == "Ed25519" and isinstance(key.get("x"), str)]


def build_signers(recipe, botscent_signers, fetch, previous, now):
    """previous: ({host: [JWK]}, {host: fetched epoch seconds}) of the snapshot in use, for rolling expiries."""
    previous_keys, previous_fetched = previous
    hosts = dict(botscent_signers)
    hosts.update({host: extra["name"] for host, extra in _real(recipe["extra"]).items()})
    signing = _real(recipe["signing"])
    unknown = sorted(set(signing) - set(hosts))
    if unknown:
        raise ValueError(f"signers.signing names hosts that are not signers: {', '.join(unknown)}")
    signers, directories, responses = {}, {}, {}
    for host in sorted(hosts):
        url = recipe["directory"].format(host=host)
        response = fetch(url, accept=recipe["accept"])
        body = response.body.decode("utf-8")
        fresh = ed25519_keys(body, recipe["key_fields"])
        if not fresh:
            raise ValueError(f"{url}: no Ed25519 keys")
        directories[host] = roll_expiry(fresh, previous_keys.get(host, []), previous_fetched.get(host),
                                        now.timestamp(), recipe["rolling_tolerance_s"])
        responses[host] = {"url": url, "fetched_at": now.isoformat(timespec="seconds"), "status": response.status,
                           "headers": {name: response.headers[name] for name in recipe["response_headers"]
                                       if name in response.headers},
                           "body": body}
        signers[host] = {"name": hosts[host], "directory": url,
                         "source": "cake" if host in recipe["extra"] else "botscent",
                         **({"signing": signing[host]} if host in signing else {})}
    return signers, directories, responses
