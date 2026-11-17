# AgentCake on a server

AgentCake normally runs on your own computer: one process and one SQLite database, a local page at
http://127.0.0.1:7878/ (`INSTALL.md`). The visitors of a public website cannot reach a program on your
computer. To see them, install the whole of AgentCake, the same process and database, on a server your website can
reach. The dashboard still never goes on the internet: it stays on that server's 127.0.0.1, and you open it through a
tunnel.

Visits go straight from the visitors' browsers to your server, through your own load balancer, on a path of your own
site. There is no relay, no tunnel for the data and no third party, and AgentCake sends no telemetry.

## Two routes

| | Only on this computer | The whole of AgentCake on a server |
|---|---|---|
| Use it for | a site you run on this computer (localhost) | the visitors of a public website |
| Install | `INSTALL.md` | this file: with systemd or with Docker |
| Listens on | 127.0.0.1:7878, the local page | 127.0.0.1:7878, the local page, and a public listener for the page script and collect |
| The dashboard | http://127.0.0.1:7878/ | http://127.0.0.1:7878/ on the server, through an SSH or IAP tunnel |
| The page script | `http://127.0.0.1:7878/cake.js` | `/cake/cake.js` on your own site |

## How it fits together

```text
visitor's browser on https://example.com/, after the visitor agreed to analytics
  |  GET  /cake/cake.js
  |  POST /cake/collect, every 2 s
  v
your load balancer: path rules send only those paths to AgentCake, everything else to your site as before;
  |  it adds X-Cake-Client-IP, X-Cake-Region, X-Cake-Subdivision, X-Cake-City, X-Cake-JA4 and X-Cake-Proto
  v
the AgentCake server, whose firewall admits the load balancer only
  0.0.0.0:8080     public listener: the page script, collect and a health check, under /cake
  127.0.0.1:7878   the local page: dashboard, sessions, replay, settings
        ^
        +-- your computer: an SSH or IAP tunnel to 127.0.0.1:7878, then http://127.0.0.1:7878/
```

## What the public listener answers

The setting `public_listen` turns on a second listener. Under `path_prefix` it answers only these, and 404 to anything
else:

| Method | Path | What |
|---|---|---|
| GET | `/cake/cake.js` | the page script |
| GET | `/cake/c.js` | the same script by its short name |
| GET | `/cake/rrweb-record.min.js` | the session recorder of cake 0.3.x, for pages that still load it with a tag of its own (the page script has had it inside since 0.4.0); content blockers block this file by its name |
| POST | `/cake/collect` | what the page script sends |
| POST | `/cake/edge` | page requests from your web server's log, signed with the server middleware's secret (Server logs, below) |
| GET | `/cake/healthz` | the load balancer's health check: `ok` |

- The dashboard, sessions, replay, settings and the JSON API are never served there, under any path.
- No CORS headers: the page script sends to a path of the page's own site. A preflight (`OPTIONS`) gets 404.
- Limits, all of them settings: a POST over 1 MB is refused (413) before its body is read (`public_max_body_bytes`); a
  session keeps at most 200,000 replay events (`max_events_per_session`); a session is judged at most every 15 s while
  its visits arrive (`public_judge_interval_ms`), and again when you open the dashboard, the sessions or its replay.

## Load balancer path rules

AgentCake lives on a path of your own site, for example `https://example.com/cake/`. In your load balancer, send
exactly these paths on your site's host to the public port of the AgentCake server, and leave every other path as it
is:

```text
/cake/cake.js
/cake/collect
```

