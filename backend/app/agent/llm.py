"""LLM construction for the deep-agent harness.

Muse Spark 1.3 via the Meta OpenAI-compatible endpoint. API key resolution:
env MODEL_API_KEY → AWS Secrets Manager secret MODEL_SECRET_NAME
(default "Muse_API_KEY_TEST"); MODEL_SECRET_KEY optionally names the JSON key,
empty means the secret value itself is the key.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from ..secrets import resolve_named_secret

MODEL_NAME = os.environ.get("MODEL_NAME", "muse-spark-1.3")
MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "https://api.meta.ai/v1")
MODEL_TEMPERATURE = float(os.environ.get("MODEL_TEMPERATURE", "0.7"))


def build_llm() -> ChatOpenAI:
    api_key = os.environ.get("MODEL_API_KEY") or resolve_named_secret(
        os.environ.get("MODEL_SECRET_NAME", "Muse_API_KEY_TEST"),
        os.environ.get("MODEL_SECRET_KEY", ""),
    )
    if not api_key:
        raise RuntimeError(
            "No model API key found. Set MODEL_API_KEY in .env or store it in "
            "AWS Secrets Manager under MODEL_SECRET_NAME "
            "(default: Muse_API_KEY_TEST)."
        )
    return ChatOpenAI(
        api_key=api_key,
        base_url=MODEL_BASE_URL,
        model=MODEL_NAME,
        temperature=MODEL_TEMPERATURE,
    )
