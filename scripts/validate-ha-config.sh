#!/usr/bin/env bash
# Basic sanity checks for tracked HA config snippets (no HA runtime required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ERR=0

check_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "MISSING: $f"
    ERR=1
  fi
}

check_file "$ROOT/docker-compose.yml"
check_file "$ROOT/homeassistant/configuration.yaml"
check_file "$ROOT/homeassistant/packages/energy.yaml"
check_file "$ROOT/homeassistant/secrets.yaml.example"

if docker compose -f "$ROOT/docker-compose.yml" config >/dev/null 2>&1; then
  echo "OK: docker compose config"
else
  echo "WARN: docker compose config failed (docker missing?)"
fi

if grep -q 'secrets.yaml' "$ROOT/.gitignore" 2>/dev/null; then
  echo "OK: secrets.yaml gitignored"
else
  echo "WARN: secrets.yaml not in .gitignore"
  ERR=1
fi

if [[ -f "$ROOT/homeassistant/secrets.yaml" ]]; then
  echo "WARN: homeassistant/secrets.yaml exists — must not be committed"
  ERR=1
fi

if [[ $ERR -eq 0 ]]; then
  echo "validate-ha-config: OK"
else
  echo "validate-ha-config: FAILED"
  exit 1
fi
