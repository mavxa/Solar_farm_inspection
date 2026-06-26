#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/setup_gazebo_env.sh" --quiet

exec gazebo --verbose "$PROJECT_ROOT/worlds/generated_solar.world"
