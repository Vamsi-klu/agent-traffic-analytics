"""Test copies of websites for `setup --print --site` and `doctor`: the static site, Express, Next.js and Flask
sites an install test connects, and smaller Hono, FastAPI, Django, PHP and WordPress ones for telling the frameworks apart
(WordPress three more ways: a repository that holds only a classic theme, a block theme or a plugin; Next.js once more
in JavaScript, next-js, with a middleware.js of its own before setup, as the site of the 0.6.0 server check had; and
with the Pages Router, next-pages, whose pages/_app.js loads the line beside the page, as Next.js's guide does).
Not a test module: discovery leaves it alone.

make_site(kind, folder, tag, mounted) writes one site into folder. tag is the cake.js line its pages carry (None: none
yet, a site before setup); mounted says whether its code mounts the server half's middleware, the way the edge
folder's README says (the Python and PHP sites also get the middleware's files, copied from edge/, as a site would; the
Node sites get edge/node copied whole into NODE_COPY, tests and scripts too, as from a checkout, and their package.json
installs it from there). Every site is a few files, with nothing installed: doctor reads files, it never runs the site.
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE = os.path.join(ROOT, "edge")
KINDS = ("static", "express", "next-app", "flask", "hono", "fastapi", "django", "php", "wordpress")
T7_KINDS = ("static", "express", "next-app", "flask")  # the four folders doctor has to pass on
NODE_KINDS = ("express", "next-app", "hono")  # the sites that install the Node middleware
NODE_COPY = "agentcake-edge"  # the folder setup --print --site has a Node site copy edge/node into
NODE_PACKAGE = "@agentcake/edge"  # edge/node/package.json's name


def write(folder, name, content):
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def page(title, tag, body="<main>Coffee beans</main>"):
    return f"<!doctype html>\n<html>\n<head>\n<title>{title}</title>\n{tag or ''}\n</head>\n<body>{body}</body>\n</html>\n"


def copy_edge_files(folder, edge, names, into=""):
    for name in names:
        os.makedirs(os.path.join(folder, into), exist_ok=True)
        shutil.copy(os.path.join(EDGE, edge, name), os.path.join(folder, into, name))


def copy_node_middleware(folder):
    """edge/node copied into the site as NODE_COPY, the way setup --print --site says."""
    shutil.copytree(os.path.join(EDGE, "node"), os.path.join(folder, NODE_COPY), ignore=shutil.ignore_patterns("node_modules"))


def node_package(folder, dependencies, mounted, **fields):
    """The site's package.json; with the middleware mounted, also NODE_COPY, and the dependency npm writes for it."""
    if mounted:
        copy_node_middleware(folder)
        dependencies = {**dependencies, NODE_PACKAGE: "file:" + NODE_COPY}
    write(folder, "package.json", json.dumps({"name": "brewbean", **fields, "dependencies": dependencies}, indent=2))


def static_site(folder, tag, mounted):
    for name, title in (("index.html", "Brew Bean"), ("about.html", "About us"), ("contact.html", "Contact")):
        write(folder, name, page(title, tag))
    write(folder, "CNAME", "brewbean.example\n")


def express_site(folder, tag, mounted):
    node_package(folder, {"express": "^4.21.2", "ejs": "^3.1.10"}, mounted, main="server.js")
    mount = ('const { cakeExpress } = require("@agentcake/edge/express")\n', 'app.use(cakeExpress({ clientIp: (req) => req.ip }))\n')
    write(folder, "server.js", 'const express = require("express")\n' + (mount[0] if mounted else "")
          + "const app = express()\n" + (mount[1] if mounted else "")
          + 'app.set("view engine", "ejs")\napp.use(express.static("public"))\n'
          + 'app.get("/", (req, res) => res.render("index"))\napp.listen(3000)\n')
    write(folder, "views/layout.ejs", page("Brew Bean", tag, "<%- body %>"))
    write(folder, "views/index.ejs", "<p>Coffee beans</p>\n")


def next_site(folder, tag, mounted):
    node_package(folder, {"next": "16.0.3", "react": "19.2.0"}, mounted, homepage="https://brewbean.example")
    write(folder, "tsconfig.json", json.dumps({"compilerOptions": {"strict": True, "jsx": "preserve"}}))
    script = ("import Script from 'next/script'\n" if tag else "")
    write(folder, "app/layout.tsx", script + "export default function RootLayout({ children }) {\n"
          + f"  return (<html lang=\"en\"><body>{tag or ''}{{children}}</body></html>)\n}}\n")
    write(folder, "app/page.tsx", "export default function Home() { return <main>Coffee beans</main> }\n")
    if mounted:
        write(folder, "middleware.ts", 'import { NextResponse, type NextRequest } from "next/server"\n'
              'import { cakeNext } from "@agentcake/edge/next"\n\n'
              'const cake = cakeNext({ clientIp: (request) => request.headers.get("x-real-ip") })\n\n'
              "export default async function middleware(request: NextRequest) {\n  return cake(request, NextResponse.next())\n}\n")


