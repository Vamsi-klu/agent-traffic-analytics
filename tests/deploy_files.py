"""The deploy files read the way the programs that run them read them, for test_server_docs.py and
test_deploy_route.py: deploy/cake.service as systemd reads it, the Dockerfile as Docker does, docker-compose.yml as a
YAML document, and deploy/Caddyfile as Caddy's lexer splits it. Neither systemd, Docker, Compose nor Caddy is needed.

    caddyfile_directives(path) -> the Caddyfile as a list of Directive(tokens, block): a line's tokens split on white
        space (a token that starts with # comments out the rest of the line); a line that ends in { opens the block of
        its directive, a line holding only } closes it. Quotes, heredocs and snippets are not read: deploy/Caddyfile
        has none.
    directives(found, *head) -> the directives of a list whose tokens start with head.
    caddyfile() -> the parts SERVER.md describes, read from those directives.
    server_settings() -> {setting: value}: what the home page's "On a server" tab tells the server to set
        (data/api.en.json setup_server.settings).
"""
import configparser
import itertools
import json
import os
import re
from collections import namedtuple

from cake_server import ROOT, read

UNIT_FILE = os.path.join(ROOT, "deploy", "cake.service")
DOCKERFILE = os.path.join(ROOT, "Dockerfile")
DOCKERIGNORE = os.path.join(ROOT, ".dockerignore")
COMPOSE_FILE = os.path.join(ROOT, "docker-compose.yml")
CADDYFILE = os.path.join(ROOT, "deploy", "Caddyfile")
API_WORDS = os.path.join(ROOT, "agentcake", "data", "api.en.json")
YAML_KEY = re.compile(r"^([\w.-]+|\"[^\"]*\"|'[^']*'):(?:\s+(.*))?$")
COMMENT = re.compile(r"(^|\s)#.*")  # a comment of YAML and of the Caddyfile: a # at the start or after a space


def unit_file():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read(UNIT_FILE, encoding="utf-8")
    return parser


def unit_data_folder():
    """The CAKE_HOME the unit file gives the service."""
    return unit_file()["Service"]["Environment"].partition("CAKE_HOME=")[2].split()[0]


def dockerfile_instructions():
    """The Dockerfile as (INSTRUCTION, arguments): comment lines dropped and continuation lines joined, the way Docker
    reads the file."""
    kept = "\n".join(line for line in read(DOCKERFILE).splitlines() if not line.lstrip().startswith("#"))
    return [(line.strip().partition(" ")[0].upper(), line.strip().partition(" ")[2].strip())
            for line in re.sub(r"\\\n", " ", kept).splitlines() if line.strip()]


def final_stage():
    """The base image and the instructions of the Dockerfile's last stage, with ${ARG} defaults filled in."""
    args, stage, base = {}, [], None
    for instruction, rest in dockerfile_instructions():
        rest = re.sub(r"\$\{(\w+)\}", lambda m: args.get(m.group(1), m.group(0)), rest)
        if instruction == "ARG" and "=" in rest:
            name, _, default = rest.partition("=")
            args[name.strip()] = default.strip()
        elif instruction == "FROM":
            stage, base = [], rest.split()[0]
        stage.append((instruction, rest))
    return base, stage


def instruction_values(stage, name):
    return [rest for instruction, rest in stage if instruction == name]


def yaml_document(text):
    """A YAML file of block mappings and lists, the form docker-compose.yml takes, as dicts, lists and strings. Flow
    collections ([…], {…}) stay strings; anchors and multi-line strings are not read."""
    lines = []
    for raw in text.splitlines():
        line = COMMENT.sub("", raw).rstrip()
        if line.strip() not in ("", "---"):
            lines.append((len(line) - len(line.lstrip()), line.strip()))
    return _yaml_block(lines, 0)[0]


def _yaml_scalar(text):
    text = text.strip()
    return text[1:-1] if len(text) > 1 and text[0] == text[-1] and text[0] in "'\"" else text


