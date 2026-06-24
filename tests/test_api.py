"""
Tests de integración para los endpoints de la API.
Todos los tests usan SQLite en memoria (ver conftest.py).
Las llamadas externas (FMP, Anthropic) se mockean.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

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


def mock_precios():
    """Contexto que parchea las llamadas externas de precios/yfinance.
    Tras la separación de api.py, precios se usa en movimientos.py y posiciones.py.
    """
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


# ── Health check ──────────────────────────────────────────────────────────────


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
