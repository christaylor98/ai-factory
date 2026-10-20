"""Skip provider tests whose optional SDK is not installed.

Provider SDKs are extras (see pyproject.toml), so `pip install -e ".[dev]"` alone does not
install them. Tests that exercise a provider's SDK are skipped, with the extra to install
named in the reason, instead of failing on ImportError. Install `.[dev,all]` to run them.
"""
import importlib.util

import pytest

# (test file, class or test name or None for the whole file) -> (module, extra)
_REQUIRES = {
    ("test_anthropic_provider.py", None): ("anthropic", "anthropic"),
    ("test_gemini_provider.py", None): ("google.genai", "gemini"),
    ("test_local_provider.py", None): ("openai", "local"),
    ("test_openai_provider.py", None): ("openai", "openai"),
    ("test_openrouter_provider.py", None): ("openai", "openrouter"),
    ("test_provider_contract.py", "TestGeminiProviderContract"): ("google.genai", "gemini"),
    ("test_provider_contract.py", "TestOpenRouterProviderContract"): ("openai", "openrouter"),
    ("test_system_and_schema.py", "test_the_openai_family_sends_them"): ("openai", "openai"),
}


def _installed(module):
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:  # parent package missing, e.g. `google` for google.genai
        return False


def pytest_collection_modifyitems(config, items):
    for item in items:
        filename = item.path.name
        names = {None, item.name.split("[")[0]}
        if item.cls is not None:
            names.add(item.cls.__name__)
        for (target_file, target_name), (module, extra) in _REQUIRES.items():
            if filename == target_file and target_name in names and not _installed(module):
                item.add_marker(pytest.mark.skip(
                    reason=f"{module} not installed: pip install -e \".[dev,{extra}]\""
                ))
                break
