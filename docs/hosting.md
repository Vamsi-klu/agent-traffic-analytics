# Hosting reference

This page describes the cost of AgentCake, its requirements on common hosting platforms, and the price of each server.

AgentCake is free and open source, under the MIT license. To record visits to a public website, AgentCake runs on a
Linux server that you control. Your website stays on its current host.

## What AgentCake costs

AgentCake itself is free. You pay for the server that AgentCake runs on. In some setups, a domain, a platform plan, or
path rules result in additional costs.

| Case | Cost per month | Details |
|---|---|---|
| Trial on this computer | $0 | You don't need a server or a DNS record. For the steps, see [INSTALL.md](../INSTALL.md). |
| Server on Oracle's free tier | $0 | Oracle's [Always Free VM](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) has 1/8 OCPU and 1 GB of memory. Oracle can reclaim an idle instance, and your home region can run out of capacity. |
| Server at another provider | [$3.65 to $12.18](#server-costs) | The range is for the cheapest plans with 1 GB of memory and a public IPv4 address. In three US regions, Google Cloud's [e2-micro and a standard disk are free](https://cloud.google.com/free/docs/free-cloud-features#compute), but the IPv4 address costs $3.65 a month. Hetzner's plan in Helsinki costs €5.49 a month, excluding VAT. |
| Your existing domain | $0 | Add [one DNS record](../SERVER.md#2-add-a-dns-record) for a subdomain, such as `cake.example.com`. |
| sslip.io name | $0 | [sslip.io](https://sslip.io/) provides a free DNS name for a site without its own domain. An sslip.io name is suitable for a trial. To learn about the risks, see [Sites without their own domain](../SERVER.md#sites-without-their-own-domain). |
| New .com domain | $0.93 | For a production site, a .com domain from Cloudflare Registrar costs [$11.17 a year](https://pricing.registrar.cloudflare.com/). |
| HTTPS certificate | $0 | Caddy obtains a free certificate from [Let's Encrypt](https://letsencrypt.org/about/). |
| City database | $0 | AgentCake uses DB-IP's free [IP to City Lite](https://db-ip.com/db/download/ip-to-city-lite) database. |
| Middleware in a free tier | $0 | On Vercel, the middleware uses about one function invocation per page view. The free [Hobby plan](https://vercel.com/docs/plans/hobby) includes 1,000,000 invocations a month, and Vercel usually pauses the feature for 30 days above that. Vercel allows the Hobby plan only for [personal or non-commercial use](https://vercel.com/legal/terms). |
| Traffic on most servers | $0 | The plans in [Server costs](#server-costs) include enough traffic for 100,000 page views a month. Google Cloud's default Premium Tier is the exception. |
| Traffic on Google's Premium Tier | $0 to $0.51 | For visitors in North America, Europe, and most of Asia, Google Cloud's default tier is free for 10,000 page views a month. For 100,000 page views a month, it charges about [$0.45 to $0.51](https://cloud.google.com/vpc/network-pricing). The Standard Tier includes 200 GiB a month for free, which covers 100,000 page views. |
| CloudFront path rules | Up to $0.41 per 10,000 page views | Within CloudFront's [free tier](https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/), the uploads of visit data cost up to $0.04 per 10,000 page views. Your site's own traffic uses the same free tier. Beyond the free tier, the total cost is about $0.13 to $0.41 per 10,000 page views. |
| Load balancer path rules | Up to $0.02 per 10,000 page views | [AWS](https://aws.amazon.com/elasticloadbalancing/pricing/) and [Google Cloud](https://cloud.google.com/load-balancing/pricing) charge about $0.005 to $0.02 per 10,000 page views for the data that the load balancer processes. |
| Platform plan upgrade | [$4 to $17](#platform-plans), billed yearly | This cost applies only when your site's current plan doesn't allow the page script. Upgrading a free site costs $4 a month on [WordPress.com](https://wordpress.com/pricing/) and $17 a month on [Wix](https://www.wix.com/plans). Upgrading from Squarespace Basic to Core costs an additional $10 a month. |

These prices are from each provider's website or public price list on November 20, 2026. Prices can change. Traffic
estimates assume about one minute on each page.

## Requirements for a public website

With the default setup, a public website needs the following:

- A page script in the head of every page. For each platform's steps, see
  [Where to add the script tag](../SERVER.md#where-to-add-the-script-tag).
- A Linux server with 1 vCPU, 1 GB of memory, 20 to 30 GB of disk, and a public IPv4 address. To set it up, see
  [Install with Docker Compose](../SERVER.md#install-with-docker-compose).
- A subdomain, such as `cake.example.com`, with one DNS record. For details, see
  [Add a DNS record](../SERVER.md#2-add-a-dns-record). A site behind its own load balancer can use
  [path rules](../SERVER.md#a-path-of-your-own-site-advanced) instead.
- If your site doesn't have its own domain, you can try AgentCake with a free sslip.io name. For production, use a
  domain that you control. For details, see
  [Sites without their own domain](../SERVER.md#sites-without-their-own-domain).
- If your site has server code, you can also add the server middleware. It adds details from your site's server, such
  as an agent's signature, to each visit. For details, see [The server middleware](../SERVER.md#the-server-middleware).

If you have your website's code, open its folder and run `agentcake setup --print --site`. The command shows which
files to change. For a site with server code, it also shows the middleware.

## Hosting platforms

This table doesn't include server prices because they're the same for every platform. The last column shows only the
additional cost of each platform. For server prices, see [Server costs](#server-costs).

| Platform | Requirements | Extra cost per month |
|---|---|---|
| **Static and front-end hosting** | | |
| Vercel | Add the page script to your framework's layout.<br>The middleware for your framework is optional.<br>Set up a server on a subdomain and add one DNS record. | The page script adds no cost because it loads from your AgentCake server.<br>The middleware uses about one [function invocation](https://vercel.com/docs/plans/hobby) per page view. The free Hobby plan includes 1,000,000 function invocations a month. |
| Netlify | Add the page script to the layout that your pages share.<br>A static site has no server middleware.<br>Set up a server on a subdomain and add one DNS record. | None. |
| GitHub Pages | Add the page script to the layout that your pages share.<br>A static site has no server middleware.<br>Set up a server on a subdomain and add one DNS record. | None. |
| Cloudflare Pages | Add the page script to the layout that your pages share.<br>A static site has no server middleware.<br>Set up a server on a subdomain and add one DNS record. | None. |
| Firebase Hosting | Add the page script to the layout that your pages share.<br>A static site has no server middleware.<br>Set up a server on a subdomain and add one DNS record. | None. |
| AWS Amplify | Add the page script to your framework's layout.<br>The middleware for your framework is optional.<br>Set up a server on a subdomain and add one DNS record. | The page script adds no cost because it loads from your AgentCake server.<br>The middleware adds at most one server request per page view. After the free tier, Amplify charges [$0.30 per million requests](https://aws.amazon.com/amplify/pricing/). |
| Amazon S3 with CloudFront | Add the page script to every page, or to the layout that the pages share.<br>A static site has no server middleware.<br>Use a subdomain or add [path rules](../SERVER.md#path-rules) to CloudFront. | A subdomain adds no cost.<br>With path rules, CloudFront charges up to $0.04 per 10,000 page views within its [free tier](https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/). Beyond the free tier, it charges about $0.13 to $0.41 per 10,000 page views. |
| **App platforms** | | |
| Render | Add the page script to your app's layout.<br>The middleware for your framework is optional.<br>Set up a server on a subdomain and add one DNS record. | The page script adds no cost because it loads from your AgentCake server.<br>The optional middleware runs inside your app and adds no requests. |
| Fly.io | Add the page script to your app's layout.<br>The middleware for your framework is optional.<br>Set up a server on a subdomain and add one DNS record. | The page script adds no cost because it loads from your AgentCake server.<br>The optional middleware runs inside your app and adds no requests. |
| Heroku | Add the page script to your app's layout.<br>The middleware for your framework is optional.<br>Set up a server on a subdomain and add one DNS record. | The page script adds no cost because it loads from your AgentCake server.<br>The optional middleware runs inside your app and adds no requests. |
| DigitalOcean App Platform | Add the page script to your app's layout.<br>The middleware for your framework is optional.<br>Set up a server on a subdomain and add one DNS record. | The page script adds no cost because it loads from your AgentCake server.<br>The optional middleware runs inside your app and adds no requests. |
| Google Cloud Run | Add the page script to your app's layout.<br>The middleware for your framework is optional.<br>Set up a server on a subdomain and add one DNS record. | The page script adds no cost because it loads from your AgentCake server.<br>The optional middleware runs inside your app and adds no requests. |
| **Your own servers** | | |
| VPS with nginx or Apache | Add the page script to your site's layout.<br>You can add your framework's middleware or import the [server logs](../SERVER.md#server-logs).<br>Use a subdomain or add [path rules](../SERVER.md#path-rules) to nginx or Apache. | None.<br>Path rules in nginx or Apache are free. |
| AWS load balancer | Add the page script to your site's layout.<br>The middleware for your framework is optional.<br>Use a subdomain or add [path rules](../SERVER.md#path-rules) to the load balancer. | A subdomain adds no cost.<br>With path rules, the load balancer charges about [$0.005 to $0.02 per 10,000 page views](https://aws.amazon.com/elasticloadbalancing/pricing/). |
| Google Cloud load balancer | Add the page script to your site's layout.<br>The middleware for your framework is optional.<br>Use a subdomain or add [path rules](../SERVER.md#path-rules) to the load balancer. | A subdomain adds no cost.<br>With path rules, the load balancer charges about [$0.005 to $0.02 per 10,000 page views](https://cloud.google.com/load-balancing/pricing). |
| **WordPress** | | |
| Self-hosted WordPress | Install [AgentCake's WordPress plugin](../edge/wordpress/agentcake/README.md), which also adds the server middleware, or add the page script to your theme's header.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The plugin comes with AgentCake at no cost. |
| WordPress.com and other managed hosts | Install AgentCake's WordPress plugin, which also adds the server middleware, or add the page script to your theme's header.<br>The site's plan must allow plugins or theme edits.<br>Set up a server on a subdomain and add one DNS record. | There's no extra cost if your plan allows plugins or theme edits.<br>On WordPress.com, plugins require the Personal plan, which costs [$4 a month](https://wordpress.com/pricing/). |
| **Site builders** | AgentCake runs only as the page script. | |
| Shopify | Add the page script to `layout/theme.liquid`.<br>Checkout pages are separate and don't include the page script.<br>Set up a server on a subdomain and add one DNS record. | There's no extra cost on the Basic plan or a higher plan.<br>Basic costs [$29 a month](https://www.shopify.com/pricing). |
| Wix | Select Settings > Custom Code > Add Custom Code, and then add the page script to all pages in Head.<br>The site must be published and connected to its own domain.<br>Set up a server on a subdomain and add one DNS record. | There's no extra cost on a Premium plan.<br>A free site can't connect its own domain. In the US, Light costs [$17 a month](https://www.wix.com/plans). |
| Squarespace | In Code Injection, add the page script to the Header field.<br>Code injection requires a Core, Plus, or Advanced plan, or an older plan that includes it.<br>Set up a server on a subdomain and add one DNS record. | There's no extra cost on Core or a higher plan.<br>Basic doesn't include code injection. Upgrading from Basic to Core costs an additional [$10 a month](https://www.squarespace.com/pricing). |
| Webflow | Select Site settings > Custom code > Head code, add the script tag, and then publish the site.<br>Custom code requires a paid Site plan or Workspace.<br>Set up a server on a subdomain and add one DNS record. | There's no extra cost on a paid Site plan.<br>The free Starter plan doesn't include custom code. Basic costs [$15 a month](https://webflow.com/pricing). |
| Framer | In Project Settings, select the Custom Code tab, and then add the page script.<br>To connect your own domain, upgrade to a paid Framer plan.<br>Set up a server on a subdomain and add one DNS record. | Framer's documentation doesn't name a plan for custom code.<br>For your own domain, Basic costs [$10 a month](https://www.framer.com/pricing). |
| Ghost | In Settings, open Advanced > Code injection, and then add the page script to the site header.<br>AgentCake has no plugin for Ghost.<br>Set up a server on a subdomain and add one DNS record. | There's no extra cost on any Ghost(Pro) plan.<br>Ghost's list of Starter limits doesn't include code injection. |
| GoDaddy Websites + Marketing | Custom code is limited to a single page section that runs in a separate frame.<br>The page script in this frame can't access the main page. | — |
| **Frameworks** | | |
| Next.js | Add the page script to `app/layout` or `pages/_app`.<br>The [`cakeNext`](../edge/node/README.md#nextjs) middleware is optional.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The middleware comes with AgentCake at no cost. |
| Express | Add the page script before `</head>` in each template.<br>The [`cakeExpress`](../edge/node/README.md#express-connect-or-nodehttp) middleware is optional.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The middleware comes with AgentCake at no cost. |
| Hono | Add the page script before `</head>` in each template.<br>The [`cakeHono`](../edge/node/README.md#hono) middleware is optional.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The middleware comes with AgentCake at no cost. |
| Flask | Add the page script before `</head>` in each template.<br>The [`CakeEdgeWSGI`](../edge/python/README.md#flask) middleware is optional.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The middleware comes with AgentCake at no cost. |
| FastAPI | Add the page script before `</head>` in each template.<br>The [`CakeEdgeASGI`](../edge/python/README.md#fastapi-or-starlette) middleware is optional.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The middleware comes with AgentCake at no cost. |
| Django | Add the page script before `</head>` in each template.<br>The [`CakeEdgeWSGI`](../edge/python/README.md#django) middleware in `wsgi.py` is optional.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The middleware comes with AgentCake at no cost. |
| PHP | Add the page script before `</head>` in each template.<br>The [`cake_edge.php`](../edge/php/README.md#any-php-site) middleware is optional.<br>Set up a server on a subdomain and add one DNS record. | None.<br>The middleware comes with AgentCake at no cost. |
| **Other cases** | | |
| Trial on this computer | Install AgentCake on this computer.<br>Add the page script to the site that you run locally.<br>You don't need a server or a DNS record. | None. |
| Site without its own domain | For a trial, use a free [sslip.io name](../SERVER.md#sites-without-their-own-domain) instead of a DNS record.<br>Use a static IP address for the server.<br>For production, use a domain that you control. | An sslip.io name is free.<br>A new .com domain costs [$11.17 a year](https://pricing.registrar.cloudflare.com/). |
| DNS on Cloudflare | To add the page script, follow the steps for your hosting platform.<br>Set up a server on a subdomain and add one DNS record.<br>[DNS only](../SERVER.md#sites-behind-cloudflares-proxy) is the recommended setting for the record. | None.<br>[Cloudflare's DNS](https://www.cloudflare.com/plans/) is free. |

Estimates per 10,000 page views assume about one minute on each page. Each range goes from an idle visitor to a constantly active one. Site builder and WordPress.com plan prices in this table are per month, billed yearly.

These prices are from each provider's website or public price list on November 20, 2026. Prices can change.

## Platform plans

These are the lowest plans on each platform that allow the page script, the plugin, or a custom domain. If your site
already uses one of these plans or a higher plan, AgentCake doesn't result in additional platform costs.

| Platform | Minimum plan | Per month, billed yearly | Per month, billed monthly |
|---|---|---|---|
| [WordPress.com](https://wordpress.com/pricing/) | Personal | $4 | $9 |
| [Shopify](https://www.shopify.com/pricing) | Basic | $29 | $39 |
| [Wix](https://www.wix.com/plans) | Light | $17 | Not listed |
| [Squarespace](https://www.squarespace.com/pricing) | Core | $29 | $39 |
| [Webflow](https://webflow.com/pricing) | Basic Site plan | $15 | $25 |
| [Framer](https://www.framer.com/pricing) | Basic | $10 | $15 |
| [Ghost(Pro)](https://ghost.org/pricing/) | Starter | $15 | $18 |

Wix's price is for the US. Prices vary by location, and the plans page shows only yearly prices.

These prices are from each platform's pricing page on November 20, 2026. Prices can change.

## Server costs

The cheapest plan at each provider with 1 GB of memory and a public IPv4 address:

| Provider | Plan | CPU | Memory | Price per month |
|---|---|---|---|---|
| [Oracle Cloud](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) | Always Free VM | 1/8 OCPU | 1 GB | $0 |
| [Google Cloud](https://cloud.google.com/free/docs/free-cloud-features#compute) | Free e2-micro VM | Shared core | 1 GB | $3.65 |
| [Vultr](https://www.vultr.com/pricing/) | Regular Performance | 1 vCPU | 1 GB | $5 |
| [Akamai Linode](https://www.linode.com/pricing/) | Nanode 1 GB | 1 vCPU | 1 GB | $5 |
| [Hetzner Cloud](https://www.hetzner.com/cloud/regular-performance) | CPX02 in Helsinki | 1 vCPU | 1 GB | €5.49 |
| [DigitalOcean](https://www.digitalocean.com/pricing/droplets) | Basic Droplet | 1 vCPU | 1 GiB | $6 |
| [Amazon Lightsail](https://aws.amazon.com/lightsail/pricing/) | Linux instance with IPv4 | 2 vCPUs | 1 GB | $7 |
| [Amazon EC2](https://aws.amazon.com/ec2/pricing/on-demand/) | t4g.micro with disk and IPv4 | 2 vCPUs | 1 GiB | $12.18 |

- Oracle Cloud: Oracle can reclaim an instance after 7 days of low CPU and network use. Your home region can also run
  out of capacity.
- Google Cloud: The free tier covers one e2-micro a month in us-west1, us-central1, or us-east1, with 30 GB of
  standard persistent disk. The price is for the [public IPv4 address](https://cloud.google.com/vpc/network-pricing#ipaddress),
  at $0.005 per hour. A 30 GB balanced disk would add [$3.00 a month](https://cloud.google.com/compute/disks-image-pricing).
- Vultr: The [plan](https://www.vultr.com/pricing/) costs $7.50 in São Paulo.
- Akamai Linode: The [Nanode](https://www.linode.com/pricing/) costs more in two regions: $6 in Jakarta and $7 in
  São Paulo.
- Hetzner Cloud: Prices are in euros and don't include VAT. [CPX02](https://www.hetzner.com/cloud/regular-performance)
  costs €6.49 in Germany and €7.99 in Singapore. It isn't available in the US, where the cheapest plan is CPX11 at
  €17.99.
- Amazon EC2: The price uses on-demand rates in us-east-1. The t4g.micro is an
  [Arm instance](https://aws.amazon.com/ec2/instance-types/t4/).

| Amazon EC2 part | Price per month |
|---|---|
| [t4g.micro instance](https://aws.amazon.com/ec2/pricing/on-demand/) | $6.13 |
| [30 GB gp3 disk](https://aws.amazon.com/ebs/pricing/) | $2.40 |
| [Public IPv4 address](https://aws.amazon.com/vpc/pricing/) | $3.65 |

These prices are from each provider's website or public price list on November 20, 2026. Prices can change.
