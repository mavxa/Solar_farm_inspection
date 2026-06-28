#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/setup_gazebo_env.sh" --quiet

BASE_WORLD="${1:-}"
if [[ -z "$BASE_WORLD" ]]; then
  # Если путь не передали, ищем стандартный Clover world в известных местах VM.
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
  # Без базового мира генератор не сможет сохранить ArUco-поле и Clover окружение.
  echo "Base world not found." >&2
  echo "Usage: $0 /path/to/clover_aruco.world" >&2
  exit 1
fi

# Добавляем панели и объекты прямо в Clover world.
python3 "$SCRIPT_DIR/generate_world.py" \
  --base-world "$BASE_WORLD" \
  --output "$PROJECT_ROOT/worlds/generated_solar.world" \
  --truth-output "$PROJECT_ROOT/worlds/generated_truth.json"

echo "Base world: $BASE_WORLD"
