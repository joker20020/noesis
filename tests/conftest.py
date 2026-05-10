import pytest
import os


@pytest.fixture(autouse=True)
def env_setup():
    """Ensure .env is loaded for tests."""
    os.environ.setdefault("NOESIS_LLM_API_KEY", "sk-test-dummy")
    os.environ.setdefault("NOESIS_NEO4J_PASSWORD", "noesis123")
