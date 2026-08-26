import os
import unittest
from unittest.mock import patch

from inference.evidence import load_corpus, retrieve_evidence, retrieve_for_metric


class EvidenceRetrieverTest(unittest.TestCase):
    def test_corpus_has_traceable_source(self) -> None:
        corpus = load_corpus()

        self.assertEqual(
            corpus["source"]["doi"],
            "10.1371/journal.pone.0302249",
        )
        self.assertTrue(all(chunk.get("page") for chunk in corpus["chunks"]))
        self.assertTrue(all(chunk.get("caveat") for chunk in corpus["chunks"]))

    def test_retrieves_measurement_and_table_for_postural_lean(self) -> None:
        results = retrieve_for_metric(
            {
                "id": "postural_lean_angle_deg",
                "label": "전신 전경사",
                "evidence_query": ["postural lean angle", "upright moderate large"],
            },
            limit=3,
        )
        evidence_ids = {result["evidence_id"] for result in results}

        self.assertIn("carson-2024-method-postural-angles", evidence_ids)
        self.assertIn("carson-2024-table1-lean-conditions", evidence_ids)

    def test_combined_retrieval_tracks_feature_matches(self) -> None:
        with patch.dict(os.environ, {"VECTOR_RAG_ENABLED": "false"}):
            results = retrieve_evidence(
                [
                    {
                        "id": "peak_hip_flexion_stance_deg",
                        "evidence_query": ["peak hip flexion", "stance phase"],
                    },
                    {
                        "id": "peak_knee_flexion_stance_deg",
                        "evidence_query": ["peak knee flexion", "stance phase"],
                    },
                ]
            )
        joint_table = next(
            result
            for result in results
            if result["evidence_id"] == "carson-2024-table1-joint-flexion"
        )

        self.assertEqual(
            set(joint_table["matched_feature_ids"]),
            {
                "peak_hip_flexion_stance_deg",
                "peak_knee_flexion_stance_deg",
            },
        )

    def test_vector_retrieval_is_preferred_when_enabled(self) -> None:
        vector_result = [
            {
                "evidence_id": "vector-result",
                "retrieval_method": "pgvector_cosine",
            }
        ]
        with (
            patch.dict(os.environ, {"VECTOR_RAG_ENABLED": "true"}),
            patch(
                "inference.vector_store.retrieve_evidence_vector",
                return_value=vector_result,
            ) as retrieve_vector,
        ):
            result = retrieve_evidence([{"id": "postural_lean_angle_deg"}])

        self.assertEqual(result, vector_result)
        retrieve_vector.assert_called_once()

    def test_vector_failure_falls_back_to_json(self) -> None:
        with (
            patch.dict(os.environ, {"VECTOR_RAG_ENABLED": "true"}),
            patch(
                "inference.vector_store.retrieve_evidence_vector",
                side_effect=ConnectionError("vector store unavailable"),
            ),
            self.assertLogs("inference.evidence", level="ERROR"),
        ):
            result = retrieve_evidence([{"id": "postural_lean_angle_deg"}])

        self.assertTrue(result)
        self.assertNotIn("retrieval_method", result[0])


if __name__ == "__main__":
    unittest.main()
