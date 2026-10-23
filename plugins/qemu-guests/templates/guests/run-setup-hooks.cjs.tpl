const fs = require('node:fs');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');
const root = __dirname;
process.env.TEST_RUNTIME_ASSETS = path.join(root, 'appium/assets');
const runtimeFile = path.join(root, 'appium/runtime.json');
if (fs.existsSync(runtimeFile)) {
    const manifest = JSON.parse(fs.readFileSync(runtimeFile, 'utf8'));
    for (const [name, value] of Object.entries(manifest.environment || {})) {
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || typeof value !== 'string' || value.includes('\0')) throw Error('Invalid runtime environment');
        process.env[name] = value.split('${RUNTIME}').join(path.join(root, 'appium'));
    }
}
const hooks = JSON.parse(fs.readFileSync(path.join(root, 'setup-hooks.json'), 'utf8'));
const logs = path.join(root, 'setup-logs');
fs.mkdirSync(logs, {recursive: true, mode: 0o700});
async function run(item, index) {
    if (path.basename(item.script) !== item.script) throw Error('Setup script must be staged beside its manifest');
    const script = path.join(root, item.script);
    const interpreters = {bash: ['/bin/bash'], python3: ['python3'],
        powershell: ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File']};
    const command = interpreters[item.interpreter];
    const log = fs.openSync(path.join(logs, `guest-setup-${index}.log`), 'w', 0o600);
    try {
        await new Promise((resolve, reject) => {
            const child = spawn(command[0], [...command.slice(1), script, ...item.arguments], {
                cwd: root, stdio: ['ignore', log, log], windowsHide: true, detached: process.platform !== 'win32',
            });
            let expired = false;
            const timer = setTimeout(() => {
                expired = true;
                if (process.platform === 'win32') {
                    const stopped = spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {windowsHide: true, stdio: 'ignore', timeout: 5000});
                    if (stopped.status !== 0) child.kill('SIGKILL');
                }
                else { try { process.kill(-child.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; } }
            }, item.timeout_seconds * 1000);
            child.once('error', error => { clearTimeout(timer); reject(error); });
            child.once('exit', code => {
                clearTimeout(timer);
                if (expired || code !== 0) reject(Error(`Project setup hook ${index} ${expired ? 'timed out' : 'failed'}; inspect private setup-logs`));
                else resolve();
            });
        });
    } finally { fs.closeSync(log); }
}
(async () => { for (let i = 0; i < hooks.length; i++) await run(hooks[i], i); })()
    .catch(error => { console.error(error.message); process.exitCode = 1; });
