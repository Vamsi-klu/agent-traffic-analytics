"""Files sent to browsers: the page script cake.js, the replay player from static/, and the compiled local pages.

cake.js is built by the repository's tools/build_js.py from the parts data/cakejs.json lists (static/src/ and rrweb's
recorder) and committed as static/cake.js; it is served with this installation's runtime values filled in between its
two runtime markers (with_runtime), gzipped for a browser that accepts gzip and with an ETag (script_response.py).

The local pages are the web/ app compiled to static files (paths.web_folder, like PostHog 1.0's frontend build that
Django serves): / is its index.html, and the pages route by the URL's # part, so no other path needs it; any other
file of the build is served by its suffix (data/web.json). Without a build (a checkout where `npm run build` has not
run) / answers 503 with how to build it. The pages read their data from /api (agentcake/api/).
"""
import json
import os
import pathlib
from http import HTTPStatus
from urllib.parse import unquote

from agentcake import config, paths, script_response
from agentcake.datafiles import load, read
from agentcake.responses import CSS, JS, TEXT, Response, not_found
from agentcake.wording import text

CACHE_CONTROL = "Cache-Control"
CAKEJS = "data/cakejs.json"


def runtime_values(c):
    """What cake.js gets from this installation, set on the settings page: the site key, whether to watch the
    site's own document lookups, and the parts of its pages never to record; agentcake/data/cakejs.json has the rest."""
    return {"site_key": c.get("site_key"), "hook_dom": bool(c["hook_dom"]), "hide_selectors": c["hide_selectors"]}


def cake_js(request):
    """/cake.js and /c.js, on both listeners."""
    return script_response.answer(request, served_script(runtime_values(config.load_cfg())).encode())


def served_script(values):
    """cake.js as cake serves it: the committed build with this installation's runtime values filled in."""
    build = load(CAKEJS)["build"]
    return with_runtime(read(build["out"]), values, build["runtime_marker"])


def with_runtime(script, values, marker=None):
    """script with values (a JSON object) between its runtime markers, replacing what was there."""
    marker = f"/*{marker or load(CAKEJS)['build']['runtime_marker']}*/"
    start = script.index(marker) + len(marker)
    end = script.index(marker, start)
    # Escaping "/" keeps a value from ever writing "/*" or "*/" next to the markers.
    filled = json.dumps(values, separators=(",", ":"), sort_keys=True).replace("/", "\\/")
    return script[:start] + filled + script[end:]


def static_file(request):
    """/static/<file> on the local listener, for the replay player's files (only the file name of the path is used)."""
    f = os.path.join(paths.STATIC_DIR, os.path.basename(request.path))
    if os.path.isfile(f):
        return Response(HTTPStatus.OK, pathlib.Path(f).read_bytes(), CSS if f.endswith(".css") else JS)
    return not_found()


def local_pages(request):
    """/ on the local listener: the compiled pages' index.html."""
    root = os.path.realpath(paths.web_folder())
    index = os.path.join(root, load("data/web.json")["index"])
    if not os.path.isfile(index):
        return Response(HTTPStatus.SERVICE_UNAVAILABLE, text("web_not_built", folder=paths.tilde(root)), TEXT)
    return _web_file(index, root)


def web_file(request):
    """Any other GET of the local listener that no route takes: a file of the compiled pages, else 404."""
    root = os.path.realpath(paths.web_folder())
    target = os.path.realpath(os.path.join(root, unquote(request.path).lstrip("/")))
    if not target.startswith(root + os.sep) or not os.path.isfile(target):
        return not_found()
    return _web_file(target, root)


def _web_file(path, root):
    web = load("data/web.json")
    kind = web["types"].get(os.path.splitext(path)[1].lower())
    if kind is None:
        return not_found()
    hashed = os.path.relpath(path, root).split(os.sep)[0] == web["hashed_dir"]
    return Response(HTTPStatus.OK, pathlib.Path(path).read_bytes(), kind,
                    {CACHE_CONTROL: web["cache"]["hashed" if hashed else "page"]})
