const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');

function fixture(t, existing) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'prepared-runtime-test-'));
    t.after(() => fs.rmSync(root, {recursive: true, force: true}));
    fs.mkdirSync(path.join(root, 'node_modules/yaml'), {recursive: true});
    // JSON is a YAML subset; isolate cache creation/relocation from YAML parsing.
    fs.writeFileSync(path.join(root, 'node_modules/yaml/index.js'),
        'exports.parse=JSON.parse;exports.stringify=JSON.stringify;');
    fs.writeFileSync(path.join(root, 'runtime.json'), JSON.stringify({source_root: '/old/runtime'}));
    const cache = path.join(root, 'extensions/node_modules/.cache/appium/extensions.yaml');
    if (existing) {
        fs.mkdirSync(path.dirname(cache), {recursive: true});
        fs.writeFileSync(cache, JSON.stringify(existing));
    }
    const metadata = path.join(root, 'prepared.json');
    fs.writeFileSync(metadata, JSON.stringify([{
        path: root + '/local-extensions/mac2',
        package: {name: 'appium-mac2-driver', version: '4.5.0', peerDependencies: {appium: '^3'},
            appium: {driverName: 'mac2', automationName: 'Mac2', platformNames: ['Mac'], mainClass: 'Mac2Driver'}},
    }]));
    const run = () => spawnSync(process.execPath, [path.join(__dirname,
        '../templates/guests/prepare-runtime.cjs.tpl'), root, metadata], {encoding: 'utf8'});
    return {root, cache, run};
}

test('adding the first extension initializes a server-only runtime cache', t => {
    const f = fixture(t);
    const result = f.run();
    assert.equal(result.status, 0, result.stderr);
    const cache = JSON.parse(fs.readFileSync(f.cache));
    assert.equal(cache.schemaRev, 4);
    assert.equal(cache.drivers.mac2.installPath, f.root + '/local-extensions/mac2');
    const manifest = JSON.parse(fs.readFileSync(path.join(f.root, 'runtime.json')));
    assert.equal(manifest.extensions.drivers.mac2, '4.5.0');
});

test('adding an extension preserves and relocates an existing registration', t => {
    const f = fixture(t, {drivers: {other: {installPath: '/old/runtime/driver', version: '1.0.0'}},
        plugins: {}, schemaRev: 4});
    const result = f.run();
    assert.equal(result.status, 0, result.stderr);
    const cache = JSON.parse(fs.readFileSync(f.cache));
    assert.equal(cache.drivers.other.installPath, f.root + '/driver');
    assert.equal(cache.drivers.mac2.version, '4.5.0');
});
