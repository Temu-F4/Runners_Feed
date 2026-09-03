from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from oci_storage import object_storage_client


BACKUP_PREFIX = "postgres/"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _retention_days() -> int:
    value = int(os.getenv("DB_BACKUP_RETENTION_DAYS", "30"))
    if value < 7:
        raise ValueError("DB_BACKUP_RETENTION_DAYS must be at least 7")
    return value


def _object_name(now: datetime) -> str:
    return (
        f"{BACKUP_PREFIX}{now:%Y/%m}/"
        f"runners-feed-{now:%Y%m%dT%H%M%SZ}.dump"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prune(client, namespace: str, bucket: str, cutoff: datetime) -> int:
    deleted = 0
    start = None
    while True:
        response = client.list_objects(
            namespace_name=namespace,
            bucket_name=bucket,
            prefix=BACKUP_PREFIX,
            start=start,
        )
        for item in response.data.objects:
            if item.time_modified < cutoff:
                client.delete_object(
                    namespace_name=namespace,
                    bucket_name=bucket,
                    object_name=item.name,
                )
                deleted += 1
        start = response.data.next_start_with
        if not start:
            return deleted


def main() -> None:
    database_url = _required("DATABASE_URL")
    bucket = _required("OCI_BACKUP_BUCKET")
    now = datetime.now(timezone.utc)
    object_name = _object_name(now)

    with tempfile.TemporaryDirectory(prefix="runners-feed-backup-") as tmp:
        dump_path = Path(tmp) / "database.dump"
        subprocess.run(
            [
                "pg_dump",
                "--dbname",
                database_url,
                "--format=custom",
                "--compress=gzip:6",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(dump_path),
            ],
            check=True,
        )
        checksum = _sha256(dump_path)
        client, namespace = object_storage_client()
        with dump_path.open("rb") as body:
            client.put_object(
                namespace_name=namespace,
                bucket_name=bucket,
                object_name=object_name,
                put_object_body=body,
                content_type="application/octet-stream",
                opc_meta={"sha256": checksum},
            )

        head = client.head_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=object_name,
        )
        if int(head.headers["content-length"]) != dump_path.stat().st_size:
            raise RuntimeError("Uploaded backup size does not match local dump")

        deleted = _prune(
            client,
            namespace,
            bucket,
            now - timedelta(days=_retention_days()),
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "object_name": object_name,
                "sha256": checksum,
                "expired_backups_deleted": deleted,
            }
        )
    )


if __name__ == "__main__":
    main()
