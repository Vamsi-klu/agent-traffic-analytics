"""Setting AgentCake up, printed for a coding agent to follow: `setup --print`, `setup --print --site`,
`snippet`, `sentence`.

setup_print_local() prints what to tell the user after install (the self-check, the local page, registering, and
connecting their website from that page: there is no demo shop).
setup_print_site(folder) reads the website's code (site_code.py) and prints the exact edits for its framework
(data/frameworks.json): the cake.js line and the files it goes in; the server half's middleware from this
installation's edge folder (the file that makes the app, the files to copy, where its secret comes from; the Node
middleware is copied into the site's code and installed from that relative path, never from this computer's edge
folder, so the site builds on its host and on any other computer); how to check
it all with doctor; what is left for the user. The page script's address is where visitors' browsers reach
AgentCake: with public_url (the subdomain route, SERVER.md) that address and path_prefix, such as
https://cake.example.com/cake/cake.js, whether this is the server or a computer that names it; else, in server mode
(public_listen), path_prefix on the site's own domain (/cake/cake.js, the same-site path); else the local page on
this computer. On the subdomain route the user is told which DNS record to add where they manage the domain: with
their approval the coding agent adds it there and checks it, the user signing in; a subdomain under a domain of
data/ip_names.json, whose DNS service answers a name with the address it holds (SERVER.md, "Sites without their own
domain"), needs no record, and the user is pointed to that service's risks instead. The words are in
data/copy.en.json.
Named site_setup, not setup, so it is never mistaken for a packaging setup.py.
"""
import os
import re
from urllib.parse import urlsplit

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
    """Where visitors' browsers reach AgentCake: public_url and path_prefix (the subdomain route); else, in server
    mode, path_prefix on the site's own domain (a path, so one line serves every page of the site wherever it is
    deployed); else the local page on this computer."""
    if c.get("public_url"):
        return c["public_url"] + (c.get("path_prefix") or "")
    return (c.get("path_prefix") or "") if server_mode(c) else base_url(c)


def script_src(c):
    return cake_root(c) + SCRIPT_PATH


def snippet(c=None):
    c = c or ensure_cfg()
    return SNIPPET.format(src=script_src(c), site_key=c["site_key"])


def next_tag(c):
    return NEXT_SCRIPT_TAG.format(src=script_src(c), site_key=c["site_key"])


def plugin_address(c):
    """The WordPress plugin's "AgentCake address", to which it adds /cake.js: a full URL, so on the same-site path the
    site's domain (or what to fill in, while site_domain is not set)."""
    if c.get("public_url") or not server_mode(c):
        return cake_root(c)
    prefix = c.get("path_prefix") or ""
    if not c.get("site_domain"):
        return text("setup_site_address_unknown", prefix=prefix)
    return load("data/frameworks.json")["public_address"].format(domain=c["site_domain"], prefix=prefix)


def edge_dir():
    """This installation's edge folder (the sites' middleware: node, python, php, wordpress), the way
    paths.web_folder() finds the local pages: $CAKE_EDGE_DIR when it is set; else the folder a release carries inside
    the package (the wheel, the .pyz and the unpacked package all have agentcake/edge); else the one beside the
    package, as a checkout has it. None when there is none. The folder's name is data/site_files.json's edge_folder."""
    if os.environ.get(EDGE_DIR_ENV):
        return os.path.abspath(os.path.expanduser(os.environ[EDGE_DIR_ENV]))
    name = load("data/site_files.json")["edge_folder"]
    for folder in (os.path.join(paths.PACKAGE_DIR, name), os.path.join(os.path.dirname(paths.PACKAGE_DIR), name)):
        if os.path.isdir(folder):
            return folder
    return None


def sentence_b(c=None):
    """Optional step: the sentence for a coding agent that connects the user's own website, in English, as the local
    page shows it (`agentcake sentence`)."""
    return text("site_sentence", launcher=paths.launcher())


def setup_print_local():
    c = ensure_cfg()
    print(text("setup_local", version=__version__, home=paths.home(), base=base_url(c), launcher=paths.launcher()))


