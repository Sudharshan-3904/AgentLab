"""Model provider factory and resolver."""

from __future__ import annotations

from typing import Dict, Optional, Type
from harness.models.interface import IModelProvider
from harness.models.lmstudio import LMStudioProvider
from harness.models.ollama import OllamaProvider


class ModelProviderRegistry:
    """Registry and factory for local and remote model provider backends."""

    _providers: Dict[str, Type[IModelProvider]] = {
        "ollama": OllamaProvider,
        "lmstudio": LMStudioProvider,
    }

    @classmethod
    def register(cls, name: str, provider_cls: Type[IModelProvider]) -> None:
        """Register a new provider class."""
        cls._providers[name.lower()] = provider_cls

    @classmethod
    def create(
        cls,
        provider_name: str,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        **kwargs,
    ) -> IModelProvider:
        """Instantiate a provider by name with optional configurations."""
        name_key = provider_name.lower()
        if name_key not in cls._providers:
            raise ValueError(
                f"Unknown model provider: '{provider_name}'. Available: {list(cls._providers.keys())}"
            )
        provider_cls = cls._providers[name_key]
        init_kwargs = {}
        if base_url:
            init_kwargs["base_url"] = base_url
        if default_model:
            init_kwargs["default_model"] = default_model
        init_kwargs.update(kwargs)
        return provider_cls(**init_kwargs)
