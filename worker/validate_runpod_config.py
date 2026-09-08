#!/usr/bin/env python3
"""Validate mandatory RunPod settings before starting the Celery worker."""

from runpod_client import client_from_environment


def main() -> int:
    try:
        client_from_environment()
    except (KeyError, TypeError, ValueError) as error:
        print(f"RUNPOD_CONFIGURATION_INVALID={error}")
        return 1
    print("RUNPOD_CONFIGURATION=VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
