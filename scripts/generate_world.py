#!/usr/bin/env python3
"""Generate a Gazebo world for the solar farm inspection task.

The script can either create a standalone world or inject generated task objects
into an existing Clover/ArUco world via --base-world. Use the second mode when
the simulator image already has a correct ArUco field and Clover setup.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

COLOR_TABLE = {
    "yellow": {
        "state": "normal",
        "rgba": "1.0 0.85 0.0 1.0",
    },
    "orange": {
        "state": "non_critical_overheat",
        "rgba": "1.0 0.35 0.0 1.0",
    },
    "red": {
        "state": "urgent_repair",
        "rgba": "1.0 0.0 0.0 1.0",
    },
    "green": {
        "state": "contamination",
        "rgba": "0.0 1.0 0.0 1.0",
    },
}


@dataclass
class Contamination:
    x: float
    y: float
    yaw: float


@dataclass
class Panel:
    index: int
    x: float
    y: float
    yaw: float
    indicator_color: str
    indicator_x: float
    indicator_y: float
    contaminations: list[Contamination]


def fmt(value: float) -> str:
    return f"{value:.3f}"


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def rotate(dx: float, dy: float, yaw: float) -> tuple[float, float]:
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return dx * cos_yaw - dy * sin_yaw, dx * sin_yaw + dy * cos_yaw


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def is_valid_position(
    candidate: tuple[float, float],
    positions: list[tuple[float, float]],
    min_center_distance: float,
) -> bool:
    return all(distance(candidate, pos) >= min_center_distance for pos in positions)


def generate_positions(
    args: argparse.Namespace, rng: random.Random
) -> list[tuple[float, float]]:
    # Use the panel bounding square diagonal as a conservative footprint. This
    # keeps the required edge gap even when panels are compared diagonally.
    min_center_distance = args.min_edge_gap + args.panel_size * math.sqrt(2.0)
    margin = args.panel_size / 2.0 + 0.05
    low = margin
    high = args.map_span - margin
    center = args.map_span / 2.0

    anchors = [
        (low, low),
        (low, high),
        (high, low),
        (high, high),
        (center, center),
    ]

    positions: list[tuple[float, float]] = []
    if args.panels <= len(anchors):
        for _ in range(500):
            candidates: list[tuple[float, float]] = []
            for anchor_x, anchor_y in anchors[: args.panels]:
                jitter_x = rng.uniform(-args.position_jitter, args.position_jitter)
                jitter_y = rng.uniform(-args.position_jitter, args.position_jitter)
                candidate = (
                    min(max(anchor_x + jitter_x, low), high) + args.x_offset,
                    min(max(anchor_y + jitter_y, low), high) + args.y_offset,
                )
                if not is_valid_position(candidate, candidates, min_center_distance):
                    break
                candidates.append(candidate)
            if len(candidates) == args.panels:
                return candidates

        positions = [
            (x + args.x_offset, y + args.y_offset) for x, y in anchors[: args.panels]
        ]
        for index, selected in enumerate(positions):
            if not is_valid_position(selected, positions[:index], min_center_distance):
                raise RuntimeError(
                    "Cannot place panels with current panel size/min gap/map span settings. "
                    "Try reducing --position-jitter or --min-edge-gap, or increasing --map-span."
                )
        return positions

    for _ in range(20_000):
        candidate = (
            rng.uniform(low, high) + args.x_offset,
            rng.uniform(low, high) + args.y_offset,
        )
        if is_valid_position(candidate, positions, min_center_distance):
            positions.append(candidate)
            if len(positions) == args.panels:
                return positions

    raise RuntimeError(
        "Failed to randomly place all panels. Increase --map-span or lower --min-edge-gap."
    )


def make_panels(args: argparse.Namespace, rng: random.Random) -> list[Panel]:
    positions = generate_positions(args, rng)
    panels: list[Panel] = []
    colors = ["yellow", "orange", "red"]

    for index, (x, y) in enumerate(positions, start=1):
        yaw = (
            rng.choice([0.0, math.pi / 2.0, math.pi, -math.pi / 2.0])
            if args.random_yaw
            else 0.0
        )
        indicator_color = rng.choice(colors)

        indicator_side = -1.0 if x > args.x_offset + args.map_span / 2.0 else 1.0
        indicator_dx, indicator_dy = rotate(
            indicator_side * args.indicator_offset, 0.0, yaw
        )
        indicator_x = x + indicator_dx
        indicator_y = y + indicator_dy

        contaminations = []
        for _ in range(rng.randint(args.min_contaminations, args.max_contaminations)):
            local_x = rng.uniform(
                -args.contamination_area / 2.0, args.contamination_area / 2.0
            )
            local_y = rng.uniform(
                -args.contamination_area / 2.0, args.contamination_area / 2.0
            )
            world_dx, world_dy = rotate(local_x, local_y, yaw)
            contaminations.append(
                Contamination(
                    x=x + world_dx,
                    y=y + world_dy,
                    yaw=yaw + rng.uniform(-0.8, 0.8),
                )
            )

        panels.append(
            Panel(
                index=index,
                x=x,
                y=y,
                yaw=yaw,
                indicator_color=indicator_color,
                indicator_x=indicator_x,
                indicator_y=indicator_y,
                contaminations=contaminations,
            )
        )

    return panels


def box_model(
    name: str,
    pose: str,
    size: str,
    rgba: str,
    collide: bool = True,
) -> str:
    collision = ""
    if collide:
        collision = f"""
      <collision name=\"collision\">
        <geometry>
          <box>
            <size>{size}</size>
          </box>
        </geometry>
      </collision>"""

    return f"""
    <model name=\"{name}\">
      <static>true</static>
      <pose>{pose}</pose>
      <link name=\"link\">
        <visual name=\"visual\">
          <geometry>
            <box>
              <size>{size}</size>
            </box>
          </geometry>
          <material>
            <ambient>{rgba}</ambient>
            <diffuse>{rgba}</diffuse>
          </material>
        </visual>{collision}
      </link>
    </model>"""


def render_task_models(panels: list[Panel], args: argparse.Namespace) -> str:
    chunks = ["\n    <!-- Generated solar farm inspection objects. -->"]

    for panel in panels:
        chunks.append(
            f"""
    <include>
      <name>solar_panel_{panel.index}</name>
      <uri>model://solar_panel</uri>
      <pose>{fmt(panel.x)} {fmt(panel.y)} {fmt(args.panel_z)} 0 0 {fmt(panel.yaw)}</pose>
    </include>"""
        )

        color = COLOR_TABLE[panel.indicator_color]
        chunks.append(
            box_model(
                name=f"solar_panel_{panel.index}_indicator_{panel.indicator_color}",
                pose=(
                    f"{fmt(panel.indicator_x)} {fmt(panel.indicator_y)} "
                    f"{fmt(args.indicator_z)} 0 0 {fmt(panel.yaw)}"
                ),
                size=f"{args.indicator_size} {args.indicator_size} {args.indicator_height}",
                rgba=color["rgba"],
            )
        )

        for contamination_index, contamination in enumerate(
            panel.contaminations, start=1
        ):
            chunks.append(
                box_model(
                    name=f"solar_panel_{panel.index}_contamination_{contamination_index}",
                    pose=(
                        f"{fmt(contamination.x)} {fmt(contamination.y)} "
                        f"{fmt(args.contamination_z)} 0 0 {fmt(contamination.yaw)}"
                    ),
                    size=(
                        f"{args.contamination_length} {args.contamination_width} "
                        f"{args.contamination_height}"
                    ),
                    rgba=COLOR_TABLE["green"]["rgba"],
                )
            )

    chunks.append("    <!-- End generated solar farm inspection objects. -->\n")
    return "\n".join(chunks)


def render_standalone_world(task_models: str) -> str:
    return f"""<?xml version=\"1.0\" ?>
