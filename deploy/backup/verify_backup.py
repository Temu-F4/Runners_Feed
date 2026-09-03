from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from backup import BACKUP_PREFIX, _required
from oci_storage import object_storage_client


def _database_url_for(database_url: str, database_name: str) -> str:
    parsed = urlsplit(database_url)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, "")
    )


def _latest_backup(client, namespace: str, bucket: str):
    response = client.list_objects(
        namespace_name=namespace,
        bucket_name=bucket,
        prefix=BACKUP_PREFIX,
        fields="name,timeModified,size,md5",
    )
    objects = list(response.data.objects)
    if not objects:
        raise RuntimeError("No PostgreSQL backup exists to verify")
    return max(objects, key=lambda item: item.time_modified)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    database_url = _required("DATABASE_URL")
    bucket = _required("OCI_BACKUP_BUCKET")
    client, namespace = object_storage_client()
    backup = _latest_backup(client, namespace, bucket)
    restore_database = f"rf_restore_check_{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    restore_url = _database_url_for(database_url, restore_database)

    with tempfile.TemporaryDirectory(prefix="runners-feed-restore-") as tmp:
        dump_path = Path(tmp) / "database.dump"
        response = client.get_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=backup.name,
        )
        with dump_path.open("wb") as output:
            for chunk in response.data.raw.stream(1024 * 1024, decode_content=False):
                output.write(chunk)

        expected_checksum = response.headers.get("opc-meta-sha256")
        actual_checksum = _sha256(dump_path)
        if expected_checksum and actual_checksum != expected_checksum:
            raise RuntimeError("Downloaded backup checksum does not match")

        subprocess.run(
            ["createdb", "--maintenance-db", database_url, restore_database],
            check=True,
        )
        try:
            subprocess.run(
                [
                    "pg_restore",
                    "--dbname",
                    restore_url,
                    "--no-owner",
                    "--no-privileges",
                    str(dump_path),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "psql",
                    "--dbname",
                    restore_url,
                    "--set=ON_ERROR_STOP=1",
                    "--tuples-only",
                    "--command",
                    "SELECT COUNT(*) FROM schema_migrations;",
                ],
                check=True,
            )
        finally:
            subprocess.run(
                [
                    "dropdb",
                    "--maintenance-db",
                    database_url,
                    "--if-exists",
                    restore_database,
                ],
                check=True,
            )

    print(
        json.dumps(
            {
                "status": "ok",
                "verified_object": backup.name,
                "sha256": actual_checksum,
            }
        )
    )


if __name__ == "__main__":
    main()
