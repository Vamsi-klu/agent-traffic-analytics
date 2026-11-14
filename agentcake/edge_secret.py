"""The server half's shared secret, $CAKE_HOME/srv_secret (from cake 0.3.3).

A site's middleware (edge/) signs each page's token with it, and `agentcake logs import` signs each batch it sends to
/edge with it (edge_signature.py); this Agent Cake checks both with it. srv_secret() reads it: None when there is none
or it is shorter than secret_min_chars (data/sizes.json), and the server half is then off. create_secret() makes one for
`agentcake secret init`: random (random_bytes.secret), base64url, readable by its owner only, and never over a file that
is there. ensure_secret() makes it on first use, for a web server log's import on this computer (logs.py), where
nobody ran `secret init`.
"""
import base64
import os
import secrets
import threading

from agentcake import paths
from agentcake.datafiles import sizes

OWNER_ONLY = 0o600  # protocol: POSIX mode rw------- (the secret file)
_SECRET_LOCK = threading.Lock()  # ensure_secret: one thread of this process makes the secret


def srv_secret():
    try:
        with open(paths.secret_file(), "rb") as f:
            v = f.read().strip()
        return v if len(v) >= sizes()["secret_min_chars"] else None
    except OSError:
        return None


def create_secret():
    """A new random secret in $CAKE_HOME/srv_secret, readable by its owner only; fails if the file exists."""
    os.makedirs(paths.home(), exist_ok=True)
    fd = os.open(paths.secret_file(), os.O_WRONLY | os.O_CREAT | os.O_EXCL, OWNER_ONLY)
    os.write(fd, base64.urlsafe_b64encode(secrets.token_bytes(sizes()["random_bytes"]["secret"])).rstrip(b"=")); os.close(fd)


def ensure_secret():
    """The secret, made on first use when there is none. Pages come in on many threads at once, so one thread makes it
    while the others wait and then read it; another process can only be first through create_secret's exclusive
    create."""
    secret = srv_secret()
    if secret:
        return secret
    with _SECRET_LOCK:
        secret = srv_secret()
        if secret:
            return secret
        try:
            create_secret()
        except FileExistsError:
            pass  # another process (e.g. `agentcake secret init`) made it first; a file too short stays as it is
        return srv_secret()
