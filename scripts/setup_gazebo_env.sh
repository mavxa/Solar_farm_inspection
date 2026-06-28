#!/usr/bin/env bash
# Source this file before running Gazebo manually:
#   source scripts/setup_gazebo_env.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

prepend_path() {
  # Добавляем путь в начало переменной, но не дублируем его при повторном source.
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

add_parent_for_model() {
  # Ищем родительский каталог модели, потому что Gazebo принимает именно parent path.
  local model_name="$1"
  local root
  local config_path
  local model_dir
  local parent_dir

  IFS=":" read -r -a gazebo_paths <<< "${GAZEBO_MODEL_PATH:-}"
  for root in "${gazebo_paths[@]}"; do
    if [[ -f "$root/$model_name/model.config" ]]; then
      return 0
    fi
  done

  # Эти места покрывают стандартную Clover VM и локальные копии basic_worlds.
  for root in \
    "$HOME/catkin_ws" \
    "$HOME/scripts" \
    "/opt/ros/noetic/share" \
    "/usr/share/gazebo-11/models"; do
    if [[ ! -d "$root" ]]; then
      continue
    fi

    config_path="$(find "$root" -path "*/$model_name/model.config" -print -quit 2>/dev/null || true)"
    if [[ -n "$config_path" ]]; then
      model_dir="$(dirname "$config_path")"
      parent_dir="$(dirname "$model_dir")"
      prepend_path GAZEBO_MODEL_PATH "$parent_dir"
      return 0
    fi
  done

  return 1
}

CLOVER_SIMULATION_PATH=""
if command -v rospack >/dev/null 2>&1; then
  # Если ROS окружение уже активировано, rospack даст самый точный путь.
  CLOVER_SIMULATION_PATH="$(rospack find clover_simulation 2>/dev/null || true)"
fi

for models_path in \
  "$CLOVER_SIMULATION_PATH/resources/models" \
  "$CLOVER_SIMULATION_PATH/models" \
  "$HOME/catkin_ws/src/clover/clover_simulation/resources/models" \
  "$HOME/catkin_ws/src/clover/clover_simulation/resources" \
  "$HOME/catkin_ws/src/clover/clover_simulation/models" \
  "$HOME/catkin_ws/install/share/clover_simulation/resources/models" \
  "$HOME/catkin_ws/install/share/clover_simulation/resources" \
  "$HOME/catkin_ws/src/clover/clover_simulation/models"; do
  prepend_path GAZEBO_MODEL_PATH "$models_path"
done

missing_models=()
for model_name in parquet_plane aruco_cmit_txt; do
  # Эти модели нужны стандартному Clover ArUco world.
  if ! add_parent_for_model "$model_name"; then
    missing_models+=("$model_name")
  fi
done

if [[ "${1:-}" != "--quiet" ]]; then
  # В обычном режиме печатаем итоговый GAZEBO_MODEL_PATH для диагностики.
  echo "GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH"
  if (( ${#missing_models[@]} > 0 )); then
    echo "Warning: missing Gazebo models: ${missing_models[*]}" >&2
    echo "Run: find ~/catkin_ws ~/scripts -path '*/model.config' | grep -E 'parquet_plane|aruco_cmit_txt'" >&2
  fi
fi
