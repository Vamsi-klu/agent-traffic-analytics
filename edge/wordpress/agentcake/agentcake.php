<?php
/**
 * Plugin Name:       AgentCake
 * Description:       AgentCake's server middleware for WordPress: a signed token in each page's Server-Timing header, and the cake.js line in each page's head.
 * Version:           0.6.1
 * Requires at least: 5.7
 * Requires PHP:      7.4
 * Author:            AgentCake
 * License:           MIT
 * License URI:       https://opensource.org/license/mit
 * Text Domain:       agentcake
 *
 * The AgentCake WordPress plugin. It wraps the PHP site middleware (cake_edge.php, cake_edge_format.php and
 * cake_edge.json, the same files as edge/php) with WordPress's own hooks and nothing else:
 *
 *   send_headers   sets the page's token in Server-Timing (Edge::sendHeader), before WordPress sends the page;
 *   wp_head        prints the cake.js line with AgentCake's address and site key (wp_print_script_tag);
 *   admin.php      the settings page under Settings > AgentCake (the Settings API).
 *
 * The secret comes from the CAKE_SERVER_TIMING_SECRET constant in wp-config.php, or the environment variable of that
 * name; it is never stored in the database or shown. The plugin's own values are in agentcake.json. It sets no cookie
 * and makes no network request; the page script itself loads from AgentCake. README.md says what a page cache plugin
 * does to the token. Part of AgentCake, MIT licence.
 */

defined('ABSPATH') || exit;

require_once __DIR__ . '/cake_edge.php';

define('AGENTCAKE_PLUGIN_FILE', __FILE__);

/** agentcake.json, read once per request. */
function agentcake_config(): array
{
    static $config = null;
    if ($config === null) {
        $config = json_decode((string) file_get_contents(__DIR__ . '/agentcake.json'), true, 512, JSON_THROW_ON_ERROR);
    }
    return $config;
}

/** The saved settings over the defaults: cake_url, site_key, insert_script, no_store, client_ip. */
function agentcake_settings(): array
{
    $config = agentcake_config();
    $saved = get_option($config['option'], []);
    return array_merge($config['defaults'], is_array($saved) ? $saved : []);
}

/** The secret from wp-config.php, or null: the middleware then reads the environment variable itself. */
function agentcake_secret(): ?string
{
    $constant = agentcake_config()['secret_constant'];
    return defined($constant) ? (string) constant($constant) : null;
}

/** The middleware, set up from the settings. */
function agentcake_edge(): \AgentCake\Edge
{
    $settings = agentcake_settings();
    return new \AgentCake\Edge([
        'secret' => agentcake_secret(),
        'noStore' => (bool) $settings['no_store'],
        'clientIp' => 'agentcake_client_ip',
        'warn' => 'agentcake_warn',
    ]);
}

/**
 * The visitor's address for the network key: the connection's (REMOTE_ADDR) when the settings say so, else none. Behind
 * a proxy or a CDN, the agentcake_client_ip filter can give the address the proxy saw instead.
 */
function agentcake_client_ip(array $server): ?string
{
    $address = agentcake_settings()['client_ip'] === 'remote_addr' ? ($server['REMOTE_ADDR'] ?? null) : null;
    $filtered = apply_filters('agentcake_client_ip', $address, $server);
    return is_string($filtered) && $filtered !== '' ? $filtered : null;
}

/** A misconfiguration goes to the PHP error log while WP_DEBUG is on; the settings page shows it either way. */
function agentcake_warn(string $line): void
{
    if (defined('WP_DEBUG') && WP_DEBUG) {
        error_log($line);
    }
}

/**
 * The request the middleware reads: null where PHP has getallheaders(), so that it takes the headers as sent, as on any
 * PHP site; else $_SERVER without the slashes WordPress adds to it before plugins run (wp_magic_quotes()), which would
 * otherwise go into the token, Signature-Agent's "https://..." as \"https://...\". PHP has no getallheaders() under
 * php-cgi and in WordPress Playground.
 */
function agentcake_request_server(): ?array
{
    return function_exists('getallheaders') ? null : wp_unslash($_SERVER);
}

/**
 * send_headers: the page's token, before WordPress sends the page; only page requests get one (cake_edge_format.php).
 * Under "Page caching" a page that got a token is also marked for page cache plugins, which read DONOTCACHEPAGE: a
 * stored page would go out to later visitors without a token, or with this one.
 */
function agentcake_send_header(): void
{
    $token = agentcake_edge()->sendHeader(agentcake_request_server());
    $constant = agentcake_config()['page_cache_constant'];
    if ($token !== null && agentcake_settings()['no_store'] && !defined($constant)) {
        define($constant, true);
    }
}

/** wp_head: the cake.js line, once AgentCake's address and the site key are set and the page script is turned on. */
function agentcake_print_script(): void
{
    $settings = agentcake_settings();
    if (!$settings['insert_script'] || $settings['cake_url'] === '' || $settings['site_key'] === '') {
        return;
    }
    wp_print_script_tag([
        'src' => $settings['cake_url'] . agentcake_config()['script_path'],
        'data-site' => $settings['site_key'],
        'defer' => true,
    ]);
}

add_action('send_headers', 'agentcake_send_header');
add_action('wp_head', 'agentcake_print_script', agentcake_config()['head_priority']);

if (is_admin()) {
    require_once __DIR__ . '/admin.php';
}
