FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

RUN pip install numpy==1.26.4 opencv-python==4.10.0.84

RUN pip install \
    torch==2.1.0 \
    torchvision==0.16.0 \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install mmengine==0.10.7

RUN pip install \
    mmcv==2.1.0 \
    -f https://download.openmmlab.com/mmcv/dist/cpu/torch2.1/index.html

RUN pip install --no-build-isolation chumpy==0.70
RUN pip install \
    mmdet==3.3.0 \
    mmpose==1.3.2
RUN pip install --force-reinstall setuptools==80.10.2 numpy==1.26.4

WORKDIR /app

COPY test_rtmpose.py /app/test_rtmpose.py

CMD ["python", "/app/test_rtmpose.py"]
