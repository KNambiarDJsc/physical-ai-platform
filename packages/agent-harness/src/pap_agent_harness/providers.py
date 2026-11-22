"""Model-independent provider configuration. The harness speaks to Strands' ``Model`` interface only; which provider
stands behind it is configuration (``PAP_LLM_PROVIDER``). Only the OpenAI-compatible provider's SDK is installed by
default; another provider's SDK is installed with its Strands extra (``strands-agents[anthropic]``, ``[ollama]``, ...).
Keys are passed to the provider's client and nowhere else."""

from __future__ import annotations

from typing import Any

from strands.models import Model

from .config import LLMSettings, NotConfigured

PROVIDERS = ("openai", "anthropic", "bedrock", "ollama", "litellm")


def build_model(s: LLMSettings, provider: str = "openai") -> Model:
    """A Strands model for the configured provider. Temperature 0: the harness wants reproducible tool use."""
    try:
        if provider == "openai":  # any OpenAI-compatible endpoint (aicredits, vLLM, LM Studio, OpenAI itself)
            from strands.models.openai import OpenAIModel

            return OpenAIModel(client_args={"api_key": s.api_key, "base_url": s.base_url}, model_id=s.model,
                               params={"temperature": 0})  # fmt: skip
        if provider == "anthropic":
            from strands.models.anthropic import AnthropicModel

            args: dict[str, Any] = {"api_key": s.api_key} | ({"base_url": s.base_url} if s.base_url else {})
            return AnthropicModel(client_args=args, model_id=s.model, max_tokens=4096, params={"temperature": 0})
        if provider == "bedrock":
            from strands.models.bedrock import BedrockModel

            return BedrockModel(model_id=s.model, temperature=0)
        if provider == "ollama":
            from strands.models.ollama import OllamaModel

            return OllamaModel(host=s.base_url, model_id=s.model, temperature=0)
        if provider == "litellm":
            from strands.models.litellm import LiteLLMModel

            return LiteLLMModel(client_args={"api_key": s.api_key, "api_base": s.base_url}, model_id=s.model,
                                params={"temperature": 0})  # fmt: skip
    except ImportError as e:
        raise NotConfigured(
            f"the {provider} provider needs its SDK: install strands-agents[{provider}] ({e.name})"
        ) from None
    raise NotConfigured(f"unknown provider {provider!r}; one of {', '.join(PROVIDERS)}")
