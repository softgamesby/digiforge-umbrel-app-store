#!/bin/sh
# DigiForge integration — Developed by Mikal
set -u

CONFIG=/config/config.json
last=""

checksum() {
  if [ -s "$CONFIG" ]; then
    cksum "$CONFIG" 2>/dev/null | awk '{print $1 ":" $2}'
  else
    echo "missing"
  fi
}

while true; do
  current="$(checksum)"

  # No pool yet: keep container healthy-ish without starting Miningcore.
  if [ "$current" = "missing" ] || ! grep -q '"id"[[:space:]]*:[[:space:]]*"dgb-sha256"' "$CONFIG" 2>/dev/null; then
    last="$current"
    sleep 2
    continue
  fi

  echo "DigiForge: starting Miningcore"
  /app/Miningcore -c "$CONFIG" &
  pid=$!
  last="$current"

  while kill -0 "$pid" 2>/dev/null; do
    sleep 3
    current="$(checksum)"
    if [ "$current" != "$last" ]; then
      echo "DigiForge: configuration changed; reloading Miningcore"
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      break
    fi
  done

  wait "$pid" 2>/dev/null || true
  sleep 2
done
