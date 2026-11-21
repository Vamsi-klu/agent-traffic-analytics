"""deploy/Caddyfile's trusted proxies: the address ranges Cloudflare publishes, from the lists that ship with AgentCake.

The Caddyfile in front of AgentCake (docker-compose.yml, SERVER.md) trusts Cloudflare's proxies, so that a subdomain
someone sets to Proxied still hands AgentCake the visitor's address (CF-Connecting-IP) instead of Cloudflare's. The
ranges are never copied by hand. `release.py refresh` writes them into the Caddyfile's trusted_proxies line from the
lists it has just built, and `release.py build` refuses a commit whose Caddyfile names other ranges than its lists,
so a release never ships the two apart (release.json "caddyfile": the file, the lists' file and entry, the line).

    ranges(tree, settings)    the entry's ranges in the lists, IPv4 then IPv6, in the lists' order
    named(tree, settings)     the ranges the Caddyfile's line names
    refresh(tree, settings)   writes ranges() into that line, the rest of the file as it is; True when it changed
    check(tree, settings)     raises ReleaseError while the two differ
"""
import json
import os

from tools.releasing.settings import ReleaseError

COMMENT = "#"  # protocol: a Caddyfile token that starts with # comments out the rest of the line


def _rules(settings):
    return settings["caddyfile"]


def _path(tree, rel):
    return os.path.join(tree, *rel.split("/"))


def ranges(tree, settings):
    rules = _rules(settings)
    try:
        with open(_path(tree, rules["ranges_file"]), encoding="utf-8") as f:
            entries = json.load(f)["ranges"]
    except (OSError, KeyError, ValueError) as error:
        raise ReleaseError(f"cannot read the address ranges in {rules['ranges_file']}: {error}") from None
    entry = next((e for e in entries if e.get("id") == rules["range_id"]), None)
    found = [*entry.get("v4", []), *entry.get("v6", [])] if entry else []
    if not found:
        raise ReleaseError(f"{rules['ranges_file']} has no address ranges for {rules['range_id']!r}")
    return found


def _lines(tree, settings):
    """The Caddyfile's lines, and the index of its one trusted_proxies line."""
    rules = _rules(settings)
    try:
        with open(_path(tree, rules["file"]), encoding="utf-8", newline="") as f:
            lines = f.read().split("\n")
    except OSError as error:
        raise ReleaseError(f"cannot read {rules['file']}: {error}") from None
    head = rules["directive"]
    at = [index for index, line in enumerate(lines) if line.split()[:len(head)] == head]
    if len(at) != 1:
        raise ReleaseError(f"{rules['file']} needs exactly one line that starts with {' '.join(head)}; it has {len(at)}")
    return lines, at[0]


def named(tree, settings):
    lines, at = _lines(tree, settings)
    tokens = lines[at].split()[len(_rules(settings)["directive"]):]
    return tokens[:next((i for i, token in enumerate(tokens) if token.startswith(COMMENT)), len(tokens))]


def refresh(tree, settings):
    lines, at = _lines(tree, settings)
    line = lines[at]
    written = line[:len(line) - len(line.lstrip())] + " ".join([*_rules(settings)["directive"], *ranges(tree, settings)])
    if written == line:
        return False
    lines[at] = written
    path = _path(tree, _rules(settings)["file"])
    with open(path + ".tmp", "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    os.replace(path + ".tmp", path)
    return True


def check(tree, settings):
    rules = _rules(settings)
    if named(tree, settings) != ranges(tree, settings):
        raise ReleaseError(f"{rules['file']} trusts other ranges than {rules['ranges_file']} has for "
                           f"{rules['range_id']!r}: run `python3 -I tools/release.py refresh`, review and commit the "
                           "result, then build again")
