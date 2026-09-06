#!/usr/bin/env python3
"""Template for a drop-in feature model entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path


def run_features(*, workspace_root: Path, run_id: str) -> None:
    run_dir = workspace_root / "run" / run_id
    output_dir = run_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # TODO(modeler): write outputs/feature_results.json.
    raise NotImplementedError("Implement the feature contract before enabling it")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace_root", type=Path)
    parser.add_argument("run_id")
    args = parser.parse_args()
    run_features(workspace_root=args.workspace_root, run_id=args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
