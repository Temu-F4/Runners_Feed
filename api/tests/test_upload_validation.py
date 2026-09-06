from unittest import TestCase

from app.main import CreateUploadRequest


class UploadValidationTests(TestCase):
    def test_accepts_mov_with_quicktime_content_type(self) -> None:
        request = CreateUploadRequest(
            filename="running-test.MOV",
            content_type="video/quicktime",
        )

        self.assertEqual(request.filename, "running-test.MOV")
        self.assertEqual(request.content_type, "video/quicktime")

    def test_accepts_mp4_with_mp4_content_type(self) -> None:
        request = CreateUploadRequest(
            filename="running-test.mp4",
            content_type="video/mp4",
        )

        self.assertEqual(request.filename, "running-test.mp4")

