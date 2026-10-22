const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {encodePassword} = require('../templates/guests/macos-autologin.cjs.tpl');

test('loginwindow credentials contain a terminated password and protect block-aligned inputs', () => {
    const key = Buffer.from([125, 137, 82, 35, 210, 188, 221, 234, 163, 185, 31]);
    for (const text of ['fixture', 'abcdefghijkl', 'a'.repeat(32)]) {
        const password = Buffer.from(text);
        const encoded = encodePassword(password);
        assert.equal(encoded.length % 12, 0);
        assert.ok(encoded.length > password.length);
        const decoded = Buffer.from(encoded.map((byte, i) => byte ^ key[i % key.length]));
        assert.equal(decoded.subarray(0, password.length).toString(), text);
        assert.ok(decoded.subarray(password.length).every(byte => byte === 0));
    }
});

test('invalid credentials are rejected without returning encoded state', () => {
    assert.throws(() => encodePassword(Buffer.alloc(0)), /nonempty/);
    assert.throws(() => encodePassword(Buffer.from('fixture\0trailing')), /nonempty/);
});

test('first-boot configuration cancels installer one-shot login before enabling persistent login', () => {
    const calls = [];
    const fakeModule = {exports: {}};
    const requireMock = name => ({
        'node:fs': {
            readFileSync: () => Buffer.from('test-fixture'),
            writeFileSync: (file, data, options) => assert.equal(options.mode, 0o600),
            chownSync() {}, renameSync() {}, rmSync() {},
        },
        'node:path': require('node:path'),
        'node:crypto': {randomUUID: () => 'fixture'},
        'node:child_process': {spawnSync: (command, args) => {
            calls.push([command, ...args]);
            return {status: 0};
        }},
    })[name];
    requireMock.main = fakeModule;
    vm.runInNewContext(fs.readFileSync(require.resolve('../templates/guests/macos-autologin.cjs.tpl'), 'utf8'), {
        require: requireMock, module: fakeModule, Buffer, __dirname: '/fixture',
        process: {platform: 'darwin', getuid: () => 0, argv: ['node', 'helper', 'developer']},
    });
    assert.deepEqual(calls.filter(call => call[0] === '/usr/bin/defaults').map(call => call.slice(-3)), [
        ['oneTimeAutoLogin', '-bool', 'false'],
        ['autoLoginUser', '-string', 'developer'],
        ['autoLoginUserScreenLocked', '-bool', 'false'],
    ]);
});
