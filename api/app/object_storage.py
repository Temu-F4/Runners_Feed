import configparser
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import oci


def load_oci_config() -> dict[str, str]:
    config_path = Path(
        os.getenv("OCI_CONFIG_FILE", "/.oci/config")
    ).expanduser()
    profile_name = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")

    try:
        config = oci.config.from_file(
            file_location=str(config_path),
            profile_name=profile_name,
        )
    except oci.exceptions.InvalidKeyFilePath:
        parser = configparser.ConfigParser()
        if not parser.read(config_path):
            raise FileNotFoundError(
                f"OCI config file does not exist: {config_path}"
            )
        if profile_name not in parser:
            raise KeyError(
                f"OCI config profile does not exist: {profile_name}"
            )

        config = dict(parser[profile_name])
        configured_key_path = Path(
            config["key_file"]
        ).expanduser()
        mounted_key_path = (
            config_path.parent / configured_key_path.name
        )
        config["key_file"] = str(mounted_key_path)

    region = os.getenv("OCI_REGION")
    if region:
        config["region"] = region

    oci.config.validate_config(config)
    return config


class ObjectStorageGateway:
    def __init__(self) -> None:
        config = load_oci_config()
        self.client = oci.object_storage.ObjectStorageClient(config)
        self.namespace = self.client.get_namespace().data
        self.raw_bucket = os.environ["OCI_RAW_BUCKET"]
        self.results_bucket = os.environ["OCI_RESULTS_BUCKET"]
        self.public_endpoint = os.getenv(
            "OCI_OBJECT_STORAGE_PUBLIC_ENDPOINT",
            f"https://objectstorage.{config['region']}.oraclecloud.com",
        ).rstrip("/")

    def create_result_read_url(
        self,
        object_name: str,
        ttl_seconds: int,
    ) -> tuple[str, datetime]:
        self.client.head_object(
            namespace_name=self.namespace,
            bucket_name=self.results_bucket,
            object_name=object_name,
        )

        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=ttl_seconds
        )
        details = oci.object_storage.models.CreatePreauthenticatedRequestDetails(
            name=f"runners-feed-result-{uuid4().hex}",
            access_type="ObjectRead",
            time_expires=expires_at,
            object_name=object_name,
        )
        request = self.client.create_preauthenticated_request(
            namespace_name=self.namespace,
            bucket_name=self.results_bucket,
            create_preauthenticated_request_details=details,
        ).data

        return (
            f"{self.public_endpoint}{request.access_uri}",
            expires_at,
        )

    def create_input_write_url(
        self,
        object_name: str,
        ttl_seconds: int,
    ) -> tuple[str, datetime]:
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=ttl_seconds
        )
        details = oci.object_storage.models.CreatePreauthenticatedRequestDetails(
            name=f"runners-feed-upload-{uuid4().hex}",
            access_type="ObjectWrite",
            time_expires=expires_at,
            object_name=object_name,
        )
        request = self.client.create_preauthenticated_request(
            namespace_name=self.namespace,
            bucket_name=self.raw_bucket,
            create_preauthenticated_request_details=details,
        ).data

        return (
            f"{self.public_endpoint}{request.access_uri}",
            expires_at,
        )

    def inspect_input_object(self, object_name: str) -> dict[str, object]:
        response = self.client.head_object(
            namespace_name=self.namespace,
            bucket_name=self.raw_bucket,
            object_name=object_name,
        )
        return {
            "size_bytes": int(response.headers["content-length"]),
            "content_type": response.headers.get("content-type"),
            "etag": response.headers.get("etag"),
        }
