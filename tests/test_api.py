"""
Tests de integración para los endpoints de la API.
Todos los tests usan SQLite en memoria (ver conftest.py).
Las llamadas externas (FMP, Anthropic) se mockean.
"""

import logging
import re
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app import models
from app.auth.security import generate_reset_token

BASE = "/api/v1"

# ── Carteras ──────────────────────────────────────────────────────────────────


class TestCarteras:
    def test_crear_cartera(self, client):
        r = client.post(f"{BASE}/carteras", json={"nombre": "Mi cartera"})
        assert r.status_code == 200
        data = r.json()
        assert data["nombre"] == "Mi cartera"
        assert "id" in data

    def test_crear_cartera_con_descripcion(self, client):
        r = client.post(
            f"{BASE}/carteras",
            json={"nombre": "Cartera 2", "descripcion": "Inversiones largo plazo"},
        )
        assert r.status_code == 200
        assert r.json()["descripcion"] == "Inversiones largo plazo"

    def test_listar_carteras_vacio(self, client):
        r = client.get(f"{BASE}/carteras")
        assert r.status_code == 200
        assert r.json() == []

    def test_listar_carteras_con_datos(self, client):
        client.post(f"{BASE}/carteras", json={"nombre": "A"})
        client.post(f"{BASE}/carteras", json={"nombre": "B"})
        r = client.get(f"{BASE}/carteras")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_eliminar_cartera(self, client):
        cartera_id = client.post(f"{BASE}/carteras", json={"nombre": "X"}).json()["id"]
        r = client.delete(f"{BASE}/carteras/{cartera_id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Ya no existe
        carteras = client.get(f"{BASE}/carteras").json()
        assert len(carteras) == 0

    def test_eliminar_cartera_inexistente(self, client):
        r = client.delete(f"{BASE}/carteras/9999")
        assert r.status_code == 404


# ── Movimientos ───────────────────────────────────────────────────────────────

MOCK_IA = {
    "nombre": "Apple Inc.",
    "tipo": "accion",
    "sector": "Tecnología",
    "pais": "Estados Unidos",
    "moneda": "USD",
    "exchange": "NASDAQ",
}


def mock_precios(fx_rates=None):
    """Contexto que parchea las llamadas externas de precios/yfinance.

    Args:
        fx_rates: dict opcional con tipos de cambio a simular, ej. {"USD": 1.085}.
            Por defecto {} → fx fallback 1.0 para todas las monedas (comportamiento anterior).
    """
    if fx_rates is None:
        fx_rates = {}

    stack = ExitStack()
    stack.enter_context(
        patch.multiple(
            "app.routers.movimientos.precios",
            enriquecer_por_isin=AsyncMock(return_value={**MOCK_IA, "ticker": "AAPL"}),
        )
    )
    stack.enter_context(
        patch.multiple(
            "app.routers.posiciones.precios",
            obtener_precios_batch=AsyncMock(return_value={"AAPL": 150.0}),
            obtener_fx_batch=AsyncMock(return_value=fx_rates),
            obtener_fx_by_date=AsyncMock(return_value=1.085),
        )
    )
    return stack


class TestMovimientos:
    def _cartera_id(self, client):
        return client.post(f"{BASE}/carteras", json={"nombre": "Test"}).json()["id"]

    def test_crear_movimiento_compra(self, client):
        cartera_id = self._cartera_id(client)
        with mock_precios():
            r = client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 180.0,
                    "comision": 5.0,
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["tipo"] == "compra"
        assert data["instrumento"]["isin"] == "US0378331005"

    def test_isin_se_normaliza_a_mayusculas(self, client):
        cartera_id = self._cartera_id(client)
        with mock_precios():
            r = client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "us0378331005",  # en minúsculas
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 5,
                    "precio": 180.0,
                },
            )
        assert r.status_code == 200
        assert r.json()["instrumento"]["isin"] == "US0378331005"

    def test_crear_movimiento_cartera_inexistente(self, client):
        with mock_precios():
            r = client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": 9999,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 180.0,
                },
            )
        assert r.status_code == 404

    def test_venta_valida(self, client):
        cartera_id = self._cartera_id(client)
        with mock_precios():
            # Compra primero
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 180.0,
                },
            )
            # Luego vende parte
            r = client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "venta",
                    "fecha": "2024-06-01",
                    "cantidad": 5,
                    "precio": 200.0,
                },
            )
        assert r.status_code == 200

    def test_venta_supera_stock_retorna_400(self, client):
        cartera_id = self._cartera_id(client)
        with mock_precios():
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 5,
                    "precio": 180.0,
                },
            )
            r = client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "venta",
                    "fecha": "2024-06-01",
                    "cantidad": 10,  # más de lo comprado
                    "precio": 200.0,
                },
            )
        assert r.status_code == 400

    def test_listar_movimientos(self, client):
        cartera_id = self._cartera_id(client)
        with mock_precios():
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 180.0,
                },
            )
        r = client.get(f"{BASE}/carteras/{cartera_id}/movimientos")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_listar_movimientos_cartera_inexistente(self, client):
        r = client.get(f"{BASE}/carteras/9999/movimientos")
        assert r.status_code == 404

    def test_eliminar_movimiento(self, client):
        cartera_id = self._cartera_id(client)
        with mock_precios():
            mov_id = client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 180.0,
                },
            ).json()["id"]
        r = client.delete(f"{BASE}/movimientos/{mov_id}")
        assert r.status_code == 200

    def test_eliminar_movimiento_inexistente(self, client):
        r = client.delete(f"{BASE}/movimientos/9999")
        assert r.status_code == 404

    def test_tipo_movimiento_invalido_retorna_422(self, client):
        cartera_id = self._cartera_id(client)
        r = client.post(
            f"{BASE}/movimientos",
            json={
                "cartera_id": cartera_id,
                "isin": "US0378331005",
                "tipo": "transferencia",  # inválido
                "fecha": "2024-01-15",
                "cantidad": 10,
                "precio": 180.0,
            },
        )
        assert r.status_code == 422

    def test_comision_negativa_retorna_422(self, client):
        cartera_id = self._cartera_id(client)
        r = client.post(
            f"{BASE}/movimientos",
            json={
                "cartera_id": cartera_id,
                "isin": "US0378331005",
                "tipo": "compra",
                "fecha": "2024-01-15",
                "cantidad": 10,
                "precio": 180.0,
                "comision": -5.0,  # inválida
            },
        )
        assert r.status_code == 422


