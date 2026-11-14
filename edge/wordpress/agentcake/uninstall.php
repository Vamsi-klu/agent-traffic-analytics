<?php
/**
 * Deleting the AgentCake plugin removes its one option, the settings. It keeps nothing else: no table, no
 * transient, no file. The secret lives in wp-config.php or the environment, which the plugin never writes.
 */

defined('WP_UNINSTALL_PLUGIN') || exit;

$agentcake_config = json_decode((string) file_get_contents(__DIR__ . '/agentcake.json'), true);
if (is_array($agentcake_config)) {
    delete_option($agentcake_config['option']);
}
