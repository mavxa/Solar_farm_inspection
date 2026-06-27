#!/usr/bin/env bash
set -euo pipefail

SHARED_ROOT="${1:-/mnt/vm_shared}"
DATASET_DIR="$SHARED_ROOT/solar_dataset/raw"

if ! mountpoint -q "$SHARED_ROOT"; then
  echo "$SHARED_ROOT is not mounted." >&2
  echo "Try: sudo mkdir -p $SHARED_ROOT && sudo mount -t virtiofs vm_shared $SHARED_ROOT" >&2
  exit 1
fi

mkdir -p "$DATASET_DIR"

test_file="$DATASET_DIR/.write_test"
if ! touch "$test_file" 2>/dev/null; then
  echo "No write permission for $DATASET_DIR" >&2
  echo "Try: sudo mkdir -p $DATASET_DIR && sudo chown -R \$USER:\$USER $SHARED_ROOT/solar_dataset" >&2
  exit 1
fi

rm -f "$test_file"
echo "Shared dataset dir is writable: $DATASET_DIR"
