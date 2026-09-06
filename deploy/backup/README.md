# PostgreSQL backup operations

The production PostgreSQL database is dumped once per day and uploaded to the
private OCI results bucket. Backup objects use the isolated prefix
`backups/postgres/YYYY/MM/` and are deleted by the backup job after 30 days.
Raw and rendered videos are not included in the database dump.

## One-time OCI setup

1. Keep `bucket-t04-results` private.
2. Confirm that the OCI API user used by `/home/ubuntu/.oci/config` can create,
   read, list, and delete objects in that bucket.
3. Configure the server `.env`:

   ```dotenv
   OCI_BACKUP_BUCKET=bucket-t04-results
   DB_BACKUP_RETENTION_DAYS=30
   ```

The Compose default is also `bucket-t04-results`; the explicit environment
value documents the production choice. Only objects below `backups/postgres/`
are considered by backup verification and retention pruning.

## Manual verification before scheduling

Run one backup and then restore it into a temporary database:

```bash
docker compose -f compose.yaml -f compose.backup.yaml --profile backup build
./deploy/run_database_backup.sh
./deploy/verify_database_backup.sh
```

The restore verifier creates a temporary database, restores the latest dump,
queries `schema_migrations`, and drops the temporary database in a `finally`
block. It never restores over the live database.

## Install timers

After the manual backup and restore both succeed, copy the four unit files from
`deploy/systemd/` to `/etc/systemd/system/`, reload systemd, and enable both
timers. The backup runs daily at 03:00 Asia/Seoul with up to 15 minutes of
random delay. The restore test runs on the first day of each month at 04:00
Asia/Seoul with up to 30 minutes of random delay.

Inspect results with:

```bash
systemctl list-timers 'runners-feed-db-backup*'
journalctl -u runners-feed-db-backup.service
journalctl -u runners-feed-db-backup-verify.service
```
