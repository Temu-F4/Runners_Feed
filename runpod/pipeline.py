import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from worker.video_analysis_contract import ARTIFACTS, validate_request, validate_manifest, validate_downloaded_artifacts


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Pipeline:
    def __init__(self, state_dir):
        self.root = Path(os.getenv('COACH_ROOT', '/app/coach'))
        self.plugin = self.root / 'model_plugins' / 'sehyeon-57e4938'
        self.weights = Path(os.getenv('COACH_MODEL_ROOT', '/models'))
        self.state_dir = Path(state_dir)
        self.manifest = json.loads((self.plugin / 'model_manifest.json').read_text())
        self.sources = {name: sha(self.plugin / name) for name in self.manifest['source_files']}
        self.models = {item['path']: sha(self.weights / item['path']) for item in self.manifest['weights']}
        if self.models != {item['path']: item['sha256'] for item in self.manifest['weights']}:
            raise ValueError('Installed weight hash mismatch')
        self.release = os.environ['MODEL_RELEASE']
        self.gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'], text=True, timeout=15).strip()

    def validate(self, request):
        validate_request(request)
        if 'transfer' not in request:
            raise ValueError('Signed transfer URLs required')
        for key, value in [('model_id', 'sehyeon-57e4938'), ('model_release', self.release), ('source_sha256', self.sources), ('model_sha256', self.models)]:
            if request[key] != value:
                raise ValueError('Release mismatch: ' + key)

    def run(self, request):
        self.validate(request)
        started = time.monotonic()
        workspace = self.state_dir / 'work' / request['attempt_id']
        workspace.mkdir(parents=True, exist_ok=False)
        (workspace / 'models').symlink_to(self.weights, target_is_directory=True)
        video = workspace / 'input' / 'source.mp4'
        video.parent.mkdir()
        transfer = request['transfer']
        with requests.get(transfer['input_url'], stream=True, timeout=(15, 120), allow_redirects=False) as response:
            if response.status_code != 200:
                raise RuntimeError('InputDownloadFailed')
            etag = response.headers.get('ETag', '').strip('"')
            if etag != request['input']['etag'].strip('"'):
                raise RuntimeError('InputETagMismatch')
            size = 0
            with video.open('wb') as target:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > request['input']['bytes']:
                        raise RuntimeError('InputSizeMismatch')
                    target.write(chunk)
        if size != request['input']['bytes']:
            raise RuntimeError('InputSizeMismatch')
        timings = {'download': time.monotonic() - started}
        output = workspace / 'run' / 'analysis' / 'outputs'
        evidence = workspace / 'cuda.json'
        env = dict(os.environ, CUDA_EVIDENCE_PATH=str(evidence))
        tick = time.monotonic()
        with (workspace / 'analysis.log').open('wb') as log:
            subprocess.run([sys.executable, '-m', 'runpod.cuda_entry', str(self.plugin / 'scripts/hpe/hpe.py'), str(workspace), 'analysis', str(video), '--device', 'cuda'], env=env, stdout=log, stderr=log, check=True, timeout=3600)
        if len(json.loads(evidence.read_text())) < 2:
            raise RuntimeError('MissingCudaEvidence')
        timings['analysis'] = time.monotonic() - tick
        tick = time.monotonic()
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(output / 'output.mp4'), '-an', '-c:v', 'h264_nvenc', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output / 'rendered.mp4')], check=True, capture_output=True, timeout=600)
        validate_downloaded_artifacts(output)
        timings['encode'] = time.monotonic() - tick
        objects = {}
        tick = time.monotonic()
        for role, (filename, content_type) in ARTIFACTS.items():
            path = output / filename
            objects[role] = dict(object_name=request['result_prefix'] + '/' + filename, content_type=content_type, bytes=path.stat().st_size, sha256=sha(path))
            with path.open('rb') as stream:
                self.upload(transfer['upload_urls'][role], stream, content_type)
        timings['upload'] = time.monotonic() - tick
        timings['worker_total'] = time.monotonic() - started
        manifest = {key: request[key] for key in ('job_id', 'attempt_id', 'model_id', 'model_release', 'source_sha256', 'model_sha256', 'input')}
        manifest.update(schema_version='video-analysis-manifest-2.0', status='complete', input_sha256=sha(video), objects=objects, execution=dict(device='cuda', provider='CUDAExecutionProvider', gpu_name=self.gpu), timings_seconds=timings)
        manifest_object = validate_manifest(manifest, request)
        encoded = json.dumps(manifest).encode()
        (output / 'pose_manifest.json').write_bytes(encoded)
        self.upload(transfer['upload_urls']['manifest'], encoded, 'application/json')
        return {'manifest_object': manifest_object}

    @staticmethod
    def upload(url, data, content_type):
        with requests.put(url, data=data, headers={'Content-Type': content_type}, timeout=(15, 300), allow_redirects=False) as response:
            if response.status_code not in (200, 201, 204):
                raise RuntimeError('ArtifactUploadFailed')
