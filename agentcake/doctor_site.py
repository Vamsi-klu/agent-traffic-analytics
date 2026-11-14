"""`doctor`, the lines about the user's website files (S1.1, S6.1): website_checks(c, folder).

Three lines. The website settings are complete (site_domain, site_dir). Every file that must load cake.js does, from
this Agent Cake's address and with its site key (site_code.py says which files: every page of a static site, the
Next.js layout, every template with </head>; in server mode the address is path_prefix on the site's own domain,
SERVER.md); the WordPress plugin adds the line itself, so there only a page opened can tell (doctor_live.py). The server
half's middleware is mounted where setup --print --site said, with the files it needs beside it; a static site has no
server code, so its line is a SKIP; for WordPress, the plugin is installed. A failing line names the file or mounting.
"""
from agentcake.doctor_lines import SKIP
from agentcake.site_code import SiteCode
from agentcake.site_setup import SCRIPT_PATH, cake_root
from agentcake.wording import text

LEGACY_SCRIPT_PATH = "/c.js"  # protocol: 0.3.x pages load c.js; routes.py serves the page script as both


def script_addresses(c):
    """Where a page may load the page script from: this Agent Cake's address, as cake.js or 0.3.x's c.js."""
    return [cake_root(c) + path for path in (SCRIPT_PATH, LEGACY_SCRIPT_PATH)]


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
    return name, True, text("doctor_site_middleware_found", middleware=middleware["name"], files=", ".join(found))
