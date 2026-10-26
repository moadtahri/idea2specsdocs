"""LLM construction for the deep-agent harness.

Muse Spark 1.3 via the Meta OpenAI-compatible endpoint. API key comes
exclusively from AWS Secrets Manager via AwsSecretManager
(secret MODEL_SECRET_NAME, default "Muse_API_KEY_TEST";
MODEL_SECRET_KEY optionally names the JSON key).
"""

from __future__ import annotations

import os

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: F401
from langchain_openai import ChatOpenAI

from ..secrets import resolve_secret

MODEL_NAME = os.environ.get("MODEL_NAME", "muse-spark-1.3")
MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "https://api.meta.ai/v1")
MODEL_TEMPERATURE = float(os.environ.get("MODEL_TEMPERATURE", "0.7"))

__all__ = ["MODEL_BASE_URL", "MODEL_NAME", "MODEL_TEMPERATURE", "build_llm"]


def build_llm() -> ChatOpenAI:
    api_key = resolve_secret(
        "MODEL_SECRET_NAME",
        os.environ.get("MODEL_SECRET_KEY", ""),
    )
    if not api_key:
        raise RuntimeError(
            "No model API key found in AWS Secrets Manager secret "
            f"{os.environ.get('MODEL_SECRET_NAME', 'Muse_API_KEY_TEST')!r}."
        )
    return ChatOpenAI(
        api_key=api_key,
        base_url=MODEL_BASE_URL,
        model=MODEL_NAME,
        temperature=MODEL_TEMPERATURE,
    )
