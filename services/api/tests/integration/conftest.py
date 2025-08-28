import os, pytest

from sqlalchemy import create_engine


TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+psycopg://postgres:postgres@postgres-test:5432/game_test",
)


@pytest.fixture(autouse=True, scope="session")
def _celery_eager():
    os.environ["CELERY_EAGER"] = os.getenv("CELERY_EAGER","true")
    yield

def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: db/celery eager tests")

@pytest.fixture(scope="session", autouse=True)
def bind_test_engine():
    from app import db as app_db

    test_engine = create_engine(TEST_DB_URL, future=True)
    original_engine = getattr(app_db, "engine", None)
    app_db.engine = test_engine
    os.environ["DB_DSN"] = TEST_DB_URL

    yield

    app_db.engine.dispose()
    if original_engine is not None:
        app_db.engine = original_engine