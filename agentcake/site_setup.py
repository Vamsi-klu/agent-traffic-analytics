"""Setting Agent Cake up, printed for a coding agent to follow (S1.1, S6.1): `setup --print`, `setup --print --site`,
`snippet`, `sentence`.

setup_print_local() prints what to tell the user after install (the self-check, the local page, registering, and
connecting their website from that page: D37, there is no demo shop).
setup_print_site(folder) reads the website's code (site_code.py) and prints the exact edits for its framework
(data/frameworks.json): the cake.js line and the files it goes in; the server half's middleware from this
installation's edge folder (the file that makes the app, the files to copy, where its secret comes from); how to check
it all with doctor; what is left for the user. The page script's address is the local page's on this computer and, in
server mode (public_listen), path_prefix on the site's own domain (/cake/cake.js, SERVER.md), where visitors' browsers
reach Agent Cake. The words are in data/copy.en.json (copy.zh.json for the sentence).
Named site_setup, not setup, so it is never mistaken for a packaging setup.py.
"""
import os

from agentcake import __version__, paths
from agentcake.config import base_url, ensure_cfg
from agentcake.datafiles import load
from agentcake.site_code import SiteCode
from agentcake.wording import raw, text

SCRIPT_PATH = "/cake.js"  # protocol: the page script's route (routes.py); 0.3.x pages load /c.js, served the same
COLLECT_PATH = "/collect"  # protocol: collect's route (routes.py)
EDGE_DIR_ENV = "CAKE_EDGE_DIR"  # another edge folder than the installation's own (like $CAKE_WEB_DIR for web/)
SNIPPET = '<script src="{src}" data-site="{site_key}" defer></script>'
NEXT_SCRIPT_TAG = '<Script src="{src}" data-site="{site_key}" strategy="afterInteractive" />'


def server_mode(c):
    return bool(c.get("public_listen"))


def cake_root(c):
    """Where visitors' browsers reach Agent Cake: the local page on this computer; in server mode, path_prefix on the
    site's own domain (a path, so one line serves every page of the site wherever it is deployed)."""
    return (c.get("path_prefix") or "") if server_mode(c) else base_url(c)


def script_src(c):
    return cake_root(c) + SCRIPT_PATH


def snippet(c=None):
    c = c or ensure_cfg()
    return SNIPPET.format(src=script_src(c), site_key=c["site_key"])


def next_tag(c):
    return NEXT_SCRIPT_TAG.format(src=script_src(c), site_key=c["site_key"])


def plugin_address(c):
    """The WordPress plugin's "AgentCake address", to which it adds /cake.js: a full URL, so in server mode the
    site's domain (or what to fill in, while site_domain is not set)."""
    if not server_mode(c):
        return base_url(c)
    prefix = c.get("path_prefix") or ""
    if not c.get("site_domain"):
        return text("setup_site_address_unknown", prefix=prefix)
    return load("data/frameworks.json")["public_address"].format(domain=c["site_domain"], prefix=prefix)


def edge_dir():
    """This installation's edge folder (the sites' middleware: node, python, php, wordpress), the way paths.web_dir()
    finds the local pages: $CAKE_EDGE_DIR when it is set; else the folder a release carries inside the package (S6.4:
    the wheel, the .pyz and the unpacked package all have agentcake/edge); else the one beside the package, as a
    checkout has it. None when there is none. The folder's name is data/site_files.json's edge_folder."""
    if os.environ.get(EDGE_DIR_ENV):
        return os.path.abspath(os.path.expanduser(os.environ[EDGE_DIR_ENV]))
    name = load("data/site_files.json")["edge_folder"]
    for folder in (os.path.join(paths.PACKAGE_DIR, name), os.path.join(os.path.dirname(paths.PACKAGE_DIR), name)):
        if os.path.isdir(folder):
            return folder
    return None


def sentence_b(c=None):
    """Optional step: connect the user's own website (shown on the home page and settings page)."""
    return text("site_sentence", lang="zh", launcher=paths.launcher())


