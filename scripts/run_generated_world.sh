#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/setup_gazebo_env.sh" --quiet

for model_name in parquet_plane aruco_cmit_txt solar_panel; do
  if [[ ! -f "$PROJECT_ROOT/models/$model_name/model.config" ]]; then
    found=0
    IFS=":" read -r -a gazebo_paths <<< "${GAZEBO_MODEL_PATH:-}"
    for root in "${gazebo_paths[@]}"; do
      if [[ -f "$root/$model_name/model.config" ]]; then
        found=1
        break
      fi
    done
    if [[ "$found" == 0 ]]; then
      echo "Missing Gazebo model: $model_name" >&2
      echo "GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH" >&2
      exit 1
    fi
  fi
done

exec gazebo --verbose "$PROJECT_ROOT/worlds/generated_solar.world"