Add `/cake/c.js` only if your pages load the script by that name, and `/cake/rrweb-record.min.js` only if they still
have cake 0.3.x's two tags, which load the session recorder as a file of its own: content blockers such as uBlock
Origin block that file by its name (EasyPrivacy's rule `/rrweb-record.min.js`), while the page script has the recorder
inside and is not blocked. The health check goes straight to the server (`/cake/healthz` on the public port, 200 when
it is up) and needs no path rule, and so does `/cake/edge`: the log import sends to the public port from the load
balancer's own machine (Server logs, below). With these rules, `/cake/` and every other path under it stay your site's
own pages, so the dashboard is out of the internet's reach twice over: the load balancer never forwards it, and
AgentCake never serves it publicly.

Choose the path (`path_prefix`) as a path of your own site that says nothing about tracking: `/cake` is fine. Under
`/api`, `/analytics` or `/stats`, content blockers already block some of AgentCake's uploads (EasyPrivacy's rules
`/api/collect|`, `/analytics/collect?` and `/stats/collect?`), and their lists target words such as analytics,
tracking, telemetry, stats and metrics; leave those out of a subdomain for AgentCake too. PostHog's guides to
serving its script through your own domain give the same advice for
[paths](https://posthog.com/docs/advanced/proxy/cloudflare) and
[subdomains](https://posthog.com/docs/advanced/proxy/managed-reverse-proxy).

Google Cloud, global external Application Load Balancer: a path matcher for your site's host in the URL map.

```yaml
pathMatchers:
- name: example-com
  defaultService: <your site's backend service>
  pathRules:
  - paths: [/cake/cake.js, /cake/collect]
    service: <AgentCake's backend service>
```

AgentCake's backend service: HTTP to an instance group whose named port is 8080, the health check `/cake/healthz` on
port 8080, request logging off (collect arrives every 2 s from every visitor, and the load balancer's log would keep
each visitor's address), and the six headers of the next section as custom request headers.

nginx in front of your site, inside your site's `server` block:

```nginx
location ~ ^/cake/(cake\.js|collect)$ {
    proxy_pass http://192.0.2.10:8080;                # the AgentCake server's public listener
    proxy_set_header X-Cake-Client-IP $remote_addr;
    proxy_set_header X-Cake-Proto $server_protocol;
    proxy_set_header X-Cake-Region "";                 # nginx knows no country: an empty value drops a visitor's own
    proxy_set_header X-Cake-Subdivision "";            # nor a region
    proxy_set_header X-Cake-City "";                   # nor a city
    proxy_set_header X-Cake-JA4 "";                    # nor a TLS fingerprint
    client_max_body_size 1m;
}
```

`$remote_addr` is the visitor's address only when nginx is the first hop. Behind another proxy or a CDN it is that
proxy's address: then set `X-Cake-Client-IP` to `""` as well.

## Which headers AgentCake trusts

Only on the public listener, only with `trust_lb` on, and only these six, which your load balancer sets:

| Header | Google Cloud custom request header | What AgentCake keeps |
|---|---|---|
| `X-Cake-Client-IP` | `X-Cake-Client-IP:{client_ip_address}` | which published range holds the address, and whether it is iCloud Private Relay, a CDN or a cloud (`agentcake/data/lists/ip_ranges.json`: the ranges AI, search, CDN and cloud companies publish); two salted hashes, of the address and of its /24 or /48, whose salt is replaced every `ip_salt_days`; never the address |
| `X-Cake-Region` | `X-Cake-Region:{client_region}` | the country |
| `X-Cake-Subdivision` | `X-Cake-Subdivision:{client_region_subdivision}` | the region (a CLDR subdivision id such as `USCA`), for the dashboard's Geography table |
| `X-Cake-City` | `X-Cake-City:{client_city}` | the city, for the dashboard's Geography table |
| `X-Cake-JA4` | `X-Cake-JA4:{tls_ja4_fingerprint}` | the TLS fingerprint |
| `X-Cake-Proto` | `X-Cake-Proto:{client_protocol}` | the HTTP version |

```sh
gcloud compute backend-services update <AgentCake's backend service> --global \
  --custom-request-header='X-Cake-Client-IP:{client_ip_address}' \
  --custom-request-header='X-Cake-Region:{client_region}' \
  --custom-request-header='X-Cake-Subdivision:{client_region_subdivision}' \
  --custom-request-header='X-Cake-City:{client_city}' \
  --custom-request-header='X-Cake-JA4:{tls_ja4_fingerprint}' \
  --custom-request-header='X-Cake-Proto:{client_protocol}'
```

- Nothing else counts: `X-Forwarded-For`, `Forwarded` and `X-Real-IP` are never read. A visitor can write anything into
  them, and how many proxies to skip differs from one setup to the next; AgentCake trusts the one layer you set up.
- The six are only true when two things hold. Your load balancer sets or empties each of them on every request it
  forwards: Google Cloud's custom request headers replace a header of the same name that a client sent, and a header
  that a load balancer neither sets nor empties passes through from the visitor unchanged. And the firewall lets only
  the load balancer reach the public port, so that nobody can connect directly with headers of their own.
- If your load balancer cannot set them, leave `trust_lb` off. AgentCake then keeps no country, region, city, range, JA4
  or protocol, and the dashboard's Geography table shows time zones and languages only; everything else works the same.
  A load balancer that knows the country but not the region or city sets those two to an empty value.
- The address is looked up and dropped: it is not stored, not logged and not shown.

## The dashboard: 127.0.0.1 only, through a tunnel

The local page (dashboard, sessions, replay, settings) always listens on 127.0.0.1, at `port` (7878 by default). No
setting makes it listen anywhere else. It has no login: nothing outside the server can reach it, and anyone who can log
in to the server can open it. From your computer, open a tunnel, then http://127.0.0.1:7878/:

```sh
ssh -N -L 7878:127.0.0.1:7878 <you>@<server>
gcloud compute ssh <vm> --zone=<zone> --tunnel-through-iap -- -N -L 7878:127.0.0.1:7878
```

If 7878 is taken on your computer, pick another port on your side: `-L 7979:127.0.0.1:7878`, then
http://127.0.0.1:7979/. With Docker, this works on the host's network only (`--network host`, below).

## Firewall

| Port | Who may connect | Google Cloud |
|---|---|---|
| the public port, 8080 | the load balancer only: its proxies and health checks | `35.191.0.0/16` and `130.211.0.0/22` |
| 22, SSH | you; on Google Cloud, IAP only | `35.235.240.0/20` |
| 7878 | nobody: it listens on 127.0.0.1 | no rule |

```sh
gcloud compute firewall-rules create agentcake-from-lb --network=default --direction=INGRESS --action=ALLOW \
  --rules=tcp:8080 --source-ranges=35.191.0.0/16,130.211.0.0/22 --target-tags=agentcake
gcloud compute firewall-rules create agentcake-ssh-from-iap --network=default --direction=INGRESS --action=ALLOW \
  --rules=tcp:22 --source-ranges=35.235.240.0/20 --target-tags=agentcake
```

The first two ranges are where Google's global external Application Load Balancer and its health checks connect from;
the third is IAP's TCP forwarding. The server needs no external address: the load balancer reaches it on its internal
one, and you reach it through IAP. AgentCake opens no connection to the internet while it runs: its name lists and
published ranges come with each release (`agentcake lists` shows their date). Only `agentcake lists update`, which you
run yourself, fetches newer ones; on a server without internet access, a new release brings them. On another host, do
the same with its firewall: the load balancer's address to the public port, SSH from where you connect, nothing else.

## Install with systemd

The way to run it on a small Linux server: one service and the system's own `python3`, with no container daemon taking
memory. You need systemd, `python3` 3.11 or newer (Debian 12 has 3.11, Debian 13 has 3.13), `deploy/cake.service` (it
comes with this file in AgentCake's source and in the release folder, `agentcake-<version>.tar.gz`) and two files of
the release: `agentcake-<version>-py3-none-any.whl` and `SHA256SUMS`. The server needs neither pip nor the internet: copy the files over (`scp`, or `gcloud compute scp …
--tunnel-through-iap`). The service, its user and its data folder keep the short name: `cake.service`, the user
`cake`, the folder `/var/lib/cake`.

```sh
sha256sum -c SHA256SUMS --ignore-missing
sudo useradd --system --home-dir /var/lib/cake --shell /usr/sbin/nologin cake
sudo install -d -o cake -g cake -m 700 /var/lib/cake
sudo python3 -I -m zipfile -e agentcake-<version>-py3-none-any.whl /opt/cake/app
sudo install -m 644 deploy/cake.service /etc/systemd/system/cake.service
```

A wheel is a zip of the package. Unpacked, `/opt/cake/app/agentcake/__main__.py` runs it with nothing installed, and
that is what the service's `ExecStart` runs. On this route, a command below that starts with `agentcake` means:

```sh
alias agentcake='sudo -u cake env CAKE_HOME=/var/lib/cake python3 -I /opt/cake/app/agentcake/__main__.py'
```

In a script, or for a coding agent that runs one command at a time, write the command out instead of the alias. Then
set it up (Settings, below) and start it:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now cake
curl -s http://127.0.0.1:8080/cake/healthz
```

- Logs: `journalctl -u cake`. AgentCake prints where it listens when it starts, and logs no requests.
- Memory: `deploy/cake.service` caps the process at 600 MB (`MemoryMax`), for a server with 1 GB. Change it without
  editing the file: `sudo systemctl set-property cake MemoryMax=800M`.
- The wheel installed instead of unpacked, in a virtual environment (on Debian, `sudo apt install python3-venv`
  first): `sudo python3 -m venv /opt/cake/venv`, then
  `sudo /opt/cake/venv/bin/pip install --no-index --no-deps agentcake-<version>-py3-none-any.whl`, then replace
  `ExecStart` in a drop-in, `/etc/systemd/system/cake.service.d/wheel.conf`, and run `sudo systemctl daemon-reload`.
  The alias becomes `sudo -u cake env CAKE_HOME=/var/lib/cake /opt/cake/venv/bin/python3 -I -m agentcake`.

```ini
[Service]
ExecStart=
ExecStart=/opt/cake/venv/bin/python3 -I -m agentcake serve
```

## Install with Docker

`Dockerfile` (next to this file) is `python:3.14-slim` with the wheel installed. It runs as a user of its own (uid
10001), keeps its data in the volume `/var/lib/cake`, and exposes only the public port, 8080. Build it in a folder that
holds `Dockerfile`, `.dockerignore` and, alone in `dist/`, `agentcake-<version>-py3-none-any.whl` checked against
`SHA256SUMS`. The release folder is such a folder: `agentcake-<version>.tar.gz`, checked against `SHA256SUMS` and
unpacked, has all three. From a checkout of the source, `python3 -I tools/release.py build` builds the release; a wheel
that `pip wheel` makes from a checkout has neither the compiled local pages nor the sites' middleware, which a release
copies into the package:

```sh
docker build -t agentcake .
docker volume create agentcake-data
docker run -d --name agentcake --network host --restart unless-stopped --memory 600m \
  -v agentcake-data:/var/lib/cake agentcake
```

It starts with the local page only. On this route, a command below that starts with `agentcake` means:

```sh
alias agentcake='docker exec agentcake python3 -I -m agentcake'
```

Set it up (Settings, below), then `docker restart agentcake` and `curl -s http://127.0.0.1:8080/cake/healthz`.

- The host's network is required. The local page listens on 127.0.0.1, which in a network of its own is the container's
  loopback, where no tunnel reaches; on the host's network it is the server's 127.0.0.1. The public listener then binds
  the server's port 8080 itself: there is nothing to publish with `-p`, and the host's firewall applies as it is.
- `docker inspect --format '{{.State.Health.Status}}' agentcake` says `healthy` while the local page answers: the
  image's health check runs `agentcake status`.
- `docker stop agentcake` ends it with SIGINT, the image's stop signal.
- A host folder instead of the volume: `sudo install -d -o 10001 -g 10001 -m 700 /srv/agentcake`, then
  `-v /srv/agentcake:/var/lib/cake`.

## Settings

Run these on the server, with `agentcake` as your route above sets it:

```sh
agentcake config set public_listen 0.0.0.0:8080
agentcake config set path_prefix /cake
agentcake config set trust_lb true
agentcake config set site_domain example.com
agentcake config set budget_mb 20480
agentcake secret init
agentcake config get site_key
```

Restart after changing a setting: `sudo systemctl restart cake`, or `docker restart agentcake`.

| Setting | On a server | What it does |
|---|---|---|
| `public_listen` | `0.0.0.0:8080` | the public listener's address and port; empty, the default, turns server mode off |
| `path_prefix` | `/cake` | the path of your site that the load balancer sends to AgentCake (how to choose it: Load balancer path rules) |
| `trust_lb` | `true` | read the load balancer's six headers on the public listener; off by default |
| `site_key` | made on first use | the key in your pages' script tag; collect refuses any other |
| `site_domain` | `example.com` | your site's domain: the dashboard's title, and where uploads should come from (uploads from another site are kept, but left out of the dashboard) |
| `port` | `7878`, the default | the local page's port, always on 127.0.0.1 |
| `budget_mb` | see Disk budget | the disk budget of the database and the replay chunks, in MB |
| `auto_free` | `true`, the default | free space in the budget: when less than 10% of it is left, delete session replays, oldest first, across all session types |
| `disk_min_free_mb` | `10240`, the default | keep this much of the disk free: below it new replays aren't stored and none is deleted, until there is room (see Disk budget) |
| `retention_days` | `0`, the default | 0 keeps everything; 30 or 90 deletes whole sessions older than that |
| `public_max_body_bytes` | `1000000`, the default | the largest POST the public listener reads |
| `max_events_per_session` | `200000`, the default | the records a session keeps at most in each stream (replay, raw input, signals); later ones are counted, not kept |
| `public_judge_interval_ms` | `15000`, the default | how often a session is judged at most while it sends |
| `ip_salt_days` | `30`, the default | how long one salt of the visitors' address hashes is used; then a new one replaces it |
| `token_max_age_ms` | `900000`, the default | a server middleware token older than this is refused |

`agentcake config get` prints every value in use; `agentcake/defaults.json` lists every setting with its default and
what it does.

## The page script on your site

Add this to your pages once a visitor has agreed to analytics (your consent banner decides when), with the key that
`agentcake config get site_key` printed:

```html
<script src="/cake/cake.js" data-site="ck_…" defer></script>
```

When a visitor declines later, call `window.cake.stop()`: recording and sending stop, and the visit id, the visitor id
and its identify hash are forgotten.

If your site has sign-in, it can have each signed-in visitor counted once across browsers and devices: call
`window.cake.identify(user.id)` after they sign in, with an internal ID that is hard to guess (not an e-mail address or
a number that counts up), and `window.cake.reset()` when they sign out. The browser sends only a SHA-256 hash of your
site key and the ID ([`PRIVACY.md`](PRIVACY.md), "Counting a signed-in visitor once").

## The server middleware

Optional. Your site's server can tell AgentCake what only it saw of a page's request, such as the request's headers and
an agent's signature. It signs a token for each page, `Server-Timing: cake;desc="c1.<payload>.<mac>"` (HMAC-SHA256 with
the secret in `srv_secret`); the page script forwards it; AgentCake accepts each token once, within 15 minutes, and
shows it on the replay page under "Server middleware". For a Node site, `edge/node/` is that middleware (its README
says how to add it). `agentcake secret init` (Settings, above) makes the secret. Hand it to your site's server through
a pipe, never by pasting it; for example, from your computer into Google Cloud's Secret Manager:

```sh
gcloud compute ssh <vm> --zone=<zone> --tunnel-through-iap \
  --command 'sudo -u cake env CAKE_HOME=/var/lib/cake python3 -I /opt/cake/app/agentcake/__main__.py secret print' \
  | gcloud secrets versions add <your secret> --data-file=-
```

## Server logs

Optional, for a site without the middleware. nginx, Apache and Caddy write every page request into their access log,
with some of what only the server sees: an agent's Web Bot Auth signature, the browser's `Sec-Fetch-*` headers.
`agentcake logs import` reads such a log where it lies and sends its page requests to AgentCake, which matches each
one to the visit it opened and keeps what it says with that visit, as it keeps a page's token.

1. Log the recommended format. AgentCake reads nginx's and Apache's combined format too, but combined has no Host,
   no `Accept-Language`, no `Sec-Fetch-*` and no signature headers, and its time is in whole seconds.
   `docs/nginx.conf.example`, `docs/apache.conf.example` and `docs/Caddyfile.example` hold the lines to add, and so
   does this command:

```sh
agentcake logs formats
```

2. When the log is written on another machine than AgentCake's (the load balancer of "Load balancer path rules"),
   install AgentCake there too and give it the server middleware's secret through a pipe, from your computer:

```sh
ssh <the AgentCake server> 'sudo -u cake env CAKE_HOME=/var/lib/cake python3 -I /opt/cake/app/agentcake/__main__.py secret print' \
  | ssh <the web server> 'umask 077; mkdir -p ~/.cake; cat > ~/.cake/srv_secret'
```

3. Import every five minutes, on the machine with the log, from its crontab. Cron's PATH is short: write agentcake's
   full path there (`command -v agentcake` prints it). On the AgentCake server itself, leave out `--to`:

```text
*/5 * * * * agentcake logs import /var/log/nginx/agentcake.log --since 10m --to http://192.0.2.10:8080/cake
```

Each run prints how many page requests it sent, how many matched a visit and which recommended headers the log
lacks; `agentcake doctor` on the AgentCake server shows the last import. A line sent twice is kept once, so the runs'
`--since` windows may overlap. After the log is rotated, import the rotated file once too (`agentcake.log.1`), for
the lines of its last minutes.

How it works:

- A log has no token. A page request belongs to the visit whose page view sent its first upload from the same
  address and with the same User-Agent at most 30 seconds later (`log_match_window_s`; `log_match_skew_s`, 2 seconds,
  allows for the web server's clock and AgentCake's to differ a little). The address is the one your load balancer
  gives AgentCake, so with `trust_lb` off no line can match, and the log has to hold the visitor's address, not a
  CDN's: behind a CDN, nginx's realip module, Apache's mod_remoteip or Caddy's `trusted_proxies` set it.
- A line that matches no visit is dropped, and nothing of it is kept: that visitor never ran the page script, because
  they did not agree to analytics or ran no JavaScript.
- Of a matched line AgentCake keeps what it keeps of an upload: the values of `User-Agent`, `Accept-Language`,
  `Sec-Fetch-*`, `Sec-CH-UA` and the signature headers, the method, the path without its query, the status, which
  published range holds the address, and the two salted hashes of the address; and whether a Web Bot Auth signature
  verifies with the bundled keys, checked at the time the line was logged. Never the address, the query, cookies or
  credentials.
- The log stays yours: it is read line by line where it lies, never copied, and only page requests leave the machine:
  a GET of a page, not a redirect or a static file.
- `/cake/edge` hears only a sender with the server middleware's secret: each request carries the HMAC of its time and
  body, and anything else gets 403. No path rule forwards it from the internet.

## The data folder

`CAKE_HOME`: `/var/lib/cake` on a server (`deploy/cake.service` and the image both use it), `~/.cake` on your own
computer. It is the only place AgentCake writes: the service may write nowhere else (`ProtectSystem=strict` with
`ReadWritePaths`), and the container writes only to its volume.

| File | What |
|---|---|
| `config.json` | the settings |
| `cake.db` | the database (SQLite in WAL mode, with `cake.db-wal` and `cake.db-shm` beside it): sessions, classifications, events, the index of the replay chunks, the server middleware's tokens |
| `replays/` | replays as compressed 10-second chunks, appended to `replays/<date>/<hour>.bin` (UTC) |
| `backups/` | the copy of `cake.db` that `agentcake migrate` makes before it changes anything |
| `srv_secret` | the server middleware's secret, readable by its owner only |
| `cake.log`, `cake.pid` | only with `agentcake start` on your own computer; the service logs to the journal |
| `lists/` | newer name and address lists, only after `agentcake lists update`; otherwise the release's own are used |

## Disk budget

AgentCake records every session and keeps it: nothing is deleted by age unless you choose 30 or 90 days
(`retention_days`; a chosen retention deletes whole sessions, their replay chunks included). AgentCake's data has a
disk budget, `budget_mb`: 10240 (10 GB) by default. It counts the database and the replay chunks.

| Boot disk | `budget_mb` |
|---|---|
| 20 GB | 10240, the default |
| 30 GB | 20480 |
| larger | the disk minus 10 GB |

Debian itself takes about 3 GB of a boot disk; the rest of the 10 GB outside the budget is room for system updates and
logs. Back up to a snapshot or another disk, not to this one.

- From 80% of the budget, the dashboard and the settings show a warning and how long until it is full at last week's
  pace.
- When less than 10% of the budget is left and `auto_free` is on (the default), AgentCake deletes session replays,
  oldest first, across all session types, until its data is under 90% of the budget (`auto_free_target_ratio`). A
  replay still being recorded (its session active in the last hour) waits until the session is quiet. Only replays
  go: every classification, share, timeline and server middleware record stays, and so do the input timing and
  browser signals the classification was made from; the session page says the replay was deleted to make room. The
  chunk files give the space back at the next upkeep round, within a minute.
- With `auto_free` off, a full AgentCake stops storing new replay events; each visit and its classification are still
  recorded.
- Whatever the budget, AgentCake keeps `disk_min_free_mb` of the disk free (10240, 10 GB, by default). Below it,
  AgentCake stores no new replays and deletes none, since a deletion cannot be undone and would not free a disk other
  files fill; it starts storing them again on its own once there is room. Each visit and its classification are still
  recorded, `/api/health`, the settings page and the dashboard say why (`"replays_stopped"` is `"disk"`), and
  `agentcake doctor` fails its disk line, with the floor and the free space. The floor counts everything on the disk,
  not only AgentCake, so with the sizes above it comes about 3 GB (Debian's share) before the budget is full.

## Backups

- On a cloud server, take disk snapshots (on Google Cloud, a daily snapshot schedule on the boot disk). A snapshot
  catches the database the way a power cut would, and SQLite is built to come back from that.
- Anywhere: stop AgentCake, copy the data folder, start it again. Visits that arrive while it is stopped are not
  recorded.

```sh
sudo install -d -m 700 /var/backups/cake
sudo systemctl stop cake
sudo tar -C /var/lib -czf /var/backups/cake/cake-$(date +%F).tar.gz cake
sudo systemctl start cake
```

The backup holds `srv_secret` and your visitors' sessions: keep it as private as the server. To restore, stop
AgentCake, put the folder back (owned by `cake`, mode 700) and start it. With Docker, stop the container and copy the volume
the same way; `docker volume inspect agentcake-data` shows where it is.

## Upgrading

Back up first, and check the new wheel against the new `SHA256SUMS`. With systemd, keep the previous program next to
the new one:

```sh
sudo systemctl stop cake
sudo mv /opt/cake/app /opt/cake/app-<old version>
sudo python3 -I -m zipfile -e agentcake-<new version>-py3-none-any.whl /opt/cake/app
sudo systemctl start cake
```

If the new release's `deploy/cake.service` differs from the installed one, install it again and run
`sudo systemctl daemon-reload`. With Docker, build the image from the new wheel (`docker build -t agentcake .`) and
replace the container; the data stays in the volume:

```sh
docker stop agentcake
docker rm agentcake
docker run -d --name agentcake --network host --restart unless-stopped --memory 600m \
  -v agentcake-data:/var/lib/cake agentcake
```

A newer AgentCake brings an older database up to date when it opens it. The way back is the previous program together
with the backup, not the previous program alone.

Coming from 0.3.4, whose replays are rows inside `cake.db`: with the service stopped (`agentcake migrate` refuses to run
while AgentCake runs on the same data folder), run these, then start it again. The first says what would be done; the
second checks there is room, copies `cake.db` to `backups/` and copies the replays into chunk files, keeping the rows.

```sh
agentcake migrate --dry-run
agentcake migrate
```

## Python 3.14 and zstd

AgentCake needs Python 3.11 or newer and nothing outside Python's standard library. It keeps replays as compressed
chunks: with zstd from Python 3.14's standard library (`compression.zstd`) when it can, otherwise with zlib, which every
Python has and which takes more disk. After 14
days, at night, the chunks are compressed again, harder; a server without a battery counts as on mains power for that.
`agentcake doctor` says which compression is in use.

- The Docker image is Python 3.14 (`python:3.14-slim`, built with zstd).
- A distribution's `python3` older than 3.14 (Debian 12: 3.11, Debian 13: 3.13) uses zlib. For zstd on such a server,
  use the Docker image, or install Python 3.14 in a folder every user can read (not under `/root` or `/home`: the
  service runs with `ProtectHome=true`) and put that `python3` in `ExecStart`.
- Chunks written with zstd can only be read by a Python that has zstd: keep a data folder that Python 3.14 wrote (the
  Docker image's volume, for one) with Python 3.14. `agentcake doctor` counts the chunks this Python cannot read.
- To check a Python: `python3 -I -c "import compression.zstd"` prints nothing and exits 0 when it has zstd.

## Check it

On the server:

```sh
curl -s http://127.0.0.1:8080/cake/healthz
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/cake/
agentcake status
agentcake lists
```

`ok`; then `404`, because the public listener has no dashboard; then `"ok": true` with the session counts and disk use;
then the date of the name lists and published ranges in use.
From anywhere, `https://example.com/cake/cake.js` answers with the script, and `https://example.com/cake/` is your
site's own 404 page, not the dashboard.
