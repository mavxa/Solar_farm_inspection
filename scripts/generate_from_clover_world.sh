#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/setup_gazebo_env.sh" --quiet

BASE_WORLD="${1:-}"
if [[ -z "$BASE_WORLD" ]]; then
  for candidate in \
    "$HOME/scripts/basic_worlds/worlds/clover_aruco.world" \
    "$HOME/catkin_ws/src/clover/clover_simulation/resources/worlds/clover_aruco.world.bak" \
    "$HOME/catkin_ws/src/clover/clover_simulation/resources/worlds/clover_aruco.world"; do
    if [[ -f "$candidate" ]]; then
      BASE_WORLD="$candidate"
      break
    fi
  done
fi

if [[ -z "$BASE_WORLD" || ! -f "$BASE_WORLD" ]]; then
  echo "Base world not found." >&2
  echo "Usage: $0 /path/to/clover_aruco.world" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/generate_world.py" \
  --base-world "$BASE_WORLD" \
  --output "$PROJECT_ROOT/worlds/generated_solar.world" \
  --truth-output "$PROJECT_ROOT/worlds/generated_truth.json"

echo "Base world: $BASE_WORLD"
