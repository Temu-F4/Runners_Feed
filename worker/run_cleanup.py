from __future__ import annotations

import shutil
from pathlib import Path


def remove_successful_run(run_dir: Path, *, run_root: Path) -> bool:
    """Remove one completed run directory without escaping its run root."""
    resolved_root = run_root.resolve(strict=True)

    if run_dir.is_symlink():
        raise ValueError("Run directory must not be a symbolic link")

    resolved_run = run_dir.resolve(strict=False)
    if resolved_run.parent != resolved_root:
        raise ValueError("Run directory must be a direct child of the run root")
    if not resolved_run.exists():
        return False
    if not resolved_run.is_dir():
        raise ValueError("Run cleanup target must be a directory")

    shutil.rmtree(resolved_run)
    return True
