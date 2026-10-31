"""LLM construction for the deep-agent harness.

Muse Spark 1.3 via the Meta OpenAI-compatible endpoint. API key comes
exclusively from AWS Secrets Manager via AwsSecretManager
(secret MODEL_SECRET_NAME, default "dev/AppAlpha/secrets";
MODEL_SECRET_KEY defaults to the "Muse_API_KEY_TEST" JSON field).
"""

from __future__ import annotations

import os

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: F401
from langchain_openai import ChatOpenAI

from ..secrets import DEFAULT_SECRET_NAME, resolve_secret

MODEL_NAME = os.environ.get("MODEL_NAME", "muse-spark-1.3")
MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "https://api.meta.ai/v1")
MODEL_TEMPERATURE = float(os.environ.get("MODEL_TEMPERATURE", "0.7"))

__all__ = [
    "MODEL_BASE_URL",
    "MODEL_NAME",
    "MODEL_TEMPERATURE",
    "ModelConfigurationError",
    "build_fallback_llm",
    "build_llm",
]


class ModelConfigurationError(RuntimeError):
    """The model credential could not be resolved from AWS."""


def build_llm(model: str = MODEL_NAME) -> ChatOpenAI:
    api_key = resolve_secret(
        "MODEL_SECRET_NAME",
        os.environ.get("MODEL_SECRET_KEY") or "Muse_API_KEY_TEST",
    )
    if not api_key:
        raise ModelConfigurationError(
            "No model API key found in AWS Secrets Manager secret "
            f"{os.environ.get('MODEL_SECRET_NAME', DEFAULT_SECRET_NAME)!r} "
            f"field {os.environ.get('MODEL_SECRET_KEY', 'Muse_API_KEY_TEST')!r}."
        )
    return ChatOpenAI(
        api_key=api_key,
        base_url=MODEL_BASE_URL,
        model=model,
        temperature=MODEL_TEMPERATURE,
    )


def build_fallback_llm() -> ChatOpenAI | None:
    """A second model on the same endpoint and key, tried when the first fails.
    Only when MODEL_FALLBACK_NAME is set."""
    name = os.environ.get("MODEL_FALLBACK_NAME", "").strip()
    return build_llm(name) if name else None
