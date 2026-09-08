import configparser
import os
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
        self.client = oci.object_storage.ObjectStorageClient(
            load_oci_config()
        )
        self.namespace = self.client.get_namespace().data
        self.raw_bucket = os.environ["OCI_RAW_BUCKET"]
        self.results_bucket = os.environ[
            "OCI_RESULTS_BUCKET"
        ]

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
