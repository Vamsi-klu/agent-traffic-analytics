"""Settings: agentcake/defaults.json, then the user's $CAKE_HOME/config.json, then $CAKE_PORT.

defaults.json lists every setting once: its default, how a typed value is checked (choices, min, max, pattern) and
what it is for ("about"), the way PostHog 1.0's posthog/settings.py gives each setting a default that the environment
can override. config.json holds only what the user set (cake 0.3.x wrote every value there; such files keep
working). load_cfg() merges the three; sources() says where each value came from; coerce(key, text) turns what was
typed into a checked value or raises ValueError naming what is allowed; base_url() is the local page's address.
A setting marked "retired" no longer does anything: it keeps its default for the code that still reads it, and
coerce() refuses every value with the reason (mask_inputs since 0.4.0: cake.js masks every input, data/privacy.json).
"""
import json
import os
import re
import secrets

from agentcake import paths
from agentcake.datafiles import load, sizes
from agentcake.wording import raw

LOCAL_HOST = "127.0.0.1"  # protocol: the local page only ever listens on loopback (a design rule, never a setting)
JSON_INDENT = 2  # protocol: config.json keeps the two-space layout cake 0.3.x wrote
TRUE_WORDS = ("1", "true", "yes", "on")
TYPES = {"str": str, "int": int, "float": float, "bool": bool}

SCHEMA = load("defaults.json")
DEFAULTS = {key: spec["default"] for key, spec in SCHEMA.items()}
SETTABLE = set(DEFAULTS)


def user_settings():
    """What the user set: config.json as written ({} before the first save); a 0.3.3 max_db_mb is the budget."""
    cfg = paths.config_file()
    if not os.path.exists(cfg):
        return {}
    with open(cfg) as f:
        user = json.load(f)
    if "max_db_mb" in user:  # 0.3.3's name for the budget: kept as the budget unless one was set since
        user.setdefault("budget_mb", int(user.pop("max_db_mb")))
    return user


def load_cfg():
    c = dict(DEFAULTS)
    c.update(user_settings())
    if os.environ.get("CAKE_PORT"):
        c["port"] = int(os.environ["CAKE_PORT"])
    return c


def sources():
    """Where each setting's value comes from: 'default', 'user' (config.json) or 'env' ($CAKE_PORT)."""
    user = user_settings()
    keys = list(DEFAULTS) + [k for k in user if k not in DEFAULTS]
    return {k: "env" if k == "port" and os.environ.get("CAKE_PORT") else "user" if k in user else "default" for k in keys}


def save_cfg(c):
    """Write c as config.json, atomically. Pass what the user set (user_settings()), not load_cfg()'s merge."""
    os.makedirs(paths.home(), exist_ok=True)
    cfg = paths.config_file()
    tmp = cfg + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f, indent=JSON_INDENT)
    os.replace(tmp, cfg)


def save_user(**values):
    """Set these keys in config.json, keeping what else the user set."""
    user = user_settings()
    user.update(values)
    save_cfg(user)


def ensure_cfg():
    """The settings, after making the site key on first use (it is kept in config.json)."""
    if not user_settings().get("site_key"):
        save_user(site_key="ck_" + secrets.token_hex(sizes()["random_bytes"]["site_key"]))
    return load_cfg()


def base_url(c=None):
    return f"http://{LOCAL_HOST}:{(c or load_cfg())['port']}"


def _path_prefix(v):
    v = "/" + v.strip().strip("/")
    return "" if v == "/" else v


# how typed text is tidied before it is checked; any other text setting is only stripped
NORMALIZE = {"site_domain": lambda v: re.sub(r"^https?://", "", v).strip("/"),
             "site_dir": lambda v: os.path.abspath(os.path.expanduser(v)),
             "path_prefix": _path_prefix}


def _invalid(key, rule, **values):
    return ValueError(raw("invalid_setting").get(key) or raw(rule).format(key=key, **values))


def coerce(k, v):
    spec = SCHEMA[k]
    if "retired" in spec:
        raise _invalid(k, "invalid_retired")
    kind = TYPES[spec["type"]] if "type" in spec else type(spec["default"])
    if kind is bool:
        return str(v).lower() in TRUE_WORDS
    if kind in (int, float):
        v = kind(v)
        if "choices" in spec and v not in spec["choices"]:
            raise _invalid(k, "invalid_choice", choices=", ".join(map(str, spec["choices"])))
        if "min" in spec and v < spec["min"]:
            raise _invalid(k, "invalid_min", min=spec["min"])
        if "max" in spec and v > spec["max"]:
            raise _invalid(k, "invalid_max", max=spec["max"])
        return v
    v = NORMALIZE.get(k, str.strip)(v)
    empty_allowed = spec["default"] == ""  # an empty public_listen or path_prefix turns server mode off
    if "pattern" in spec and (v or not empty_allowed) and not re.fullmatch(spec["pattern"], v):
        raise _invalid(k, "invalid_pattern")
    return v
