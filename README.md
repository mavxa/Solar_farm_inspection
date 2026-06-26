# Solar Farm Inspection

ROS/Gazebo solution workspace for the solar panel inspection task.

## Generate Gazebo World

The provided solar panel model is normalized under `models/solar_panel` and can be loaded as `model://solar_panel`.

Before launching Gazebo, add local models to Gazebo search path:

```bash
export GAZEBO_MODEL_PATH="$GAZEBO_MODEL_PATH:$PWD/models"
```

Generate a standalone world:

```bash
python3 scripts/generate_world.py --seed 42
```

This creates:

```text
worlds/generated_solar.world
worlds/generated_truth.json
```

If the simulator image already has a Clover/ArUco world, inject generated objects into it instead of replacing the base world:

```bash
python3 scripts/generate_world.py \
  --base-world /path/to/clover_aruco.world \
  --output worlds/generated_solar.world
```

`generated_truth.json` is only for debugging. Mission/recognition code must not read it during evaluation.
