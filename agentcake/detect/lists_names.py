"""Builds names.json (S3.1): every name a User-Agent can declare, merged from our own additions, botscent, PostHog
and ai.robots.txt, each with its kind (kinds.json) and the sources that list it.

    build_names(recipe, kinds, files) -> (names, hints, platforms, counts, disagreements)

`recipe` is sources.json "names"; `files` holds each repository's fetched files as text. How each source is read,
what is left out and why, and our own corrections are all in sources.json; this module only applies them. Sources
are merged in the order of "precedence": a name's text, operator and kind come from the first source that lists it,
and every source that lists it is recorded. Where sources disagree on whether a name is an agent or a bot, the
disagreement goes into names.json for a maintainer to settle in sources.json ("overrides"), which also corrects a
display name a source has out of date.
PostHog's bot_definitions.py is read with `ast` (literal values only): nothing fetched is ever executed.
"""
import ast
import json
import re

REGEX_SYNTAX = set("\\^$*+?()[]{}|")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _same_text(text):
    """How two sources' texts are compared to find the same name: case and a trailing '/' ignored."""
    return text.rstrip("/").lower()


def _real(mapping):
    """A mapping from sources.json without its "$comment"."""
    return {key: value for key, value in mapping.items() if not key.startswith("$")}


class _Registry:
    """The names collected so far, by list id, and an index from pattern text to list id."""

    def __init__(self):
        self.entries, self.by_text = {}, {}

    def find(self, text):
        return self.by_text.get(_same_text(text))

    def get(self, list_id, source, fields=None):
        entry = self.entries.setdefault(list_id, {"id": list_id, "name": None, "operator": None, "patterns": [],
                                                  "sources": [], "kinds": {}})
        for field, value in (fields or {}).items():
            if value and not entry.get(field):
                entry[field] = value
        if source not in entry["sources"]:
            entry["sources"].append(source)
        return entry

    def add_pattern(self, entry, match, text, source):
        if any(p["match"] == match and p["text"] == text for p in entry["patterns"]):
            return
        entry["patterns"].append({"match": match, "text": text, "source": source})
        if match != "regex":
            self.by_text.setdefault(_same_text(text), entry["id"])

    @staticmethod
    def set_kind(entry, source, kind):
        if kind:
            entry["kinds"].setdefault(source, kind)


def _add_cake(registry, own):
    for item in own:
        entry = registry.get(item["id"], "cake", {k: item.get(k) for k in ("name", "operator", "evidence", "note")})
        registry.set_kind(entry, "cake", item["kind"])
        for pattern in item["patterns"]:
            registry.add_pattern(entry, pattern["match"], pattern["text"], "cake")


def _add_botscent(registry, recipe, files):
    names = json.loads(files["names"])["names"]
    tokens = json.loads(files["tokens"])["tokens"]
    page = json.loads(files["page"])
    by_id = {list_id: group["kind"] for group in recipe["ids"] for list_id in group["ids"]}
    for list_id, info in names.items():
        entry = registry.get(list_id, "botscent", {"name": info["display"], "operator": info["vendor"]})
        registry.set_kind(entry, "botscent", by_id.get(list_id) or recipe["kinds"].get(info["kind"]))
    for token in tokens:
        entry = registry.get(registry.find(token["token"]) or token["name"], "botscent")
        registry.add_pattern(entry, token.get("match", "token"), token["token"], "botscent")
    for prefix, list_id in page["user_agent_prefixes"].items():
        registry.add_pattern(registry.get(list_id, "botscent"), "prefix", prefix, "botscent")
    for token, list_id in page["user_agent_tokens"].items():
        registry.add_pattern(registry.get(list_id, "botscent"), "versioned", token, "botscent")
    return dict(page["platforms"]), {"names": len(names), "tokens": len(tokens)}


def parse_posthog(text, recipe):
    """[(pattern, fields)] from PostHog's BOT_DEFINITIONS, reading literals only (never running the file)."""
    for node in ast.parse(text).body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None)
        if not (isinstance(target, ast.Name) and target.id == recipe["variable"]):
            continue
        if not isinstance(node.value, ast.Dict) or None in node.value.keys:
            raise ValueError(f"{recipe['variable']} is not a plain dict")
        return [(ast.literal_eval(key), _posthog_fields(call, recipe))
                for key, call in zip(node.value.keys, node.value.values)]
    raise ValueError(f"{recipe['variable']} not found")


def _posthog_fields(call, recipe):
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == recipe["constructor"]):
        raise ValueError(f"line {getattr(call, 'lineno', '?')}: not a {recipe['constructor']}(...)")
    fields = dict(zip(recipe["fields"], (ast.literal_eval(arg) for arg in call.args)))
    fields.update({keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords})
    return fields


def posthog_literal(pattern):
    """The plain text a PostHog pattern stands for (escaped dots allowed), or None when it is a real regex."""
    text = pattern.replace("\\.", ".")
    return None if REGEX_SYNTAX & set(text) else text


