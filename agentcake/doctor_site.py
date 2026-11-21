"""`doctor`, the lines about the user's website files: website_checks(c, folder).

Three lines. The website settings are complete (site_domain, site_dir). Every file that must load cake.js does, from
this AgentCake's address and with its site key (site_code.py says which files: every page of a static site, the
Next.js layout, every template with </head>; in server mode the address is path_prefix on the site's own domain,
SERVER.md, and on the subdomain route also public_url with path_prefix: the 8th check of doctor_public.py); the
WordPress plugin adds the line itself, so there only a page opened can tell (doctor_live.py). The server
half's middleware is mounted where setup --print --site said, with the files it needs beside it (for Node, its copy in
the site's code, which package.json installs it from: from anywhere else, such as AgentCake's own edge folder, the
site would not build on its host or another computer); a static site has no server code, so its line is a SKIP; for
WordPress, the plugin is installed (a SKIP in a folder that holds only a theme or a plugin: the plugin is installed on
the WordPress site, never there). A failing line names the file or mounting.
"""
from agentcake import paths
from agentcake.doctor_lines import SKIP
from agentcake.site_code import SiteCode, installs_the_copy
from agentcake.site_setup import SCRIPT_PATH, cake_root, server_mode
from agentcake.wording import text

LEGACY_SCRIPT_PATH = "/c.js"  # protocol: 0.3.x pages load c.js; routes.py serves the page script as both


def script_addresses(c):
    """Where a page may load the page script from, as cake.js or 0.3.x's c.js: this AgentCake's address (cake_root:
    with public_url, the subdomain route's), and in server mode also the same-site path (path_prefix), for a site
    moving from one route to the other."""
    roots = [cake_root(c)] + ([c.get("path_prefix") or ""] if server_mode(c) else [])
    return list(dict.fromkeys(root + path for root in roots for path in (SCRIPT_PATH, LEGACY_SCRIPT_PATH)))


def website_checks(c, folder, code=None):
    code = code or SiteCode(folder)
    return [settings_check(c), script_check(c, code), middleware_check(code)]


def settings_check(c):
    missing = [key for key in ("site_domain", "site_dir") if not c.get(key)]
    if missing:
        return text("doctor_site_settings"), False, text("doctor_site_missing", keys=", ".join(missing))
    return text("doctor_site_settings"), True, text("doctor_site_domain", domain=c["site_domain"])


def script_check(c, code):
    if code.spec and code.spec["script"] == "plugin":
        return text("doctor_site_script"), SKIP, text("doctor_site_script_plugin")
    found = code.files_loading(script_addresses(c), c.get("site_key"))
    missing = [path for path in code.script_targets() if path not in found]
    info = (", ".join(found) or text("doctor_site_found_none")) + (
        text("doctor_site_missing_in", files=", ".join(missing)) if missing else "")
    return text("doctor_site_script"), bool(found) and not missing, info


def middleware_check(code):
    name, middleware = text("doctor_site_middleware"), code.middleware()
    if not middleware:
        return name, SKIP, text("doctor_site_middleware_static" if code.spec else "doctor_site_middleware_unknown")
    if middleware.get("installed_elsewhere"):  # a theme's or a plugin's own folder: the plugin is on the WordPress site
        return name, SKIP, text("doctor_site_plugin_elsewhere")
    found = code.middleware_files()
    if "paths" in middleware:  # the WordPress plugin: installed or not
        if not found:
            return name, False, text("doctor_site_plugin_none")
        return name, True, text("doctor_site_plugin_found", files=", ".join(found))
    if not found:
        return name, False, text("doctor_site_middleware_none", middleware=middleware["name"])
    missing = code.missing_beside()
    if missing:
        return name, False, text("doctor_site_middleware_beside", files=", ".join(missing))
    problem = copied_package_problem(code, middleware)
    if problem:
        return name, False, problem
    return name, True, text("doctor_site_middleware_found", middleware=middleware["name"], files=", ".join(found))


def copied_package_problem(code, middleware):
    """For the Node middleware, copied into the site's code as one folder: what is wrong, or '' when the copy is there
    and package.json's dependencies install it from that folder (a workspace dependency included)."""
    folder = middleware.get("folder")
    if not folder:
        return ""
    if not code.has_copied_folder():
        return text("doctor_site_middleware_folder", folder=folder, launcher=paths.launcher())
    spec = code.dependency(middleware["package"])
    if spec is None:
        return text("doctor_site_middleware_unlisted", package=middleware["package"], folder=folder)
    if not installs_the_copy(spec, folder):
        return text("doctor_site_middleware_package", package=middleware["package"], spec=spec, folder=folder)
    return ""
