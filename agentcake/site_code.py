"""Reading a website's code folder: which framework it uses, which of its files must carry the cake.js line,
which file makes the app, and where the server half's middleware is mounted.

SiteCode(folder) walks the folder once (never into data/site_files.json's skip_dirs: installed packages, build output,
virtual environments, WordPress's own code; nor into the Node middleware's copy, data/frameworks.json's folder) and
recognises the first framework of data/frameworks.json that matches (a folder that holds only a WordPress theme or
plugin by its file header, header_field(), as WordPress does). For the Node middleware it also reads whether its copy
is in the site and what package.json's dependencies install it from (local_folder(): a folder inside the site, or
None for one a CI server or another computer does not have; installs_the_copy(): from the copy, a workspace too).
setup --print --site (site_setup.py) says what to change from it; doctor (doctor_site.py) checks the change from it.
Paths it returns are relative to the folder. It only reads: it never runs the site or installs anything.
loads_from(text, address): whether a page's text names the page script's address as a whole, also doctor's test of an
opened page (doctor_live.py).
"""
import fnmatch
import json
import os
import re

from agentcake.datafiles import load


# A character an address cannot follow and still stand alone: /cake/cake.js inside https://stats.example.com/cake/cake.js
# is the end of another address, not the same-site path.
WITHIN_ADDRESS = r"\w.:/@-"


def loads_from(text, address):
    """Whether text names address as a whole: not as the end of a longer address, nor as the start of a longer name."""
    return re.search(f"(?<![{WITHIN_ADDRESS}])" + re.escape(address) + r"(?![\w-])", text) is not None


def header_field(head, field):
    """A field's value in a WordPress file header ('' when there is none), read the way WordPress's get_file_data()
    does: a line that starts with the field's name (any case) and a colon, after an opening <?php and comment marks,
    its value up to the end of the line or a closing */ or ?>. Themes and plugins are recognised by it (the Theme and
    Plugin Handbooks)."""
    found = re.search(r"^(?:[ \t]*<\?(?:php)?)?[ \t/*#@]*" + re.escape(field) + r":(.*)$", head.replace("\r", "\n"),
                      re.MULTILINE | re.IGNORECASE)
    return re.sub(r"\s*(?:\*/|\?>).*", "", found.group(1)).strip() if found else ""


def local_folder(spec):
    """The folder inside the site that a package.json dependency installs from, normalised: a relative path after one
    of data/frameworks.json's local_protocols, the way npm, pnpm and Yarn write a local folder (file:agentcake-edge).
    None for anything else: a version, a git address, or a folder outside the site, absolute or climbing out of it (what
    `npm install` writes for AgentCake's own edge folder), which the site's host and other computers do not have."""
    protocol = next((name for name in load("data/frameworks.json")["local_protocols"] if spec.startswith(name)), None)
    path = spec[len(protocol):] if protocol else ""
    if not path or os.path.isabs(path):
        return None
    folder = os.path.normpath(path)
    return None if folder == os.pardir or folder.startswith(os.pardir + os.sep) else folder


def installs_the_copy(spec, folder):
    """Whether a package.json dependency installs the Node middleware from its copy, the site's folder named folder: a
    relative path to it (local_folder()), or data/frameworks.json's workspace_protocol (pnpm's and Yarn's), which
    installs the package of that name among the site's own, the copy whose package.json names it (has_copied_folder()).
    Which folders a workspace takes in is not read: one that leaves the copy out fails the site's own install."""
    protocol = load("data/frameworks.json")["workspace_protocol"]
    return spec.startswith(protocol) or local_folder(spec) == os.path.normpath(folder)


def _read_object(path):
    """A JSON file's object, or {} when it is missing, unreadable or not an object."""
    try:
        with open(path, encoding="utf-8") as f:
            found = json.load(f)
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def _not_walked():
    """The folders a walk never enters: skip_dirs, and the Node middleware's copy in the site, AgentCake's own code,
    whose files define cakeExpress( and the rest and whose tests make apps: read as the site's, it would show a
    mounting the site doesn't have."""
    copies = {spec["middleware"]["folder"] for spec in load("data/frameworks.json")["frameworks"]
              if "folder" in spec.get("middleware", {})}
    return set(load("data/site_files.json")["skip_dirs"]) | copies


