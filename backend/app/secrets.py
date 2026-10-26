"""Secrets access: AWS Secrets Manager ONLY (no .env key fallback).

Model keys resolve via AwsSecretManager against MODEL_SECRET_NAME
(default "Muse_API_KEY_TEST") in AWS_REGION (default us-west-2).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache


# User-supplied AwsSecretManager below is verbatim; exempt from style rules.
# ruff: noqa: UP004, TRY002, BLE001
class AwsSecretManager(object):
    __slots__ = ["_session", "client"]

    def __init__(self):
        import boto3  # local import: keep boto3 optional at module load

        self._session = boto3.session.Session()
        self.client = self._session.client(
            service_name="secretsmanager", region_name="us-west-2"
        )

    def get_secrets(self, secret_name=""):
        try:
            if secret_name == "":
                raise Exception("Secret Name cannot be Null ")
            get_secret_value_response = self.client.get_secret_value(
                SecretId=secret_name
            )
            if "SecretString" in get_secret_value_response:
                secret = get_secret_value_response["SecretString"]
                secret = json.loads(secret)
                return {
                    "status": 200,
                    "error": {},
                    "data": {"message": secret},
                }
        except Exception as e:
            return {"status": -1, "error": {"message": str(e)}}

    # create a function that returns specific secret
    def get_secret(self, secret_name, secret_key):
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            secrets = json.loads(response["SecretString"])
            secret = secrets[secret_key]
            return secret
        except Exception as e:
            return {"status": -1, "error": {"message": str(e)}}


@lru_cache(maxsize=32)
def _fetch_secret(secret_name: str) -> dict | str | None:
    mgr = AwsSecretManager()
    result = mgr.get_secrets(secret_name)
    if result.get("status") == 200:
        return result["data"]["message"]
    return None


def resolve_secret(
    secret_name_env: str = "MODEL_SECRET_NAME",
    secret_key: str = "",
    default_secret: str = "Muse_API_KEY_TEST",
) -> str | None:
    """Return the model key via AwsSecretManager ONLY (no env key fallback)."""
    secret_name = os.environ.get(secret_name_env, "") or default_secret
    if not secret_name:
        return None
    try:
        if secret_key:
            value = AwsSecretManager().get_secret(secret_name, secret_key)
        else:
            payload = _fetch_secret(secret_name)
            if isinstance(payload, dict):
                if len(payload) == 1:
                    value = next(iter(payload.values()))
                else:
                    return None
            else:
                value = payload
        if isinstance(value, dict) and "status" in value:
            return None
        return str(value) if value is not None else None
    except Exception:
        return None


def resolve_named_secret(
    secret_name: str,
    secret_key: str = "",
) -> str | None:
    """Fetch a secret by name via AwsSecretManager.

    Empty secret_key + single-key JSON (or plaintext) means the value itself
    is the key. Kept for backwards-compat; prefers resolve_secret().
    """
    try:
        if secret_key:
            value = AwsSecretManager().get_secret(secret_name, secret_key)
        else:
            payload = _fetch_secret(secret_name)
            if isinstance(payload, dict):
                if len(payload) == 1:
                    value = next(iter(payload.values()))
                else:
                    return None
            else:
                value = payload
        if isinstance(value, dict) and "status" in value:
            return None
        return str(value) if value is not None else None
    except Exception:
        return None
