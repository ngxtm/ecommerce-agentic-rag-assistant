from __future__ import annotations

import json
import subprocess

import boto3
from botocore.credentials import Credentials, RefreshableCredentials
from botocore.session import get_session


def _load_exported_cli_credentials() -> dict[str, str] | None:
    try:
        result = subprocess.run(
            ["aws", "configure", "export-credentials", "--format", "process"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    access_key = payload.get("AccessKeyId")
    secret_key = payload.get("SecretAccessKey")
    if not access_key or not secret_key:
        return None

    return {
        "access_key": access_key,
        "secret_key": secret_key,
        "token": payload.get("SessionToken"),
        "expiry_time": payload.get("Expiration"),
    }


def get_boto3_session(region_name: str | None = None) -> boto3.Session:
    session = boto3.Session(region_name=region_name)
    if session.get_credentials() is not None:
        return session

    exported = _load_exported_cli_credentials()
    if exported is None:
        return session

    botocore_session = get_session()
    if exported.get("expiry_time"):
        refreshable = RefreshableCredentials.create_from_metadata(
            metadata={
                "access_key": exported["access_key"],
                "secret_key": exported["secret_key"],
                "token": exported.get("token"),
                "expiry_time": exported["expiry_time"],
            },
            refresh_using=_load_exported_cli_credentials,
            method="aws-cli-export",
        )
        botocore_session._credentials = refreshable
    else:
        botocore_session.set_credentials(
            exported["access_key"],
            exported["secret_key"],
            exported.get("token"),
        )

    if region_name:
        botocore_session.set_config_variable("region", region_name)
    return boto3.Session(botocore_session=botocore_session, region_name=region_name)


def get_frozen_credentials(region_name: str | None = None) -> Credentials | None:
    session = get_boto3_session(region_name=region_name)
    credentials = session.get_credentials()
    if credentials is None:
        return None
    return credentials.get_frozen_credentials()
