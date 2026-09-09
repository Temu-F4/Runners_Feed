import unittest

from runpod.cuda_entry import compatible_rtmdet_class


class FakeRTMDet:
    def __init__(self, onnx_model, model_input_size, backend, device):
        self.received = {
            'onnx_model': onnx_model,
            'model_input_size': model_input_size,
            'backend': backend,
            'device': device,
        }


class CudaEntryTests(unittest.TestCase):
    def test_adapts_model_team_detector_options_for_pinned_rtmlib(self):
        detector = compatible_rtmdet_class(FakeRTMDet)(
            onnx_model='detector.onnx',
            model_input_size=(320, 320),
            det_mode='human',
            score_thr=0.6,
            nms_thr=0.45,
            backend='onnxruntime',
            device='cuda',
        )

        self.assertEqual(detector.score_thr, 0.6)
        self.assertEqual(detector.nms_thr, 0.45)
        self.assertEqual(detector.received['device'], 'cuda')

    def test_rejects_unsupported_detection_modes(self):
        Detector = compatible_rtmdet_class(FakeRTMDet)
        with self.assertRaisesRegex(ValueError, 'human detection only'):
            Detector(
                onnx_model='detector.onnx',
                model_input_size=(320, 320),
                det_mode='animal',
                backend='onnxruntime',
                device='cuda',
            )


if __name__ == '__main__':
    unittest.main()
