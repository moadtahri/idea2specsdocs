"""Run from backend: python -m scripts.check_transcription_secret. Never prints keys."""

import os
import sys

from app.secrets import AwsSecretManager

if __name__ == "__main__":
    if "--list-matching" in sys.argv:
        manager = AwsSecretManager()
        for page in manager.client.get_paginator("list_secrets").paginate(
            Filters=[
                {
                    "Key": "name",
                    "Values": ["openai", "OpenAI", "OPENAI", "Muse", "muse"],
                }
            ]
        ):
            for secret in page.get("SecretList", []):
                print("Candidate secret:", secret["Name"])
        raise SystemExit(0)
    secret_name = (
        os.environ.get("ASSEMBLYAI_SECRET_NAME")
        or os.environ.get("MODEL_SECRET_NAME")
        or "dev/AppAlpha/secrets"
    )
    secret_key = os.environ.get("ASSEMBLYAI_SECRET_KEY") or "ASSEMBLYAI_API_KEY"
    try:
        result = AwsSecretManager().get_secret(secret_name, secret_key)
    except Exception as exc:  # noqa: BLE001 -- diagnostic reports client setup failures
        result = None
        print("AWS client error:", type(exc).__name__)
    available = isinstance(result, str) and bool(result.strip())
    print(
        "AWS transcription key: "
        + (
            "available"
            if available
            else "unavailable; check backend AWS credentials, secret name and access"
        )
    )
    if isinstance(result, dict) and result.get("status") == -1:
        print(
            "AWS lookup error:", result.get("error", {}).get("message", "Unknown error")
        )
    raise SystemExit(0 if available else 1)
