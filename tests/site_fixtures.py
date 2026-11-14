"""Test copies of websites for `setup --print --site` and `doctor`: the static site, Express, Next.js and Flask
sites an install test connects, and smaller Hono, FastAPI, Django, PHP and WordPress ones for telling the frameworks apart.
Not a test module: discovery leaves it alone.

make_site(kind, folder, tag, mounted) writes one site into folder. tag is the cake.js line its pages carry (None: none
yet, a site before setup); mounted says whether its code mounts the server half's middleware, the way the edge
folder's README says (the Python and PHP sites also get the middleware's files, copied from edge/, as a site would).
Every site is a few files, with nothing installed: doctor reads files, it never runs the site.
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE = os.path.join(ROOT, "edge")
KINDS = ("static", "express", "next-app", "flask", "hono", "fastapi", "django", "php", "wordpress")
T7_KINDS = ("static", "express", "next-app", "flask")  # the four folders doctor has to pass on


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


def static_site(folder, tag, mounted):
    for name, title in (("index.html", "Brew Bean"), ("about.html", "About us"), ("contact.html", "Contact")):
        write(folder, name, page(title, tag))
    write(folder, "CNAME", "brewbean.example\n")


def express_site(folder, tag, mounted):
    write(folder, "package.json", json.dumps({"name": "brewbean", "main": "server.js",
                                              "dependencies": {"express": "^4.21.2", "ejs": "^3.1.10"}}, indent=2))
    mount = ('const { cakeExpress } = require("@agentcake/edge/express")\n', 'app.use(cakeExpress({ clientIp: (req) => req.ip }))\n')
    write(folder, "server.js", 'const express = require("express")\n' + (mount[0] if mounted else "")
          + "const app = express()\n" + (mount[1] if mounted else "")
          + 'app.set("view engine", "ejs")\napp.use(express.static("public"))\n'
          + 'app.get("/", (req, res) => res.render("index"))\napp.listen(3000)\n')
    write(folder, "views/layout.ejs", page("Brew Bean", tag, "<%- body %>"))
    write(folder, "views/index.ejs", "<p>Coffee beans</p>\n")


def next_site(folder, tag, mounted):
    write(folder, "package.json", json.dumps({"name": "brewbean", "homepage": "https://brewbean.example",
                                              "dependencies": {"next": "16.0.3", "react": "19.2.0"}}, indent=2))
    script = ("import Script from 'next/script'\n" if tag else "")
    write(folder, "app/layout.tsx", script + "export default function RootLayout({ children }) {\n"
          + f"  return (<html lang=\"en\"><body>{tag or ''}{{children}}</body></html>)\n}}\n")
    write(folder, "app/page.tsx", "export default function Home() { return <main>Coffee beans</main> }\n")
    if mounted:
        write(folder, "middleware.ts", 'import { NextResponse, type NextRequest } from "next/server"\n'
              'import { cakeNext } from "@agentcake/edge/next"\n\n'
              'const cake = cakeNext({ clientIp: (request) => request.headers.get("x-real-ip") })\n\n'
              "export async function middleware(request: NextRequest) {\n  return cake(request, NextResponse.next())\n}\n")


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
    write(folder, "package.json", json.dumps({"name": "brewbean", "dependencies": {"hono": "^4.6.0"}}, indent=2))
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


MAKERS = {"static": static_site, "express": express_site, "next-app": next_site, "flask": flask_site, "hono": hono_site,
          "fastapi": fastapi_site, "django": django_site, "php": php_site, "wordpress": wordpress_site}


def make_site(kind, folder, tag, mounted=True):
    MAKERS[kind](folder, tag, mounted)
    return folder
