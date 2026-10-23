const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.join(__dirname, 'appium');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'runtime.json'), 'utf8'));
const plugins = manifest.plugins || [];
for (const [name, value] of Object.entries(manifest.environment || {})) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || typeof value !== 'string' || value.includes('\0')) {
        throw Error('Invalid runtime environment');
    }
    process.env[name] = value.split('${RUNTIME}').join(root);
}
if (!Array.isArray(plugins) || plugins.some(name => typeof name !== 'string' || !/^[a-z0-9-]+$/.test(name))) {
    throw Error('Invalid Appium plugin activation list');
}
process.env.APPIUM_HOME = path.join(root, 'extensions');
// macOS ships Git as an install-on-demand shim. Appium's optional build-info
// probe must report missing tools instead of opening a developer-tools installer.
// Respect explicitly configured or already selected developer toolchains.
if (process.platform === 'darwin' && !process.env.DEVELOPER_DIR &&
    spawnSync('/usr/bin/xcode-select', ['--print-path'], {stdio: 'ignore'}).status !== 0) {
    process.env.DEVELOPER_DIR = '/Library/Developer/CommandLineTools';
}
process.argv = [process.execPath, path.join(root, 'node_modules/appium/index.js'),
    '--address', '127.0.0.1', '--port', '4723', '--log-no-colors',
    ...(plugins.length ? ['--use-plugins', plugins.join(',')] : [])];
// Run in the service's own process so stopping it cannot orphan an Appium child.
require(path.join(root, 'node_modules/appium')).main();
