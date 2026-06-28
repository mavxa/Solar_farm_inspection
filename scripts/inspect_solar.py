#!/usr/bin/env python3
"""Autonomous solar farm inspection mission for Clover/Gazebo."""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional

import cv2
import numpy as np
import rospy
from clover import srv
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image
from std_srvs.srv import Trigger

CLASS_COLORS = {
    "contamination": (0, 255, 0),
    "indicator_orange": (0, 140, 255),
    "indicator_red": (0, 0, 255),
    "indicator_yellow": (0, 255, 255),
    "solar_panel": (255, 160, 0),
}

STATE_BY_INDICATOR = {
    "indicator_yellow": "normal",
    "indicator_orange": "non_critical_overheat",
    "indicator_red": "urgent_repair",
}

LED_BY_STATE = {
    "moving": (255, 255, 255),
    "normal": (255, 255, 0),
    "non_critical_overheat": (255, 140, 0),
    "urgent_repair": (255, 0, 0),
    "unknown": (255, 255, 255),
}


@dataclass
class Detection:
    class_name: str
    confidence: float
    xyxy: tuple[int, int, int, int]


@dataclass
class InspectionResult:
    panel_index: int
    x: float
    y: float
    state: str
    contamination_count: int
    panel_detected: bool


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


class CameraBuffer:
    def __init__(self, topic: str) -> None:
        self.bridge = CvBridge()
        self.lock = Lock()
        self.frame = None
        self.stamp = None
        self.subscriber = rospy.Subscriber(topic, Image, self._on_image, queue_size=1)

    def _on_image(self, msg: Image) -> None:
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except CvBridgeError as exc:
            rospy.logwarn("Image conversion failed: %s", exc)
            return

        with self.lock:
            self.frame = frame
            self.stamp = msg.header.stamp if msg.header.stamp else rospy.Time.now()

    def wait_for_frame(self, timeout: float) -> None:
        deadline = time.time() + timeout
        rate = rospy.Rate(20)
        while not rospy.is_shutdown() and time.time() < deadline:
            with self.lock:
                if self.frame is not None:
                    return
            rate.sleep()
        raise RuntimeError("No image frames received. Check --image-topic.")

    def latest(self) -> Optional[np.ndarray]:
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()


