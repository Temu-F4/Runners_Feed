#!/usr/bin/env python3
"""Template for a drop-in pose model entrypoint.

Copy this file into a model-specific directory and implement only the model
logic. Keep the CLI and artifact names stable.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def run_model(
    *,
    workspace_root: Path,
    run_id: str,
    video_path: Path,
) -> None:
    run_dir = workspace_root / "run" / run_id
    output_dir = run_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # TODO(modeler): write output.mp4, details.json, and pose_predictions.json.
    # Do not change the input video or access the service database here.
    raise NotImplementedError("Implement the model contract before enabling it")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace_root", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("video_path", type=Path)
    args = parser.parse_args()
    run_model(
        workspace_root=args.workspace_root,
        run_id=args.run_id,
        video_path=args.video_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
