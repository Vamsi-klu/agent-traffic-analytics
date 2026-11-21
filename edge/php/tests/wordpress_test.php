<?php
/**
 * The WordPress plugin's own code (edge/wordpress/agentcake/agentcake.php) on a request as WordPress hands it to a
 * plugin. WordPress adds slashes to $_SERVER (wp_magic_quotes(), before plugins hook in), and where PHP has no
 * getallheaders() (php-cgi, WordPress Playground's PHP, and the CLI these tests run in) the middleware reads the
 * request's headers from $_SERVER: a quoted value, Signature-Agent's "https://..." or sec-ch-ua's brands, went into
 * the token as \"...\" (found on WordPress Playground: doctor said Signature-Agent did not reach the site). The
 * plugin gives the middleware $_SERVER without WordPress's slashes. WordPress itself is not loaded: the few functions
 * the plugin calls are stood in for below, written from the WordPress code reference's descriptions (not copied).
 */

declare(strict_types=1);

namespace {
    const ABSPATH = __DIR__ . '/';
    const CAKE_SERVER_TIMING_SECRET = \AgentCake\Tests\SECRET;

    function add_action(string $hook, $callback, int $priority = 10, int $arguments = 1): void
    {
    }

    function is_admin(): bool
    {
        return false;
    }

    function get_option(string $name, $default = false)
    {
        return $default;
    }

    function apply_filters(string $hook, $value, ...$arguments)
    {
        return $value;
    }

    /** WordPress's add_magic_quotes(): addslashes() on every string of an array, at any depth. */
    function add_magic_quotes(array $values): array
    {
        return array_map(function ($value) {
            return is_array($value) ? add_magic_quotes($value) : (is_string($value) ? addslashes($value) : $value);
        }, $values);
    }

    /** WordPress's wp_unslash(): stripslashes() on every string, at any depth. */
    function wp_unslash($value)
    {
        if (is_array($value)) {
            return array_map('wp_unslash', $value);
        }
        return is_string($value) ? stripslashes($value) : $value;
    }

    require_once \AgentCake\Tests\REPO . '/edge/wordpress/agentcake/agentcake.php';
}

namespace AgentCake\Tests {
    const SIGNATURE_AGENT = '"https://chatgpt.com"'; // Web Bot Auth: a quoted string (RFC 8941 sf-string)
    const HEADLESS_BRANDS = '"HeadlessChrome";v="142", "Chromium";v="142", "Not_A Brand";v="99"';

    /** A page typed into a headless Chrome that signs its requests, as WordPress hands it to a plugin: slashed. */
    function wordpress_server(): array
    {
        $lines = [];
        foreach (chrome_page() as [$name, $value]) {
            $lines[] = [$name, strtolower($name) === 'sec-ch-ua' ? HEADLESS_BRANDS : $value];
        }
        $lines[] = ['Signature-Agent', SIGNATURE_AGENT];
        return \add_magic_quotes(server_vars('/', $lines));
    }

    function test_wordpress_slashes_never_reach_the_token_where_php_has_no_getallheaders(): void
    {
        check(!function_exists('getallheaders'), 'these tests run where PHP has no getallheaders()');
        $kept = $_SERVER;
        try {
            $_SERVER = wordpress_server();
            same('\\"https://chatgpt.com\\"', $_SERVER['HTTP_SIGNATURE_AGENT'], 'WordPress slashed $_SERVER');
            $token = \agentcake_edge()->tokenForRequest(\agentcake_request_server());
            check($token !== null, 'a page gets a token');
            $payload = payload_of($token);
            same(SIGNATURE_AGENT, $payload['sg']['a'], 'Signature-Agent as sent');
            same(HEADLESS_BRANDS, $payload['ch']['ua'], 'sec-ch-ua as sent');
            same('"macOS"', $payload['ch']['pf'], 'sec-ch-ua-platform as sent');
        } finally {
            $_SERVER = $kept;
        }
    }
}
