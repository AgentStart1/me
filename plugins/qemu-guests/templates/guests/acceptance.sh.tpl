set -eu
. /etc/profile.d/qemu-guests.sh
work="$(mktemp -d)"
image=qemu-guests-validation:{{TOKEN}}
container=""
cleanup() {
    [ -z "$container" ] || docker rm -f "$container" >/dev/null 2>&1 || true
    docker image rm "$image" >/dev/null 2>&1 || true
    rm -rf -- "$work"
}
trap cleanup EXIT
cd "$work"
printf '%s\n' 'FROM busybox:1.37' 'COPY index.html /www/index.html' 'CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]' > Dockerfile
printf '%s' '{{TOKEN}}' > index.html
docker build -t "$image" .
container="$(docker run -d --rm --label com.me.qemu-guests.validation={{TOKEN}} -p {{PORT}}:8080 "$image")"
python3 - <<'PY'
import json, time, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
assert json.load(opener.open('http://127.0.0.1:2375/version', timeout=5))['Os'] == 'linux'
for attempt in range(30):
    try:
        response = opener.open('http://127.0.0.1:{{PORT}}', timeout=2)
        assert response.read().decode() == '{{TOKEN}}'
        break
    except OSError:
        if attempt == 29: raise
        time.sleep(.2)
print('CLI_BUILD_API_PUBLISHED_PORT_OK')
PY