# ── Resumen de cartera ────────────────────────────────────────────────────────


class TestResumenCartera:
    def _setup_cartera_con_compra(self, client):
        cartera_id = client.post(f"{BASE}/carteras", json={"nombre": "Test"}).json()[
            "id"
        ]
        with mock_precios():
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 100.0,
                },
            )
        return cartera_id

    def test_resumen_con_precio(self, client):
        cartera_id = self._setup_cartera_con_compra(client)
        with mock_precios():
            r = client.get(f"{BASE}/carteras/{cartera_id}/resumen")
        assert r.status_code == 200
        data = r.json()
        assert data["num_posiciones"] == 1
        assert data["valor_total"] == pytest.approx(1500.0)  # 10 * 150 (precio mock)
        assert data["coste_total"] == pytest.approx(1000.0)

    def test_resumen_cartera_inexistente(self, client):
        with mock_precios():
            r = client.get(f"{BASE}/carteras/9999/resumen")
        assert r.status_code == 404

    def test_resumen_posicion_cerrada_no_pierde_plusvalia(self, client):
        """P/L realizada de posiciones cerradas debe aparecer en el resumen."""
        cartera_id = client.post(f"{BASE}/carteras", json={"nombre": "Test"}).json()[
            "id"
        ]
        with mock_precios():
            # Compra y venta total → posición cerrada
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-01",
                    "cantidad": 10,
                    "precio": 100.0,
                },
            )
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "venta",
                    "fecha": "2024-06-01",
                    "cantidad": 10,
                    "precio": 120.0,
                },
            )
            r = client.get(f"{BASE}/carteras/{cartera_id}/resumen")
        assert r.status_code == 200
        data = r.json()
        # La posición está cerrada → no aparece en posiciones
        assert data["num_posiciones"] == 0
        # Pero la plusvalía realizada sí debe estar: 10*(120-100) = 200
        assert data["plusvalia_realizada"] == pytest.approx(200.0, abs=0.01)


# ── Instrumentos ──────────────────────────────────────────────────────────────


