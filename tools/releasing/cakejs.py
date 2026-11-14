"""cake.js in the release (S6.4): the committed build of agentcake/build_js.py, minified with esbuild.

esbuild (MIT, https://github.com/evanw/esbuild) is pinned in tools/releasing/package.json and package-lock.json and
installed with `npm ci` in the exported commit; it is used only here, never shipped. Before minifying, build_js.py
--check confirms the committed cake.js is what its sources make. esbuild keeps the /*! ... */ comments (the bundled
parts' licences and cake.js's own header) and, with release.json's target, rewrites no syntax.

cake fills in an installation's values between two runtime markers, /*cake:runtime*/{}/*cake:runtime*/
(agentcake/data/cakejs.json). A minifier drops comments inside an expression, so while esbuild runs the marked value
is replaced by a name nothing else uses (release.json "runtime_slot"), which esbuild leaves as it is because it is a
global, and the markers are put back afterwards. minify() refuses any result in which the slot is not there exactly
once, and build() checks the markers, the licences and the size of what comes out.
"""
import json
import os
import sys

from tools.releasing import commands
from tools.releasing.settings import ReleaseError, read_json

MARKERS = 2  # the runtime value sits between an opening and a closing marker (agentcake/build_js.py)


def marker_expression(marker):
    """The marked runtime value as the unminified cake.js writes it."""
    return f"/*{marker}*/{{}}/*{marker}*/"


def minify(source, marker, slot, minifier):
    """source minified by minifier (a function of the text), the runtime markers kept."""
    marked = marker_expression(marker)
    if source.count(marked) != 1:
        raise ReleaseError(f"cake.js must hold {marked} exactly once")
    if slot in source:
        raise ReleaseError(f"cake.js already uses {slot}, the name that stands in for its runtime value")
    result = minifier(source.replace(marked, slot))
    if result.count(slot) != 1:
        raise ReleaseError(f"the minifier changed cake.js's runtime value ({slot} is there {result.count(slot)} times)")
    return result.replace(slot, marked)


def pinned_esbuild(tools_folder):
    """The esbuild version tools/releasing/package.json pins."""
    package = read_json(os.path.join(tools_folder, "package.json"))
    return package["devDependencies"]["esbuild"]


def esbuild_command(tree, settings):
    """Install the pinned esbuild in the exported commit and return the command that runs it."""
    rules = settings["cakejs"]
    tools_folder = os.path.join(tree, rules["tools_folder"])
    commands.run(rules["install"], tools_folder, tree)
    executable = os.path.join(tools_folder, rules["esbuild"])
    if not os.path.isfile(executable):
        raise ReleaseError(f"esbuild is not in {rules['tools_folder']} after npm ci: cake.js cannot be minified")
    installed = commands.output([executable, "--version"], "", tools_folder).strip()
    if installed != pinned_esbuild(tools_folder):
        raise ReleaseError(f"esbuild {installed} was installed, package.json pins {pinned_esbuild(tools_folder)}")
    return [executable, *rules["flags"]], installed


def build_config(tree, settings):
    """agentcake/data/cakejs.json "build": the runtime marker and the parts (their paths relative to the package)."""
    return read_json(os.path.join(tree, settings["cakejs"]["config_file"]))["build"]


def licences(tree, settings):
    """The licence texts of the bundled third-party parts of cake.js."""
    texts = []
    for part in build_config(tree, settings)["parts"]:
        if "licence" in part:
            with open(os.path.join(tree, settings["package"], part["licence"]), encoding="utf-8") as f:
                texts.append(f.read().strip())
    return texts


def check_current(tree, settings):
    """build_js.py --check of the exported commit: the committed cake.js is what its sources make."""
    check = settings["cakejs"]["check"]
    commands.run([sys.executable, "-I", "-B", os.path.join(tree, check[0]), *check[1:]], tree, tree)


def build(tree, settings):
    """Minify the exported commit's cake.js in place; returns (bytes before, bytes after, esbuild version)."""
    rules = settings["cakejs"]
    check_current(tree, settings)
    command, version = esbuild_command(tree, settings)
    path = os.path.join(tree, rules["file"])
    with open(path, encoding="utf-8") as f:
        source = f.read()
    marker = build_config(tree, settings)["runtime_marker"]
    folder = os.path.dirname(path)
    result = minify(source, marker, rules["runtime_slot"], lambda text: commands.output(command, text, folder))
    if result.count(f"/*{marker}*/") != MARKERS:
        raise ReleaseError("the minified cake.js must hold its two runtime markers and no other copy of them")
    missing = [text.splitlines()[0] for text in licences(tree, settings) if text not in result]
    if missing:
        raise ReleaseError(f"the minified cake.js lost a bundled licence: {json.dumps(missing)}")
    if len(result) >= len(source):
        raise ReleaseError("the minified cake.js is not smaller than the committed one")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(result)
    return len(source.encode("utf-8")), len(result.encode("utf-8")), version
