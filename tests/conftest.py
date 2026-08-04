import os
from pathlib import Path
os.environ["ITSM_DATABASE_URL"] = "sqlite:///./data/test_itsm.db"
os.environ["ITSM_SECRET_KEY"] = "test-secret-key-that-is-long-enough"
os.environ["ITSM_LOGIN_ATTEMPTS"] = "5"

import pytest
from fastapi.testclient import TestClient
from itsm.database import Base, engine
from itsm.seed import seed
from itsm.main import app


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.drop_all(engine); seed(reset=False)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    Path("data/test_itsm.db").unlink(missing_ok=True)


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=True) as value:
        yield value


def login_as(client, username="admin", password="ChangeMe!2026"):
    result = client.post("/api/auth/login", json={"username":username,"password":password})
    assert result.status_code == 200, result.text
    return result.json()["csrf_token"]


@pytest.fixture()
def admin(client):
    csrf=login_as(client,"admin")
    client.headers.update({"X-CSRF-Token":csrf})
    return client
