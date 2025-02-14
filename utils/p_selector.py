import importlib
import inspect
import os
import random
import httpx
from typing import Dict, Any

class BaseProvider:
    def __init__(self, async_client=None):
        self.async_client = async_client
        self.models = []

def discover_providers(provider_directory: str = "providers") -> Dict[str, Any]:

    providers = {}
    for filename in os.listdir(provider_directory):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"{provider_directory}.{module_name}")
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseProvider) and obj != BaseProvider:
                        provider_name = name.lower().replace(" ", "_").replace("-", "_")
                        providers[provider_name] = obj
            except Exception as e:
                print(f"Error loading provider from {filename}: {e}")
    return providers

def initialize_providers(async_client=None, provider_directory: str = "providers") -> Dict[str, BaseProvider]:

    if async_client is None:
        async_client = httpx.AsyncClient()

    provider_classes = discover_providers(provider_directory)
    initialized_providers = {}
    for name, provider_class in provider_classes.items():
        try:
            initialized_providers[name] = provider_class(async_client)
        except Exception as e:
            print(f"Error initializing provider {name}: {e}")
            print(f"Error initializing provider {name}: {e}")
    
    return initialized_providers

def select_provider(model: str, provider_type: str = 'chat', async_client=None, provider_directory: str = "providers"):
    providers = initialize_providers(async_client, provider_directory)
    
    allowed_providers = [
        provider for provider in providers.values() 
        if model in provider.models and (
            (provider_type == 'chat' and (
                hasattr(provider, 'create_chat_completions') or 
                hasattr(provider, 'create_translation')
            )) or
            (provider_type == 'tts' and hasattr(provider, 'create_tts_completions')) or
            (provider_type == 'moderation' and hasattr(provider, 'create_moderation')) or
            (provider_type == 'transcription' and hasattr(provider, 'create_transcription')) or
            (provider_type == 'image' and hasattr(provider, 'create_image'))
        )
    ]
    
    if not allowed_providers:
        return None
    
    return random.choice(allowed_providers)
