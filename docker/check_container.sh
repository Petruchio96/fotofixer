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

run_opts=(--rm -d --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true -p 127.0.0.1:18080:8080)
fail() { echo "FAIL: $*" >&2; exit 1; }
wait_up() {
    for _ in $(seq 1 30); do
        curl -fs -o /dev/null http://127.0.0.1:18080/healthz && return 0
        sleep 1
    done
    docker logs "$1" || true
    fail "the container did not answer on /healthz"
}

echo "== open (no password)"
cid=$(docker run "${run_opts[@]}" "$IMAGE")
trap 'docker stop "$cid" >/dev/null 2>&1 || true' EXIT
wait_up "$cid"
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
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18080/tests/photo_store.test.mjs)
[ "$code" = "404" ] || fail "tests are in the image (got $code)"
docker stop "$cid" >/dev/null

echo "== with a password"
cid=$(docker run "${run_opts[@]}" -e APP_USERNAME=friend -e APP_PASSWORD='s3cret pass' "$IMAGE")
wait_up "$cid"
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18080/)
[ "$code" = "401" ] || fail "expected 401 without the password, got $code"
code=$(curl -s -o /dev/null -w "%{http_code}" -u 'friend:wrong' http://127.0.0.1:18080/)
[ "$code" = "401" ] || fail "expected 401 with a wrong password, got $code"
code=$(curl -s -o /dev/null -w "%{http_code}" -u 'friend:s3cret pass' http://127.0.0.1:18080/)
[ "$code" = "200" ] || fail "expected 200 with the password, got $code"
curl -fs http://127.0.0.1:18080/healthz | grep -q ok || fail "/healthz should not need the password"
docker stop "$cid" >/dev/null

echo "== with a password file"
secret=$(mktemp)
printf 'from-a-file' > "$secret"
cid=$(docker run "${run_opts[@]}" -v "$secret:/run/secrets/pw:ro" -e APP_PASSWORD_FILE=/run/secrets/pw "$IMAGE")
wait_up "$cid"
code=$(curl -s -o /dev/null -w "%{http_code}" -u 'fotofixer:from-a-file' http://127.0.0.1:18080/)
[ "$code" = "200" ] || fail "expected 200 with the password from the file, got $code"
docker stop "$cid" >/dev/null
rm -f "$secret"

echo "== nothing secret in the image"
if docker run --rm --entrypoint sh "$IMAGE" -c 'grep -rIlE "(api[_-]?key|token|password)\s*[:=]\s*[\"'"'"'][A-Za-z0-9]{12,}" /usr/share/nginx/html' | grep .; then
    fail "something in the image looks like a key"
fi

trap - EXIT
echo "all container checks passed"
