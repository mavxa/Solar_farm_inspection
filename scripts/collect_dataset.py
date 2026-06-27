#!/usr/bin/env python3
"""Collect camera frames for the solar farm dataset in Clover/Gazebo.

This script is for dataset collection only. It may use generated_truth.json to
visit generated panel positions. Do not use generated_truth.json in the final
inspection/recognition mission code.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path
from threading import Lock

import cv2
import rospy
from clover import srv
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image
from std_srvs.srv import Trigger


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


class FrameCollector:
    def __init__(self, image_topic: str, output_dir: Path, jpeg_quality: int) -> None:
        self.bridge = CvBridge()
        self.output_dir = output_dir
        self.jpeg_quality = jpeg_quality
        self.lock = Lock()
        self.latest_frame = None
        self.latest_stamp = None
        self.saved_count = 0

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.subscriber = rospy.Subscriber(image_topic, Image, self._on_image, queue_size=1)

    def _on_image(self, msg: Image) -> None:
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except CvBridgeError as exc:
            rospy.logwarn("Failed to convert image: %s", exc)
            return

        with self.lock:
            self.latest_frame = frame
            self.latest_stamp = msg.header.stamp if msg.header.stamp else rospy.Time.now()

    def wait_for_frame(self, timeout: float) -> None:
        deadline = time.time() + timeout
        rate = rospy.Rate(20)
        while not rospy.is_shutdown() and time.time() < deadline:
            with self.lock:
                if self.latest_frame is not None:
                    return
            rate.sleep()
        raise RuntimeError("No camera frames received. Check --image-topic.")

    def save_latest(self, label: str) -> Path | None:
        with self.lock:
            if self.latest_frame is None:
                return None
            frame = self.latest_frame.copy()
            stamp = self.latest_stamp.to_nsec() if self.latest_stamp else rospy.Time.now().to_nsec()

        safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_") or "frame"
        next_count = self.saved_count + 1
        filename = f"{next_count:06d}_{safe_label}_{stamp}.jpg"
        path = self.output_dir / filename
        ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not ok:
            rospy.logwarn("Failed to write image: %s", path)
            return None
        self.saved_count = next_count
        return path


def navigate_wait(
    navigate,
    get_telemetry,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    yaw: float = float("nan"),
    speed: float = 0.5,
    frame_id: str = "body",
    auto_arm: bool = False,
    tolerance: float = 0.2,
) -> None:
    res = navigate(
        x=x,
        y=y,
        z=z,
        yaw=yaw,
        speed=speed,
        frame_id=frame_id,
        auto_arm=auto_arm,
    )
    if not res.success:
        raise RuntimeError(res.message)

    rate = rospy.Rate(5)
    while not rospy.is_shutdown():
        telem = get_telemetry(frame_id="navigate_target")
        distance = math.sqrt(telem.x**2 + telem.y**2 + telem.z**2)
        if distance < tolerance:
            return
        rate.sleep()


def land_wait(land, get_telemetry) -> None:
    land()
    rate = rospy.Rate(5)
    while not rospy.is_shutdown() and get_telemetry().armed:
        rate.sleep()


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def load_panel_waypoints(args: argparse.Namespace) -> list[tuple[str, float, float, float]]:
    truth_path = args.truth
    data = json.loads(truth_path.read_text(encoding="utf-8"))
    waypoints: list[tuple[str, float, float, float]] = []

    offsets = [(0.0, 0.0)]
    if args.include_offset_views:
        offset = args.view_offset
        offsets.extend([(offset, 0.0), (-offset, 0.0), (0.0, offset), (0.0, -offset)])

    for panel in data.get("panels", []):
        index = int(panel["index"])
        x = float(panel["x"])
        y = float(panel["y"])
        for offset_index, (dx, dy) in enumerate(offsets):
            target_x = clamp(x + dx, args.safe_min_x, args.safe_max_x)
            target_y = clamp(y + dy, args.safe_min_y, args.safe_max_y)
            waypoints.append((f"panel_{index}_view_{offset_index}", target_x, target_y, args.altitude))

    if not waypoints:
        raise RuntimeError(f"No panels found in truth file: {truth_path}")
    return waypoints


def make_grid_waypoints(args: argparse.Namespace) -> list[tuple[str, float, float, float]]:
    waypoints = []
    index = 1
    x = args.grid_min_x
    while x <= args.grid_max_x + 1e-9:
        y = args.grid_min_y
        while y <= args.grid_max_y + 1e-9:
            waypoints.append((f"grid_{index}", x, y, args.altitude))
            index += 1
            y += args.grid_step
        x += args.grid_step
    return waypoints


def log_waypoints(waypoints: list[tuple[str, float, float, float]], frame_id: str) -> None:
    print(f"Planned waypoints in frame '{frame_id}':")
    for index, (label, x, y, z) in enumerate(waypoints, start=1):
        print(f"  {index:02d}. {label}: x={x:.2f}, y={y:.2f}, z={z:.2f}")


def capture_during_dwell(collector: FrameCollector, label: str, dwell: float, interval: float) -> None:
    deadline = time.time() + dwell
    next_capture = 0.0
    while not rospy.is_shutdown() and time.time() < deadline:
        now = time.time()
        if now >= next_capture:
            path = collector.save_latest(label)
            if path:
                rospy.loginfo("Saved %s", path)
            next_capture = now + interval
        rospy.sleep(0.05)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-topic", default="/main_camera/image_raw")
    parser.add_argument("--output-dir", type=Path, default=project_root / "dataset" / "raw")
    parser.add_argument("--truth", type=Path, default=project_root / "worlds" / "generated_truth.json")
    parser.add_argument("--mode", choices=("panels", "grid"), default="panels")
    parser.add_argument("--frame-id", default="map")
    parser.add_argument("--altitude", type=float, default=1.4)
    parser.add_argument("--speed", type=float, default=0.35)
    parser.add_argument("--takeoff-altitude", type=float, default=1.0)
    parser.add_argument("--dwell", type=float, default=3.0)
    parser.add_argument("--capture-interval", type=float, default=0.5)
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--include-offset-views", action="store_true")
    parser.add_argument("--view-offset", type=float, default=0.2)
    parser.add_argument("--safe-min-x", type=float, default=0.45)
    parser.add_argument("--safe-max-x", type=float, default=5.55)
    parser.add_argument("--safe-min-y", type=float, default=0.45)
    parser.add_argument("--safe-max-y", type=float, default=5.55)
    parser.add_argument("--skip-flight", action="store_true", help="Only save frames from the current camera topic.")
    parser.add_argument("--skip-land", action="store_true")
    parser.add_argument("--max-waypoints", type=int, default=0, help="Limit visited waypoints; 0 means no limit.")
    parser.add_argument("--grid-min-x", type=float, default=0.5)
    parser.add_argument("--grid-max-x", type=float, default=5.5)
    parser.add_argument("--grid-min-y", type=float, default=0.5)
    parser.add_argument("--grid-max-y", type=float, default=5.5)
    parser.add_argument("--grid-step", type=float, default=1.25)
    return parser.parse_args()


def main() -> None:
    configure_output_encoding()
    args = parse_args()

    rospy.init_node("solar_dataset_collector")
    collector = FrameCollector(args.image_topic, args.output_dir, args.jpeg_quality)
    collector.wait_for_frame(timeout=10.0)

    if args.skip_flight:
        rospy.loginfo("Skipping flight; collecting frames in place.")
        capture_during_dwell(collector, "static", args.dwell, args.capture_interval)
        rospy.loginfo("Saved %d frames to %s", collector.saved_count, args.output_dir)
        return

    rospy.wait_for_service("get_telemetry")
    rospy.wait_for_service("navigate")
    rospy.wait_for_service("land")

    get_telemetry = rospy.ServiceProxy("get_telemetry", srv.GetTelemetry)
    navigate = rospy.ServiceProxy("navigate", srv.Navigate)
    land = rospy.ServiceProxy("land", Trigger)

    if args.mode == "panels":
        waypoints = load_panel_waypoints(args)
    else:
        waypoints = make_grid_waypoints(args)

    if args.max_waypoints > 0:
        waypoints = waypoints[: args.max_waypoints]

    log_waypoints(waypoints, args.frame_id)

    rospy.loginfo("Taking off")
    navigate_wait(
        navigate,
        get_telemetry,
        z=args.takeoff_altitude,
        frame_id="body",
        speed=args.speed,
        auto_arm=True,
    )

    try:
        for label, x, y, z in waypoints:
            rospy.loginfo("Navigate to %s: x=%.2f y=%.2f z=%.2f frame=%s", label, x, y, z, args.frame_id)
            navigate_wait(navigate, get_telemetry, x=x, y=y, z=z, frame_id=args.frame_id, speed=args.speed)
            capture_during_dwell(collector, label, args.dwell, args.capture_interval)
    except rospy.ROSInterruptException:
        rospy.logwarn("Interrupted by ROS shutdown")
    finally:
        if not args.skip_land and not rospy.is_shutdown():
            rospy.loginfo("Landing")
            try:
                land_wait(land, get_telemetry)
            except Exception as exc:
                rospy.logwarn("Landing failed: %s", exc)

    rospy.loginfo("Saved %d frames to %s", collector.saved_count, args.output_dir)


if __name__ == "__main__":
    main()