class TestInstrumentos:
    def test_patch_instrumento(self, client):
        cartera_id = client.post(f"{BASE}/carteras", json={"nombre": "Test"}).json()[
            "id"
        ]
        with mock_precios():
            mov = client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 5,
                    "precio": 180.0,
                },
            ).json()
        instrumento_id = mov["instrumento"]["id"]
        r = client.patch(
            f"{BASE}/instrumentos/{instrumento_id}",
            json={
                "sector": "Consumo Básico",
                "pais": "Canadá",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["sector"] == "Consumo Básico"
        assert data["pais"] == "Canadá"

    def test_patch_instrumento_inexistente(self, client):
        r = client.patch(f"{BASE}/instrumentos/9999", json={"sector": "X"})
        assert r.status_code == 404

    def test_listar_instrumentos(self, client):
        cartera_id = client.post(f"{BASE}/carteras", json={"nombre": "Test"}).json()[
            "id"
        ]
        with mock_precios():
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 5,
                    "precio": 180.0,
                },
            )
        r = client.get(f"{BASE}/instrumentos")
        assert r.status_code == 200
        assert len(r.json()) == 1


# ── Backfill FX ───────────────────────────────────────────────────────────────


class TestBackfillFx:
    def _setup(self, client):
        """Crea cartera con un movimiento USD sin tipo_cambio."""
        cartera_id = client.post(f"{BASE}/carteras", json={"nombre": "FX Test"}).json()[
            "id"
        ]
        with mock_precios():
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 150.0,
                    # sin tipo_cambio → queda en NULL
                },
            )
        return cartera_id

    def test_backfill_actualiza_movimientos_usd(self, client):
        cartera_id = self._setup(client)
        with mock_precios():
            r = client.post(f"{BASE}/carteras/{cartera_id}/backfill-fx")
        assert r.status_code == 200
        data = r.json()
        assert data["actualizados"] == 1
        assert data["omitidos"] == 0

    def test_backfill_cartera_inexistente_retorna_404(self, client):
        r = client.post(f"{BASE}/carteras/9999/backfill-fx")
        assert r.status_code == 404

    def test_backfill_no_toca_movimientos_eur(self, client):
        """Movimientos de instrumentos EUR no deben modificarse."""
        cartera_id = client.post(
            f"{BASE}/carteras", json={"nombre": "EUR Test"}
        ).json()["id"]
        mock_eur = {**MOCK_IA, "moneda": "EUR", "ticker": "SAN"}
        with ExitStack() as stack:
            stack.enter_context(
                patch.multiple(
                    "app.routers.movimientos.precios",
                    enriquecer_por_isin=AsyncMock(return_value=mock_eur),
                )
            )
            stack.enter_context(
                patch.multiple(
                    "app.routers.posiciones.precios",
                    obtener_precios_batch=AsyncMock(return_value={"SAN": 4.0}),
                    obtener_fx_batch=AsyncMock(return_value={}),
                    obtener_fx_by_date=AsyncMock(return_value=1.085),
                )
            )
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "ES0113900J37",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 100,
                    "precio": 3.5,
                },
            )
            r = client.post(f"{BASE}/carteras/{cartera_id}/backfill-fx")
        assert r.status_code == 200
        data = r.json()
        # No hay movimientos USD/no-EUR → nada que actualizar
        assert data["actualizados"] == 0
        assert data["omitidos"] == 0

    def test_backfill_omite_cuando_yfinance_sin_datos(self, client):
        cartera_id = self._setup(client)
        with ExitStack() as stack:
            stack.enter_context(
                patch.multiple(
                    "app.routers.posiciones.precios",
                    obtener_precios_batch=AsyncMock(return_value={"AAPL": 150.0}),
                    obtener_fx_batch=AsyncMock(return_value={}),
                    obtener_fx_by_date=AsyncMock(return_value=None),  # sin datos
                )
            )
            r = client.post(f"{BASE}/carteras/{cartera_id}/backfill-fx")
        assert r.status_code == 200
        data = r.json()
        assert data["actualizados"] == 0
        assert data["omitidos"] == 1


# ── Dual-currency en resumen ──────────────────────────────────────────────────


