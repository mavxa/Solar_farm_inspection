#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ACTION="${1:-install}"
WORLD_NAME="${2:-clover_aruco.world}"
GENERATED_WORLD="$PROJECT_ROOT/worlds/generated_solar.world"

find_clover_simulation() {
  if command -v rospack >/dev/null 2>&1; then
    local rospack_path
    rospack_path="$(rospack find clover_simulation 2>/dev/null || true)"
    if [[ -n "$rospack_path" && -d "$rospack_path" ]]; then
      echo "$rospack_path"
      return 0
    fi
  fi

  for candidate in \
    "$HOME/catkin_ws/src/clover/clover_simulation" \
    "$HOME/catkin_ws/install/share/clover_simulation"; do
    if [[ -d "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

usage() {
  cat <<EOF
Usage: $0 [install|restore|status] [world_name]

Default world_name: clover_aruco.world

install: replace Clover world with worlds/generated_solar.world
restore: restore original Clover world from backup
status:  show target and backup paths
EOF
}

case "$ACTION" in
  -h|--help|help)
    usage
    exit 0
    ;;
esac

CLOVER_SIMULATION_PATH="$(find_clover_simulation || true)"
if [[ -z "$CLOVER_SIMULATION_PATH" ]]; then
  echo "clover_simulation package not found." >&2
  exit 1
fi

TARGET_WORLD="$CLOVER_SIMULATION_PATH/resources/worlds/$WORLD_NAME"
BACKUP_WORLD="$TARGET_WORLD.before_solar.bak"

case "$ACTION" in
  install)
    if [[ ! -f "$GENERATED_WORLD" ]]; then
      echo "Generated world not found: $GENERATED_WORLD" >&2
      echo "Run scripts/generate_from_clover_world.sh first." >&2
      exit 1
    fi
    if [[ ! -f "$TARGET_WORLD" ]]; then
      echo "Target Clover world not found: $TARGET_WORLD" >&2
      exit 1
    fi
    if [[ ! -f "$BACKUP_WORLD" ]]; then
      cp "$TARGET_WORLD" "$BACKUP_WORLD"
      echo "Backup created: $BACKUP_WORLD"
    else
      echo "Backup already exists: $BACKUP_WORLD"
    fi
    cp "$GENERATED_WORLD" "$TARGET_WORLD"
    echo "Installed solar world: $TARGET_WORLD"
    ;;
  restore)
    if [[ ! -f "$BACKUP_WORLD" ]]; then
      echo "Backup not found: $BACKUP_WORLD" >&2
      exit 1
    fi
    cp "$BACKUP_WORLD" "$TARGET_WORLD"
    echo "Restored original world: $TARGET_WORLD"
    ;;
  status)
    echo "Clover simulation: $CLOVER_SIMULATION_PATH"
    echo "Target world:      $TARGET_WORLD"
    echo "Backup world:      $BACKUP_WORLD"
    echo "Generated world:   $GENERATED_WORLD"
    if [[ -f "$TARGET_WORLD" && -f "$GENERATED_WORLD" ]] && cmp -s "$TARGET_WORLD" "$GENERATED_WORLD"; then
      echo "State: solar world is installed"
    else
      echo "State: solar world is not installed or differs"
    fi
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
