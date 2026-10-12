#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: %s USER@HOST:/remote/project/path/\n' "$0" >&2
  printf 'Example: %s pi@raspberrypi.local:/opt/inm2/\n' "$0" >&2
  exit 2
fi

target=$1
if [[ "$target" != *@*:* ]]; then
  printf 'Target must look like USER@HOST:/remote/project/path/\n' >&2
  exit 2
fi

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Intentionally do not use --delete: files on the Raspberry Pi are preserved.
# Instance configuration and runtime data are excluded from upload entirely.
rsync -avz --human-readable --progress \
  --exclude='/.git/' \
  --exclude='/.env' \
  --exclude='/.env.*' \
  --exclude='/databases/' \
  --exclude='/logs/' \
  --exclude='__pycache__/' \
  --exclude='*.py[cod]' \
  --exclude='node_modules/' \
  --exclude='dist/' \
  "$project_dir/" "$target"
