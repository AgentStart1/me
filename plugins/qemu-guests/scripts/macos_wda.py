"""Restart only the reviewed WDA runner left behind by its launchd wrapper."""
import shlex
import time
from urllib.parse import urlsplit

from test_environment_owner import CleanupUncertain
from test_cancellation import is_cancellation


def listener(shell, url, allow_missing=False):
    port = urlsplit(url).port
    output = shell(f'/usr/sbin/lsof -nP -a -iTCP:{port} -sTCP:LISTEN -t; '
                   'result=$?; [ "$result" -eq 0 ] || [ "$result" -eq 1 ]', timeout=10)
    values = set(output.decode().split())
    if not values and allow_missing:
        return None
    if len(values) != 1 or not next(iter(values)).isdigit():
        raise RuntimeError('Prepared WDA listener identity is missing or ambiguous')
    return int(next(iter(values)))


def process_record(shell, pid):
    return shell(f'ps -ww -p {pid} -o pid= -o uid= -o lstart= -o comm=; '
                 'result=$?; [ "$result" -eq 0 ] || [ "$result" -eq 1 ]', timeout=10).decode().strip()


def restart(shell, config, plan, owner):
    owner.checkpoint()
    try:
        with owner.cancellation.shield():
            _restart(shell, config, plan, owner)
    except BaseException as error:
        owner.retain()
        if is_cancellation(error):
            raise
        raise CleanupUncertain('Prepared WDA restart is unconfirmed') from error
    owner.checkpoint()


def _restart(shell, config, plan, owner):
    uid = shell('id -u').decode().strip()
    if not uid.isdigit():
        raise RuntimeError('Guest account identity is invalid')
    domain = 'gui/' + uid
    service = domain + '/' + plan.wda_service
    shell('launchctl bootout ' + service, timeout=30)
    # xcodebuild is the launchd job, but testmanagerd launches the runner as a
    # separate app. Killing/restarting only xcodebuild can leave its listener alive.
    pid = listener(shell, plan.wda_url, allow_missing=True)
    if pid is not None:
        stop_runner(shell, pid, uid, plan, owner)
    plist = '/Users/' + config['ssh_user'] + '/Library/LaunchAgents/' + plan.wda_service + '.plist'
    shell('launchctl bootstrap ' + domain + ' ' + shlex.quote(plist), timeout=30)


def stop_runner(shell, pid, uid, plan, owner):
    record = process_record(shell, pid)
    if not record:
        return  # A graceful job shutdown may finish between lsof and ps.
    fields = record.split(None, 2)
    approved = False
    for target in plan.permissions:
        executable = shell('/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" ' +
                           shlex.quote(target.path + '/Contents/Info.plist')).decode().strip()
        if not executable or '/' in executable or executable in ('.', '..'):
            raise RuntimeError('Reviewed application executable is invalid')
        if record.endswith(' ' + target.path + '/Contents/MacOS/' + executable):
            approved = True
    if len(fields) != 3 or fields[:2] != [str(pid), uid] or not approved:
        raise CleanupUncertain('WDA listener is not the reviewed test-account application')
    # Recheck PID, account, start time and executable in the same guest shell
    # that sends TERM. Never kill a replacement process or scan by broad name.
    query = f'ps -ww -p {pid} -o pid= -o uid= -o lstart= -o comm='
    command = 'actual=$(' + query + '); actual="${actual#"${actual%%[![:space:]]*}"}"; '
    command += '[ "$actual" = ' + shlex.quote(record) + f' ] && kill -TERM {pid}'
    try:
        shell(command)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            owner.checkpoint()
            current = process_record(shell, pid)
            if not current or current != record:
                break
            time.sleep(.25)
        else:
            raise CleanupUncertain('Reviewed WDA runner exit was not confirmed')
    except (OSError, RuntimeError) as error:
        if is_cancellation(error):
            raise
        # bootout can finish the original runner between the guarded ps and
        # TERM. Only definite absence confirms exit; never signal a replacement.
        if not process_record(shell, pid):
            return
        raise CleanupUncertain('Reviewed WDA runner stop is unconfirmed') from error