def _walk(d):
    """Every file under d, relative to it and sorted, without looking into skip_dirs or the middleware's copy."""
    skip = _not_walked()
    found = []
    for root, dirs, names in os.walk(d):
        dirs[:] = sorted(x for x in dirs if x not in skip)
        found += [os.path.relpath(os.path.join(root, name), d) for name in names]
    return sorted(found)


class SiteCode:
    """One website folder, read once: its files and its framework (an entry of data/frameworks.json, or None)."""

    def __init__(self, folder):
        self.folder = folder
        self.files = _walk(folder)
        self._texts = {}
        self.spec = next((spec for spec in load("data/frameworks.json")["frameworks"] if self._is(spec["detect"])), None)

    @property
    def framework(self):
        return self.spec["name"] if self.spec else "unknown"

    def middleware(self):
        """The framework's middleware entry, or None (a static site, an unknown folder)."""
        return (self.spec or {}).get("middleware")

    # ---------------------------------------------------------------- the cake.js line
    def pages(self):
        return self.ending_in(load("data/site_files.json")["page_suffixes"])

    def head_files(self):
        """The templates that hold a page's </head>, where the cake.js line goes on a site with server code."""
        files = load("data/site_files.json")
        head_end = files["head_end"].lower()
        return [path for path in self.ending_in(files["head_suffixes"]) if head_end in self.read(path).lower()]

    def layout_file(self):
        """The Next.js layout (or _app) the framework was recognised by, else None."""
        if not self.spec or self.spec["script"] != "next":
            return None
        return next(path for path in map(os.path.normpath, self.spec["detect"]["paths"]) if path in self.files)

    def script_targets(self):
        """The files that must load cake.js: every page of a static site, the Next.js layout, every template with a
        </head>; none for WordPress, whose plugin adds the line."""
        kind = self.spec["script"] if self.spec else None
        if kind == "static":
            return self.pages()
        if kind == "next":
            return [self.layout_file()]
        if kind == "head":
            return self.head_files()
        return []

    def files_loading(self, addresses, site_key):
        """The files that load the page script from one of addresses with this site key."""
        if not site_key:  # no key yet (config.json was never written): no file can carry it
            return []
        suffixes = load("data/site_files.json")["script_suffixes"]
        return [path for path in self.ending_in(suffixes)
                if site_key in self.read(path) and any(loads_from(self.read(path), address) for address in addresses)]

    # ---------------------------------------------------------------- the server half
    def app_file(self):
        """The file that makes the app (Express's express(), Flask(__name__), Django's wsgi.py, ...), or None."""
        app = (self.spec or {}).get("app")
        if not app:
            return None
        if "files" in app:
            return next((path for path in map(os.path.normpath, app["files"]) if path in self.files), None)
        return next(iter(self.matching(app["patterns"], app["suffixes"], every=False)), None)

    def middleware_files(self):
        """Where the middleware is mounted: the files that match every one of its patterns (the WordPress plugin: its
        main file, where it is installed; none in a theme's or a plugin's own folder, as it is installed on the site)."""
        middleware = self.middleware()
        if not middleware or middleware.get("installed_elsewhere"):
            return []
        if "paths" in middleware:
            return [path for path in map(os.path.normpath, middleware["paths"]) if path in self.files]
        copied = set(middleware.get("files", []))  # the middleware's own files define what the patterns look for
        return [path for path in self.matching(middleware["patterns"], middleware["suffixes"], every=True)
                if os.path.basename(path) not in copied]

    def missing_beside(self):
        """For a middleware that is copied into the site (Python, PHP): the names of its files that are not side by side
        with the first one; all of them when the first one is nowhere."""
        names = (self.middleware() or {}).get("files", [])
        if not names:
            return []
        first = next((path for path in self.files if os.path.basename(path) == names[0]), None)
        if first is None:
            return list(names)
        folder = os.path.dirname(first)
        return [name for name in names[1:] if os.path.join(folder, name) not in self.files]

    def has_copied_folder(self):
        """For the Node middleware: whether its copy is in the site, the folder whose package.json names the package."""
        middleware = self.middleware() or {}
        if "folder" not in middleware:
            return False
        package = _read_object(os.path.join(self.folder, middleware["folder"], "package.json"))
        return package.get("name") == middleware["package"]

    def dependency(self, name):
        """What package.json's dependencies give for a package (a version, a local folder, ...), or None. Only
        dependencies count: a production install leaves devDependencies out."""
        listed = self._package().get("dependencies")
        spec = listed.get(name) if isinstance(listed, dict) else None
        return spec if isinstance(spec, str) else None

    def language(self, path):
        """What code pasted into path must be written in, so that it is valid there: "ts" (TypeScript), "esm" (a
        JavaScript module: import) or "cjs" (CommonJS: require()). The file's ending says it where it can; else a file
        of the site by the module syntax it already uses; else package.json's "type". A file not made yet (path None, or
        not in the folder) is TypeScript where the site has a tsconfig.json. The rules: data/frameworks.json's languages.
        """
        rules = load("data/frameworks.json")["languages"]
        suffix = os.path.splitext(path or "")[1]
        if suffix in rules["typescript_suffixes"]:
            return "ts"
        if suffix in rules["module_suffixes"]:
            return "esm"
        if suffix in rules["commonjs_suffixes"]:
            return "cjs"
        if path in self.files:
            if re.search(rules["module_statement"], self.read(path), re.MULTILINE):
                return "esm"
            if re.search(rules["commonjs_call"], self.read(path)):
                return "cjs"
        elif rules["typescript_config"] in self.files:
            return "ts"
        return "esm" if self._package().get("type") == rules["module_type"] else "cjs"

    # ---------------------------------------------------------------- reading
    def ending_in(self, suffixes):
        return [path for path in self.files if path.endswith(tuple(suffixes))]

    def matching(self, patterns, suffixes, every):
        compiled = [re.compile(pattern) for pattern in patterns]
        test = all if every else any
        return [path for path in self.ending_in(suffixes) if test(p.search(self.read(path)) for p in compiled)]

    def read(self, path):
        """A file's text, read once (setup and doctor look at the same files several times)."""
        if path not in self._texts:
            with open(os.path.join(self.folder, path), encoding="utf-8", errors="ignore") as f:
                self._texts[path] = f.read()
        return self._texts[path]

    # ---------------------------------------------------------------- recognising the framework
    def _is(self, detect):
        return (any(os.path.exists(os.path.join(self.folder, path)) for path in detect.get("paths", []))
                or bool(set(detect.get("node_deps", [])) & self._node_deps())
                or any(self._python_dep(name) for name in detect.get("python_deps", []))
                or bool(detect.get("suffixes") and self.ending_in(detect["suffixes"]))
                or any(self._has_header(pattern, field) for pattern, field in detect.get("headers", {}).items()))

    def _has_header(self, pattern, field):
        """Whether a file at the top of the folder whose name matches pattern names field in its file header, with a
        value: how WordPress recognises a theme (style.css, Theme Name) and a plugin (its main PHP file, Plugin Name)."""
        return any(header_field(self._head(path), field)
                   for path in self.files if os.sep not in path and fnmatch.fnmatchcase(path, pattern))

    def _head(self, path):
        """The start of a file, as much of it as WordPress reads for its header: header_bytes of the file as it is
        (counted before its line endings are read, as get_file_data() does)."""
        with open(os.path.join(self.folder, path), "rb") as f:
            return f.read(load("data/frameworks.json")["header_bytes"]).decode("utf-8", errors="ignore")

    def _package(self):
        """package.json at the top of the folder, as an object ({} when there is none)."""
        return _read_object(os.path.join(self.folder, "package.json"))

    def _node_deps(self):
        """The packages package.json depends on."""
        package = self._package()
        return {name for key in ("dependencies", "devDependencies") if isinstance(package.get(key), dict)
                for name in package[key]}

    def _python_dep(self, name):
        """Whether a dependency file names the package, or a .py file imports it."""
        named = re.compile(rf"(?<![\w.-]){re.escape(name)}(?![\w-])", re.IGNORECASE)
        for path in load("data/frameworks.json")["python_dependency_files"]:
            if path in self.files and named.search(self.read(path)):
                return True
        imported = re.compile(rf"^\s*(?:from|import)\s+{re.escape(name)}\b", re.MULTILINE)
        return any(imported.search(self.read(path)) for path in self.ending_in([".py"]))
