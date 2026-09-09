import asyncio
import hmac
import os
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from runpod.state import Ledger, Conflict


def create_app(pipeline=None, state_dir=None, token=None):
    secret = token or os.environ.get('RUNPOD_SHARED_TOKEN', '')
    if len(secret) < 24 or secret != secret.strip():
        raise ValueError('RUNPOD_SHARED_TOKEN must have at least 24 characters')
    root = Path(state_dir or os.getenv('RUNPOD_STATE_DIR', '/workspace/runpod-state'))
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    ledger = Ledger(root / 'jobs.sqlite3')

    @asynccontextmanager
    async def lifespan(app):
        # One process per state directory; protects recovery against live workers.
        import fcntl
        lock = (root / 'worker.lock').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            nonlocal pipeline
            if pipeline is None:
                from runpod.pipeline import Pipeline
                pipeline = Pipeline(root)
            ledger.recover()
            stopping = asyncio.Event()

            async def worker():
                while not stopping.is_set():
                    job = ledger.claim()
                    if job is None:
                        await asyncio.sleep(0.25)
                        continue
                    remote_id, payload = job
                    try:
                        result = await asyncio.to_thread(pipeline.run, payload)
                        ledger.finish(remote_id, 'complete', result)
                    except Exception as error:
                        # Never return exception strings containing signed URLs.
                        private_log = root / 'work' / payload['attempt_id'] / 'failure.log'
                        private_log.parent.mkdir(parents=True, exist_ok=True)
                        private_log.write_text(traceback.format_exc(), encoding='utf-8')
                        os.chmod(private_log, 0o600)
                        ledger.finish(remote_id, 'failed', {'error_code': type(error).__name__, 'error_message': 'Analysis failed; inspect private worker logs.'})

            task = asyncio.create_task(worker())
            try:
                yield
            finally:
                stopping.set()
                await task
        finally:
            lock.close()

    app = FastAPI(lifespan=lifespan)

    def authenticate(authorization):
        if not hmac.compare_digest(authorization or '', 'Bearer ' + secret):
            raise HTTPException(401, 'Unauthorized')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'contract': 'video-analysis-request-2.0', 'transport': 'submit-poll'}

    @app.post('/v4/storage-video-analysis', status_code=202)
    def submit(payload: dict, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        try:
            pipeline.validate(payload)
            remote_id = ledger.submit(payload)
        except Conflict:
            raise HTTPException(409, 'Attempt identity conflict')
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, 'Invalid request or release identity')
        return {'status': 'accepted', 'remote_job_id': remote_id, 'job_id': payload['job_id'], 'attempt_id': payload['attempt_id']}

    @app.get('/v4/storage-video-analysis/{remote_job_id}')
    def poll(remote_job_id: str, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        result = ledger.get(remote_job_id)
        if result is None:
            raise HTTPException(404, 'Unknown remote job')
        return result

    return app
