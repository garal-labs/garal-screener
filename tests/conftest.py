"""
Fixtures compartidos para los tests de integración.
Usa SQLite en memoria para aislar completamente cada test.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.models import Base
from main import app

# SQLite en memoria con URI compartida para que todas las conexiones
# del mismo test vean las mismas tablas (sin esto cada conexión es una DB distinta)
SQLALCHEMY_TEST_URL = "sqlite:///file::memory:?cache=shared&uri=true"

engine_test = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False, "uri": True},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(autouse=True)
def setup_db():
    """Crea y destruye las tablas antes/después de cada test."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db_session():
    """Sesión de DB para fixtures que necesitan insertar datos directamente."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(setup_db):
    """TestClient con la DB en memoria inyectada vía override.
    init_db se parchea para que el lifespan no recree tablas en el engine de producción.
    """

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with patch("main.init_db"):  # evita que el lifespan toque el engine de producción
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()


AUTH_CLIENT_EMAIL = "fixture-user@example.com"
AUTH_CLIENT_PASSWORD = "fixture-password-123"


@pytest.fixture
def auth_client(client):
    """`client` con una sesión ya iniciada (cookie `access_token` seteada).

    Registra y loguea un usuario de prueba (`AUTH_CLIENT_EMAIL`). Suficiente
    para tests de login/logout/me; los escenarios owner-vs-foreign completos
    se cubren en la Fase 4 (PR3) con más de un usuario.
    """
    client.post(
        "/api/v1/auth/register",
        json={"email": AUTH_CLIENT_EMAIL, "password": AUTH_CLIENT_PASSWORD},
    )
    client.post(
        "/api/v1/auth/login",
        json={"email": AUTH_CLIENT_EMAIL, "password": AUTH_CLIENT_PASSWORD},
    )
    return client