def _add_posthog(registry, recipe, text, guard):
    definitions = parse_posthog(text, recipe)
    fixes, hints, excluded, named = _real(recipe["patterns"]), [], [], 0
    for pattern, fields in definitions:
        if pattern in recipe["exclude"]:
            excluded.append(pattern)
            continue
        if pattern in recipe["hints"]:
            hints.append({"id": recipe["hints"][pattern], "name": fields["name"], "pattern": pattern})
            continue
        fix, literal = fixes.get(pattern, {}), posthog_literal(pattern)
        list_id = (registry.find(literal) if literal else None) or slug(literal or fields["name"])
        entry = registry.get(list_id, "posthog", {"name": fields["name"], "operator": fields["operator"]})
        registry.set_kind(entry, "posthog", fix.get("kind")
                          or recipe["kinds"].get(f"{fields['traffic_type']}/{fields['category']}"))
        default = {"match": "word", "text": literal} if literal else {"match": "regex", "text": pattern}
        for spec in fix.get("patterns") or [default]:
            regex = spec["match"] == "regex" and not spec["text"].startswith("^")
            registry.add_pattern(entry, spec["match"], f"{guard}(?:{spec['text']})" if regex else spec["text"],
                                 "posthog")
        named += 1
    counts = {"definitions": len(definitions), "named": named, "hints": len(hints), "excluded": excluded}
    return hints, counts


def _robots_kind(function, recipe):
    if function in recipe["functions"]:
        return recipe["functions"][function]
    free, lowered = recipe["free_text"], function.lower()
    if any(word in lowered for word in free["agent_words"]):
        return free["agent_kind"]
    if any(word in lowered for word in free["crawler_words"]):
        return free["crawler_kind"]
    return None


def _robots_operator(text, recipe):
    if not text or text in recipe["unknown_operators"]:
        return None
    link = MARKDOWN_LINK.match(text)
    return link.group(1) if link else text.split(",")[0].strip()


def _add_ai_robots(registry, recipe, text, aliases):
    robots = json.loads(text)
    named, attached, skipped = 0, 0, {}
    for raw, info in robots.items():
        name = re.sub(recipe["version_suffix"], "", raw)
        reason = recipe["exclude"].get(raw) or recipe["exclude"].get(name)
        kind = _robots_kind(info.get("function") or "", recipe)
        list_id = aliases.get(raw) or aliases.get(name) or registry.find(name)
        if reason:
            skipped[raw] = reason
        elif list_id:
            entry = registry.get(list_id, "ai-robots-txt")
            registry.set_kind(entry, "ai-robots-txt", kind)
            registry.add_pattern(entry, "token", name, "ai-robots-txt")
            attached += 1
        elif kind is None:
            skipped[raw] = "its function names no kind"
        elif len(name) < recipe["min_length"]:
            skipped[raw] = "too short to name from a User-Agent"
        else:
            entry = registry.get(slug(name), "ai-robots-txt",
                                 {"name": name, "operator": _robots_operator(info.get("operator"), recipe)})
            registry.set_kind(entry, "ai-robots-txt", kind)
            registry.add_pattern(entry, "token", name, "ai-robots-txt")
            named += 1
    return {"names": len(robots), "named": named, "attached": attached, "skipped": skipped}


def _finish(registry, recipe, kinds):
    """Each name's final kind (override, else the first source in precedence) and display name (override, else the
    first source's), and the disagreements."""
    overrides, names, disagreements = _real(recipe["overrides"]), [], []
    for list_id in sorted(registry.entries):
        entry = registry.entries[list_id]
        ranked = [entry["kinds"][s] for s in recipe["precedence"] if s in entry["kinds"]]
        fix = overrides.get(list_id, {})
        kind = fix.get("kind") or (ranked[0] if ranked else None)
        if kind not in kinds:
            raise ValueError(f"{list_id}: kind {kind!r} is not in kinds.json")
        if len({kinds[k]["category"] for k in ranked}) > 1:
            disagreements.append({"id": list_id, "kinds": entry["kinds"], "chosen": kind, "settled": fix.get("reason")})
        out = {"id": list_id, "name": fix.get("name") or entry["name"] or list_id, "operator": entry["operator"],
               "kind": kind,
               "patterns": entry["patterns"], "sources": entry["sources"]}
        out.update({k: entry[k] for k in ("evidence", "note") if entry.get(k)})
        names.append(out)
    return names, disagreements


def build_names(recipe, kinds, files, guard):
    """Merge the sources in order of precedence. files: {"botscent": {...}, "posthog": {...}, "ai-robots-txt": ...}."""
    registry = _Registry()
    _add_cake(registry, recipe["cake"])
    platforms, botscent = _add_botscent(registry, recipe["botscent"], files["botscent"])
    hints, posthog = _add_posthog(registry, recipe["posthog"], files["posthog"]["bot_definitions"], guard)
    robots = _add_ai_robots(registry, recipe["ai-robots-txt"], files["ai-robots-txt"]["robots"],
                            _real(recipe["aliases"]))
    names, disagreements = _finish(registry, recipe, kinds)
    counts = {"cake": {"named": len(recipe["cake"])}, "botscent": botscent, "posthog": posthog,
              "ai-robots-txt": robots}
    return names, hints, platforms, counts, disagreements