def next_js_site(folder, tag, mounted):
    """A Next.js site written in JavaScript (jsconfig.json, no tsconfig.json) whose middleware.js was there before
    setup: mounted, it takes the JavaScript mounting setup gives, with the site's own response passed on."""
    node_package(folder, {"next": "14.2.35", "react": "18.3.1"}, mounted)
    write(folder, "jsconfig.json", json.dumps({"compilerOptions": {"paths": {"@/*": ["./*"]}}}))
    script = ("import Script from 'next/script'\n" if tag else "")
    write(folder, "app/layout.js", script + "export default function RootLayout({ children }) {\n"
          + f"  return (<html lang=\"en\"><body>{tag or ''}{{children}}</body></html>)\n}}\n")
    own = 'const response = NextResponse.next()\n  response.headers.set("x-shop", "brewbean")\n'
    mount = ('import { cakeNext } from "@agentcake/edge/next"\n\n'
             'const cake = cakeNext({ clientIp: (request) => request.headers.get("x-real-ip") })\n\n')
    write(folder, "middleware.js", 'import { NextResponse } from "next/server"\n' + (mount if mounted else "\n")
          + "export default async function middleware(request) {\n  " + own
          + ("  return cake(request, response)\n}\n" if mounted else "  return response\n}\n"))


def next_pages_site(folder, tag, mounted):
    """A Next.js site with the Pages Router: pages/_app.js returns the page, with the cake.js tag beside it in a fragment
    once connected (nextjs.org/docs/pages/guides/scripts, "load a script for all routes"); _app has no <body>."""
    node_package(folder, {"next": "14.2.35", "react": "18.3.1"}, mounted)
    page = "<Component {...pageProps} />"
    returned = f"(<>{page}{tag}</>)" if tag else page
    write(folder, "pages/_app.js", ("import Script from 'next/script'\n\n" if tag else "")
          + f"export default function MyApp({{ Component, pageProps }}) {{\n  return {returned}\n}}\n")
    write(folder, "pages/index.js", "export default function Home() { return <main>Coffee beans</main> }\n")
    if mounted:
        write(folder, "middleware.js", 'import { NextResponse } from "next/server"\n'
              'import { cakeNext } from "@agentcake/edge/next"\n\n'
              'const cake = cakeNext({ clientIp: (request) => request.headers.get("x-real-ip") })\n\n'
              "export default async function middleware(request) {\n  return cake(request, NextResponse.next())\n}\n")


def flask_site(folder, tag, mounted):
    write(folder, "requirements.txt", "Flask==3.1.0\n")
    mount = ("from cake_edge import CakeEdgeWSGI\n",
             'app.wsgi_app = CakeEdgeWSGI(app.wsgi_app, client_ip=lambda environ: environ.get("REMOTE_ADDR"))\n')
    write(folder, "app.py", "from flask import Flask, render_template\n" + (mount[0] if mounted else "")
          + "\napp = Flask(__name__)\n" + (mount[1] if mounted else "")
          + '\n\n@app.route("/")\ndef index():\n    return render_template("index.html")\n')
    write(folder, "templates/base.html", page("Brew Bean", tag, "{% block body %}{% endblock %}"))
    write(folder, "templates/index.html", '{% extends "base.html" %}{% block body %}<p>Coffee beans</p>{% endblock %}\n')
    if mounted:
        copy_edge_files(folder, "python", ("cake_edge.py", "cake_edge.json"))


def hono_site(folder, tag, mounted):
    node_package(folder, {"hono": "^4.6.0"}, mounted)
    mount = 'import { cakeHono } from "@agentcake/edge/hono"\napp.use(cakeHono({ clientIp: (c) => null }))\n'
    write(folder, "src/index.ts", 'import { Hono } from "hono"\nconst app = new Hono()\n' + (mount if mounted else "")
          + f"app.get(\"/\", (c) => c.html(`{page('Brew Bean', tag)}`))\nexport default app\n")


def fastapi_site(folder, tag, mounted):
    write(folder, "pyproject.toml", '[project]\nname = "brewbean"\ndependencies = ["fastapi>=0.115", "jinja2"]\n')
    mount = ("from cake_edge import CakeEdgeASGI\n",
             'app.add_middleware(CakeEdgeASGI, client_ip=lambda scope: (scope.get("client") or [None])[0])\n')
    write(folder, "main.py", "from fastapi import FastAPI\n" + (mount[0] if mounted else "") + "\napp = FastAPI()\n"
          + (mount[1] if mounted else ""))
    write(folder, "templates/base.html", page("Brew Bean", tag))
    if mounted:
        copy_edge_files(folder, "python", ("cake_edge.py", "cake_edge.json"))