def setup_print_site(d):
    c, code, launcher = ensure_cfg(), SiteCode(d), paths.launcher()
    parts = [text("setup_site", version=__version__, home=paths.home(), base=base_url(c), site_key=c["site_key"],
                  script=script_src(c), collect=cake_root(c) + COLLECT_PATH, framework=code.framework, folder=d)]
    if server_mode(c):
        parts.append(text("setup_site_server_mode" if c.get("public_url") else "setup_site_server_mode_path",
                          listen=c["public_listen"], prefix=c.get("path_prefix") or "/", address=cake_root(c)))
    parts.append(text("setup_site_settings", launcher=launcher, folder=d, framework=code.framework,
                      domain=c.get("site_domain") or raw("setup_site_domain_unknown")))
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
    if kind == "next":  # App Router: inside the root layout's <body>; Pages Router: beside the page in _app
        return text(code.spec["script_copy"], file=code.layout_file(), tag=next_tag(c))
    if kind == "head":
        heads = code.head_files()
        if not heads:
            return text("setup_site_head_none", snippet=snippet(c))
        return text("setup_site_head", count=len(heads), files=", ".join(heads), snippet=snippet(c))
    if kind == "plugin":
        if not edge_dir():
            return text("setup_site_plugin_no_edge")
        plugin = os.path.join(edge_dir(), *code.middleware()["plugin"].split("/"))
        if code.middleware().get("installed_elsewhere"):  # a theme's or a plugin's own folder: uploaded to the site
            return text("setup_site_plugin_elsewhere", folder=os.path.dirname(plugin), zip_name=os.path.basename(plugin),
                        address=plugin_address(c), site_key=c["site_key"])
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
    frameworks, file = load("data/frameworks.json"), mounting_file(code)
    mount = text(middleware["copy"], edge=edge, file=file or raw("setup_site_app_unknown"), beside=manage_py_folder(code),
                 folder=middleware.get("folder"), suffix=os.path.splitext(file or "")[1],
                 mounting=mounting_code(code, middleware, file))
    secret = text(middleware.get("secret_copy", "setup_site_secret"), launcher=launcher, env=frameworks["secret_env"],
                  readme=os.path.join(edge, *middleware["readme"].split("/")))
    return [text("setup_site_half"), mount, secret]


def mounting_file(code):
    """The file the mounting goes in: the one that has it already, else the one that makes the app; for Next.js, which
    has none yet, a new middleware file beside the app (or pages) folder, the way the edge folder's README says, in the
    site's language (middleware.ts where it has a tsconfig.json, else middleware.js). None when there is no such file."""
    existing = (code.middleware_files() or [None])[0] or code.app_file()
    if existing or code.spec["script"] != "next":
        return existing
    beside_app_folder = os.path.dirname(os.path.dirname(code.layout_file()))
    typed = code.language(None) == "ts"
    typescript = tuple(load("data/frameworks.json")["languages"]["typescript_suffixes"])
    return os.path.join(beside_app_folder, next(name for name in code.spec["app"]["files"]
                                                if name.endswith(typescript) == typed))


def mounting_code(code, middleware, file):
    """The Node middleware's mounting in the language of the file it goes in (SiteCode.language): TypeScript, import
    or require(), so that it is valid pasted there as it is. '' for a middleware that has one way (Python, PHP)."""
    entries = middleware.get("mounting")
    return text(entries[code.language(file)]) if entries else ""


def manage_py_folder(code):
    """Django: the folder that has manage.py (on sys.path when the site runs), where the copied middleware is imported
    from; the site's folder itself when there is none."""
    manage = next((path for path in code.files if os.path.basename(path) == "manage.py"), None)
    return (os.path.dirname(manage) if manage else "") or os.curdir


def holds_its_address(host):
    """Whether host is under a domain of data/ip_names.json and holds an IPv4 address right before it, in the form its
    DNS service answers with that address (cake.203-0-113-10.<domain>, data/ip_names.json address): such a subdomain
    needs no DNS record of the user's. A name under such a domain without an address leads nowhere: it is any other
    name, which gets the DNS record."""
    names = load("data/ip_names.json")
    domain = next((domain for domain in names["domains"] if host.endswith("." + domain)), None)
    return domain is not None and re.search(names["address"], host[:-len(domain) - 1]) is not None


def tell_step(c):
    """Step 5: what is left, which the coding agent does as its approved plan says, the user signing in: where
    visitors' browsers reach AgentCake (its subdomain, with the DNS record at the user's DNS provider, or none for a name
    that holds the server's address; a path of the site's own domain; this computer); their privacy notice; and, only
    if they ask for it, counting a signed-in visitor once (window.cake.identify() and reset())."""
    if c.get("public_url"):
        host = urlsplit(c["public_url"]).hostname
        record = "setup_site_tell_server_ip_name" if holds_its_address(host) else "setup_site_tell_server_record"
        where = "\n".join(text(key, public_url=c["public_url"], address=cake_root(c), host=host)
                          for key in ("setup_site_tell_server", record, "setup_site_tell_server_check"))
    elif server_mode(c):
        where = text("setup_site_tell_server_path", prefix=c.get("path_prefix") or "/")
    else:
        where = text("setup_site_tell_local")
    return "\n".join([text("setup_site_tell"), where, text("setup_site_tell_privacy"), text("setup_site_tell_identify")])
