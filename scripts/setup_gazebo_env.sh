#!/usr/bin/env bash
# Source this file before running Gazebo manually:
#   source scripts/setup_gazebo_env.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

prepend_path() {
  local var_name="$1"
  local new_path="$2"
  local current_value="${!var_name:-}"

  if [[ ! -d "$new_path" ]]; then
    return 0
  fi

  case ":$current_value:" in
    *":$new_path:"*) ;;
    *) export "$var_name=$new_path${current_value:+:$current_value}" ;;
  esac
}

prepend_path GAZEBO_MODEL_PATH "$PROJECT_ROOT/models"

CLOVER_SIMULATION_PATH=""
if command -v rospack >/dev/null 2>&1; then
  CLOVER_SIMULATION_PATH="$(rospack find clover_simulation 2>/dev/null || true)"
fi

for models_path in \
  "$CLOVER_SIMULATION_PATH/resources/models" \
  "$CLOVER_SIMULATION_PATH/models" \
  "$HOME/catkin_ws/src/clover/clover_simulation/resources/models" \
  "$HOME/catkin_ws/src/clover/clover_simulation/models"; do
  prepend_path GAZEBO_MODEL_PATH "$models_path"
done

if [[ "${1:-}" != "--quiet" ]]; then
  echo "GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH"
fi
