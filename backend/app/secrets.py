"""Secrets access: AWS Secrets Manager with .env fallback.

Resolution order for a key:
1. Explicit env var (e.g. MODEL_API_KEY in .env / shell).
2. AWS Secrets Manager (secret name from *_SECRET_NAME, region from AWS_REGION),
   lazy boto3 client so local dev without AWS still works.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache


class AwsSecretManager:
    """Minimal Secrets Manager client (no boto3 import at module load)."""

    __slots__ = ["_session", "client"]

    def __init__(self, region_name: str = "us-west-2"):
        import boto3  # local import: optional dependency

        self._session = boto3.session.Session()
        self.client = self._session.client(
            service_name="secretsmanager", region_name=region_name
        )

    def get_secrets(self, secret_name: str = "") -> dict:
        try:
            if secret_name == "":
                raise ValueError("Secret Name cannot be Null")
            resp = self.client.get_secret_value(SecretId=secret_name)
            if "SecretString" in resp:
                raw = resp["SecretString"]
                try:
                    secret = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    secret = raw  # plaintext secret: the value itself
                return {"status": 200, "error": {}, "data": {"message": secret}}
            return {"status": -1, "error": {"message": "No SecretString found"}}
        except Exception as e:  # noqa: BLE001 — surfaced to caller as data
            return {"status": -1, "error": {"message": str(e)}}

    def get_secret(self, secret_name: str, secret_key: str = "") -> str | dict:
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            raw = response["SecretString"]
            try:
                secrets = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw  # plaintext secret is the value itself
            if isinstance(secrets, dict):
                if secret_key:
                    return secrets[secret_key]
                if len(secrets) == 1:
                    return next(iter(secrets.values()))
                return secrets
            return secrets
        except Exception as e:  # noqa: BLE001 — surfaced to caller as data
            return {"status": -1, "error": {"message": str(e)}}


@lru_cache(maxsize=32)
def _fetch_secret(secret_name: str, region: str) -> dict | None:
    mgr = AwsSecretManager(region_name=region)
    result = mgr.get_secrets(secret_name)
    if result.get("status") == 200:
        return result["data"]["message"]
    return None


def resolve_secret(
    env_key: str,
    secret_name_env: str = "",
    secret_key: str = "",
    default_region: str = "us-west-2",
) -> str | None:
    """Return secret value: env var first, then Secrets Manager JSON key."""
    direct = os.environ.get(env_key)
    if direct:
        return direct
    region = os.environ.get("AWS_REGION", default_region)
    secret_name = os.environ.get(secret_name_env, "") if secret_name_env else ""
    if not secret_name or not secret_key:
        return None
    try:
        payload = _fetch_secret(secret_name, region)
    except Exception:  # noqa: BLE001 — missing creds/boto3: fall through to None
        return None
    if isinstance(payload, dict):
        value = payload.get(secret_key)
        return str(value) if value is not None else None
    return None


def resolve_named_secret(
    secret_name: str,
    secret_key: str = "",
    default_region: str = "us-west-2",
) -> str | None:
    """Fetch a secret by name; works for JSON or plaintext SecretString.

    Empty secret_key means the secret value itself is the key.
    """
    region = os.environ.get("AWS_REGION", default_region)
    try:
        payload = _fetch_secret(secret_name, region)
    except Exception:  # noqa: BLE001 — missing creds/boto3: fall through to None
        return None
    if payload is None:
        return None
    if isinstance(payload, dict):
        if secret_key:
            value = payload.get(secret_key)
            return str(value) if value is not None else None
        if len(payload) == 1:
            value = next(iter(payload.values()))
            return str(value) if value is not None else None
        return None
    return str(payload)
