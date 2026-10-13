#!/usr/bin/env bash
# Build the image and check a running container the way CI does: the page
# loads, the WebAssembly has the right type, the security headers are there,
# the password works when set and is absent when not, and nothing in the
# image looks like a key. Needs Docker.
#
#   docker/check_container.sh            # builds fotofixer:check and tests it
#   IMAGE=fotofixer:ci docker/check_container.sh   # tests an image already built
set -euo pipefail

cd "$(dirname "$0")/.."
IMAGE="${IMAGE:-}"
if [ -z "$IMAGE" ]; then
    IMAGE=fotofixer:check
    docker build -f docker/Dockerfile -t "$IMAGE" .
fi

# Not --rm: a container that dies at start must keep its logs for us.
run_opts=(-d --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true -p 127.0.0.1:18080:8080)
cid=""
stop() {
    if [ -n "$cid" ]; then
        docker stop "$cid" >/dev/null 2>&1 || true
        docker rm -f "$cid" >/dev/null 2>&1 || true
    fi
    cid=""
}
trap stop EXIT
fail() {
    echo "FAIL: $*" >&2
    if [ -n "$cid" ]; then
        echo "--- container logs:" >&2
        docker logs "$cid" >&2 || true
    fi
    exit 1
}
wait_up() {
    for _ in $(seq 1 30); do
        curl -fs -o /dev/null http://127.0.0.1:18080/healthz && return 0
        sleep 1
    done
    fail "the container did not answer on /healthz"
}

echo "== open (no password)"
cid=$(docker run "${run_opts[@]}" "$IMAGE")
wait_up
headers=$(curl -fsi http://127.0.0.1:18080/)
grep -qi "^content-security-policy: .*wasm-unsafe-eval" <<<"$headers" || fail "no Content-Security-Policy header"
grep -qi "^x-content-type-options: nosniff" <<<"$headers" || fail "no X-Content-Type-Options header"
grep -qi "^referrer-policy: strict-origin-when-cross-origin" <<<"$headers" || fail "no Referrer-Policy header"
grep -qi "^cache-control: no-cache" <<<"$headers" || fail "no Cache-Control header"
grep -q "FotoFixer" <<<"$headers" || fail "the page does not mention FotoFixer"
wasm=$(curl -fsI -H "Accept-Encoding: gzip" http://127.0.0.1:18080/vendor/zeroperl.wasm)
grep -qi "^content-type: application/wasm" <<<"$wasm" || fail "zeroperl.wasm is not served as application/wasm"
grep -qi "^content-encoding: gzip" <<<"$wasm" || fail "zeroperl.wasm is not served pre-compressed"
curl -fs -o /dev/null http://127.0.0.1:18080/app/main.js || fail "app/main.js missing"
curl -fs -o /dev/null http://127.0.0.1:18080/worker/exif_worker.js || fail "worker missing"
curl -fs -o /dev/null http://127.0.0.1:18080/vendor/exiftool.js || fail "vendor/exiftool.js missing"
pyodide=$(curl -fsI -H "Accept-Encoding: gzip" http://127.0.0.1:18080/vendor/pyodide/pyodide.asm.wasm)
grep -qi "^content-type: application/wasm" <<<"$pyodide" || fail "pyodide.asm.wasm is not served as application/wasm"
grep -qi "^content-encoding: gzip" <<<"$pyodide" || fail "pyodide.asm.wasm is not served pre-compressed"
curl -fs -o /dev/null http://127.0.0.1:18080/vendor/pyodide/pyodide.mjs || fail "pyodide.mjs missing"
curl -fs -o /dev/null http://127.0.0.1:18080/vendor/pyodide/python_stdlib.zip || fail "python_stdlib.zip missing"
curl -fs -o /dev/null http://127.0.0.1:18080/vendor/pyodide/tzdata-2025.3-py2.py3-none-any.whl || fail "tzdata wheel missing"
curl -fs -o /dev/null http://127.0.0.1:18080/py/fotofixer_py.zip || fail "py/fotofixer_py.zip missing"
curl -fs -o /dev/null http://127.0.0.1:18080/vendor/leaflet/leaflet.esm.js || fail "leaflet.esm.js missing"
curl -fsI http://127.0.0.1:18080/vendor/leaflet/leaflet.css | grep -qi "^content-type: text/css" || fail "leaflet.css missing or not text/css"
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18080/tests/photo_store.test.mjs)
[ "$code" = "404" ] || fail "tests are in the image (got $code)"
stop

echo "== with a password"
cid=$(docker run "${run_opts[@]}" -e APP_USERNAME=friend -e APP_PASSWORD='s3cret pass' "$IMAGE")
wait_up
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18080/)
[ "$code" = "401" ] || fail "expected 401 without the password, got $code"
code=$(curl -s -o /dev/null -w "%{http_code}" -u 'friend:wrong' http://127.0.0.1:18080/)
[ "$code" = "401" ] || fail "expected 401 with a wrong password, got $code"
code=$(curl -s -o /dev/null -w "%{http_code}" -u 'friend:s3cret pass' http://127.0.0.1:18080/)
[ "$code" = "200" ] || fail "expected 200 with the password, got $code"
curl -fs http://127.0.0.1:18080/healthz | grep -q ok || fail "/healthz should not need the password"
stop

echo "== with a password file"
secret=$(mktemp)
printf 'from-a-file' > "$secret"
# The container reads it as the nginx user, not as us (mktemp makes it 0600).
chmod 644 "$secret"
cid=$(docker run "${run_opts[@]}" -v "$secret:/run/secrets/pw:ro" -e APP_PASSWORD_FILE=/run/secrets/pw "$IMAGE")
wait_up
code=$(curl -s -o /dev/null -w "%{http_code}" -u 'fotofixer:from-a-file' http://127.0.0.1:18080/)
[ "$code" = "200" ] || fail "expected 200 with the password from the file, got $code"
stop
rm -f "$secret"

echo "== an unreadable password file stops the container with a message"
secret=$(mktemp)
printf 'hidden' > "$secret"
chmod 600 "$secret"
cid=$(docker run "${run_opts[@]}" -v "$secret:/run/secrets/pw:ro" -e APP_PASSWORD_FILE=/run/secrets/pw "$IMAGE")
sleep 3
docker logs "$cid" 2>&1 | grep -q "cannot read APP_PASSWORD_FILE" || fail "no message about the unreadable password file"
stop
rm -f "$secret"

echo "== nothing secret in the image"
if docker run --rm --entrypoint sh "$IMAGE" -c 'grep -rIlE "(api[_-]?key|token|password)\s*[:=]\s*[\"'"'"'][A-Za-z0-9]{12,}" /usr/share/nginx/html' | grep .; then
    fail "something in the image looks like a key"
fi

echo "all container checks passed"
