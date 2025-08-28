import os
import pytest
import httpx

@pytest.fixture(scope="session")
def base_url():
    return os.getenv("API_BASE_URL", "http://localhost:8081")

@pytest.fixture(scope="session")
def api_key():
    return os.getenv("API_KEY", "dev")

@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url, timeout=5.0) as c:
        yield c