class SolarInspector:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.camera = CameraBuffer(args.image_topic)
        self.bridge = CvBridge()
        self.solar_pub = rospy.Publisher(args.output_topic, Image, queue_size=1)

        try:
            from ultralytics import YOLO
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "ultralytics is not installed in this Python environment"
            ) from exc

        self.model = YOLO(str(args.model))
        self.class_names = self._load_class_names()

        self.get_telemetry = rospy.ServiceProxy("get_telemetry", srv.GetTelemetry)
        self.navigate = rospy.ServiceProxy("navigate", srv.Navigate)
        self.land = rospy.ServiceProxy("land", Trigger)
        self.set_effect = None

        try:
            self.set_effect = rospy.ServiceProxy("led/set_effect", srv.SetLEDEffect)
            rospy.wait_for_service("led/set_effect", timeout=2.0)
        except Exception as exc:
            self.set_effect = None
            rospy.logwarn("LED service is unavailable: %s", exc)

    def _load_class_names(self) -> dict[int, str]:
        names = self.model.names
        if isinstance(names, dict):
            return {int(key): str(value) for key, value in names.items()}
        return {index: str(value) for index, value in enumerate(names)}

    def set_led(self, state: str) -> None:
        if self.set_effect is None:
            return
        r, g, b = LED_BY_STATE.get(state, LED_BY_STATE["unknown"])
        try:
            self.set_effect(effect="fill", r=r, g=g, b=b)
        except Exception as exc:
            rospy.logwarn("Failed to set LED: %s", exc)

    def navigate_wait(
        self,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        yaw: float = float("nan"),
        frame_id: str = "body",
        auto_arm: bool = False,
    ) -> None:
        response = self.navigate(
            x=x,
            y=y,
            z=z,
            yaw=yaw,
            speed=self.args.speed,
            frame_id=frame_id,
            auto_arm=auto_arm,
        )
        if not response.success:
            raise RuntimeError(response.message)

        deadline = time.time() + self.args.navigate_timeout
        rate = rospy.Rate(5)
        while not rospy.is_shutdown():
            telem = self.get_telemetry(frame_id="navigate_target")
            distance = math.sqrt(telem.x**2 + telem.y**2 + telem.z**2)
            if distance < self.args.tolerance:
                return
            if time.time() > deadline:
                raise RuntimeError(
                    f"Navigation timeout, distance to target is {distance:.2f} m"
                )
            rate.sleep()

    def land_wait(self) -> None:
        self.land()
        rate = rospy.Rate(5)
        while not rospy.is_shutdown() and self.get_telemetry().armed:
            rate.sleep()

    def detect(self, frame: np.ndarray) -> list[Detection]:
        result = self.model(
            frame, imgsz=self.args.imgsz, conf=self.args.conf, verbose=False
        )[0]
        detections = []

        if result.boxes is None:
            return detections

        for box in result.boxes:
            class_id = int(box.cls.item())
            class_name = self.class_names.get(class_id, str(class_id))
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = [int(round(value)) for value in box.xyxy[0].tolist()]
            detections.append(
                Detection(
                    class_name=class_name, confidence=confidence, xyxy=(x1, y1, x2, y2)
                )
            )

        return detections

    def green_contours(self, frame: np.ndarray) -> list[np.ndarray]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([35, 60, 40], dtype=np.uint8)
        upper = np.array([90, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [
            contour
            for contour in contours
            if cv2.contourArea(contour) >= self.args.green_min_area
        ]

    def annotate(self, frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
        annotated = frame.copy()
        contours = self.green_contours(frame)
        cv2.drawContours(annotated, contours, -1, (0, 255, 0), 2)

        for detection in detections:
            x1, y1, x2, y2 = detection.xyxy
            color = CLASS_COLORS.get(detection.class_name, (255, 255, 255))
            label = f"{detection.class_name} {detection.confidence:.2f}"
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                annotated,
                label,
                (x1, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
            )

        return annotated

    def publish_annotated(self, annotated: np.ndarray) -> None:
        msg = self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8")
        msg.header.stamp = rospy.Time.now()
        self.solar_pub.publish(msg)

    def inspect_current_view(
        self, panel_index: int, target_x: float, target_y: float
    ) -> InspectionResult:
        deadline = time.time() + self.args.inspect_time
        next_process = 0.0

        contamination_counts = []
        indicator_scores: defaultdict[str, float] = defaultdict(float)
        panel_detected_votes = 0
        led_state_set = False

        while not rospy.is_shutdown() and time.time() < deadline:
            now = time.time()
            if now < next_process:
                rospy.sleep(0.03)
                continue

            frame = self.camera.latest()
            if frame is None:
                rospy.sleep(0.03)
                continue

            detections = self.detect(frame)
            annotated = self.annotate(frame, detections)
            self.publish_annotated(annotated)

            contamination_count = sum(
                1 for det in detections if det.class_name == "contamination"
            )
            contamination_counts.append(contamination_count)

            if any(det.class_name == "solar_panel" for det in detections):
                panel_detected_votes += 1

            for det in detections:
                if det.class_name in STATE_BY_INDICATOR:
                    indicator_scores[det.class_name] += det.confidence

            if indicator_scores and not led_state_set:
                best_indicator = max(indicator_scores, key=indicator_scores.get)
                self.set_led(STATE_BY_INDICATOR[best_indicator])
                led_state_set = True

            next_process = now + self.args.process_interval

        if indicator_scores:
            best_indicator = max(indicator_scores, key=indicator_scores.get)
            state = STATE_BY_INDICATOR[best_indicator]
        else:
            state = "unknown"

        self.set_led(state)

        if contamination_counts:
            contamination_count = int(max(contamination_counts))
        else:
            contamination_count = 0

        try:
            telemetry = self.get_telemetry(frame_id=self.args.frame_id)
            report_x = float(telemetry.x)
            report_y = float(telemetry.y)
        except Exception:
            report_x = target_x
            report_y = target_y

        panel_detected = panel_detected_votes > 0
        return InspectionResult(
            panel_index=panel_index,
            x=report_x,
            y=report_y,
            state=state,
            contamination_count=contamination_count,
            panel_detected=panel_detected,
        )

    def run(self) -> list[InspectionResult]:
        rospy.wait_for_service("get_telemetry")
        rospy.wait_for_service("navigate")
        rospy.wait_for_service("land")
        self.camera.wait_for_frame(timeout=10.0)

        waypoints = parse_waypoints(self.args.waypoints)
        print("Mission waypoints:")
        for index, (x, y) in enumerate(waypoints, start=1):
            print(
                f"  {index}. x={x:.2f}, y={y:.2f}, z={self.args.altitude:.2f}, frame={self.args.frame_id}"
            )

        results = []
        start_frame = self.args.frame_id

        self.set_led("moving")
        rospy.loginfo("Taking off")
        self.navigate_wait(z=self.args.takeoff_altitude, frame_id="body", auto_arm=True)

        try:
            for index, (x, y) in enumerate(waypoints, start=1):
                self.set_led("moving")
                rospy.loginfo(
                    "Navigate to panel %d: x=%.2f y=%.2f z=%.2f frame=%s",
                    index,
                    x,
                    y,
                    self.args.altitude,
                    start_frame,
                )
                self.navigate_wait(x=x, y=y, z=self.args.altitude, frame_id=start_frame)
                rospy.sleep(self.args.settle_time)

                result = self.inspect_current_view(index, x, y)
                print(
                    f"Solar panel #{result.panel_index}: "
                    f"{result.x:.2f} {result.y:.2f}, "
                    f"{result.state}, {result.contamination_count} contaminations"
                )
                results.append(result)

            self.set_led("moving")
            rospy.loginfo("Returning to start")
            self.navigate_wait(
                x=self.args.return_x,
                y=self.args.return_y,
                z=self.args.altitude,
                frame_id=start_frame,
            )
        finally:
            if not self.args.skip_land and not rospy.is_shutdown():
                rospy.loginfo("Landing")
                try:
                    self.land_wait()
                except Exception as exc:
                    rospy.logwarn("Landing failed: %s", exc)

        return results


def parse_waypoints(raw: str) -> list[tuple[float, float]]:
    waypoints = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.replace(",", " ").split()
        if len(parts) != 2:
            raise ValueError(f"Invalid waypoint: {chunk}")
        waypoints.append((float(parts[0]), float(parts[1])))
    if not waypoints:
        raise ValueError("No waypoints provided")
    return waypoints


def write_report(path: Path, results: list[InspectionResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for result in results:
        lines.append(
            f"Solar panel #{result.panel_index}: "
            f"coordinates {result.x:.2f} {result.y:.2f}, "
            f"{result.state}, {result.contamination_count} contaminations"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-topic", default="/main_camera/image_raw")
    parser.add_argument("--output-topic", default="/solar")
    parser.add_argument(
        "--model", type=Path, default=project_root / "weights" / "solar_yolov8n_best.pt"
    )
    parser.add_argument(
        "--report", type=Path, default=project_root / "reports" / "solar_report.txt"
    )
    parser.add_argument("--frame-id", default="map")
    parser.add_argument(
        "--waypoints", default="0.55,0.55;0.55,5.45;5.45,0.55;5.45,5.45;3.0,3.0"
    )
    parser.add_argument("--altitude", type=float, default=1.4)
    parser.add_argument("--takeoff-altitude", type=float, default=1.0)
    parser.add_argument("--return-x", type=float, default=0.0)
    parser.add_argument("--return-y", type=float, default=0.0)
    parser.add_argument("--speed", type=float, default=0.35)
    parser.add_argument("--tolerance", type=float, default=0.25)
    parser.add_argument("--navigate-timeout", type=float, default=45.0)
    parser.add_argument("--settle-time", type=float, default=0.7)
    parser.add_argument("--inspect-time", type=float, default=5.0)
    parser.add_argument("--process-interval", type=float, default=0.35)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--green-min-area", type=float, default=20.0)
    parser.add_argument("--skip-land", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_output_encoding()
    args = parse_args()
    rospy.init_node("solar_inspection")

    inspector = SolarInspector(args)
    results = inspector.run()
    write_report(args.report, results)
    print(f"Report saved: {args.report}")


if __name__ == "__main__":
    main()
