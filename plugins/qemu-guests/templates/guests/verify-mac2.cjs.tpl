const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

async function verify() {
    const root = '/opt/qemu-guests/appium';
    const yaml = require(path.join(root, 'node_modules/yaml'));
    const config = yaml.parse(fs.readFileSync(path.join(root,
        'extensions/node_modules/.cache/appium/extensions.yaml'), 'utf8'));
    const driver = config.drivers?.mac2;
    if (!driver || driver.automationName !== 'Mac2' ||
        !driver.platformNames?.includes('Mac') || typeof driver.installPath !== 'string') {
        throw Error('Prepared Mac2 driver is missing');
    }
    // Import only: catch incompatible/missing native dependencies without
    // creating a session, starting WDA or allowing a build fallback.
    const entry = require.resolve(driver.installPath);
    const loaded = await import(pathToFileURL(entry).href);
    if (typeof loaded[driver.mainClass] !== 'function') {
        throw Error('Prepared Mac2 driver entry is incompatible');
    }
}

verify().catch(() => {
    console.error('Prepared Mac2 driver could not be loaded; supply a complete runtime for this OS/CPU.');
    process.exitCode = 1;
});