def django_site(folder, tag, mounted):
    write(folder, "manage.py", "import os, sys\nfrom django.core.management import execute_from_command_line\n")
    wsgi = ("import os\nfrom django.core.wsgi import get_wsgi_application\n"
            + ("from cake_edge import CakeEdgeWSGI\n\napplication = CakeEdgeWSGI(get_wsgi_application(), "
               'client_ip=lambda environ: environ.get("REMOTE_ADDR"))\n' if mounted else "\napplication = get_wsgi_application()\n"))
    write(folder, "brewbean/wsgi.py", wsgi)
    write(folder, "brewbean/templates/base.html", page("Brew Bean", tag))
    if mounted:
        copy_edge_files(folder, "python", ("cake_edge.py", "cake_edge.json"))


def php_site(folder, tag, mounted):
    mount = ("<?php\nrequire __DIR__ . '/cake/cake_edge.php';\n(new \\AgentCake\\Edge(['clientIp' => function (array $server)"
             ": ?string { return $server['REMOTE_ADDR'] ?? null; }]))->sendHeader();\n?>\n")
    write(folder, "index.php", (mount if mounted else "") + "<?php include 'header.php'; ?>\n<main>Coffee beans</main>\n")
    write(folder, "header.php", page("Brew Bean", tag, ""))
    if mounted:
        copy_edge_files(folder, "php", ("cake_edge.php", "cake_edge_format.php", "cake_edge.json"), into="cake")


def wordpress_site(folder, tag, mounted):
    write(folder, "wp-config.php", "<?php\ndefine( 'DB_NAME', 'wordpress' );\n")
    write(folder, "wp-content/themes/twentytwentyfive/style.css", "/* Theme Name: Twenty Twenty-Five */\n")
    if mounted:
        shutil.copytree(os.path.join(EDGE, "wordpress", "agentcake"), os.path.join(folder, "wp-content", "plugins", "agentcake"))


THEME_HEADER = "/*\nTheme Name: Brew Bean\nAuthor: Brew Bean\nVersion: 1.0\n*/\n"


def wordpress_theme_site(folder, tag, mounted):
    """A repository that is one classic WordPress theme, the way the Theme Handbook lays it out: style.css with its
    header at the top, PHP templates, no WordPress around it. The plugin is never here (mounted means nothing): it is
    installed on the WordPress site that runs the theme."""
    write(folder, "style.css", THEME_HEADER + "body { font-family: serif; }\n")
    write(folder, "functions.php", "<?php\nadd_theme_support( 'title-tag' );\n")
    write(folder, "header.php", "<!doctype html>\n<html <?php language_attributes(); ?>>\n<head>\n<?php wp_head(); ?>\n"
          + (tag or "") + "\n</head>\n<body <?php body_class(); ?>>\n")
    write(folder, "footer.php", "<?php wp_footer(); ?>\n</body>\n</html>\n")
    write(folder, "index.php", "<?php get_header(); ?>\n<main>Coffee beans</main>\n<?php get_footer(); ?>\n")


def wordpress_block_theme_site(folder, tag, mounted):
    """A repository that is one block theme: style.css with its header, theme.json and HTML templates, no PHP."""
    write(folder, "style.css", THEME_HEADER)
    write(folder, "theme.json", json.dumps({"version": 3}))
    write(folder, "templates/index.html", "<!-- wp:template-part {\"slug\":\"header\"} /-->\n<!-- wp:post-content /-->\n")
    write(folder, "parts/header.html", "<!-- wp:site-title /-->\n")


def wordpress_plugin_site(folder, tag, mounted):
    """A repository that is one WordPress plugin: its main file's header names it, the way the Plugin Handbook says."""
    write(folder, "brew-bean-extras.php", "<?php\n/**\n * Plugin Name: Brew Bean Extras\n * Version: 1.0\n */\n\n"
          "add_action( 'init', function () {} );\n")
    write(folder, "index.php", "<?php\n// Silence is golden.\n")


MAKERS = {"static": static_site, "express": express_site, "next-app": next_site, "next-js": next_js_site,
          "next-pages": next_pages_site, "flask": flask_site, "hono": hono_site, "fastapi": fastapi_site,
          "django": django_site, "php": php_site, "wordpress": wordpress_site, "wordpress-theme": wordpress_theme_site,
          "wordpress-block-theme": wordpress_block_theme_site, "wordpress-plugin": wordpress_plugin_site}
# A theme's or a plugin's own folder: recognised as WordPress, with AgentCake's plugin installed on the site, not here.
WORDPRESS_PARTS = ("wordpress-theme", "wordpress-block-theme", "wordpress-plugin")


def make_site(kind, folder, tag, mounted=True):
    MAKERS[kind](folder, tag, mounted)
    return folder
