"""Files sent to browsers: the page script cake.js (S1.3), the rrweb recorder and player from static/ (S1.1), and the
compiled local pages (S5.1).

cake.js is built from static/src/ by build_js.py and committed as static/cake.js; it is served with this
installation's runtime values filled in. The recorder stays at /rrweb-record.min.js for pages that still have a
0.3.x cake.js cached (the new cake.js has rrweb inside).

The local pages are the web/ app compiled to static files (paths.web_folder, like PostHog 1.0's frontend build that
Django serves): / is its index.html, and the pages route by the URL's # part, so no other path needs it; any other
file of the build is served by its suffix (data/web.json). Without a build (a checkout where `npm run build` has not
run) / answers 503 with how to build it. The pages read their data from /api (agentcake/api/).
"""
import os
import pathlib
from http import HTTPStatus
from urllib.parse import unquote

from agentcake import build_js, config, paths
from agentcake.datafiles import load
from agentcake.responses import CSS, JS, TEXT, Response, not_found
from agentcake.wording import text

CACHE_CONTROL = "Cache-Control"


def runtime_values(c):
    """What cake.js gets from this installation, set on the settings page (S5.5): the site key, whether to watch the
    site's own document lookups, and the parts of its pages never to record; agentcake/data/cakejs.json has the rest."""
    return {"site_key": c.get("site_key"), "hook_dom": bool(c["hook_dom"]), "hide_selectors": c["hide_selectors"]}


def cake_js(request):
    """/cake.js and /c.js, on both listeners."""
    return Response(HTTPStatus.OK, build_js.served_script(runtime_values(config.load_cfg())), JS)


def static_file(request):
    """/rrweb-record.min.js and /static/<file> on the local listener (only the file name of the path is used)."""
    f = os.path.join(paths.STATIC_DIR, os.path.basename(request.path))
    if os.path.isfile(f):
        return Response(HTTPStatus.OK, pathlib.Path(f).read_bytes(), CSS if f.endswith(".css") else JS)
    return not_found()


def recorder(request):
    """/rrweb-record.min.js on the public listener."""
    return Response(HTTPStatus.OK, pathlib.Path(paths.STATIC_DIR, "rrweb-record.min.js").read_bytes(), JS)


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