def _yaml_block(lines, i):
    """(the mapping or list that starts at lines[i], the index after it)."""
    indent, first = lines[i]
    if first == "-" or first.startswith("- "):
        items = []
        while i < len(lines) and lines[i][0] == indent and (lines[i][1] == "-" or lines[i][1].startswith("- ")):
            rest = lines[i][1][1:].strip()
            if YAML_KEY.match(rest):  # a mapping in the list: read as if it began on a line of its own
                lines[i] = (indent + 2, rest)
                item, i = _yaml_block(lines, i)
            elif rest:
                item, i = _yaml_scalar(rest), i + 1
            else:
                item, i = _yaml_block(lines, i + 1)
            items.append(item)
        return items, i
    mapping = {}
    while i < len(lines) and lines[i][0] == indent:
        key, value = YAML_KEY.match(lines[i][1]).groups()
        nested = i + 1 < len(lines) and (lines[i + 1][0] > indent or lines[i + 1][1].startswith("-"))
        if value:
            mapping[_yaml_scalar(key)], i = _yaml_scalar(value), i + 1
        elif nested:
            mapping[_yaml_scalar(key)], i = _yaml_block(lines, i + 1)
        else:
            mapping[_yaml_scalar(key)], i = None, i + 1
    return mapping, i


def compose_file():
    return yaml_document(read(COMPOSE_FILE))


def mounts(service):
    """{where in the container: what is mounted there} of a Compose service's volumes, in the short form
    (source:target[:mode]) or the long one (a mapping with source and target)."""
    found = {}
    for entry in service.get("volumes") or []:
        if isinstance(entry, dict):
            found[entry["target"]] = entry.get("source")
        else:
            source, target = entry.split(":")[:2]
            found[target] = source
    return found


Directive = namedtuple("Directive", "tokens block")


def caddyfile_directives(path=CADDYFILE):
    top = []
    open_blocks = [top]
    for number, line in enumerate(read(path).splitlines(), 1):
        tokens = list(itertools.takewhile(lambda token: not token.startswith("#"), line.split()))
        if not tokens:
            continue
        if tokens == ["}"]:
            if len(open_blocks) == 1:
                raise ValueError(f"line {number}: }} closes no block")
            open_blocks.pop()
            continue
        opens = tokens[-1] == "{"
        head = tuple(tokens[:-1] if opens else tokens)
        if "{" in head or "}" in head:
            raise ValueError(f"line {number}: a brace inside a line")
        directive = Directive(head, [] if opens else None)
        open_blocks[-1].append(directive)
        if opens:
            open_blocks.append(directive.block)
    if len(open_blocks) != 1:
        raise ValueError("a block is never closed")
    return top


def directives(found, *head):
    return [d for d in found if d.tokens[:len(head)] == head]


def _lines(found, depth=0):
    """The directives as the text of their lines, blocks indented: a block's text without comments."""
    for directive in found:
        yield "\t" * depth + " ".join(directive.tokens)
        yield from _lines(directive.block or [], depth + 1)


def caddyfile():
    """deploy/Caddyfile, the parts SERVER.md describes: the global options' text, the site's address, the paths it
    forwards, where to, its header_up lines as {name: value, or None for a header it removes}, and whether the site
    answers 404 to everything else. The proxy is `reverse_proxy @matcher upstream`, or `reverse_proxy upstream` in a
    `handle @matcher` block; everything else is a `respond 404` of the site, or of its `handle` without a matcher."""
    found = caddyfile_directives()
    options = next(d for d in found if d.tokens == ())
    site = next(d for d in found if d.tokens != ())
    handles = directives(site.block, "handle")
    holders = [site] + [h for h in handles if len(h.tokens) == 2]
    (holder, proxy), = [(h, p) for h in holders for p in directives(h.block, "reverse_proxy")]
    matcher, upstream = (holder.tokens[1], proxy.tokens[1]) if holder is not site else proxy.tokens[1:3]
    if matcher.startswith("@"):
        forwarded = list(next(d for d in site.block if d.tokens[:2] == (matcher, "path")).tokens[2:])
    else:
        forwarded = [matcher]
    headers = {}
    for directive in directives(proxy.block or [], "header_up"):
        name, value = directive.tokens[1], " ".join(directive.tokens[2:])
        headers.update({name[1:]: None} if name.startswith("-") else {name: value})
    elsewhere = [site] + [h for h in handles if len(h.tokens) == 1]
    return {"global": "\n".join(_lines([options])), "site": site.tokens[0], "forwarded": forwarded,
            "upstream": upstream, "headers": headers,
            "answers_404": any(directives(h.block, "respond", "404") for h in elsewhere)}


def server_settings():
    with open(API_WORDS, encoding="utf-8") as f:
        lines = json.load(f)["setup_server"]["settings"]
    settings = {}
    for line in lines:
        words = line.split()
        if words[1:3] == ["config", "set"]:
            settings[words[3]] = words[4]
    return settings
