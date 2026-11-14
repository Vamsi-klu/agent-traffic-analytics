"""Reading a website's code folder: which framework it uses, which of its files must carry the cake.js line,
which file makes the app, and where the server half's middleware is mounted.

SiteCode(folder) walks the folder once (never into data/site_files.json's skip_dirs: installed packages, build output,
virtual environments, WordPress's own code) and recognises the first framework of data/frameworks.json that matches.
setup --print --site (site_setup.py) says what to change from it; doctor (doctor_site.py) checks the change from it.
Paths it returns are relative to the folder. It only reads: it never runs the site or installs anything.
"""
import json
import os
import re

from agentcake.datafiles import load


def _walk(d):
    """Every file under d, relative to it and sorted, without looking into skip_dirs."""
    skip = set(load("data/site_files.json")["skip_dirs"])
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
                if site_key in self.read(path) and any(address in self.read(path) for address in addresses)]

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
        main file, where it is installed)."""
        middleware = self.middleware()
        if not middleware:
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
                or bool(detect.get("suffixes") and self.ending_in(detect["suffixes"])))

    def _node_deps(self):
        """The packages package.json (at the top of the folder) depends on."""
        try:
            with open(os.path.join(self.folder, "package.json"), encoding="utf-8") as f:
                package = json.load(f)
        except (OSError, ValueError):
            return set()
        if not isinstance(package, dict):
            return set()
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
