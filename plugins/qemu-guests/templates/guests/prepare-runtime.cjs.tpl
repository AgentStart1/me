const fs = require('node:fs');
const path = require('node:path');
const root = process.argv[2];
const prepared = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const yaml = require(path.join(root, 'node_modules/yaml'));
const manifestFile = path.join(root, 'runtime.json');
const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
const file = path.join(root, 'extensions/node_modules/.cache/appium/extensions.yaml');
const replace = value => {
    if (typeof value === 'string') return value.split(manifest.source_root).join(root);
    if (Array.isArray(value)) return value.map(replace);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k,replace(v)]));
    return value;
};
// A server-only offline runtime has no extension cache until its first start.
const config = fs.existsSync(file) ? replace(yaml.parse(fs.readFileSync(file, 'utf8'))) :
    {drivers: {}, plugins: {}, schemaRev: 4};
for (const {path: installPath, package: pkg} of prepared) {
    const metadata = pkg.appium;
    const plugins = Boolean(metadata.pluginName);
    const collection = plugins ? config.plugins : config.drivers;
    const name = metadata.pluginName || metadata.driverName;
    collection[name] = {
        pkgName: pkg.name, version: pkg.version, installType: 'local', installSpec: installPath,
        installPath, appiumVersion: pkg.peerDependencies.appium,
        mainClass: metadata.mainClass,
        ...(!plugins ? {automationName: metadata.automationName, platformNames: metadata.platformNames} : {}),
    };
}
manifest.plugins = Object.keys(config.plugins || {});
manifest.extensions = Object.fromEntries(['drivers', 'plugins'].map(kind => [kind,
    Object.fromEntries(Object.entries(config[kind] || {}).map(([name, item]) => [name, item.version]))]));
manifest.source_root = root;
fs.mkdirSync(path.dirname(file), {recursive: true});
fs.writeFileSync(file, yaml.stringify(config));
fs.writeFileSync(manifestFile, JSON.stringify(manifest));
