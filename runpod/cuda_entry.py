"""Execute unmodified model source while recording its actual ORT sessions."""
import json
import os
import runpy
import sys
from pathlib import Path

import onnxruntime as ort

original = ort.InferenceSession
evidence = []


def compatible_rtmdet_class(base):
    """Accept the model team's RTMDet options on rtmlib 0.0.13.

    The pinned runtime predates these constructor arguments, but its
    post-processing code already reads ``score_thr`` and ``nms_thr`` from the
    instance.  Keep the model source untouched and adapt only the runtime seam.
    """
    class CompatibleRTMDet(base):
        def __init__(
            self,
            *args,
            det_mode=None,
            score_thr=0.3,
            nms_thr=0.45,
            **kwargs,
        ):
            if det_mode not in (None, 'human'):
                raise ValueError('rtmlib 0.0.13 compatibility supports human detection only')
            super().__init__(*args, **kwargs)
            self.score_thr = score_thr
            self.nms_thr = nms_thr

    return CompatibleRTMDet


def checked_session(*args, **kwargs):
    session = original(*args, **kwargs)
    if 'CUDAExecutionProvider' not in session.get_providers():
        raise RuntimeError('CUDA provider missing from actual model session')
    session.disable_fallback()
    evidence.append(session.get_providers())
    return session


if __name__ == '__main__':
    import rtmlib

    ort.InferenceSession = checked_session
    rtmlib.RTMDet = compatible_rtmdet_class(rtmlib.RTMDet)
    entry, *arguments = sys.argv[1:]
    sys.path.insert(0, str(Path(entry).parents[2]))
    sys.argv = [entry, *arguments]
    runpy.run_path(entry, run_name='__main__')
    if len(evidence) < 2:
        raise RuntimeError('Missing detector/pose CUDA session evidence')
    Path(os.environ['CUDA_EVIDENCE_PATH']).write_text(json.dumps(evidence))
