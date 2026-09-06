FROM postgres:16-bookworm

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG BUILD_SOURCE=https://github.com/Temu-F4/Runners_Feed

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="${BUILD_SOURCE}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --break-system-packages oci==2.184.2

WORKDIR /app

COPY deploy/backup/backup.py /app/backup.py
COPY deploy/backup/verify_backup.py /app/verify_backup.py
COPY deploy/backup/oci_storage.py /app/oci_storage.py

ENTRYPOINT ["python3", "/app/backup.py"]
