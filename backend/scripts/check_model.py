"""Diagnose model setup without printing credentials."""

import asyncio
import os
import sys

from app.agent.llm import MODEL_BASE_URL, MODEL_NAME, build_llm

if __name__ == "__main__":
    print("Model:", MODEL_NAME)
    print("Endpoint:", MODEL_BASE_URL)
    print("AWS secret:", os.environ.get("MODEL_SECRET_NAME") or "dev/AppAlpha/secrets")
    print("Secret field:", os.environ.get("MODEL_SECRET_KEY") or "Muse_API_KEY_TEST")
    try:
        model = build_llm()
    except Exception as exc:  # noqa: BLE001 -- diagnostic intentionally reports setup class
        print("Model initialization:", type(exc).__name__, str(exc))
        raise SystemExit(1)
    print("Model initialization: available")
    if "--invoke" in sys.argv:
        try:
            response = asyncio.run(model.ainvoke("Reply with exactly: model-ready"))
        except Exception as exc:  # noqa: BLE001 -- diagnostic reports provider failures
            print("Model request:", type(exc).__name__, str(exc)[:300])
            raise SystemExit(1)
        print("Model request:", "available" if response.content else "empty response")
