import configparser
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        self.client = oci.object_storage.ObjectStorageClient(
            config
        )
        self.namespace = self.client.get_namespace().data
        self.raw_bucket = os.environ["OCI_RAW_BUCKET"]
        self.results_bucket = os.environ[
            "OCI_RESULTS_BUCKET"
        ]
        self.public_endpoint = os.getenv(
            "OCI_OBJECT_STORAGE_PUBLIC_ENDPOINT",
            f"https://objectstorage.{config['region']}.oraclecloud.com",
        ).rstrip("/")

    def _create_signed_url(
        self,
        *,
        bucket_name: str,
        object_name: str,
        access_type: str,
        ttl_seconds: int,
    ) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        details = oci.object_storage.models.CreatePreauthenticatedRequestDetails(
            name=f"runpod-{access_type.lower()}-{os.urandom(8).hex()}",
            access_type=access_type,
            time_expires=expires_at,
            object_name=object_name,
        )
        request = self.client.create_preauthenticated_request(
            namespace_name=self.namespace,
            bucket_name=bucket_name,
            create_preauthenticated_request_details=details,
        ).data
        return f"{self.public_endpoint}{request.access_uri}"

    def create_video_analysis_transfer(
        self,
        *,
        input_object_name: str,
        result_prefix: str,
        ttl_seconds: int,
    ) -> dict[str, object]:
        if ttl_seconds < 300:
            raise ValueError("signed URL TTL must be at least 300 seconds")
        objects = {
            "predictions": f"{result_prefix}/pose_predictions.json",
            "details": f"{result_prefix}/details.json",
            "video": f"{result_prefix}/rendered.mp4",
            "manifest": f"{result_prefix}/pose_manifest.json",
        }
        return {
            "input_url": self._create_signed_url(
                bucket_name=self.raw_bucket,
                object_name=input_object_name,
                access_type="ObjectRead",
                ttl_seconds=ttl_seconds,
            ),
            "upload_urls": {
                role: self._create_signed_url(
                    bucket_name=self.results_bucket,
                    object_name=object_name,
                    access_type="ObjectWrite",
                    ttl_seconds=ttl_seconds,
                )
                for role, object_name in objects.items()
            },
        }

    def download_input(
        self,
        object_name: str,
        destination: Path,
    ) -> None:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary_path = destination.with_suffix(
            destination.suffix + ".part"
        )

        response = self.client.get_object(
            namespace_name=self.namespace,
            bucket_name=self.raw_bucket,
            object_name=object_name,
        )

        try:
            with temporary_path.open("wb") as output:
                for chunk in response.data.raw.stream(
                    1024 * 1024,
                    decode_content=False,
                ):
                    output.write(chunk)

            temporary_path.replace(destination)

        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def download_result(
        self,
        object_name: str,
        destination: Path,
        *,
        max_bytes: int,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = destination.with_suffix(destination.suffix + ".part")
        response = self.client.get_object(
            namespace_name=self.namespace,
            bucket_name=self.results_bucket,
            object_name=object_name,
        )
        total = 0
        try:
            with temporary_path.open("wb") as output:
                for chunk in response.data.raw.stream(1024 * 1024, decode_content=False):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"Result object exceeds size limit: {object_name}")
                    output.write(chunk)
            temporary_path.replace(destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        finally:
            response.data.close()

    def load_result_json(self, object_name: str, *, max_bytes: int = 1024 * 1024) -> dict:
        response = self.client.get_object(
            namespace_name=self.namespace,
            bucket_name=self.results_bucket,
            object_name=object_name,
        )
        try:
            payload = response.data.content
            if len(payload) > max_bytes:
                raise ValueError(f"Result JSON exceeds size limit: {object_name}")
            value = json.loads(payload)
        finally:
            response.data.close()
        if not isinstance(value, dict):
            raise ValueError(f"Result JSON must contain an object: {object_name}")
        return value

    def upload_result(
        self,
        source: Path,
        object_name: str,
        content_type: str,
    ) -> None:
        if not source.is_file():
            raise FileNotFoundError(
                f"Result artifact does not exist: {source}"
            )

        with source.open("rb") as body:
            self.client.put_object(
                namespace_name=self.namespace,
                bucket_name=self.results_bucket,
                object_name=object_name,
                put_object_body=body,
                content_type=content_type,
            )

    def delete_input(self, object_name: str) -> bool:
        return self._delete_object(self.raw_bucket, object_name)

    def delete_result(self, object_name: str) -> bool:
        return self._delete_object(self.results_bucket, object_name)

    def _delete_object(self, bucket_name: str, object_name: str) -> bool:
        try:
            self.client.delete_object(
                namespace_name=self.namespace,
                bucket_name=bucket_name,
                object_name=object_name,
            )
            return True
        except oci.exceptions.ServiceError as error:
            if error.status == 404:
                return False
            raise
