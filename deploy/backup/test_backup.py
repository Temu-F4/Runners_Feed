import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parent))
storage_stub = ModuleType("oci_storage")
storage_stub.object_storage_client = lambda: None
sys.modules.setdefault("oci_storage", storage_stub)

from backup import _object_name, _retention_days
from verify_backup import _database_url_for


class BackupPolicyTest(unittest.TestCase):
    def test_builds_partitioned_utc_object_name(self) -> None:
        now = datetime(2026, 9, 4, 3, 5, 6, tzinfo=timezone.utc)

        self.assertEqual(
            _object_name(now),
            "postgres/2026/09/runners-feed-20260904T030506Z.dump",
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_to_30_day_retention(self) -> None:
        self.assertEqual(_retention_days(), 30)

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
