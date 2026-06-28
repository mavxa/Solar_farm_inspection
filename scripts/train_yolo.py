#!/usr/bin/env python3
"""Train a YOLO detector for the solar farm Gazebo dataset."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    default_data = project_root / "dataset" / "lm" / "gazeboSolars.v1-gazebosolars.yolov8" / "data.yaml"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=default_data)
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--project", type=Path, default=project_root / "runs" / "detect")
    parser.add_argument("--name", default="solar_yolov8n")
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.data.exists():
        raise SystemExit(f"Dataset YAML not found: {args.data}")

    try:
        from ultralytics import YOLO
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "ultralytics is not installed. Install it with:\n"
            "  python3 -m venv .venv\n"
            "  source .venv/bin/activate\n"
            "  pip install -U pip ultralytics\n"
        ) from exc

    model = YOLO(args.model)
    model.train(
        data=str(args.data),
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project=str(args.project),
        name=args.name,
        patience=args.patience,
        seed=args.seed,
        cache=False,
        pretrained=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