<sdf version=\"1.6\">
  <world name=\"solar_farm_inspection\">
    <include>
      <uri>model://sun</uri>
    </include>
    <include>
      <uri>model://ground_plane</uri>
    </include>
{task_models}
  </world>
</sdf>
"""


def inject_into_base_world(base_world: Path, task_models: str) -> str:
    content = base_world.read_text(encoding="utf-8")
    marker = "</world>"
    if marker not in content:
        raise RuntimeError(f"Base world does not contain {marker}: {base_world}")
    return content.replace(marker, f"{task_models}\n  {marker}", 1)


def write_truth(
    path: Path, panels: list[Panel], args: argparse.Namespace, seed: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": seed,
        "note": "Debug truth only. Mission recognition code must not read this file.",
        "panel_size_assumption_m": args.panel_size,
        "min_edge_gap_m": args.min_edge_gap,
        "panels": [],
    }

    for panel in panels:
        data = asdict(panel)
        data["state"] = COLOR_TABLE[panel.indicator_color]["state"]
        data["contamination_count"] = len(panel.contaminations)
        payload["panels"].append(data)

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-world",
        type=Path,
        help="Existing Clover/ArUco world to inject objects into.",
    )
    parser.add_argument(
        "--output", type=Path, default=project_root / "worlds" / "generated_solar.world"
    )
    parser.add_argument(
        "--truth-output",
        type=Path,
        default=project_root / "worlds" / "generated_truth.json",
    )
    parser.add_argument("--seed", type=int, default=None)

    parser.add_argument("--panels", type=int, default=5)
    parser.add_argument(
        "--map-span",
        type=float,
        default=6.0,
        help="ArUco map span in meters, usually 6 for 7 markers at 1m spacing.",
    )
    parser.add_argument("--x-offset", type=float, default=0.0)
    parser.add_argument("--y-offset", type=float, default=0.0)
    parser.add_argument("--panel-size", type=float, default=1.0)
    parser.add_argument("--min-edge-gap", type=float, default=2.0)
    parser.add_argument("--position-jitter", type=float, default=0.08)
    parser.add_argument("--random-yaw", action="store_true")

    parser.add_argument("--panel-z", type=float, default=0.0)
    parser.add_argument("--indicator-offset", type=float, default=0.78)
    parser.add_argument("--indicator-size", type=float, default=0.45)
    parser.add_argument("--indicator-height", type=float, default=0.02)
    parser.add_argument("--indicator-z", type=float, default=0.011)

    parser.add_argument("--min-contaminations", type=int, default=2)
    parser.add_argument("--max-contaminations", type=int, default=5)
    parser.add_argument("--contamination-area", type=float, default=0.55)
    parser.add_argument("--contamination-length", type=float, default=0.28)
    parser.add_argument("--contamination-width", type=float, default=0.11)
    parser.add_argument("--contamination-height", type=float, default=0.025)
    parser.add_argument("--contamination-z", type=float, default=0.62)

    return parser.parse_args()


def main() -> None:
    configure_output_encoding()
    args = parse_args()
    if args.min_contaminations > args.max_contaminations:
        raise SystemExit("--min-contaminations must be <= --max-contaminations")

    seed = args.seed if args.seed is not None else time.time_ns()
    rng = random.Random(seed)
    panels = make_panels(args, rng)
    task_models = render_task_models(panels, args)

    if args.base_world:
        world = inject_into_base_world(args.base_world, task_models)
    else:
        world = render_standalone_world(task_models)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(world, encoding="utf-8")
    write_truth(args.truth_output, panels, args, seed)

    print(f"Generated world: {args.output}")
    print(f"Generated debug truth: {args.truth_output}")
    print(f"Seed: {seed}")
    for panel in panels:
        state = COLOR_TABLE[panel.indicator_color]["state"]
        print(
            f"Solar panel #{panel.index}: "
            f"{panel.x:.2f} {panel.y:.2f}, {state}, {len(panel.contaminations)} contaminations"
        )


if __name__ == "__main__":
    main()
