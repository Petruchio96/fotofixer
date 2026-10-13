#!/bin/sh
# Runs at container start (the nginx image runs /docker-entrypoint.d/*.sh).
# Turns the optional password on or off, and sets the access log, by writing
# two small files nginx includes. They go to /tmp (a tmpfs in the compose
# file) because the container's own file system is read-only.
#
#   APP_USERNAME       the one shared user name (default: fotofixer)
#   APP_PASSWORD       its password; or
#   APP_PASSWORD_FILE  a file holding the password (Docker secrets)
#   ACCESS_LOG         "off" to log no requests (default: on, to stdout)
#
# Without a password the page is open to anyone who can reach it. A visitor
# can only ever change their own files, so the password only decides who can
# load the page.
set -eu

dir=/tmp/fotofixer
mkdir -p "$dir"

password="${APP_PASSWORD:-}"
if [ -n "${APP_PASSWORD_FILE:-}" ]; then
    password="$(cat "$APP_PASSWORD_FILE")"
fi

if [ -n "$password" ]; then
    user="${APP_USERNAME:-fotofixer}"
    # bcrypt hash; the password goes through stdin, not the command line.
    printf '%s\n' "$password" | htpasswd -niB "$user" > "$dir/htpasswd"
    printf 'auth_basic "FotoFixer";\nauth_basic_user_file %s/htpasswd;\n' "$dir" > "$dir/auth.conf"
    echo "FotoFixer: password protection is on (user \"$user\")."
else
    printf 'auth_basic off;\n' > "$dir/auth.conf"
    echo "FotoFixer: no password set (APP_PASSWORD or APP_PASSWORD_FILE); the page is open to anyone who can reach it."
fi

case "${ACCESS_LOG:-on}" in
    off|false|0|no) printf 'access_log off;\n' > "$dir/log.conf" ;;
    *) printf 'access_log /dev/stdout;\n' > "$dir/log.conf" ;;
esac
