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

## Train YOLO

The trained detector is stored at:

```text
weights/solar_yolov8n_best.pt
```

Training helper:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip ultralytics
python scripts/train_yolo.py
```

## Run Inspection Mission In Clover VM

Create a ROS-compatible Python environment that can import both ROS packages and Ultralytics:

```bash
cd ~/scripts/Solar_farm_inspection
python3 -m venv --system-site-packages .venv_ros
source .venv_ros/bin/activate
pip install -U pip ultralytics
```

Run Clover/Gazebo first, then start the mission:

```bash
source .venv_ros/bin/activate
python scripts/inspect_solar.py \
  --image-topic /main_camera/image_raw \
  --model weights/solar_yolov8n_best.pt \
  --output-topic /solar \
  --report reports/solar_report.txt \
  --frame-id map
```

The mission publishes annotated images to `/solar` and writes `reports/solar_report.txt`.
