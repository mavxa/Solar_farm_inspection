#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_MODEL="$PROJECT_ROOT/models/solar_panel"
TARGET_ROOT="${GAZEBO_USER_MODEL_PATH:-$HOME/.gazebo/models}"
TARGET_MODEL="$TARGET_ROOT/solar_panel"

# Gazebo ждёт model.config и model.sdf; без них model://solar_panel не загрузится.
if [[ ! -f "$SOURCE_MODEL/model.config" || ! -f "$SOURCE_MODEL/model.sdf" ]]; then
  echo "solar_panel model is not valid: $SOURCE_MODEL" >&2
  exit 1
fi

mkdir -p "$TARGET_ROOT"

if [[ -L "$TARGET_MODEL" ]]; then
  # Если ссылка уже правильная, второй запуск скрипта ничего не меняет.
  current_target="$(readlink "$TARGET_MODEL")"
  if [[ "$current_target" == "$SOURCE_MODEL" ]]; then
    echo "Gazebo model symlink already installed: $TARGET_MODEL -> $SOURCE_MODEL"
    exit 0
  fi
  echo "Replacing existing symlink: $TARGET_MODEL -> $current_target"
  rm "$TARGET_MODEL"
elif [[ -e "$TARGET_MODEL" ]]; then
  # Чужую модель не удаляем: переносим в backup рядом.
  backup="$TARGET_MODEL.backup.$(date +%Y%m%d_%H%M%S)"
  mv "$TARGET_MODEL" "$backup"
  echo "Existing model moved to backup: $backup"
fi

ln -s "$SOURCE_MODEL" "$TARGET_MODEL"
echo "Installed Gazebo model symlink: $TARGET_MODEL -> $SOURCE_MODEL"
