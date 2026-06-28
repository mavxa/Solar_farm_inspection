# Solar Farm Inspection

## Demo

- Watch: https://rutube.ru/video/private/9a565140615dd2a88e00a43022babae3/?p=D9bHZGmMB7lim2hGRaDhrQ
- Download: https://drive.google.com/file/d/1Ud2coed4hlWKt3O1LneeI_CeDVL_ZYq8/view?usp=sharing

The video is stored externally because GitHub rejects files larger than 100 MB without Git LFS.

ROS/Gazebo solution for the solar farm inspection qualification task: Gazebo world generation, autonomous Clover flight, YOLO-based panel inspection, `/solar` image publication, LED indication, and report generation.

Russian version: [`README.md`](README.md).

## What This Solution Does

- Generates a Gazebo world based on the standard Clover ArUco world.
- Places 5 solar panels inside the ArUco field.
- Places yellow/orange/red status indicators near panels.
- Places 2-5 green contamination objects on each panel.
- Runs an autonomous 5-panel inspection mission.
- Detects `solar_panel`, `contamination`, `indicator_yellow`, `indicator_orange`, `indicator_red` with YOLOv8n.
- Publishes annotated `sensor_msgs/Image` frames to `/solar`.
- Prints recognized results to the terminal.
- Saves `reports/solar_report.txt`.
- Uses `led/set_effect` for LED indication when the service is available.

## Repository Layout

```text
docs/                         task PDF
models/solar_panel/            Gazebo solar panel model
scripts/generate_world.py      world generator
scripts/inspect_solar.py       autonomous mission
scripts/use_solar_world.sh     installs generated world as Clover world
scripts/install_gazebo_models.sh installs solar_panel into Gazebo model path
weights/solar_yolov8n_best.pt  trained YOLOv8n weights
worlds/generated_solar.world   generated world
README.md                      Russian instructions
```

## Requirements

- ROS Noetic / ROS1 in a Clover image.
- Gazebo 11.
- Working Clover simulation with an ArUco world.
- Python 3.8 inside the VM.
- Internet access for the first Python dependency installation.

The solution was tested in a Clover VM running through QEMU/KVM.

## Fresh Installation

Clone the repository:

```bash
cd ~/scripts
git clone https://github.com/mavxa/Solar_farm_inspectio.git Solar_farm_inspection
cd Solar_farm_inspection
```

Or with SSH:

```bash
cd ~/scripts
git clone git@github.com:mavxa/Solar_farm_inspectio.git Solar_farm_inspection
cd Solar_farm_inspection
```

Make scripts executable:

```bash
chmod +x scripts/*.py scripts/*.sh
```

Source ROS:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash 2>/dev/null || source ~/catkin_ws/install/setup.bash
```

Create a Python environment. `--system-site-packages` is required so the venv can import ROS packages such as `rospy`, `cv_bridge`, and `clover`.

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -U pip
```

Install CPU-only PyTorch. This avoids downloading multi-gigabyte CUDA/NVIDIA packages on a VM without NVIDIA GPU.

```bash
pip install torch==2.4.1+cpu torchvision==0.19.1+cpu \
  --index-url https://download.pytorch.org/whl/cpu
```

Install Ultralytics and runtime dependencies:

```bash
pip install ultralytics==8.4.80 --no-deps
pip install numpy==1.24.4 opencv-python-headless pillow matplotlib psutil requests polars ultralytics-thop
```

Check the environment:

```bash
python - <<'PY'
import torch
import ultralytics
import cv2
import rospy
print('torch:', torch.__version__)
print('cuda:', torch.cuda.is_available())
print('ultralytics:', ultralytics.__version__)
print('cv2:', cv2.__version__)
print('rospy: ok')
PY
```

Expected: `cuda: False`.

## Gazebo Model Setup

Install the local solar panel model into Gazebo's user model path:

```bash
scripts/install_gazebo_models.sh
```

It creates:

```text
~/.gazebo/models/solar_panel -> ~/scripts/Solar_farm_inspection/models/solar_panel
```

## World Generation

Generate a random world based on Clover's ArUco world:

```bash
python3 scripts/generate_world.py \
  --base-world ~/scripts/basic_worlds/worlds/clover_aruco.world \
  --output worlds/generated_solar.world \
  --truth-output worlds/generated_truth.json \
  --contamination-length 0.20 \
  --contamination-width 0.07 \
  --contamination-gap 0.05
```

If `~/scripts/basic_worlds/worlds/clover_aruco.world` is not available, use the Clover package world:

```bash
python3 scripts/generate_world.py \
  --base-world ~/catkin_ws/src/clover/clover_simulation/resources/worlds/clover_aruco.world \
  --output worlds/generated_solar.world \
  --truth-output worlds/generated_truth.json
```

Do not pass `--seed` when demonstrating random generation. The script prints the generated seed and panel data.

As a fallback, the repository already includes a ready-to-use `worlds/generated_solar.world`. If generation fails on a specific VM because of Clover paths or a missing base world file, you can skip generation and install the prepared world with `scripts/use_solar_world.sh install`.

`generated_truth.json` is for debugging only. The mission script does not read it.

## Install Generated World Into Clover

```bash
scripts/use_solar_world.sh install
```

Check status:

```bash
scripts/use_solar_world.sh status
```

Restore the original Clover world:

```bash
scripts/use_solar_world.sh restore
```

## Run Simulation

Start Clover/Gazebo with the launch file used by your image for ArUco navigation. Example:

```bash
roslaunch clover_simulation simulator.launch
```

Check required services:

```bash
rosservice list | grep -E 'navigate|get_telemetry|land'
```

Check camera topics:

```bash
rostopic list | grep -i image
```

The default camera topic used by the mission is:

```text
/main_camera/image_raw
```

## Run Autonomous Mission

In a separate terminal:

```bash
cd ~/scripts/Solar_farm_inspection
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash 2>/dev/null || source ~/catkin_ws/install/setup.bash
source .venv/bin/activate
```

Start the mission:

```bash
python scripts/inspect_solar.py \
  --image-topic /main_camera/image_raw \
  --model weights/solar_yolov8n_best.pt \
  --output-topic /solar \
  --report reports/solar_report.txt \
  --frame-id map
```

The mission takes off, visits all 5 panels, inspects each panel for about 5 seconds, publishes annotated frames to `/solar`, sets the LED color, prints results, returns, lands, and writes a report.

Check `/solar`:

```bash
rostopic hz /solar
```

Read the report:

```bash
cat reports/solar_report.txt
```

## Report Format

Example:

```text
Solar panel #1: coordinates 0.55 0.55, normal, 3 contaminations
Solar panel #2: coordinates 0.55 5.45, urgent_repair, 4 contaminations
```

The report uses ASCII text to avoid Clover VM locale issues.

## Trained Model

The detector is YOLOv8n, selected because it is fast enough for CPU/VM inference.

Weights:

```text
weights/solar_yolov8n_best.pt
```

Classes:

```text
contamination
indicator_orange
indicator_red
indicator_yellow
solar_panel
```

Metrics:

```text
Validation: mAP50 0.967, mAP50-95 0.891
Test:       mAP50 0.949, mAP50-95 0.919
```

## Retraining

```bash
source .venv/bin/activate
python scripts/train_yolo.py \
  --data dataset/lm/gazeboSolars.v1-gazebosolars.yolov8/data.yaml \
  --model yolov8n.pt \
  --epochs 100 \
  --batch 8 \
  --imgsz 640 \
  --device cpu
```

Best weights will be saved to:

```text
runs/detect/solar_yolov8n/weights/best.pt
```

## Demo Video

The demo video is available through the links at the top of this README.

The competition video should show Gazebo, the mission terminal, `/solar`, and `reports/solar_report.txt`.

## Troubleshooting

If colored boxes are visible but solar panel meshes are missing:

```bash
scripts/install_gazebo_models.sh
```

If Gazebo cannot find `parquet_plane` or `aruco_cmit_txt`:

```bash
source scripts/setup_gazebo_env.sh
```

If CUDA packages filled the disk during `pip install ultralytics`:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
rm -rf ~/.cache/pip
```

Then install CPU-only PyTorch as described above.

If `aruco_map -> map` transform is unavailable, use:

```bash
--frame-id map
```

This is already used in the default mission command.
