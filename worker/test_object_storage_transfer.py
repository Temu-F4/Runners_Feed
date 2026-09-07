import sys
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import Mock

try:
    import oci  # noqa: F401
except ModuleNotFoundError:
    sys.modules["oci"] = Mock()

module_path = Path(__file__).with_name("object_storage_gateway.py")
spec = importlib.util.spec_from_file_location("object_storage_gateway_transfer_test", module_path)
object_storage_gateway = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(object_storage_gateway)
ObjectStorageGateway = object_storage_gateway.ObjectStorageGateway


class SignedTransferTests(unittest.TestCase):
    def test_creates_one_read_and_four_object_scoped_write_urls(self):
        gateway = ObjectStorageGateway.__new__(ObjectStorageGateway)
        gateway.client = Mock()
        gateway.namespace = "namespace"
        gateway.raw_bucket = "raw"
        gateway.results_bucket = "results"
        gateway.public_endpoint = "https://objectstorage.region.oraclecloud.com"
        gateway.client.create_preauthenticated_request.side_effect = [
            Mock(data=Mock(access_uri=f"/p/{index}"))
            for index in range(5)
        ]
        details_factory = Mock(side_effect=lambda **values: values)
        object_storage_gateway.oci.object_storage.models.CreatePreauthenticatedRequestDetails = details_factory

        transfer = gateway.create_video_analysis_transfer(
            input_object_name="uploads/input.mp4",
            result_prefix="jobs/job/video-analysis/attempt",
            ttl_seconds=7200,
        )

        self.assertEqual(set(transfer["upload_urls"]), {
            "predictions", "details", "video", "manifest"
        })
        calls = gateway.client.create_preauthenticated_request.call_args_list
        self.assertEqual(len(calls), 5)
        self.assertEqual(calls[0].kwargs["bucket_name"], "raw")
        self.assertTrue(all(call.kwargs["bucket_name"] == "results" for call in calls[1:]))
        details = details_factory.call_args_list
        self.assertEqual(details[0].kwargs["access_type"], "ObjectRead")
        self.assertTrue(all(call.kwargs["access_type"] == "ObjectWrite" for call in details[1:]))


if __name__ == "__main__":
    unittest.main()
