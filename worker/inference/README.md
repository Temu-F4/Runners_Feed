# RTMPose Halpe-26 inference

모델팀의 다음 저장소와 커밋에서 HPE 영상 추론 코드를 이관했습니다.

- Source: `J-sehyeon/Oracle_Project`
- Commit: `9b36675`
- Detector: RTMDet-nano
- Pose model: RTMPose-M Halpe-26
- Backend: ONNX Runtime

ONNX 모델, 입력 영상, 출력 결과는 GitHub에 저장하지 않습니다.

모델 파일 구조:

```text
models/
├── detectors/rtmdet-nano-person-320x320/end2end.onnx
└── pose/rtmpose-m-halpe26-384x288/end2end.onnx

## PostgreSQL pgvector evidence retrieval

The default evidence retriever remains the bundled JSON corpus. To use the
pgvector retriever, start the `poc` profile, pull the local embedding model,
initialize/ingest the corpus, and only then enable `VECTOR_RAG_ENABLED=true`.

```bash
docker compose -f compose.yaml -f compose.poc.yaml --profile poc up -d postgres ollama
docker compose -f compose.yaml -f compose.poc.yaml --profile poc exec ollama ollama pull embeddinggemma
docker compose -f compose.yaml -f compose.poc.yaml --profile poc run --rm --entrypoint python inference-poc -m inference.vector_store ingest
```

The ingestion command is idempotent: current chunks are upserted and stale
chunks for the same source are removed. Runtime retrieval filters by
`feature_ids` before cosine similarity search. If PostgreSQL or Ollama is
unavailable, report generation logs the vector error and falls back to the
JSON/keyword retriever.
