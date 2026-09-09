import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from runpod.state import Ledger, Conflict


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Ledger(Path(self.tmp.name) / 'jobs.db')
        self.payload = dict(job_id='job1', attempt_id='attempt1', input={'etag': 'v1'}, transfer={'url': 'private'})

    def test_concurrent_replay_claims_only_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.ledger.submit(self.payload), range(20)))
        self.assertEqual(len(set(ids)), 1)
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda _: self.ledger.claim(), range(20)))
        self.assertEqual(sum(x is not None for x in claims), 1)

    def test_identity_conflict(self):
        self.ledger.submit(self.payload)
        with self.assertRaises(Conflict):
            self.ledger.submit(dict(self.payload, input={'etag': 'v2'}))

    def test_restart_does_not_repeat_inference(self):
        remote = self.ledger.submit(self.payload)
        self.ledger.claim()
        restarted = Ledger(self.ledger.path)
        restarted.recover()
        self.assertEqual(restarted.submit(self.payload), remote)
        self.assertEqual(restarted.get(remote)['status'], 'failed')
        self.assertIsNone(restarted.claim())

    def test_completed_replay_and_url_rotation(self):
        remote = self.ledger.submit(self.payload)
        self.ledger.claim()
        self.ledger.finish(remote, 'complete', {'manifest_object': 'manifest'})
        self.assertEqual(self.ledger.submit(dict(self.payload, transfer={'url': 'renewed'})), remote)
        self.assertEqual(self.ledger.get(remote)['manifest_object'], 'manifest')
        self.assertIsNone(self.ledger.claim())


if __name__ == '__main__':
    unittest.main()
