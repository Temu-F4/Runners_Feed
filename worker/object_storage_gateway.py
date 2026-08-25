import os
from pathlib import Path

import oci


class ObjectStorageGateway:
    def __init__(self) -> None:
        config = oci.config.from_file(
            file_location=os.getenv(
                "OCI_CONFIG_FILE",
                "/root/.oci/config",
            ),
            profile_name=os.getenv(
                "OCI_CONFIG_PROFILE",
                "DEFAULT",
            ),
        )

        region = os.getenv("OCI_REGION")
        if region:
            config["region"] = region

        oci.config.validate_config(config)

        self.client = oci.object_storage.ObjectStorageClient(
            config
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