class TestResumenDualCurrency:
    def _setup_usd(self, client, fx_rates=None):
        cartera_id = client.post(
            f"{BASE}/carteras", json={"nombre": "USD Test"}
        ).json()["id"]
        with mock_precios(fx_rates=fx_rates or {}):
            client.post(
                f"{BASE}/movimientos",
                json={
                    "cartera_id": cartera_id,
                    "isin": "US0378331005",
                    "tipo": "compra",
                    "fecha": "2024-01-15",
                    "cantidad": 10,
                    "precio": 150.0,
                    "tipo_cambio": 1.10,
                },
            )
        return cartera_id

    def test_resumen_incluye_campos_dual_currency(self, client):
        cartera_id = self._setup_usd(client, fx_rates={"USD": 1.05})
        with mock_precios(fx_rates={"USD": 1.05}):
            r = client.get(f"{BASE}/carteras/{cartera_id}/resumen")
        assert r.status_code == 200
        pos = r.json()["posiciones"][0]
        assert "valor_actual_eur" in pos
        assert "valor_actual_nativo" in pos
        assert "moneda_nativa" in pos
        assert "fx_actual" in pos

    def test_moneda_nativa_correcta(self, client):
        cartera_id = self._setup_usd(client, fx_rates={"USD": 1.05})
        with mock_precios(fx_rates={"USD": 1.05}):
            r = client.get(f"{BASE}/carteras/{cartera_id}/resumen")
        pos = r.json()["posiciones"][0]
        assert pos["moneda_nativa"] == "USD"

    def test_valor_actual_es_alias_de_valor_actual_eur(self, client):
        """valor_actual debe ser igual a valor_actual_eur (backwards-compat)."""
        cartera_id = self._setup_usd(client, fx_rates={"USD": 1.05})
        with mock_precios(fx_rates={"USD": 1.05}):
            r = client.get(f"{BASE}/carteras/{cartera_id}/resumen")
        pos = r.json()["posiciones"][0]
        assert pos["valor_actual"] == pos["valor_actual_eur"]

    def test_valor_actual_nativo_en_moneda_nativa(self, client):
        """valor_actual_nativo = precio_actual * cantidad (sin conversión FX)."""
        cartera_id = self._setup_usd(client, fx_rates={"USD": 1.05})
        with mock_precios(fx_rates={"USD": 1.05}):
            r = client.get(f"{BASE}/carteras/{cartera_id}/resumen")
        pos = r.json()["posiciones"][0]
        # precio mock = 150, cantidad = 10 → 1500 USD
        assert pos["valor_actual_nativo"] == pytest.approx(1500.0)

    def test_valor_actual_eur_aplica_fx(self, client):
        """valor_actual_eur = precio_nativo / fx * cantidad."""
        cartera_id = self._setup_usd(client, fx_rates={"USD": 1.05})
        with mock_precios(fx_rates={"USD": 1.05}):
            r = client.get(f"{BASE}/carteras/{cartera_id}/resumen")
        pos = r.json()["posiciones"][0]
        # precio mock=150, fx=1.05, cantidad=10 → 150/1.05*10 ≈ 1428.57
        assert pos["valor_actual_eur"] == pytest.approx(150.0 / 1.05 * 10, abs=0.01)


# ── Health check ──────────────────────────────────────────────────────────────


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────────────────

AUTH_BASE = f"{BASE}/auth"


