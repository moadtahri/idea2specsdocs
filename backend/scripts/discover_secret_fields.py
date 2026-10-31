"""List Secrets Manager JSON field names without displaying values."""

from app.secrets import AwsSecretManager

if __name__ == "__main__":
    manager = AwsSecretManager()
    found = False
    paginator = manager.client.get_paginator("list_secrets")
    for page in paginator.paginate():
        for item in page.get("SecretList", []):
            name = item["Name"]
            result = manager.get_secrets(name)
            payload = (
                result.get("data", {}).get("message")
                if result.get("status") == 200
                else None
            )
            fields = sorted(payload) if isinstance(payload, dict) else []
            if "openai_api_key" in fields:
                found = True
                print(f"FOUND openai_api_key in secret: {name}")
            print(
                f"{name}: {', '.join(fields) if fields else '[non-JSON or unavailable]'}"
            )
    if not found:
        print("No accessible JSON secret contains openai_api_key.")
        raise SystemExit(1)
