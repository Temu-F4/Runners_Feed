"""Durable idempotency ledger. A crashed running attempt is never inferred again."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing


class Conflict(ValueError):
    pass


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        with closing(self.connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, attempt TEXT UNIQUE, fingerprint TEXT, payload TEXT, status TEXT, result TEXT)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def submit(self, payload):
        identity = {k: v for k, v in payload.items() if k != 'transfer'}
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT id, fingerprint FROM jobs WHERE attempt=?', (payload['attempt_id'],)).fetchone()
            if row:
                if row[1] != fingerprint:
                    raise Conflict('attempt_id already belongs to a different request')
                return row[0]
            remote_id = uuid.uuid4().hex
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,NULL)', (remote_id, payload['attempt_id'], fingerprint, json.dumps(payload), 'queued'))
            return remote_id

    def claim(self):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id, payload FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (row[0],))
                return row[0], json.loads(row[1])

    def finish(self, remote_id, status, result):
        with closing(self.connect()) as db, db:
            db.execute('UPDATE jobs SET status=?, result=? WHERE id=? AND status=\'running\'', (status, json.dumps(result), remote_id))

    def recover(self):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE jobs SET status='failed', result=? WHERE status='running'", (json.dumps({'error_code': 'WorkerInterrupted', 'error_message': 'Worker stopped; use a new attempt after review.'}),))

    def get(self, remote_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT payload,status,result FROM jobs WHERE id=?', (remote_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        return dict(job_id=payload['job_id'], attempt_id=payload['attempt_id'], remote_job_id=remote_id, status=row[1], **json.loads(row[2] or '{}'))
