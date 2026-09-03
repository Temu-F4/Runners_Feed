# PostgreSQL backup operations

The production PostgreSQL database is dumped once per day and uploaded to a
dedicated private OCI Object Storage bucket. Backup objects use the prefix
`postgres/YYYY/MM/` and are deleted after 30 days. Raw and rendered videos are
not included because they already live in separate Object Storage buckets.

## One-time OCI setup

1. Create a private Standard-tier bucket, for example `bucket-t04-backups`.
2. Do not enable public access.
3. Grant the OCI API user used by `/home/ubuntu/.oci/config` permission to
   inspect the bucket and create, read, list, and delete objects in that bucket.
4. Add the exact bucket name to the server `.env`:

   ```dotenv
   OCI_BACKUP_BUCKET=bucket-t04-backups
   DB_BACKUP_RETENTION_DAYS=30
   ```

The service intentionally refuses to start when `OCI_BACKUP_BUCKET` is absent.
This prevents a database dump from being written to a video bucket by mistake.

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
