# sehyeon-dcc2d7d model plugin

This directory preserves the production Python source from the modeler's
`sehyeon` repository at commit `dcc2d7d7a7eaacb8b2828745d31a5b375c5b893b`.
Service concerns such as Celery, OCI Object Storage, database updates, stage
logging, H.264 conversion, and final API report adaptation stay outside this
directory.

The ONNX files are not committed. They are mounted at `/workspace/models` and
must match the SHA-256 values in `model_manifest.json`.

`quality_baseline.json` is a structural safety baseline until the modeler
provides an approved golden video, expected outputs, and reviewed tolerances.
