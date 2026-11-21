<?php
/**
 * The files around the PHP middleware: its settings are the Node middleware's, the WordPress plugin carries this very
 * middleware, and the READMEs a site owner reads before mounting it (PHP, WordPress) name every field of the token, say
 * what it never holds and what a page cache does to it.
 */

declare(strict_types=1);

namespace AgentCake\Tests;

use AgentCake\EdgeFormat;

const PLUGIN = REPO . '/edge/wordpress/agentcake';
const NODE_ONLY = ['verdict_wait_ms']; // botscent's wait: botscent is a JavaScript library

function readme(string $folder): string
{
    return (string) preg_replace('/\s+/', ' ', (string) file_get_contents("$folder/README.md"));
}

function test_the_settings_are_the_node_middlewares(): void
{
    $node = read_json(REPO . '/edge/node/defaults.json');
    $ours = EdgeFormat::settings();
    same($node['fixed'], $ours['fixed']);
    same(read_json(REPO . '/edge/node/headers.json'), $ours['headers']);
    $options = $node['options'];
    foreach (NODE_ONLY as $key) {
        unset($options[$key]);
    }
    same($options, $ours['options']);
}

function test_the_wordpress_plugin_carries_this_very_middleware_and_its_settings(): void
{
    foreach (['cake_edge.php', 'cake_edge_format.php', 'cake_edge.json'] as $file) {
        same(hash_file('sha256', REPO . "/edge/php/$file"), hash_file('sha256', PLUGIN . "/$file"), "copy edge/php/$file into the plugin");
    }
}

function test_the_plugin_writes_the_cake_js_line_agent_cake_expects(): void
{
    $plugin = read_json(PLUGIN . '/agentcake.json');
    same(read_json(REPO . '/agentcake/defaults.json')['site_key']['pattern'], $plugin['site_key_pattern'], 'the site key');
    check(strpos((string) file_get_contents(REPO . '/agentcake/routes.py'), '"GET", "' . $plugin['script_path'] . '"') !== false, 'cake serves the script there');
    $snippet = (string) file_get_contents(REPO . '/agentcake/site_setup.py');
    check(strpos($snippet, '<script src="{src}" data-site="{site_key}" defer>') !== false, 'the attributes of cake\'s own line');
    check(strpos($snippet, 'SCRIPT_PATH = "' . $plugin['script_path'] . '"') !== false, 'its src ends in the same path');
}

/** A plugin header field read the way WordPress's get_file_data() reads it, from the file's first 8 KB. */
function plugin_header(string $field): ?string
{
    $head = (string) file_get_contents(PLUGIN . '/agentcake.php', false, null, 0, 8192);
    return preg_match('/^(?:[ \t]*<\?php)?[ \t\/*#@]*' . preg_quote($field, '/') . ':(.*)$/mi', $head, $match) === 1 ? trim($match[1]) : null;
}

function test_the_plugin_header_names_its_licence_and_the_versions_it_needs(): void
{
    $expected = ['Plugin Name' => 'AgentCake', 'License' => 'MIT', 'Requires PHP' => '7.4', 'Text Domain' => 'agentcake'];
    foreach ($expected as $field => $value) {
        same($value, plugin_header($field), $field);
    }
    check(version_compare((string) plugin_header('Requires at least'), '5.7', '>='), 'wp_print_script_tag() came in WordPress 5.7');
}

function test_the_readmes_name_every_field_of_the_token_and_what_it_never_holds(): void
{
    $fields = array_keys(vectors()['mint'][0]['payload']);
    foreach ([REPO . '/edge/php', PLUGIN] as $folder) {
        $text = (string) file_get_contents("$folder/README.md");
        foreach ($fields as $field) {
            check(preg_match('/^\| `' . $field . '` \|/m', $text) === 1, basename($folder) . " README names $field");
        }
        check(stripos(readme($folder), 'never holds an IP address') !== false, basename($folder) . ' README: never an IP');
    }
}

function test_the_readmes_explain_caching_and_the_wordpress_one_page_cache_plugins(): void
{
    check(strpos(readme(REPO . '/edge/php'), 'noStore') !== false && strpos(readme(REPO . '/edge/php'), '304') !== false, 'PHP README: noStore, 304');
    $wordpress = readme(PLUGIN);
    foreach (['page cache', 'reuse', 'CAKE_SERVER_TIMING_SECRET', 'wp-config.php', 'wp_head', 'send_headers'] as $words) {
        check(stripos($wordpress, $words) !== false, "WordPress README: $words");
    }
}
