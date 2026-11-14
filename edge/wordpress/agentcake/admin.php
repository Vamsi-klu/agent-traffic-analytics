<?php
/**
 * The AgentCake plugin's settings page, Settings > AgentCake (step S4.3), made with WordPress's Settings API and
 * WordPress's own admin markup: AgentCake's address and the site key for the cake.js line, whether to print that line,
 * where the visitor's address comes from, noStore, and whether the server-half secret is set (never its value). Loaded
 * by agentcake.php in wp-admin only. The site key must look like AgentCake's (ck_ and 3 to 40 letters, digits or _).
 */

defined('ABSPATH') || exit;

add_action('admin_menu', 'agentcake_add_settings_page');
add_action('admin_init', 'agentcake_register_settings');
add_filter('plugin_action_links_' . plugin_basename(AGENTCAKE_PLUGIN_FILE), 'agentcake_action_links');

function agentcake_add_settings_page(): void
{
    $config = agentcake_config();
    add_options_page(__('AgentCake', 'agentcake'), __('AgentCake', 'agentcake'), $config['capability'], $config['page_slug'], 'agentcake_render_settings_page');
}

/** A "Settings" link beside Deactivate on the Plugins screen. */
function agentcake_action_links(array $links): array
{
    $url = admin_url('options-general.php?page=' . agentcake_config()['page_slug']);
    array_unshift($links, '<a href="' . esc_url($url) . '">' . esc_html__('Settings', 'agentcake') . '</a>');
    return $links;
}

function agentcake_register_settings(): void
{
    $config = agentcake_config();
    $page = $config['page_slug'];
    register_setting($config['settings_group'], $config['option'], [
        'type' => 'array',
        'sanitize_callback' => 'agentcake_sanitize',
        'default' => $config['defaults'],
    ]);
    add_settings_section('agentcake_script', __('Page script', 'agentcake'), 'agentcake_section_script', $page);
    add_settings_field('agentcake_cake_url', __('AgentCake address', 'agentcake'), 'agentcake_field_cake_url', $page, 'agentcake_script', ['label_for' => 'agentcake_cake_url']);
    add_settings_field('agentcake_site_key', __('Site key', 'agentcake'), 'agentcake_field_site_key', $page, 'agentcake_script', ['label_for' => 'agentcake_site_key']);
    add_settings_field('agentcake_insert_script', __('cake.js line', 'agentcake'), 'agentcake_field_insert_script', $page, 'agentcake_script');
    add_settings_section('agentcake_server_half', __('Server half', 'agentcake'), 'agentcake_section_server_half', $page);
    add_settings_field('agentcake_secret', __('Secret', 'agentcake'), 'agentcake_field_secret', $page, 'agentcake_server_half');
    add_settings_field('agentcake_client_ip', __('Visitor address', 'agentcake'), 'agentcake_field_client_ip', $page, 'agentcake_server_half', ['label_for' => 'agentcake_client_ip']);
    add_settings_field('agentcake_no_store', __('Page caching', 'agentcake'), 'agentcake_field_no_store', $page, 'agentcake_server_half');
}

/** What the form sends, made safe to keep: an http(s) address without a trailing slash, a site key of the right form. */
function agentcake_sanitize($input): array
{
    $config = agentcake_config();
    $input = is_array($input) ? $input : [];
    $key = trim((string) ($input['site_key'] ?? ''));
    if ($key !== '' && preg_match('/\A' . $config['site_key_pattern'] . '\z/', $key) !== 1) {
        add_settings_error($config['option'], 'agentcake_site_key', __('The site key is ck_ followed by 3 to 40 letters, digits or _. It was not changed.', 'agentcake'));
        $key = agentcake_settings()['site_key'];
    }
    $source = (string) ($input['client_ip'] ?? '');
    return [
        'cake_url' => untrailingslashit(esc_url_raw(trim((string) ($input['cake_url'] ?? '')), $config['url_schemes'])),
        'site_key' => $key,
        'insert_script' => !empty($input['insert_script']),
        'no_store' => !empty($input['no_store']),
        'client_ip' => in_array($source, $config['client_ip_sources'], true) ? $source : $config['defaults']['client_ip'],
    ];
}

function agentcake_render_settings_page(): void
{
    $config = agentcake_config();
    if (!current_user_can($config['capability'])) {
        return;
    }
    echo '<div class="wrap"><h1>' . esc_html(get_admin_page_title()) . '</h1><form action="options.php" method="post">';
    settings_fields($config['settings_group']);
    do_settings_sections($config['page_slug']);
    submit_button();
    echo '</form></div>';
}

