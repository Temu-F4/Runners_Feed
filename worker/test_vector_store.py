import unittest

from inference.vector_store import (
    EMBEDDING_DIMENSIONS,
    _document_text,
    _query_text,
    _validate_embedding,
)


class VectorStoreTest(unittest.TestCase):
    def test_accepts_embeddinggemma_dimensions(self) -> None:
        embedding = [0.0] * EMBEDDING_DIMENSIONS

        self.assertEqual(_validate_embedding(embedding), embedding)

    def test_rejects_unexpected_embedding_dimensions(self) -> None:
        with self.assertRaisesRegex(ValueError, "768-dimensional"):
            _validate_embedding([0.0] * 32)

    def test_document_and_query_include_feature_context(self) -> None:
        source = {"title": "Running paper"}
        chunk = {
            "section": "Methods",
            "feature_ids": ["postural_lean_angle_deg"],
            "text": "Postural lean was measured relative to vertical.",
            "caveat": "2-D is not equivalent to Vicon.",
        }
        metric = {
            "id": "postural_lean_angle_deg",
            "label": "전신 전경사",
            "evidence_query": ["postural lean angle"],
        }

        document = _document_text(source, chunk)
        query = _query_text(metric)

        self.assertIn("postural_lean_angle_deg", document)
        self.assertIn("postural_lean_angle_deg", query)
        self.assertIn("postural lean angle", query)


if __name__ == "__main__":
    unittest.main()
