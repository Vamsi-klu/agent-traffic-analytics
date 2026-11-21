# AgentCake on a server

By default, AgentCake runs on your computer as one process with one SQLite database. Its local page is at
http://127.0.0.1:7878/, as described in `INSTALL.md`.

Visitors to a public website can't reach a program on your computer. To record their visits, install AgentCake and its
database on a server that you control.

Your website can stay on its current host, such as WordPress hosting, Shopify, Wix, Vercel, or AWS, including sites behind
Cloudflare. The
dashboard is never exposed to the internet. It runs at http://127.0.0.1:7878/ on the server, and you can open it through
an SSH tunnel.

Visitor data goes directly from browsers to your server. The data doesn't pass through a relay, a data tunnel, or a
third party. AgentCake also doesn't send telemetry.

## Two setup options

**Subdomain (default):** Your pages load the page script from a subdomain of your site, such as `cake.example.com`.
A DNS record points the subdomain to your server, where Docker Compose runs AgentCake and Caddy. This option works for
any site that can add a script tag to the head of every page.

**Path of your own site (advanced):** This option is for sites that already have a load balancer or a reverse proxy.
The load balancer or reverse proxy sends two paths of your site, `/cake/cake.js` and `/cake/collect`, to AgentCake. For details, see
[A path of your own site (advanced)](#a-path-of-your-own-site-advanced).

| | Subdomain (default) | Path of your own site (advanced) |
|---|---|---|
| Page script URL | `https://cake.example.com/cake/cake.js` | `/cake/cake.js` on your own site |
| Server software | AgentCake and Caddy | AgentCake |
| Installation | Docker Compose or systemd | Docker Compose or systemd |
| Required setup | One DNS record | Path rules in your load balancer |
| HTTPS certificate | Caddy obtains and renews it automatically | Your load balancer manages the certificate for your domain |
| Dashboard | http://127.0.0.1:7878/ on the server | http://127.0.0.1:7878/ on the server |
| Dashboard access | Through an SSH tunnel | Through an SSH tunnel |

## How it fits together

```text
a visitor's browser on https://www.example.com, after the visitor agreed to analytics
  |  GET  https://cake.example.com/cake/cake.js
  |  POST https://cake.example.com/cake/collect, every 2 s
  v
DNS: cake.example.com -> your server's IP address (on Cloudflare: DNS only)
  v
your server
  :80, :443        Caddy: gets and renews the certificate; sends only /cake/cake.js and /cake/collect on, with the
                   visitor's address in X-Cake-Client-IP; answers 404 to everything else
  127.0.0.1:8080   AgentCake's public listener: the page script, collect and a health check, under /cake
  127.0.0.1:7878   the local page: dashboard, sessions, replay, settings
        ^
        +-- your computer: an SSH tunnel to 127.0.0.1:7878, then http://127.0.0.1:7878/
```

## Install with Docker Compose

To set up the subdomain option, follow these eight steps. You need access to your DNS provider's settings for step 2
and to your website for step 7. Complete the other steps on the server and on your computer.

### 1. Get a server

You can ask a coding agent to create this server. The agent uses your cloud provider's command-line tool and reserves
a static IP address. To learn how the agent does this step, see [`INSTALL.md`](INSTALL.md).

Use a Linux server with 1 vCPU, 1 GB of memory, a 20 to 30 GB persistent disk, and a public IPv4 address. Open
ports 80 and 443 to the internet in the server's firewall. Also open them in your cloud provider's firewall or security
group.

Ports 80 and 443 are for HTTPS. Caddy also uses port 80 to obtain its certificate.

Allow SSH on port 22 only from your own IP address. You can also use your cloud provider's SSH access, such as IAP on
Google Cloud.

Install Docker Engine with its Compose plugin. For the steps for your Linux distribution, see
[Docker's guide](https://docs.docker.com/engine/install/). To run AgentCake without containers, see
[Install with systemd](#install-with-systemd).

### 2. Add a DNS record

You can ask a coding agent to add this record. The agent uses your DNS provider's command-line tool or your browser.
To learn how the agent does this step, see [`INSTALL.md`](INSTALL.md).

In your DNS provider's settings, add one record. Your DNS provider is often your domain registrar.

| Type | Name | Value |
|---|---|---|
| A | `cake` | Your server's public IPv4 address |

If the server has an IPv6 address, also add an AAAA record with the same name. A new record can take from a few minutes
to a few hours to take effect.

- Add this record in your own DNS provider account.
- On Cloudflare, set the record's proxy status to **DNS only** (gray cloud). For details, see
  [Cloudflare's guide](https://developers.cloudflare.com/dns/proxy-status/). Visitors then connect to your server
  directly, and AgentCake receives their real IP addresses.
- You can use a name other than `cake`. Don't use words such as analytics, tracking, stats, telemetry, and metrics.
  Content blockers block subdomains that contain these words.
- For a site without its own domain, such as `you.github.io`, or a site that uses Cloudflare's proxy, see
  [Two special cases](#two-special-cases).

### 3. Copy the release to the server

From your computer, copy the release archive and the checksum file to the server. Both files are in the release assets,
next to the files that `INSTALL.md` downloads:

```sh
scp agentcake-<version>.tar.gz SHA256SUMS <you>@<server>:
```

On the server, check the archive, unpack it, and add your subdomain to the Caddyfile:

```sh
sha256sum -c SHA256SUMS --ignore-missing
tar -xzf agentcake-<version>.tar.gz
cd agentcake-<version>
sed -i 's/cake\.example\.com/cake.<your-domain>/' deploy/Caddyfile
```

Make sure that the check prints `OK`. The release folder contains `docker-compose.yml`, `Dockerfile`, `deploy/Caddyfile`,
`deploy/cake.service`, and the wheel in `dist/`.

The last command replaces `cake.example.com` in `deploy/Caddyfile` with your subdomain. With this file, Caddy does the
following:

- Caddy obtains an HTTPS certificate for your subdomain from Let's Encrypt and renews the certificate before it expires.
- Caddy forwards `/cake/cake.js` and `/cake/collect` to AgentCake at `127.0.0.1:8080`.
- Caddy returns a 404 error for all other paths.
- Caddy sends each visitor's IP address to AgentCake in the `X-Cake-Client-IP` header.
- Caddy removes any other `X-Cake-` header from visitor requests.
- Caddy forwards the original `Host`, `User-Agent`, and `Accept-Language` headers, which AgentCake checks.

### 4. Start AgentCake

```sh
docker compose build
docker compose up -d
```

The first command builds the AgentCake image from the wheel in `dist/`. The second command starts two services on the
server's host network: `agentcake` and `caddy`. Both services restart automatically after a reboot.

To check the services, run `docker compose ps`. The `agentcake` service shows `healthy` when its local page responds.

With Docker Compose, the `agentcake` commands in this guide use the following alias. Run them from the release folder:

```sh
alias agentcake='docker compose exec agentcake python3 -I -m agentcake'
```

In scripts, use the full command instead of the alias. The same applies to coding agents that run one command
at a time.

### 5. Configure AgentCake

Replace `<your-domain>` with your own domain:

```sh
agentcake config set public_listen 127.0.0.1:8080
agentcake config set path_prefix /cake
agentcake config set trust_lb true
agentcake config set site_domain <your-domain>
agentcake config set public_url https://cake.<your-domain>
agentcake secret init
agentcake config get site_key
docker compose restart agentcake
```

- The public listener listens only on 127.0.0.1, where only Caddy on the same server can reach it.
- Use the site key that `config get site_key` shows in your script tag. Site keys start with `ck_`.
- Your pages might already use a site key from AgentCake on your computer. In this case, run
  `agentcake config set site_key <your-site-key>` before the restart.
- To learn what each setting does, see [Settings](#settings).

### 6. Run doctor

```sh
agentcake doctor
```

Run doctor on the server to test the full setup. Doctor shows one line for each of these checks:

- The subdomain points to this server, not through a CDN.
- The HTTPS certificate is valid.
- The page script at the subdomain comes from this AgentCake server.
- The collect endpoint allows cross-origin uploads from your site's pages.
- Doctor sends a test upload in the same way as your site's pages, and the headers arrive unchanged.
- AgentCake receives each visitor's real IP address.

Each line shows PASS, WARN, FAIL, or SKIP. A FAIL line also explains how to fix the problem.

### 7. Add the script tag to every page

```html
<script src="https://cake.example.com/cake/cake.js" data-site="ck_…" defer></script>
```

Replace the subdomain and site key with your own. Add the script tag to the head of every page, just before `</head>`.
If your site asks visitors for consent, load the script only after a visitor agrees to analytics.

For platform-specific instructions, see [Where to add the script tag](#where-to-add-the-script-tag). You don't need to
change anything else on your website, such as its hosting, load balancer, or CDN.

### 8. Open the dashboard

On your computer, open an SSH tunnel to the server:

```sh
ssh -N -L 127.0.0.1:7878:127.0.0.1:7878 <you>@<server>
```

Then open http://127.0.0.1:7878/. A visit appears a few seconds after a visitor opens a page with the script tag. For
more information, see [The dashboard](#the-dashboard-127001-only-through-a-tunnel).

## Install with systemd

On a small Linux server, you can use systemd instead of Docker to save memory. AgentCake runs as one systemd
service with the system's `python3`, and Caddy runs as another service.

You need systemd, `python3` 3.11 or newer, and Caddy 2.8 or newer. Debian 12 has Python 3.11, and Debian 13 has 3.13.
The server doesn't need pip.

Debian 12 and 13 include Caddy 2.6.2, which doesn't support `deploy/Caddyfile`. Install the official Caddy package by
following [Caddy's guide](https://caddyserver.com/docs/install#debian-ubuntu-raspbian). On Debian 13, you can also use
the package in trixie-backports.

The systemd service is named `cake.service` and runs as the user `cake`. The service stores its data in
`/var/lib/cake`.

Follow steps 1 to 3 above, without installing Docker. Then run these commands in the release folder:

```sh
sudo useradd --system --home-dir /var/lib/cake --shell /usr/sbin/nologin cake
sudo install -d -o cake -g cake -m 700 /var/lib/cake
sudo python3 -I -m zipfile -e dist/agentcake-<version>-py3-none-any.whl /opt/cake/app
sudo install -m 644 deploy/cake.service /etc/systemd/system/cake.service
```

A wheel is a zip file of the package. After you unpack it, `/opt/cake/app/agentcake/__main__.py` runs AgentCake without
any other installation. The service's `ExecStart` runs this file.

With systemd, define this alias for the `agentcake` commands in this guide:

```sh
alias agentcake='sudo -u cake env CAKE_HOME=/var/lib/cake python3 -I /opt/cake/app/agentcake/__main__.py'
```

In scripts, use the full command instead of the alias. The same applies to coding agents that run one command
at a time.

Run the commands from step 5, except the last line. Then start AgentCake and install the Caddyfile for Caddy:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now cake
curl -s --retry 5 --retry-connrefused --retry-delay 1 http://127.0.0.1:8080/cake/healthz
caddy version
sudo install -m 644 deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Make sure that `healthz` returns `ok` and that `caddy version` shows v2.8 or newer. Then follow steps 6 to 8.

- City database: By default, AgentCake downloads the city database at its first check. To download the database now,
  run `agentcake lists update`. For more information, see [Location](#location-country-region-and-city).
- Logs: Run `journalctl -u cake` for AgentCake and `journalctl -u caddy` for Caddy. AgentCake logs its listening
  addresses at startup and doesn't log requests.
- Memory: `deploy/cake.service` caps AgentCake and the process it starts for the monthly update together at 600 MB
  (`MemoryMax`), for a server with 1 GB. If the update's process reaches the limit, that process stops and AgentCake
  keeps running. Change it without editing the file: `sudo systemctl set-property cake MemoryMax=800M`.

To install the wheel in a virtual environment instead of unpacking it, run `sudo python3 -m venv /opt/cake/venv`. On
Debian, run `sudo apt install python3-venv` first. Then run
`sudo /opt/cake/venv/bin/pip install --no-index --no-deps dist/agentcake-<version>-py3-none-any.whl`.

In a drop-in file, `/etc/systemd/system/cake.service.d/wheel.conf`, replace `ExecStart` as shown below. Then run
`sudo systemctl daemon-reload`. The alias becomes
`sudo -u cake env CAKE_HOME=/var/lib/cake /opt/cake/venv/bin/python3 -I -m agentcake`.

```ini
[Service]
ExecStart=
ExecStart=/opt/cake/venv/bin/python3 -I -m agentcake serve
```

## Where to add the script tag

Each platform has one place where you can add code to the head of every page. If you have your site's source code, run
`agentcake setup --print --site` in its folder. The command finds the right file and shows the script tag.

To see what AgentCake needs on each hosting platform and what it costs, see [Hosting reference](docs/hosting.md).

| Your site | Where to add the script tag | Requirements | Source |
|---|---|---|---|
| WordPress | AgentCake's WordPress plugin adds the script tag to every page. Set its AgentCake address to `https://cake.example.com/cake`. You can also add the script tag to your theme's header, before `</head>`. | A plan that lets you add plugins or edit the theme | `edge/wordpress/agentcake/README.md` |
| Shopify | Select Online Store > Themes > Edit code, and then add it to `layout/theme.liquid` before `</head>`. | Checkout pages are separate and don't include the script tag | [Shopify: layouts](https://shopify.dev/docs/storefronts/themes/architecture/layouts) |
| Wix | Select Settings > Custom Code > Add Custom Code, and then add it to all pages in Head. | A published site with a connected domain of your own | [Wix: custom code](https://support.wix.com/en/article/wix-editor-embedding-custom-code-on-your-site) |
| Squarespace | Add it under Code Injection > Header. | A Core, Plus, or Advanced plan. Some older plans also include code injection. | [Squarespace: code injection](https://support.squarespace.com/hc/en-us/articles/205815908) |
| Webflow | Select Site settings > Custom code > Head code, add the script tag, and then publish the site. | A paid Site plan or a paid Workspace | [Webflow: custom code](https://help.webflow.com/hc/en-us/articles/33961357265299-Custom-code-in-head-and-body-tags) |
| A static site (GitHub Pages, Netlify, Cloudflare Pages, plain HTML) | The layout or head template that your site generator shares between pages. For plain HTML, add it to every page. | No other requirements | [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) |
| Next.js | The root layout (`app/layout.tsx`) or `pages/_app.tsx` | No other requirements | `agentcake setup --print --site` |
| GoDaddy Websites + Marketing | Not supported. Custom code is limited to a single page section that runs in a separate frame. The page script in this frame can't access the main page. | — | [GoDaddy: HTML section](https://www.godaddy.com/help/add-html-or-custom-code-to-my-site-27252) |

On Wix, Squarespace, Webflow, Shopify, and other hosted builders, AgentCake runs only as the page script. The server
middleware and server logs need access to the site's own server.

## Two special cases

### Sites without their own domain

Some sites don't have their own domain and use an address from their platform, such as `you.github.io` or
`you.vercel.app`. You can't add a DNS record to that address.

Instead, you can use a free name from sslip.io for AgentCake's server. The name contains your server's IP address, with
dashes instead of dots. For example, for a server at `203.0.113.10`, the name is `cake.203-0-113-10.sslip.io`.

sslip.io resolves this name to your server's IP address. You don't need to register a domain or add a DNS record.
Skip step 2.

Replace `203-0-113-10` with your server's IP address in the steps below. In step 3, run this command instead of the
last command:

```sh
sed -i 's/cake\.example\.com/cake.203-0-113-10.sslip.io/' deploy/Caddyfile
```

In step 5, set `site_domain` to your site's address, and set `public_url` to the sslip.io name:

```sh
agentcake config set site_domain you.github.io
agentcake config set public_url https://cake.203-0-113-10.sslip.io
```

Caddy obtains an HTTPS certificate for this name from Let's Encrypt and renews it automatically. In step 7, the script
tag loads the script from `https://cake.203-0-113-10.sslip.io/cake/cake.js`.

Use a static IP address for the server.

If the IP address changes, the name also changes. Update the name in the Caddyfile and in `public_url`, and restart
Caddy and AgentCake. Then update the script tag on your pages.

A third party runs sslip.io as a free service. An sslip.io name has the following risks:

- The operators of sslip.io control the DNS records for your name and can obtain certificates for it. If the service
  is compromised, your pages can load a script from another server.
- A script from another server runs on your pages with the same permissions as your own scripts. AgentCake's masking
  doesn't apply to other scripts.
- This script can read page content, form input, browser storage, and cookies that aren't HttpOnly. It can send this
  data to any server.
- Your pages also send their visit data to that server instead of your AgentCake server.
- Scripts from other services, such as chat widgets, have the same risk.
- This risk doesn't affect your AgentCake server or the data that's stored on it. The local page (dashboard, sessions,
  replay, settings) always listens on 127.0.0.1, at `port` (7878 by default).
- If sslip.io is unavailable, browsers can't load the script. Your pages still load, but AgentCake doesn't record
  visits.
- Let's Encrypt limits new certificates across all sslip.io names. If this limit is reached, Caddy might not get a
  new certificate. Without a certificate, browsers can't load the script.

An sslip.io name is suitable for a trial. For production, use a domain that you control, such as `example.net`.

Add the record from step 2 to your domain, and use `cake.example.net` in place of the sslip.io name. When the server's
IP address changes, only the DNS record requires an update.

Use a DNS provider that supports CAA records, such as Cloudflare or Amazon Route 53. Add a CAA record for
`letsencrypt.org` to limit which certificate authorities can issue certificates for your domain.

The collect endpoint accepts uploads from any site. AgentCake uses `site_domain` to decide which visits belong to your
site.

### Sites behind Cloudflare's proxy

You can turn on Cloudflare's proxy (orange cloud) for the AgentCake record. `deploy/Caddyfile` trusts Cloudflare's published
IP address ranges, and each release includes the current list. Caddy reads each visitor's IP address
from `CF-Connecting-IP`.

Set Cloudflare's SSL/TLS encryption mode to Full (strict).

DNS only is the recommended setting. With DNS only, visitors connect directly to your server. In this case, the list of
Cloudflare's IP ranges doesn't need to be up to date.

If most visitor IP addresses look like Cloudflare's, `agentcake doctor` and the dashboard show a warning ("CDN IP
addresses detected"). In this case, AgentCake doesn't use IP addresses to classify sessions. The warning disappears
within a few sessions after AgentCake receives real visitor IP addresses again.

## What the public listener answers

The setting `public_listen` turns on a second listener. Under `path_prefix` it answers only these, and 404 to anything
else:

| Method | Path | Description |
|---|---|---|
| GET | `/cake/cake.js` | The page script |
| GET | `/cake/c.js` | A shorter URL for the page script |
| POST | `/cake/collect` | Uploads from the page script |
| OPTIONS | `/cake/collect` | A browser's CORS preflight. AgentCake responds with status 204 and sets `Access-Control-Allow-Origin` to the request's origin. |
| POST | `/cake/edge` | Page requests from your web server's log. These requests are signed with the server middleware's secret. For details, see Server logs. |
| GET | `/cake/healthz` | A health check that returns `ok` |

- The dashboard, sessions, replay, settings and the JSON API are never served there, under any path.
- The collect endpoint accepts uploads from any site (CORS). All responses set `Access-Control-Allow-Origin` to the
  request's origin and include `Vary: Origin`. AgentCake also sets these headers when it rejects an upload.
- The collect endpoint doesn't accept cookies.
- AgentCake uses `site_domain` to determine which uploads count as visits to your site. AgentCake keeps uploads from
  other sites but excludes them from the dashboard.
- For other paths, AgentCake doesn't send CORS headers and returns a 404 error to preflight requests.
- Limits, all of them settings: a POST over 1 MB is refused (413) before its body is read (`public_max_body_bytes`); a
  session keeps at most 200,000 replay events (`max_events_per_session`); a session is judged at most every 15 s while
  its visits arrive (`public_judge_interval_ms`), and again when you open the dashboard, the sessions or its replay.

## The dashboard: 127.0.0.1 only, through a tunnel

The local page (dashboard, sessions, replay, settings) always listens on 127.0.0.1, at `port` (7878 by default). No
setting makes it listen anywhere else. It has no login: nothing outside the server can reach it, and anyone who can log
in to the server can open it. From your computer, open a tunnel, then http://127.0.0.1:7878/:

```sh
ssh -N -L 127.0.0.1:7878:127.0.0.1:7878 <you>@<server>
gcloud compute ssh <vm> --zone=<zone> --tunnel-through-iap -- -N -L 127.0.0.1:7878:127.0.0.1:7878
```

If 7878 is taken on your computer, pick another port on your side: `-L 127.0.0.1:7979:127.0.0.1:7878`, then
http://127.0.0.1:7979/. With Docker, `docker-compose.yml` runs AgentCake on the server's host network. This way, the
tunnel can reach the local page. On a separate Docker network, 127.0.0.1 would refer to the container itself.

Its dates and times are in AgentCake's time zone: by default the server's own, which is often UTC, and the Trends chart
names it ("Times in UTC"). To see your own, choose it under Time zone in Settings, or run
`agentcake config set timezone America/Los_Angeles` with your IANA time zone name.

## Firewall

| Port | Subdomain | Path of your own site |
|---|---|---|
| 80, 443 | Open to everyone (Caddy) | No rule needed |
| 22 (SSH) | Only you | Only you, through IAP on Google Cloud |
| 8080 (public port) | Closed | Only your load balancer |
| 7878 (local page) | Closed | Closed |

A closed port listens only on 127.0.0.1. Computers outside the server can't connect to a closed port. To set up the load
balancer rules, see [Firewall for the path option](#firewall-for-the-path-option).

Each release includes the name lists and published ranges. To check their date, run `agentcake lists`. AgentCake
downloads newer lists and the city database over HTTPS once a month.

These downloads use only the public addresses in `agentcake/data/lists/sources.json` and `agentcake/data/geo.json`.
They don't include any visitor data.

To turn them off, set `lists_auto_update` to `false`. To download them at any time, run `agentcake lists update`. For
more information, see [Location](#location-country-region-and-city).

Caddy connects to Let's Encrypt to obtain its certificate.

## Settings

Run these commands on the server with the `agentcake` alias for your setup option. After you change a setting, restart
AgentCake with `docker compose restart agentcake` or `sudo systemctl restart cake`.

| Setting | Value for a subdomain | Description |
|---|---|---|
| `public_listen` | `127.0.0.1:8080` | The public listener's address and port. If this setting is empty, server mode is off. The setting is empty by default. If you use the path option, set it to `0.0.0.0:8080` so that your load balancer can reach the public listener. |
| `path_prefix` | `/cake` | The path that the public listener uses. To choose one, see Path rules. |
| `public_url` | `https://cake.example.com` | The address where browsers reach AgentCake on a subdomain. The script tag, doctor, and the setup page use this address. If this setting is empty, AgentCake uses the path option. The setting is empty by default. |
| `trust_lb` | `true` | If this setting is on, AgentCake reads the visitor's IP address from headers that Caddy or your load balancer sets on the public listener. Off by default. |
| `proxy_hops` | `0` (default) | This setting applies only to the path option. The number of proxies in front of AgentCake that add an address to `X-Forwarded-For`. AgentCake counts that number of entries from the right to find the visitor's address. If the value is 0, AgentCake reads only `X-Cake-Client-IP`. |
| `site_key` | Created on first use | The key in your script tag. The collect endpoint rejects any other key. |
| `site_domain` | `example.com` | Your site's domain. The dashboard uses this domain as its title. The domain also determines which uploads count as visits to your site. AgentCake keeps uploads from other sites but excludes them from the dashboard. |
| `port` | `7878` (default) | The port of the local page, which always uses 127.0.0.1. |
| `budget_mb` | See Disk budget | The disk budget for the database and the replay chunks, in MB. |
| `auto_free` | `true` (default) | When this setting is on and less than 10% of the budget is left, AgentCake deletes the oldest session replays first. AgentCake treats replays of all session types the same way. |
| `disk_min_free_mb` | `10240` (default) | The amount of disk space to keep free. When free disk space falls below this amount, AgentCake stops storing new replays and keeps the existing ones. AgentCake resumes storing replays when enough space is available. For details, see Disk budget. |
| `retention_days` | `0` (default) | The number of days that AgentCake keeps sessions. If you set the value to 30 or 90, AgentCake deletes whole sessions after 30 or 90 days. By default, the value is 0 and AgentCake keeps all sessions. |
| `timezone` | For example, `America/Los_Angeles` | The IANA time zone for the dashboard's dates and times. If it's empty (the default), the dashboard uses the server's time zone. |
| `lists_auto_update` | `true` (default) | When this setting is on, AgentCake downloads the latest name lists, published ranges, and city database once a month. When it's off, AgentCake downloads them only when you run `agentcake lists update`. |
| `public_max_body_bytes` | `1000000` (default) | The maximum size, in bytes, of a POST request that the public listener reads. |
| `max_events_per_session` | `200000` (default) | The maximum number of records that a session keeps in each stream (replay, raw input, and signals). AgentCake counts any additional records but doesn't store them. |
| `public_judge_interval_ms` | `15000` (default) | The minimum time between two classifications of a session that is sending data. |
| `ip_salt_days` | `30` (default) | The number of days before AgentCake replaces the salt that it uses to hash visitor IP addresses. |
| `token_max_age_ms` | `900000` (default) | The maximum age of a server middleware token. AgentCake rejects older tokens. |

`agentcake config get` prints every value in use; `agentcake/defaults.json` lists every setting with its default and
what it does.

## The page script on your site

Use the script tag from step 7 with your site key. To see the site key, run `agentcake config get site_key`. Add the
script tag to your pages after a visitor agrees to analytics in your consent banner.

If you use the path option, the script tag loads the page script from your own site:

```html
<script src="/cake/cake.js" data-site="ck_…" defer></script>
```

When a visitor declines later, call `window.cake.stop()`: recording and sending stop, and the visit id, the visitor id
and its identify hash are forgotten.

If your site has sign-in, it can have each signed-in visitor counted once across browsers and devices: call
`window.cake.identify(user.id)` after they sign in, with an internal ID that is hard to guess (not an e-mail address or
a number that counts up), and `window.cake.reset()` when they sign out. The browser sends only a SHA-256 hash of your
site key and the ID ([`PRIVACY.md`](PRIVACY.md), "Counting a signed-in visitor once").

## A path of your own site (advanced)

Use this option if your site already has a load balancer or a reverse proxy in front of it. With this option, the page
script loads from a path on your own domain, such as `https://example.com/cake/cake.js`.

Your load balancer forwards two paths of your site to AgentCake. This option doesn't require a DNS record or Caddy.
Install AgentCake as described above, and then do the following:

- With Docker Compose, run `docker compose up -d agentcake` to start AgentCake without Caddy.
- With systemd, skip the Caddy steps.
- Set `public_listen` to `0.0.0.0:8080` so that your load balancer can reach the public port. Leave `public_url`
  empty. The other settings are the same as in step 5:

```sh
agentcake config set public_listen 0.0.0.0:8080
agentcake config set path_prefix /cake
agentcake config set trust_lb true
agentcake config set site_domain example.com
```

### Path rules

In your load balancer, send exactly these paths on your site's host to the public port of the AgentCake server, and
leave every other path as it is:

```text
/cake/cake.js
/cake/collect
```

Add `/cake/c.js` only if your pages load the script by that name. The health check goes straight to the server
(`/cake/healthz` on the public port, 200 when it is up) and needs no path rule, and so does `/cake/edge`: the log import
sends to the public port from the load balancer's own machine (Server logs, below). With these rules, `/cake/` and every
other path under it stay your site's own pages, so the dashboard is out of the internet's reach twice over: the load
balancer never forwards it, and AgentCake never serves it publicly.

Choose the path (`path_prefix`) as a path of your own site that says nothing about tracking: `/cake` is fine. Content
blockers already block some AgentCake uploads under `/api`, `/analytics`, or `/stats`. For example, EasyPrivacy has the
rules `/api/collect|`, `/analytics/collect?`, and `/stats/collect?`.

Content blocker lists also target words such as analytics, tracking, telemetry, stats, and metrics. PostHog's guides to serving its script through your own domain give the same
advice for [paths](https://posthog.com/docs/advanced/proxy/cloudflare) and
[subdomains](https://posthog.com/docs/advanced/proxy/managed-reverse-proxy).

Keep the original `Host` header. Agents that sign their requests include your site's host name in the signature.
AgentCake verifies the signature against this host name.

Google Cloud's load balancer and Caddy keep the original header. By default, nginx and Apache replace it, so configure
them as the following examples show.

Google Cloud, global external Application Load Balancer: a path matcher for your site's host in the URL map.

```yaml
pathMatchers:
- name: example-com
  defaultService: <your site's backend service>
  pathRules:
  - paths: [/cake/cake.js, /cake/collect]
    service: <AgentCake's backend service>
```

Configure AgentCake's backend service to use HTTP and an instance group with the named port 8080. Use `/cake/healthz` on
port 8080 as its health check. Add the headers in the next section as custom request headers.

Turn off request logging for this backend service. Otherwise, the log stores each visitor's IP address with every
request. Each visitor sends a collect request every 2 seconds.

If nginx runs in front of your site, add the following lines to your site's `server` block:

```nginx
location ~ ^/cake/(cake\.js|collect)$ {
    proxy_pass http://192.0.2.10:8080;                # the AgentCake server's public listener
    proxy_set_header Host $host;                      # your site's own name, which signed requests sign
    proxy_set_header X-Cake-Client-IP $remote_addr;
    proxy_set_header X-Cake-Proto $server_protocol;
    proxy_set_header X-Cake-JA4 "";                   # nginx knows no TLS fingerprint: an empty value drops a visitor's own
    client_max_body_size 1m;
}
```

If nginx receives requests directly from visitors, `$remote_addr` contains each visitor's IP address. If a CDN or
another proxy is in front of nginx, `$remote_addr` contains the address of that proxy. In this case, make these changes:

- Set `X-Cake-Client-IP` to `""`.
- Add `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`.
- Set `proxy_hops` to `2` to account for both the CDN and nginx. For more information, see
  [Which headers AgentCake trusts](#which-headers-agentcake-trusts).

If Apache is in front of your site, enable `mod_proxy_http` and `mod_headers`. Then add these lines inside your site's
`VirtualHost`:

```apache
ProxyPreserveHost On
ProxyPass "/cake/cake.js" "http://192.0.2.10:8080/cake/cake.js"
ProxyPass "/cake/collect" "http://192.0.2.10:8080/cake/collect"
RequestHeader set X-Cake-Client-IP "expr=%{REMOTE_ADDR}"
RequestHeader set X-Cake-Proto "expr=%{SERVER_PROTOCOL}"
RequestHeader unset X-Cake-JA4
```

If Apache receives requests directly from visitors, `REMOTE_ADDR` contains each visitor's IP address. If a CDN is in
front of Apache, `REMOTE_ADDR` contains the CDN's address.

In this case, unset `X-Cake-Client-IP` and set `proxy_hops` to `2`. Apache automatically adds the CDN's address to
`X-Forwarded-For`.

For AWS CloudFront, create a behavior for the path pattern `/cake/*` with the AgentCake server as its origin. For
**Allowed HTTP methods**, choose **GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE**. The page script uses POST to send
data to `/cake/collect`. If POST isn't allowed, CloudFront rejects each upload with HTTP status 403.

For **Origin domain**, enter a public DNS name for the server, not an IP address. The public port uses plain HTTP, so
set **Protocol** to **HTTP only** and **HTTP port** to `8080`. Requests from CloudFront to the server aren't encrypted
and travel over the internet.

Use the managed origin request policy **AllViewer**, which appears in
[AWS's list of managed policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html).

Without this policy, CloudFront removes `Accept-Language` before the request reaches AgentCake. CloudFront also replaces
`User-Agent` and `Host`.

You can also use **AllViewerExceptHostHeader**. Don't use **UserAgentRefererHeaders**. This policy removes the
`Signature` headers, so AgentCake can't verify signed agents.

With CloudFront's default settings, AgentCake doesn't classify human visitors as agents. The session page lists the
missing `Accept-Language` header as a weak signal. A proxy in front of AgentCake might have removed this header.

CloudFront doesn't set any `X-Cake-` header. Set `proxy_hops` to `1`. If an Application Load Balancer is behind
CloudFront, set `proxy_hops` to `2`.

With Cloudflare's proxy, you need a Worker to send a path of your site to another server. A subdomain doesn't need a
Worker.

### Which headers AgentCake trusts

AgentCake trusts only the headers in the following table. AgentCake trusts these headers only when all of the following
conditions are met:

- The request arrives on the public listener.
- The `trust_lb` setting is on.
- Your load balancer sets the headers.

| Header | Google Cloud custom request header | What AgentCake keeps |
|---|---|---|
| `X-Cake-Client-IP` | `X-Cake-Client-IP:{client_ip_address}` | The location (see [Location](#location-country-region-and-city)). The published range that contains the address. Whether the address belongs to iCloud Private Relay, a CDN, or a cloud provider. `agentcake/data/lists/ip_ranges.json` lists the ranges that AI, search, CDN, and cloud companies publish. A salted hash of the address and a salted hash of its /24 or /48 network. The `ip_salt_days` setting sets how many days AgentCake uses each salt. AgentCake doesn't store the address itself. |
| `X-Cake-JA4` | `X-Cake-JA4:{tls_ja4_fingerprint}` | The TLS fingerprint, shown on the session page |
| `X-Cake-Proto` | `X-Cake-Proto:{client_protocol}` | The HTTP version, shown on the session page |

```sh
gcloud compute backend-services update <AgentCake's backend service> --global \
  --custom-request-header='X-Cake-Client-IP:{client_ip_address}' \
  --custom-request-header='X-Cake-JA4:{tls_ja4_fingerprint}' \
  --custom-request-header='X-Cake-Proto:{client_protocol}'
```

- AgentCake looks up the country, region, and city from the IP address. You can remove the headers that earlier
  versions used: `X-Cake-Region`, `X-Cake-Subdivision`, and `X-Cake-City`.
- Most load balancers can't set `X-Cake-Client-IP`. Instead, they add the visitor's IP address to `X-Forwarded-For`.
  Examples include AWS's Application Load Balancer and CloudFront, Vercel, and Heroku.
- Set `proxy_hops` to the number of these proxies. Each proxy adds the sender's address to the end of the
  header. To find the visitor's address, AgentCake counts `proxy_hops` entries from the right.
- AgentCake doesn't use the leftmost entry. A visitor can set this entry to any value.
- AgentCake ignores the `Forwarded` and `X-Real-IP` headers. When `proxy_hops` is above 0, AgentCake doesn't read
  `X-Cake-Client-IP`.
- If a request has fewer entries than the `proxy_hops` value, AgentCake doesn't use any address from the request. Some
  proxies add a port number to an entry. AgentCake removes this port number.
- AgentCake can trust these headers only when two conditions are met. Your load balancer sets or empties each of them on every request it
  forwards: Google Cloud's custom request headers replace a header of the same name that a client sent, and a header
  that a load balancer neither sets nor empties passes through from the visitor unchanged. And the firewall lets only
  the load balancer reach the public port, so that nobody can connect directly with headers of their own.
- Turn on `trust_lb` only if your load balancer meets both conditions. When `trust_lb` is off, AgentCake doesn't store
  the location, range, JA4, or protocol.
- Without `trust_lb`, the Geography table shows only time zones and languages. Other features work the same way.
- If your load balancer doesn't provide the TLS fingerprint, set `X-Cake-JA4` to an empty value.
- The address is looked up and dropped: it is not stored, not logged and not shown.

### Firewall for the path option

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
the third is IAP's TCP forwarding. On another host, do the same with its firewall: the load balancer's address to the
public port, SSH from where you connect, nothing else.

The server doesn't need an external IP address for incoming connections. The load balancer reaches the server at its
internal IP address, and you connect through IAP.

However, the server needs outbound internet access, through an external IP address or NAT, such as Cloud NAT on Google
Cloud. Docker uses this access to download the base image for AgentCake's image. AgentCake uses it to download the
lists and the city database once a month.

If your server runs on AWS behind CloudFront, use its security group as the firewall. Allow the public port only from
the AWS-managed prefix list `com.amazonaws.global.cloudfront.origin-facing`.

## The server middleware

Optional. Your site's server can tell AgentCake what only it saw of a page's request, such as the request's headers and
an agent's signature. It signs a token for each page, `Server-Timing: cake;desc="c1.<payload>.<mac>"` (HMAC-SHA256 with
the secret in `srv_secret`); the page script forwards it; AgentCake accepts each token once, within 15 minutes, and
shows it on the replay page under "Server middleware". For a Node site, `edge/node/` is that middleware (its README says
how to add it). The `agentcake secret init` command in step 5 creates the secret. Hand it to your site's server through
a pipe, never by pasting it; for example, from your computer into Google Cloud's Secret Manager:

```sh
gcloud compute ssh <vm> --zone=<zone> --tunnel-through-iap \
  --command 'sudo -u cake env CAKE_HOME=/var/lib/cake python3 -I /opt/cake/app/agentcake/__main__.py secret print' \
  | gcloud secrets versions add <your secret> --data-file=-
```

With Docker Compose, use `docker compose exec -T agentcake python3 -I -m agentcake secret print` instead. Run this
command in the release folder on the server.

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

2. If another machine, such as your web server or load balancer, writes the log, also install AgentCake on that machine.
   Then run this command on your computer to send the secret through a pipe:

```sh
ssh <the AgentCake server> 'sudo -u cake env CAKE_HOME=/var/lib/cake python3 -I /opt/cake/app/agentcake/__main__.py secret print' \
  | ssh <the web server> 'umask 077; mkdir -p ~/.cake; cat > ~/.cake/srv_secret'
```

3. Import every five minutes, on the machine with the log, from its crontab. Cron's PATH is short: write agentcake's
   full path there (`command -v agentcake` prints it). On the AgentCake server itself, leave out `--to`:

```text
*/5 * * * * agentcake logs import /var/log/nginx/agentcake.log --since 10m --to http://192.0.2.10:8080/cake
```

With the subdomain option, the public port of the AgentCake server listens only on 127.0.0.1. Caddy also doesn't forward
`/cake/edge`. Import the log on the AgentCake server, or connect the web server to the public port through an SSH
tunnel.

To create the tunnel, run `ssh -N -L 127.0.0.1:8080:127.0.0.1:8080 <you>@<the AgentCake server>`. Then add
`--to http://127.0.0.1:8080/cake` to the import command.

Each run prints how many page requests it sent, how many matched a visit and which recommended headers the log
lacks; `agentcake doctor` on the AgentCake server shows the last import. A line sent twice is kept once, so the runs'
`--since` windows may overlap. After the log is rotated, import the rotated file once too (`agentcake.log.1`), for
the lines of its last minutes.

How it works:

- A log has no token. A page request belongs to the visit whose page view sent its first upload from the same address
  and with the same User-Agent at most 30 seconds later (`log_match_window_s`; `log_match_skew_s`, 2 seconds, allows for
  the web server's clock and AgentCake's to differ a little). AgentCake matches log lines by the address that Caddy or
  your load balancer provides. When `trust_lb` is off, AgentCake can't match log lines to visits. The log must record
  the visitor's IP address rather than the address of a CDN. To log the visitor's address behind a CDN, use nginx's
  realip module, Apache's mod_remoteip, or Caddy's `trusted_proxies`.
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

## Location: country, region and city

AgentCake looks up each visitor's country, region, and city on your server, based on the visitor's IP address. It uses
DB-IP's free IP to City Lite database, which is available under the Creative Commons Attribution 4.0 license.

DB-IP publishes a new database on the first day of each month. The download is about 86 MB. On the server, the converted
database takes about 110 MB.

The release and the Docker image don't include the database. By default, AgentCake downloads it at its first check. To
download the database now, run this command after you complete the settings in step 5:

```sh
agentcake lists update
```

By default, AgentCake checks for updates 1 to 15 minutes after it starts, and then once a day. On both setup options,
AgentCake downloads the newest database once a month. It saves the database in the `geo/` folder inside the data folder.

If a download fails, AgentCake keeps using the current database and tries again the next day.

AgentCake uses the new database starting with the next visit. You don't need to restart AgentCake.

The `agentcake lists update` command downloads the database only on a server. Before you run the command, set
`public_listen` and `trust_lb`.

On your computer, all visits come from 127.0.0.1. For this reason, the command skips the database and shows a message.

The command also downloads newer name lists and published ranges.

Until AgentCake downloads the database, every session's country is Not set. The Region and City tables are also empty.

Sessions without a country don't appear in either table. Before the first download, `agentcake doctor` shows when
AgentCake downloads the database. If automatic updates are off or a download fails, doctor shows the command to download
the database.

If the region or city of an address is unknown, the dashboard shows Not set. For example, a German address without a
known region or city appears as "Germany – Not set".

AgentCake looks up the IP address and then deletes it. The database is stored on your server. Lookups don't send any
data outside the server.

The database license requires a credit wherever the dashboard shows a location. The credit "IP Geolocation by DB-IP"
appears with a link under the Geography table. The same credit appears on a session's network line.

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
| `lists/` | This folder holds the name and address lists that AgentCake downloads once a month or when you run `agentcake lists update`. Without these lists, AgentCake uses the lists that come with the release. |
| `geo/` | On a server, this folder contains the city database (DB-IP's IP to City Lite) and its notice. The monthly update and `agentcake lists update` download these files. |
| `updates.json`, `updates.lock` | When the lists and the city database were last updated, and whether the update succeeded. The lock file keeps two updates from running at the same time. |

## Disk budget

AgentCake records every session and keeps it: nothing is deleted by age unless you choose 30 or 90 days
(`retention_days`; a chosen retention deletes whole sessions, their replay chunks included). AgentCake's data has a
disk budget, `budget_mb`: 10240 (10 GB) by default. It counts the database and the replay chunks.

| Boot disk | `budget_mb` |
|---|---|
| 20 GB | 10240, the default |
| 30 GB | 20480 |
| larger | the disk minus 10 GB |

Debian itself uses about 3 GB of the boot disk. The budget leaves room on the disk for system updates, logs,
Docker images, and the city database. Back up to a snapshot or another disk, not to this one.

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
sudo chmod 600 /var/backups/cake/cake-$(date +%F).tar.gz
sudo systemctl start cake
```

The backup holds `srv_secret` and your visitors' sessions: keep it as private as the server. To restore, stop
AgentCake, put the folder back (owned by `cake`, mode 700) and start it.

With Docker Compose, the data folder is the `agentcake-data` volume, and its files belong to user ID 10001. To create
a backup, run the following commands from the release folder on the server. The `tar` command uses `sudo` to read the
files.

```sh
sudo install -d -m 700 /var/backups/cake
docker compose stop agentcake
sudo tar -C "$(docker volume inspect -f '{{ .Mountpoint }}' agentcake-data)" -czf /var/backups/cake/cake-$(date +%F).tar.gz .
sudo chmod 600 /var/backups/cake/cake-$(date +%F).tar.gz
docker compose start agentcake
```

To restore a backup, stop AgentCake and replace the contents of the volume's folder with the files from the backup.
Make sure that the folder is owned by user ID 10001 and has mode 700. Then start AgentCake.

The archive is saved in `/var/backups/cake`, on the same disk as your data. Copy the archive to another disk or to
your computer.

Only root can read the archive. Use `sudo` on the server to copy it.

Caddy's volume contains only its certificates and its Let's Encrypt account. If the volume is lost, Caddy obtains new
ones automatically.

## Upgrading

Before you upgrade, back up your data and check the new release against the new `SHA256SUMS`.

With Docker Compose, unpack the new release into a separate folder next to the current one. Then add your subdomain to
its `deploy/Caddyfile`, as in step 3. In the old folder, stop the old containers:

```sh
docker compose down
```

Then start the new containers in the new folder:

```sh
docker compose build
docker compose up -d
```

`docker compose down` removes the containers but not the volumes. The `agentcake-data` volume stores your data.
Caddy's volume stores its certificates.

After the upgrade, run the `agentcake` alias in the new release folder.

With systemd, keep the previous program next to the new one:

```sh
sudo systemctl stop cake
sudo mv /opt/cake/app /opt/cake/app-<old version>
sudo python3 -I -m zipfile -e dist/agentcake-<new version>-py3-none-any.whl /opt/cake/app
sudo systemctl start cake
```

If the new release's `deploy/cake.service` differs from the installed one, install it again and run
`sudo systemctl daemon-reload`. If the new `deploy/Caddyfile` is different, add your subdomain to the new
file. Then install the file again and run `sudo systemctl reload caddy`.

A newer AgentCake brings an older database up to date when it opens it. The way back is the previous program together
with the backup, not the previous program alone.

Coming from 0.3.4, whose replays are rows inside `cake.db`: with the service stopped (`agentcake migrate` refuses to run
while AgentCake runs on the same data folder), run these, then start it again. The first says what would be done; the
second checks there is room, copies `cake.db` to `backups/` and copies the replays into chunk files, keeping the rows.

```sh
agentcake migrate --dry-run
agentcake migrate
```

The release no longer includes `bin/cake` or `cake.py`. If you run commands with either file, use `bin/agentcake`
instead. On a server, use the `agentcake` alias.

If your systemd service runs `cake.py`, install `deploy/cake.service` again, as described above.

AgentCake no longer serves `rrweb-record.min.js`. The page script includes the session recorder. If a page still has a
script tag for this file, remove the tag.

## Upgrading from 0.5.1

Version 0.5.1 supported only a path of your own site.

You don't need to migrate the database. Sessions recorded earlier keep their country, region, and city data.

On a server, choose one of these two options.

### Keep the path option

Upgrade as described in [Upgrading](#upgrading). You don't need to change your load balancer, pages, or settings.

Starting with this version, AgentCake looks up each visitor's location on the server. Your load balancer can stop
sending `X-Cake-Region`, `X-Cake-Subdivision`, and `X-Cake-City`.

With Docker, use `docker-compose.yml` instead of the `docker run` command. Stop and remove the old container with
`docker stop agentcake` and then `docker rm agentcake`.

Then run `docker compose up -d agentcake` to start AgentCake without Caddy. The new container uses the same
`agentcake-data` volume.

### Move to a subdomain

1. Add the DNS record (step 2).
2. Add Caddy. With Docker Compose, run `docker compose up -d`. With systemd, install Caddy as described in
   [Install with systemd](#install-with-systemd).
3. Set `public_url` to your subdomain (step 5), and then run `agentcake doctor`.
4. Update the script tag on your pages to load `https://cake.example.com/cake/cake.js`.
5. After the new script tag is live on every page, set `public_listen` to `127.0.0.1:8080`. Then remove the path rules
   and the firewall rule for the public port.

Your site key stays the same. The dashboard keeps all existing data.

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
then the date of the name lists and published ranges in use. For all other checks, run `agentcake doctor`.

For a subdomain, open `https://cake.example.com/cake/cake.js` from any computer to see the script.
The address `https://cake.example.com/cake/` returns a 404 error.

For the path option, open `https://example.com/cake/cake.js` to see the script. Opening `https://example.com/cake/`
shows your site's 404 page instead of the dashboard.