def setup_print_local():
    c = ensure_cfg()
    print(text("setup_local", version=__version__, home=paths.home(), base=base_url(c), launcher=paths.launcher()))


def setup_print_site(d):
    c, code, launcher = ensure_cfg(), SiteCode(d), paths.launcher()
    parts = [text("setup_site", version=__version__, home=paths.home(), base=base_url(c), site_key=c["site_key"],
                  script=script_src(c), collect=cake_root(c) + COLLECT_PATH, framework=code.framework, folder=d)]
    if server_mode(c):
        parts.append(text("setup_site_server_mode", listen=c["public_listen"], prefix=c.get("path_prefix") or "/"))
    parts.append(text("setup_site_settings", launcher=launcher, folder=d, framework=code.framework))
    parts.append(script_step(c, code))
    parts += half_step(code, launcher)
    parts.append(text("setup_site_check", launcher=launcher))
    parts.append(tell_step(c))
    print("\n".join(parts))


def script_step(c, code):
    """Step 2: where the cake.js line goes, for the framework."""
    kind = code.spec["script"] if code.spec else None
    if kind == "static":
        return text("setup_site_static", count=len(code.pages()), snippet=snippet(c))
    if kind == "next":
        return text("setup_site_next", file=code.layout_file(), tag=next_tag(c))
    if kind == "head":
        heads = code.head_files()
        if not heads:
            return text("setup_site_head_none", snippet=snippet(c))
        return text("setup_site_head", count=len(heads), files=", ".join(heads), snippet=snippet(c))
    if kind == "plugin":
        if not edge_dir():
            return text("setup_site_plugin_no_edge")
        plugin = os.path.join(edge_dir(), *code.middleware()["plugin"].split("/"))
        return text("setup_site_plugin", plugin=plugin, address=plugin_address(c), site_key=c["site_key"])
    return text("setup_site_unknown", snippet=snippet(c))


def half_step(code, launcher):
    """Step 3: the server half's middleware, mounted where the framework's README says, and its secret."""
    middleware = code.middleware()
    if not middleware:
        return [text("setup_site_half_none" if code.spec else "setup_site_half_unknown")]
    edge = edge_dir()
    if not edge:
        return [text("setup_site_half"), text("setup_site_no_edge")]
    frameworks = load("data/frameworks.json")
    mount = text(middleware["copy"], edge=edge, file=mounting_file(code), beside=manage_py_folder(code))
    secret = text(middleware.get("secret_copy", "setup_site_secret"), launcher=launcher, env=frameworks["secret_env"],
                  readme=os.path.join(edge, *middleware["readme"].split("/")))
    return [text("setup_site_half"), mount, secret]


def mounting_file(code):
    """The file the mounting goes in: the one that has it already, else the one that makes the app; for Next.js, which
    has none yet, a new middleware.ts beside the app (or pages) folder, the way the edge folder's README says."""
    existing = (code.middleware_files() or [None])[0] or code.app_file()
    if existing:
        return existing
    if code.spec["script"] == "next":
        beside_app_folder = os.path.dirname(os.path.dirname(code.layout_file()))
        return os.path.join(beside_app_folder, code.spec["app"]["files"][0])
    return raw("setup_site_app_unknown")


def manage_py_folder(code):
    """Django: the folder that has manage.py (on sys.path when the site runs), where the copied middleware is imported
    from; the site's folder itself when there is none."""
    manage = next((path for path in code.files if os.path.basename(path) == "manage.py"), None)
    return (os.path.dirname(manage) if manage else "") or os.curdir


def tell_step(c):
    """Step 5: what is left for the user, on this computer or in server mode."""
    where = (text("setup_site_tell_server", prefix=c.get("path_prefix") or "/") if server_mode(c)
             else text("setup_site_tell_local"))
    return "\n".join([text("setup_site_tell"), where, text("setup_site_tell_privacy")])
