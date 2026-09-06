#!/bin/sh
# DigiForge integration — Developed by Mikal
set -eu

PGDATA="${PGDATA:-/var/lib/postgresql/data}"
PGUSER="${POSTGRES_USER:-miningcore}"
PGDATABASE="${POSTGRES_DB:-miningcore}"
PASSWORD_FILE="${POSTGRES_PASSWORD_FILE:-/secrets/postgres-password}"

if [ ! -s "$PASSWORD_FILE" ]; then
    echo "DigiForge: PostgreSQL password file missing or empty" >&2
    exit 1
fi

# Fresh database: let the official entrypoint initialize PostgreSQL
# directly with POSTGRES_PASSWORD_FILE.
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    exec docker-entrypoint.sh "$@"
fi

# Existing database: start normally, then rotate the role password
# locally over PostgreSQL's trusted Unix socket.
docker-entrypoint.sh "$@" &
postgres_pid=$!

trap 'kill -TERM "$postgres_pid" 2>/dev/null || true' TERM INT

while ! pg_isready \
    -h /var/run/postgresql \
    -U "$PGUSER" \
    -d "$PGDATABASE" >/dev/null 2>&1; do
    if ! kill -0 "$postgres_pid" 2>/dev/null; then
        wait "$postgres_pid"
        exit $?
    fi
    sleep 1
done

NEW_PASSWORD="$(cat "$PASSWORD_FILE")"
ESCAPED_PASSWORD="$(printf '%s' "$NEW_PASSWORD" | sed "s/'/''/g")"

printf "ALTER ROLE miningcore WITH PASSWORD '%s';\n" "$ESCAPED_PASSWORD" |
    psql \
        -h /var/run/postgresql \
        -U "$PGUSER" \
        -d "$PGDATABASE" \
        -q -v ON_ERROR_STOP=1 >/dev/null

unset NEW_PASSWORD ESCAPED_PASSWORD

echo "DigiForge: PostgreSQL credential synchronized"

wait "$postgres_pid"
