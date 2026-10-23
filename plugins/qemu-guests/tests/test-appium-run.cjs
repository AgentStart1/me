const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../templates/guests/appium-run.cjs.tpl'), 'utf8');

function start(platform, selectedStatus, env = {}) {
    const process = {platform, env: {...env}, execPath: '/runtime/node'};
    const probes = [];
    let starts = 0;
    vm.runInNewContext(source, {
        __dirname: '/fixture', process,
        require: name => ({
            'node:fs': {readFileSync: () => JSON.stringify({plugins: []})},
            'node:path': require('node:path'),
            'node:child_process': {spawnSync: (...args) => {
                probes.push(args);
                return {status: selectedStatus};
            }},
        })[name] || {main: () => starts++},
    });
    assert.equal(starts, 1);
    return {env: process.env, probes};
}

test('a Mac without developer tools reports unavailable tooling without launching installation', () => {
    const result = start('darwin', 2);
    assert.equal(result.env.DEVELOPER_DIR, '/Library/Developer/CommandLineTools');
    assert.equal(result.probes.length, 1);
    assert.equal(result.probes[0][0], '/usr/bin/xcode-select');
    assert.deepEqual(Array.from(result.probes[0][1]), ['--print-path']);
});

test('selected or explicitly configured toolchains and other platforms remain usable', () => {
    assert.equal(start('darwin', 0).env.DEVELOPER_DIR, undefined);
    const explicit = start('darwin', 2, {DEVELOPER_DIR: '/Applications/OperatorXcode.app'});
    assert.equal(explicit.env.DEVELOPER_DIR, '/Applications/OperatorXcode.app');
    assert.equal(explicit.probes.length, 0);
    for (const platform of ['win32', 'linux']) {
        const result = start(platform, 2);
        assert.equal(result.env.DEVELOPER_DIR, undefined);
        assert.equal(result.probes.length, 0);
    }
});
