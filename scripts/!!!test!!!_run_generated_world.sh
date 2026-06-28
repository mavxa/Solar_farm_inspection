#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Тонкая обёртка для старого тестового имени; основной запуск в run_generated_world.sh.
exec "$SCRIPT_DIR/run_generated_world.sh"
