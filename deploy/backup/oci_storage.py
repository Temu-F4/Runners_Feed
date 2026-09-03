from __future__ import annotations

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
        configured_key_path = Path(config["key_file"]).expanduser()
        config["key_file"] = str(
            config_path.parent / configured_key_path.name
        )

    if os.getenv("OCI_REGION"):
        config["region"] = os.environ["OCI_REGION"]
    oci.config.validate_config(config)
    return config


def object_storage_client():
    config = load_oci_config()
    client = oci.object_storage.ObjectStorageClient(config)
    namespace = client.get_namespace().data
    return client, namespace
