import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).parent))
storage_stub = ModuleType("oci_storage")
storage_stub.object_storage_client = lambda: None
sys.modules.setdefault("oci_storage", storage_stub)

from backup import BACKUP_PREFIX, _object_name, _prune, _retention_days
from verify_backup import _database_url_for


class BackupPolicyTest(unittest.TestCase):
    def test_builds_partitioned_utc_object_name(self) -> None:
        now = datetime(2026, 9, 4, 3, 5, 6, tzinfo=timezone.utc)

        self.assertEqual(
            _object_name(now),
            "backups/postgres/2026/09/runners-feed-20260904T030506Z.dump",
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_to_30_day_retention(self) -> None:
        self.assertEqual(_retention_days(), 30)

    def test_prune_requests_object_modification_times(self) -> None:
        client = MagicMock()
        client.list_objects.return_value.data = SimpleNamespace(
            objects=[],
            next_start_with=None,
        )
        cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)

        self.assertEqual(_prune(client, "namespace", "bucket", cutoff), 0)
        client.list_objects.assert_called_once_with(
            namespace_name="namespace",
            bucket_name="bucket",
            prefix=BACKUP_PREFIX,
            fields="name,timeModified",
            start=None,
        )

    @patch.dict(os.environ, {"DB_BACKUP_RETENTION_DAYS": "6"})
    def test_rejects_dangerously_short_retention(self) -> None:
        with self.assertRaises(ValueError):
            _retention_days()

    def test_replaces_only_database_path_in_connection_url(self) -> None:
        actual = _database_url_for(
            "postgresql://user:pass@postgres:5432/runners_feed?sslmode=disable",
            "restore_check",
        )

        self.assertEqual(
            actual,
            "postgresql://user:pass@postgres:5432/restore_check?sslmode=disable",
        )


if __name__ == "__main__":
    unittest.main()
