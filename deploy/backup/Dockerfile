FROM postgres:16-bookworm

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
