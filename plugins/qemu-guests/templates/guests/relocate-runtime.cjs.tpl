const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, 'appium');
const yaml = require(path.join(root, 'node_modules', 'yaml'));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'runtime.json'), 'utf8'));
if (manifest.platform !== process.platform) throw Error('Appium runtime platform mismatch');
if (manifest.arch && manifest.arch !== process.arch) throw Error('Appium runtime CPU architecture mismatch');
const file = path.join(root, 'extensions', 'node_modules', '.cache', 'appium', 'extensions.yaml');
if (fs.existsSync(file)) {
    const replace = value => {
        if (typeof value === 'string') return value.split(manifest.source_root).join(root);
        if (Array.isArray(value)) return value.map(replace);
        if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, replace(v)]));
        return value;
    };
    fs.writeFileSync(file, yaml.stringify(replace(yaml.parse(fs.readFileSync(file, 'utf8')))));
}
