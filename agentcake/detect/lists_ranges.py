"""Builds ip_ranges.json: each operator's published address list, read in its own format and collapsed into
CIDR blocks, kept in the lookup order of sources.json "ip_ranges".

    build_ranges(recipe, fetch) -> [range entry]      read_blocks(spec, bodies, published_fields) -> (blocks, published)

Formats: "prefixes" is Google's {"prefixes": [{"ipv4Prefix" | "ipv6Prefix"}]}, also used by OpenAI, Perplexity, Bing,
Apple, DuckDuckGo and Ahrefs; "aws" and "oracle" are those clouds' own JSON, "aws" with only the prefixes of the
services a range names when it names some (Amazon CloudFront's); "csv-first-column" (iCloud Private Relay,
DigitalOcean) and "lines" (Cloudflare) are text; "sail" is a SAIL file (draft-kelley-webbotauth-sail-00, Anthropic):
the prefix sets of the one named service. Like PostHog's refresh_bot_ip_ranges.py (PostHog/posthog 241e18e,
products/web_analytics/scripts/, MIT outside ee/; the idea and its two floors, kept in sources.json), an agent's or
bot's list holding a block wider than the floor is refused as an upstream mistake.
"""
import csv
import io
import ipaddress
import json


def _prefixes(text, spec):
    data = json.loads(text)
    return [p.get("ipv4Prefix") or p.get("ipv6Prefix") for p in data["prefixes"]], data


def _aws(text, spec):
    """Every prefix, or only those of spec's "services": each prefix names its service, AMAZON holding them all."""
    data = json.loads(text)
    prefixes = [(p["ip_prefix"], p.get("service")) for p in data["prefixes"]] + \
        [(p["ipv6_prefix"], p.get("service")) for p in data["ipv6_prefixes"]]
    wanted = spec.get("services")
    if wanted is None:
        return [block for block, _ in prefixes], data
    missing = sorted(set(wanted) - {service for _, service in prefixes})
    if missing:
        raise ValueError(f"{spec['id']}: no prefix of the service {', '.join(missing)} (has AWS renamed it?)")
    return [block for block, service in prefixes if service in wanted], data


def _oracle(text, spec):
    data = json.loads(text)
    return [cidr["cidr"] for region in data["regions"] for cidr in region["cidrs"]], data


def _csv_first_column(text, spec):
    rows = csv.reader(io.StringIO(text))
    return [row[0] for row in rows if row and row[0].strip() and not row[0].startswith("#")], {}


def _lines(text, spec):
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")], {}


def _sail(text, spec):
    # tomllib is in the standard library from Python 3.11; pyproject.toml allows older Pythons, which can still run
    # everything except reading a SAIL file during `agentcake lists update`.
    import tomllib

    data = tomllib.loads(text)
    service = next((s for s in data["services"] if s["name"] == spec["service"]), None)
    if service is None:
        raise ValueError(f"no service {spec['service']!r} in the SAIL file")
    sets = {prefix_set["name"]: prefix_set for prefix_set in data["prefix_sets"]}
    return [block for name in service["prefix_sets"]
            for block in sets[name].get("ipv4_prefixes", []) + sets[name].get("ipv6_prefixes", [])], data


READERS = {"prefixes": _prefixes, "aws": _aws, "oracle": _oracle, "csv-first-column": _csv_first_column,
           "lines": _lines, "sail": _sail}


def read_blocks(spec, bodies, published_fields):
    """All blocks of one range from its fetched files, and the publication time the files give, if any."""
    blocks, published = [], None
    for text in bodies:
        found, data = READERS[spec["format"]](text, spec)
        blocks += [block for block in found if block]
        published = published or (data.get(published_fields.get(spec["format"], "")) if data else None)
    # A SAIL file is TOML, whose dates arrive as datetime objects.
    return blocks, published.isoformat() if hasattr(published, "isoformat") else published


def collapse(blocks, spec, floors):
    """{"v4": [cidr], "v6": [cidr]}, collapsed; a block that is not an address or network is an error."""
    networks = {"v4": [], "v6": []}
    for block in blocks:
        try:
            network = ipaddress.ip_network(str(block).strip(), strict=False)
        except ValueError as error:
            raise ValueError(f"{spec['id']}: {error}") from error
        family = f"v{network.version}"
        if spec["kind"] in floors["kinds"] and network.prefixlen < floors[family]:
            raise ValueError(f"{spec['id']}: {network} is wider than /{floors[family]}; refusing it")
        networks[family].append(network)
    if not any(networks.values()):
        raise ValueError(f"{spec['id']}: no address blocks (has the format changed?)")
    return {family: [str(n) for n in ipaddress.collapse_addresses(found)] for family, found in networks.items()}


def build_ranges(recipe, fetch):
    """Fetch and read every range of sources.json "ip_ranges", in order; a file two ranges read is fetched once."""
    out, fetched = [], {}
    for spec in recipe["ranges"]:
        for url in spec["urls"]:
            if url not in fetched:
                fetched[url] = fetch(url).body.decode("utf-8")
        bodies = [fetched[url] for url in spec["urls"]]
        blocks, published = read_blocks(spec, bodies, recipe["published_fields"])
        entry = {key: spec[key] for key in ("id", "label", "kind", "operator", "verifies", "urls")}
        entry["published"] = published
        entry.update(collapse(blocks, spec, recipe["floors"]))
        out.append(entry)
    return out