class TestAuth:
    def test_register_login_me(self, client):
        r = client.post(
            f"{AUTH_BASE}/register",
            json={"email": "new-user@example.com", "password": "supersecret1"},
        )
        assert r.status_code == 201
        assert r.json()["email"] == "new-user@example.com"

        r = client.post(
            f"{AUTH_BASE}/login",
            json={"email": "new-user@example.com", "password": "supersecret1"},
        )
        assert r.status_code == 200
        assert "access_token" in r.cookies

        r = client.get(f"{AUTH_BASE}/me")
        assert r.status_code == 200
        assert r.json()["email"] == "new-user@example.com"

    def test_register_duplicate_email_rejected(self, client):
        payload = {"email": "dup@example.com", "password": "supersecret1"}
        client.post(f"{AUTH_BASE}/register", json=payload)
        r = client.post(f"{AUTH_BASE}/register", json=payload)
        assert r.status_code == 400

    def test_register_password_length_boundaries(self, client):
        r_short = client.post(
            f"{AUTH_BASE}/register",
            json={"email": "short-pass@example.com", "password": "1234567"},
        )
        r_long = client.post(
            f"{AUTH_BASE}/register",
            json={"email": "long-pass@example.com", "password": "x" * 73},
        )
        assert r_short.status_code == 422
        assert r_long.status_code == 422

    def test_register_invalid_email_format_returns_422(self, client):
        r = client.post(
            f"{AUTH_BASE}/register",
            json={"email": "not-an-email", "password": "supersecret1"},
        )
        assert r.status_code == 422

    def test_login_wrong_password_rejected(self, client):
        client.post(
            f"{AUTH_BASE}/register",
            json={"email": "wrongpass@example.com", "password": "supersecret1"},
        )
        r = client.post(
            f"{AUTH_BASE}/login",
            json={"email": "wrongpass@example.com", "password": "not-the-password"},
        )
        assert r.status_code == 401
        assert "access_token" not in r.cookies

    def test_login_unknown_email_rejected(self, client):
        r = client.post(
            f"{AUTH_BASE}/login",
            json={"email": "ghost@example.com", "password": "whatever123"},
        )
        assert r.status_code == 401

    def test_me_without_session_rejected(self, client):
        r = client.get(f"{AUTH_BASE}/me")
        assert r.status_code == 401

    def test_logout_clears_cookie(self, auth_client):
        r = auth_client.get(f"{AUTH_BASE}/me")
        assert r.status_code == 200

        r = auth_client.post(f"{AUTH_BASE}/logout")
        assert r.status_code == 200

        r = auth_client.get(f"{AUTH_BASE}/me")
        assert r.status_code == 401

    def test_logout_without_session_is_safe(self, client):
        r = client.post(f"{AUTH_BASE}/logout")
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestPasswordReset:
    EMAIL = "reset-me@example.com"
    PASSWORD = "original-password1"

    def _register(self, client):
        client.post(
            f"{AUTH_BASE}/register",
            json={"email": self.EMAIL, "password": self.PASSWORD},
        )

    def _captured_token(self, client, caplog):
        """Registers the test user and captures the dev-stub reset token from logs."""
        self._register(client)
        caplog.set_level(logging.INFO, logger="app.auth.router")
        r = client.post(f"{AUTH_BASE}/forgot-password", json={"email": self.EMAIL})
        assert r.status_code == 200
        match = re.search(r"token=(\S+)", caplog.text)
        assert match, "expected the dev stub to log a reset token"
        return match.group(1)

    def test_forgot_password_does_not_leak_existence(self, client):
        self._register(client)
        r_known = client.post(
            f"{AUTH_BASE}/forgot-password", json={"email": self.EMAIL}
        )
        r_unknown = client.post(
            f"{AUTH_BASE}/forgot-password", json={"email": "nobody@example.com"}
        )
        assert r_known.status_code == 200
        assert r_unknown.status_code == 200
        assert r_known.json() == r_unknown.json()

    def test_reset_password_success_and_single_use(self, client, caplog):
        token = self._captured_token(client, caplog)

        r = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": token, "new_password": "brand-new-password1"},
        )
        assert r.status_code == 200

        # Old password no longer works, new one does.
        r = client.post(
            f"{AUTH_BASE}/login",
            json={"email": self.EMAIL, "password": self.PASSWORD},
        )
        assert r.status_code == 401
        r = client.post(
            f"{AUTH_BASE}/login",
            json={"email": self.EMAIL, "password": "brand-new-password1"},
        )
        assert r.status_code == 200

        # Token is single-use: reusing it fails.
        r = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": token, "new_password": "another-password1"},
        )
        assert r.status_code == 400

    def test_reset_password_garbage_token_rejected(self, client):
        self._register(client)
        r = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": "not-a-real-token", "new_password": "whatever-new-1"},
        )
        assert r.status_code == 400

    def test_reset_password_expired_token_rejected(self, client, db_session):
        self._register(client)
        user = (
            db_session.query(models.User)
            .filter(models.User.email == self.EMAIL)
            .first()
        )
        assert user is not None

        raw_token, token_hash = generate_reset_token()
        db_session.add(
            models.PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        db_session.commit()

        r = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": raw_token, "new_password": "new-password-123"},
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "Invalid, expired, or already-used token"
