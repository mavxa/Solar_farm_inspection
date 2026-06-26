#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export GAZEBO_MODEL_PATH="$PROJECT_ROOT/models${GAZEBO_MODEL_PATH:+:$GAZEBO_MODEL_PATH}"

exec gazebo --verbose "$PROJECT_ROOT/worlds/generated_solar.world"
