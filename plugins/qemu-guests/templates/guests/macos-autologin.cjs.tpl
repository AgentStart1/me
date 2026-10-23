const fs = require('node:fs');
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const {spawnSync} = require('node:child_process');

function encodePassword(password) {
    if (!Buffer.isBuffer(password) || !password.length || password.includes(0)) {
        throw Error('A nonempty generated account password is required');
    }
    // loginwindow's kcpassword format: NUL-terminated, padded, repeated XOR key.
    const key = Buffer.from([0x7d, 0x89, 0x52, 0x23, 0xd2, 0xbc, 0xdd, 0xea, 0xa3, 0xb9, 0x1f]);
    const data = Buffer.alloc(Math.ceil((password.length + 1) / 12) * 12);
    password.copy(data);
    for (let i = 0; i < data.length; i++) data[i] ^= key[i % key.length];
    return data;
}

function configure(user) {
    if (process.platform !== 'darwin' || process.getuid() !== 0 || typeof user !== 'string' ||
        !/^[a-z][a-z0-9_-]*$/.test(user)) {
        throw Error('A validated test account and macOS root context are required');
    }
    const password = fs.readFileSync(path.join(__dirname, 'account-password'));
    const encoded = encodePassword(password);
    // Do not expose child arguments or password bytes in thrown process errors.
    if (spawnSync('/usr/bin/dscl', ['.', '-authonly', user, password.toString('utf8')],
        {stdio: 'ignore'}).status !== 0) throw Error('Test-account authentication failed');
    const temporary = '/etc/.kcpassword-' + randomUUID();
    try {
        fs.writeFileSync(temporary, encoded, {flag: 'wx', mode: 0o600});
        fs.chownSync(temporary, 0, 0);
        fs.renameSync(temporary, '/etc/kcpassword');
    } finally {
        fs.rmSync(temporary, {force: true});
        password.fill(0);
    }
    // Apple's installer leaves a one-shot login flag which otherwise deletes
    // both autoLoginUser and kcpassword when the first desktop session starts.
    for (const [name, type, value] of [['oneTimeAutoLogin', '-bool', 'false'],
        ['autoLoginUser', '-string', user],
        ['autoLoginUserScreenLocked', '-bool', 'false']]) {
        if (spawnSync('/usr/bin/defaults', ['write', '/Library/Preferences/com.apple.loginwindow',
            name, type, value], {stdio: 'ignore'}).status !== 0) {
            throw Error('Could not configure test-account automatic login');
        }
    }
}

if (require.main === module) configure(process.argv[2]);
module.exports = {encodePassword};
