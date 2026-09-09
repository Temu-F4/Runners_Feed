"""Execute unmodified model source while recording its actual ORT sessions."""
import json
import os
import runpy
import sys
from pathlib import Path

import onnxruntime as ort

original = ort.InferenceSession
evidence = []


def checked_session(*args, **kwargs):
    session = original(*args, **kwargs)
    if 'CUDAExecutionProvider' not in session.get_providers():
        raise RuntimeError('CUDA provider missing from actual model session')
    session.disable_fallback()
    evidence.append(session.get_providers())
    return session


if __name__ == '__main__':
    ort.InferenceSession = checked_session
    entry, *arguments = sys.argv[1:]
    sys.path.insert(0, str(Path(entry).parents[2]))
    sys.argv = [entry, *arguments]
    runpy.run_path(entry, run_name='__main__')
    if len(evidence) < 2:
        raise RuntimeError('Missing detector/pose CUDA session evidence')
    Path(os.environ['CUDA_EVIDENCE_PATH']).write_text(json.dumps(evidence))
