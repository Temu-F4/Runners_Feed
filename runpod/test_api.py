import tempfile
import threading
import time
import unittest
from fastapi.testclient import TestClient
from runpod.app import create_app


class FakePipeline:
    def __init__(self):
        self.calls = 0
        self.release = threading.Event()

    def validate(self, payload):
        if not payload.get('job_id') or not payload.get('attempt_id'):
            raise ValueError('missing identity')

    def run(self, payload):
        self.calls += 1
        self.release.wait(5)
        return {'manifest_object': 'jobs/j/video-analysis/a/pose_manifest.json'}


class ApiTests(unittest.TestCase):
    def test_submit_poll_auth_and_replay(self):
        pipeline = FakePipeline()
        token = 'test-token-' * 4
        headers = {'Authorization': 'Bearer ' + token}
        payload = {'job_id': 'j', 'attempt_id': 'a'}
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(pipeline, directory, token)) as client:
                self.assertEqual(client.post('/v4/storage-video-analysis', json=payload).status_code, 401)
                response = client.post('/v4/storage-video-analysis', json=payload, headers=headers)
                self.assertEqual(response.status_code, 202)
                remote = response.json()['remote_job_id']
                self.assertEqual(response.json()['status'], 'accepted')
                path = '/v4/storage-video-analysis/' + remote
                self.assertIn(client.get(path, headers=headers).json()['status'], ['queued', 'running'])
                replay = client.post('/v4/storage-video-analysis', json=payload, headers=headers)
                self.assertEqual(replay.json()['remote_job_id'], remote)
                self.assertEqual(client.post('/v4/storage-video-analysis', json=dict(payload, job_id='other'), headers=headers).status_code, 409)
                self.assertEqual(client.get(path).status_code, 401)
                self.assertEqual(client.get('/v4/storage-video-analysis/unknown', headers=headers).status_code, 404)
                pipeline.release.set()
                for _ in range(100):
                    result = client.get(path, headers=headers).json()
                    if result['status'] == 'complete':
                        break
                    time.sleep(.02)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(pipeline.calls, 1)
            with TestClient(create_app(pipeline, directory, token)) as client:
                self.assertEqual(client.post('/v4/storage-video-analysis', json=payload, headers=headers).json()['remote_job_id'], remote)
                self.assertEqual(client.get(path, headers=headers).json()['status'], 'complete')
                self.assertEqual(pipeline.calls, 1)


if __name__ == '__main__':
    unittest.main()
