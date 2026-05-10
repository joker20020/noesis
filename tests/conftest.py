import pytest
import os


@pytest.fixture(autouse=True)
def env_setup():
    """Ensure .env is loaded for tests."""
    os.environ.setdefault("INFOCAP_LLM_API_KEY", "sk-test-dummy")
    os.environ.setdefault("INFOCAP_NEO4J_PASSWORD", "infocap123")
