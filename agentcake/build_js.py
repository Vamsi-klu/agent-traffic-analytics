"""Build Agent Cake's page script, agentcake/static/cake.js, and fill in its runtime values (plan steps S1.3, S1.4).

cake.js is made from the sources in agentcake/static/src/, in the order agentcake/data/cakejs.json lists them
("build" -> "parts"), plus the "script" settings and the data files listed under "build" -> "data" (the privacy rules
of agentcake/data/privacy.json), which become the CFG object every part reads: no number or name is written in the
sources. Each part runs inside its own function within one enclosing function, so nothing reaches the
page but window.cake; the parts share a private namespace, C. The licences of the vendored third-party parts are kept
in /*! ... */ comments at the top. The development build is this plain concatenation; the release build minifies the
same output and keeps those comments (plan step S6.4).

When cake serves /cake.js it calls with_runtime() to put in the values that belong to one installation (the site key,
settings the site owner turned on) between the two runtime markers.

    python3 -I agentcake/build_js.py           write agentcake/static/cake.js
    python3 -I agentcake/build_js.py --check   exit 1 when the committed cake.js is not what the sources make now
"""
import argparse
import hashlib
import json
import os
import sys

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PACKAGE_DIR, "data", "cakejs.json")
SOURCE_MAP_PREFIX = "//# sourceMappingURL="

# How a part is put into the enclosing function: "scoped" runs it at once in its own function; "umd" does the same but
# hides any module loader of the page (a UMD wrapper would hand its export to the page's AMD or CommonJS instead of to
# cake); "deferred" makes it a function that cake.js calls when it starts (botscent starts itself when it runs).
SCOPED_OPEN = "  ;(function () {"
SCOPED_CLOSE = "  }).call(SCOPE)"
HIDE_LOADERS = "  var exports, module, define // the UMD wrapper below gives its export to SCOPE, not to a page loader"


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_part(part):
    """A source file's text; a vendored file's trailing source-map comment is dropped (the map is not shipped)."""
    text = read(os.path.join(PACKAGE_DIR, part["file"])).rstrip("\n")
    last_line = text.rsplit("\n", 1)[-1]
    if last_line.startswith(SOURCE_MAP_PREFIX):
        text = text[: -len(last_line)].rstrip("\n")
    return text


def licence_comment(part):
    text = read(os.path.join(PACKAGE_DIR, part["licence"])).strip()
    if "*/" in text:
        raise ValueError(f"{part['licence']} would end the comment that carries it")
    return f"/*! {part['name']} {part['version']} ({part['source']}):\n{text}\n*/"


def wrap(part, text):
    name = part["file"]
    if part["wrap"] == "deferred":
        return f"  // ---- {name} (started by cake.js)\n  C.{part['as']} = function () {{\n{text}\n  }}"
    lines = [f"  // ---- {name}", SCOPED_OPEN]
    if part["wrap"] == "umd":
        lines.append(HIDE_LOADERS)
    elif part["wrap"] != "scoped":
        raise ValueError(f"{name}: unknown wrap {part['wrap']!r}")
    lines.append(text)
    lines.extend(f"  C.{key} = {value}" for key, value in part.get("expose", {}).items())
    lines.append(SCOPED_CLOSE)
    return "\n".join(lines)


def script_settings(config):
    """CFG: cakejs.json's "script" object, plus each data file listed under "build" -> "data" (one key of it)."""
    settings = dict(config["script"])
    for name, source in config["build"].get("data", {}).items():
        settings[name] = load_config(os.path.join(PACKAGE_DIR, source["file"]))[source["key"]]
    return settings


def build(config=None):
    """The complete text of cake.js for this configuration."""
    config = config or load_config()
    settings = config["build"]
    parts = [(part, read_part(part)) for part in settings["parts"]]
    cfg = json.dumps(script_settings(config), separators=(",", ":"), ensure_ascii=False)
    build_id = hashlib.sha256("\n".join([cfg] + [text for _, text in parts]).encode()).hexdigest()
    build_id = build_id[: settings["build_id_chars"]]
    vendored = [part for part, _ in parts if "licence" in part]
    marker = settings["runtime_marker"]
    lines = [
        f"/*! Agent Cake page script (cake.js), upload format v{config['script']['format_version']}, build {build_id}."
        f" Made by agentcake/build_js.py from agentcake/static/src/ and agentcake/data/cakejs.json; do not edit."
        f" Bundles {', '.join(p['name'] for p in vendored)}, whose licences follow. */",
        *(licence_comment(part) for part in vendored),
        ";(function () {",
        "  'use strict'",
        "  if (window.cake && window.cake.version) return // cake.js is already running on this page",
        "  var STARTED = performance.now() // cake.js reports how long its own first task took",
        "  var TAG = document.currentScript",
        f"  var CFG = {cfg}",
        f"  var RUNTIME = /*{marker}*/{{}}/*{marker}*/",
        f"  var BUILD = {json.dumps(build_id)}",
        "  var C = {}",
        "  var SCOPE = {}",
        *(wrap(part, text) for part, text in parts),
        "})()",
        "",
    ]
    return "\n".join(lines)


def with_runtime(script, values, marker=None):
    """script with values (a JSON object) between its runtime markers, replacing what was there."""
    marker = f"/*{marker or load_config()['build']['runtime_marker']}*/"
    start = script.index(marker) + len(marker)
    end = script.index(marker, start)
    # Escaping "/" keeps a value from ever writing "/*" or "*/" next to the markers.
    filled = json.dumps(values, separators=(",", ":"), sort_keys=True).replace("/", "\\/")
    return script[:start] + filled + script[end:]


def served_script(values):
    """cake.js as cake serves it: the committed build with this installation's runtime values filled in."""
    config = load_config()
    script = read(os.path.join(PACKAGE_DIR, config["build"]["out"]))
    return with_runtime(script, values, config["build"]["runtime_marker"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build agentcake/static/cake.js from agentcake/static/src/.")
    parser.add_argument("--check", action="store_true", help="only check that the committed cake.js is current")
    args = parser.parse_args(argv)
    config = load_config()
    out = os.path.join(PACKAGE_DIR, config["build"]["out"])
    script = build(config)
    if args.check:
        current = read(out) if os.path.isfile(out) else None
        print("cake.js is current" if current == script else f"{out} is stale: run python3 -I agentcake/build_js.py")
        return 0 if current == script else 1
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)
    print(f"wrote {out} ({len(script.encode())} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