function agentcake_section_script(): void
{
    echo '<p>' . esc_html__('AgentCake records visits through its page script. Run "agentcake setup --print --site" on the machine with AgentCake to see its address and the site key.', 'agentcake') . '</p>';
}

function agentcake_section_server_half(): void
{
    echo '<p>' . esc_html__('On each page, the plugin adds a signed token to the Server-Timing header with what only your server sees: the request\'s fetch metadata and Web Bot Auth headers. AgentCake checks it with the secret it shares with this site.', 'agentcake') . '</p>';
}

/** The name and value attributes of one setting's input. */
function agentcake_input_name(string $field): string
{
    return esc_attr(agentcake_config()['option'] . '[' . $field . ']');
}

function agentcake_field_cake_url(): void
{
    printf('<input type="url" id="agentcake_cake_url" name="%s" value="%s" class="regular-text code" placeholder="https://cake.example.com">', agentcake_input_name('cake_url'), esc_attr(agentcake_settings()['cake_url']));
    echo '<p class="description">' . esc_html__('Where visitors\' browsers reach AgentCake; the page script loads from here.', 'agentcake') . '</p>';
}

function agentcake_field_site_key(): void
{
    printf('<input type="text" id="agentcake_site_key" name="%s" value="%s" class="regular-text code" placeholder="ck_..." autocomplete="off">', agentcake_input_name('site_key'), esc_attr(agentcake_settings()['site_key']));
}

function agentcake_field_insert_script(): void
{
    printf('<label><input type="checkbox" name="%s" value="1"%s> %s</label>', agentcake_input_name('insert_script'), checked(agentcake_settings()['insert_script'], true, false), esc_html__('Add the cake.js line to every page\'s head', 'agentcake'));
    echo '<p class="description">' . esc_html__('Turn this off if the line is already in your theme.', 'agentcake') . '</p>';
}

function agentcake_field_secret(): void
{
    $constant = agentcake_config()['secret_constant'];
    $edge = new \AgentCake\Edge(['secret' => agentcake_secret(), 'warn' => '__return_null']);
    if ($edge->enabled()) {
        echo '<p>' . esc_html(defined($constant) ? __('Set in wp-config.php. Pages carry a token.', 'agentcake') : __('Set in the environment. Pages carry a token.', 'agentcake')) . '</p>';
        return;
    }
    echo '<p><strong>' . esc_html__('Not set, or shorter than 32 bytes: pages carry no token.', 'agentcake') . '</strong></p><p class="description">';
    printf(
        /* translators: 1: a line of PHP for wp-config.php, 2: a command */
        esc_html__('Add %1$s to wp-config.php, with the value %2$s prints on the machine with AgentCake.', 'agentcake'),
        '<code>' . esc_html("define( '$constant', '...' );") . '</code>',
        '<code>agentcake secret print</code>'
    );
    echo '</p>';
}

function agentcake_field_client_ip(): void
{
    $choices = [
        'none' => __('Not used: tokens carry no network key', 'agentcake'),
        'remote_addr' => __('The connection\'s address (REMOTE_ADDR)', 'agentcake'),
    ];
    printf('<select id="agentcake_client_ip" name="%s">', agentcake_input_name('client_ip'));
    foreach ($choices as $value => $label) {
        printf('<option value="%s"%s>%s</option>', esc_attr($value), selected(agentcake_settings()['client_ip'], $value, false), esc_html($label));
    }
    echo '</select><p class="description">' . esc_html__('Behind a proxy or a CDN, the connection\'s address is the proxy\'s: leave this off, or give the visitor\'s address with the agentcake_client_ip filter. The address is never sent; only a day-scoped key of its network is.', 'agentcake') . '</p>';
}

function agentcake_field_no_store(): void
{
    printf('<label><input type="checkbox" name="%s" value="1"%s> %s</label>', agentcake_input_name('no_store'), checked(agentcake_settings()['no_store'], true, false), esc_html__('Keep pages out of caches (Cache-Control: private, no-store, and DONOTCACHEPAGE for page cache plugins)', 'agentcake'));
    echo '<p class="description">' . esc_html__('A page served from a cache carries no token, or the same token for every visitor, which AgentCake accepts once. Turn this on if every page view should have a server half; clear the page cache afterwards. See the plugin\'s README.', 'agentcake') . '</p>';
}
