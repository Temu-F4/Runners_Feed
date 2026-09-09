FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG BUILD_SOURCE=https://github.com/Temu-F4/Runners_Feed

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="${BUILD_SOURCE}"

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
COPY runpod/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY worker/video_analysis_contract.py /app/worker/video_analysis_contract.py
COPY coach/model_plugins/sehyeon-57e4938 /app/coach/model_plugins/sehyeon-57e4938
COPY runpod /app/runpod
EXPOSE 8000
CMD ["uvicorn", "runpod.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
