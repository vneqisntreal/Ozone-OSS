
import importlib
import inspect
import os
import sys
import os
import importlib
from typing import Dict, Any
import sys

import httpx

from utils.providers.base import BaseProvider

def discover_providers(provider_directory: str) -> Dict[str, Any]:

    provider_path = os.path.abspath(provider_directory)
    if provider_path not in sys.path:
        sys.path.insert(0, provider_path)
        
    providers = {}

    for filename in os.listdir(provider_directory):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"providers.{module_name}")
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseProvider) and obj != BaseProvider:
                        provider_name = name.lower().replace(" ", "_").replace("-", "_")
                        providers[provider_name] = obj
            except Exception as e:
                print(f"Error loading provider from {filename}: {e}")
    return providers

def initialize_providers(async_client: httpx.AsyncClient, provider_directory: str) -> Dict[str, BaseProvider]:

    provider_classes = discover_providers(provider_directory)
    initialized_providers = {}
    for name, provider_class in provider_classes.items():
        try:
            initialized_providers[name] = provider_class(async_client)
        except Exception as e:
            print(f"Error initializing provider {name}: {e}")
            print(f"Error initializing provider {name}: {e}")
    return initialized_providers
