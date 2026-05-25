"""
Tests unitarios para app/services/calculos.py

Se usan SimpleNamespace para simular objetos ORM sin necesidad de DB.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.calculos import (
    VentaInvalidaError,
    agrupar_por_campo,
    calcular_plusvalia_latente,
    calcular_posicion_fifo,
    calcular_resumen_cartera,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def compra(id, fecha, cantidad, precio, comision=0.0, tipo_cambio=None):
    return SimpleNamespace(
        id=id,
        tipo="compra",
        fecha=fecha,
        cantidad=cantidad,
        precio=precio,
        comision=comision,
        tipo_cambio=tipo_cambio,
    )


def venta(id, fecha, cantidad, precio, comision=0.0, tipo_cambio=None):
    return SimpleNamespace(
        id=id,
        tipo="venta",
        fecha=fecha,
        cantidad=cantidad,
        precio=precio,
        comision=comision,
        tipo_cambio=tipo_cambio,
    )


D1 = date(2024, 1, 1)
D2 = date(2024, 2, 1)
D3 = date(2024, 3, 1)


# ── calcular_posicion_fifo ────────────────────────────────────────────────────


class TestCalcularPosicionFifo:
    def test_compra_unica(self):
        movs = [compra(1, D1, 10, 100.0)]
        r = calcular_posicion_fifo(movs)
        assert r["cantidad_actual"] == 10
        assert r["coste_total"] == 1000.0
        assert r["precio_medio"] == 100.0
        assert r["plusvalia_realizada"] == 0.0

    def test_multiples_compras(self):
        movs = [
            compra(1, D1, 10, 100.0),
            compra(2, D2, 5, 200.0),
        ]
        r = calcular_posicion_fifo(movs)
        assert r["cantidad_actual"] == 15
        assert r["coste_total"] == 2000.0  # 10*100 + 5*200
        assert r["precio_medio"] == pytest.approx(133.3333, abs=0.001)

    def test_venta_parcial_fifo(self):
        movs = [
            compra(1, D1, 10, 100.0),  # lote a 100
            compra(2, D2, 5, 200.0),  # lote a 200
            venta(3, D3, 6, 150.0),  # vende 6 del primer lote (FIFO)
        ]
        r = calcular_posicion_fifo(movs)
        # Quedan 4 del lote a 100 + 5 a 200
        assert r["cantidad_actual"] == pytest.approx(9, abs=1e-6)
        assert r["coste_total"] == pytest.approx(4 * 100 + 5 * 200, abs=0.01)
        # P/L realizada: ingreso=6*150=900, coste=6*100=600 → +300
        assert r["plusvalia_realizada"] == pytest.approx(300.0, abs=0.01)

    def test_venta_total(self):
        movs = [
            compra(1, D1, 10, 100.0),
            venta(2, D2, 10, 120.0),
        ]
        r = calcular_posicion_fifo(movs)
        assert r["cantidad_actual"] == 0
        assert r["coste_total"] == 0.0
        assert r["plusvalia_realizada"] == pytest.approx(200.0)  # 10*(120-100)

    def test_venta_invalida_lanza_error(self):
        movs = [
            compra(1, D1, 5, 100.0),
            venta(2, D2, 10, 100.0),  # vende más de lo comprado
        ]
        with pytest.raises(VentaInvalidaError):
            calcular_posicion_fifo(movs)

    def test_orden_deterministico_mismo_dia(self):
        """Dos compras en el mismo día → la de id menor se consume primero."""
        movs = [
            compra(2, D1, 5, 200.0),  # id mayor, precio mayor
            compra(1, D1, 5, 100.0),  # id menor, precio menor
            venta(3, D2, 5, 150.0),  # debe consumir el id=1 (100€) primero
        ]
        r = calcular_posicion_fifo(movs)
        # P/L = 5*(150-100) = 250
        assert r["plusvalia_realizada"] == pytest.approx(250.0, abs=0.01)

    def test_compra_con_comision(self):
        movs = [compra(1, D1, 10, 100.0, comision=10.0)]
        r = calcular_posicion_fifo(movs)
        # Precio unitario = 100 + 10/10 = 101
        assert r["precio_medio"] == pytest.approx(101.0)
        assert r["coste_total"] == pytest.approx(1010.0)

    def test_venta_con_comision(self):
        movs = [
            compra(1, D1, 10, 100.0),
            venta(2, D2, 10, 120.0, comision=5.0),
        ]
        r = calcular_posicion_fifo(movs)
        # ingreso = 10*120 - 5 = 1195, coste = 10*100 = 1000, P/L = 195
        assert r["plusvalia_realizada"] == pytest.approx(195.0, abs=0.01)

    def test_tipo_cambio_aplicado_en_compra(self):
        # Precio en USD con tipo_cambio=1.1 (1 EUR = 1.1 USD → precio_eur = precio/tc?)
        # _precio_en_eur = precio * tipo_cambio → 100 * 1.1 = 110 EUR por accion
        movs = [compra(1, D1, 10, 100.0, tipo_cambio=1.1)]
        r = calcular_posicion_fifo(movs)
        assert r["precio_medio"] == pytest.approx(110.0)

    def test_tipo_cambio_none_equivale_a_1(self):
        movs_con_none = [compra(1, D1, 10, 100.0, tipo_cambio=None)]
        movs_sin_tc = [compra(2, D1, 10, 100.0)]
        r1 = calcular_posicion_fifo(movs_con_none)
        r2 = calcular_posicion_fifo(movs_sin_tc)
        assert r1["precio_medio"] == r2["precio_medio"]

    def test_lista_vacia(self):
        r = calcular_posicion_fifo([])
        assert r["cantidad_actual"] == 0
        assert r["coste_total"] == 0.0
        assert r["plusvalia_realizada"] == 0.0


# ── calcular_plusvalia_latente ────────────────────────────────────────────────


class TestCalcularPlusvalia:
    def _posicion(self, cantidad=10, coste=1000.0, plusvalia_realizada=0.0):
        return {
            "cantidad_actual": cantidad,
            "coste_total": coste,
            "precio_medio": coste / cantidad if cantidad else 0,
            "plusvalia_realizada": plusvalia_realizada,
        }

    def test_ganancia(self):
        pos = self._posicion(10, 1000.0)
        r = calcular_plusvalia_latente(pos, 120.0)
        assert r["valor_actual"] == 1200.0
        assert r["plusvalia_latente"] == 200.0
        assert r["rentabilidad_pct"] == pytest.approx(20.0)

    def test_perdida(self):
        pos = self._posicion(10, 1000.0)
        r = calcular_plusvalia_latente(pos, 80.0)
        assert r["plusvalia_latente"] == -200.0
        assert r["rentabilidad_pct"] == pytest.approx(-20.0)

    def test_plusvalia_total_incluye_realizada(self):
        pos = self._posicion(10, 1000.0, plusvalia_realizada=50.0)
        r = calcular_plusvalia_latente(pos, 100.0)  # sin ganancia latente
        # plusvalia_total = latente(0) + realizada(50) = 50
        assert r["plusvalia_total"] == pytest.approx(50.0)

    def test_coste_cero_no_divide_por_cero(self):
        pos = self._posicion(0, 0.0)
        r = calcular_plusvalia_latente(pos, 100.0)
        assert r["rentabilidad_pct"] == 0.0


# ── calcular_resumen_cartera ──────────────────────────────────────────────────


class TestCalcularResumen:
    def _pos(
        self,
        valor_actual=None,
        coste_total=1000.0,
        plusvalia_latente=None,
        plusvalia_realizada=0.0,
        cantidad_actual=10,
    ):
        return {
            "valor_actual": valor_actual,
            "coste_total": coste_total,
            "plusvalia_latente": plusvalia_latente,
            "plusvalia_realizada": plusvalia_realizada,
            "cantidad_actual": cantidad_actual,
        }

    def test_resumen_con_precios(self):
        posiciones = [
            self._pos(
                valor_actual=1200.0,
                coste_total=1000.0,
                plusvalia_latente=200.0,
                plusvalia_realizada=50.0,
            ),
            self._pos(
                valor_actual=800.0,
                coste_total=1000.0,
                plusvalia_latente=-200.0,
                plusvalia_realizada=0.0,
            ),
        ]
        r = calcular_resumen_cartera(posiciones)
        assert r["valor_total"] == 2000.0
        assert r["coste_total"] == 2000.0
        assert r["plusvalia_latente"] == 0.0
        assert r["plusvalia_realizada"] == 50.0
        assert r["plusvalia_total"] == 50.0
        assert r["num_posiciones"] == 2

    def test_resumen_sin_precios(self):
        """Sin precio actual, valor_total usa coste_total como fallback."""
        posiciones = [self._pos(valor_actual=None, coste_total=1000.0, plusvalia_latente=None)]
        r = calcular_resumen_cartera(posiciones)
        assert r["valor_total"] == 1000.0  # fallback a coste_total
        assert r["plusvalia_latente"] == 0.0

    def test_resumen_vacio(self):
        r = calcular_resumen_cartera([])
        assert r["valor_total"] == 0.0
        assert r["rentabilidad_pct"] == 0.0
        assert r["num_posiciones"] == 0

    def test_rentabilidad_usa_plusvalia_total(self):
        """La rentabilidad debe basarse en plusvalia_total (latente + realizada)."""
        posiciones = [
            self._pos(
                valor_actual=1000.0,
                coste_total=1000.0,
                plusvalia_latente=0.0,  # sin ganancia latente
                plusvalia_realizada=100.0,  # pero sí realizada
            )
        ]
        r = calcular_resumen_cartera(posiciones)
        # rentabilidad = (0+100)/1000 * 100 = 10%
        assert r["rentabilidad_pct"] == pytest.approx(10.0)


# ── agrupar_por_campo ─────────────────────────────────────────────────────────


class TestAgruparPorCampo:
    def test_agrupacion_basica(self):
        posiciones = [
            {"sector": "Tecnología", "valor_actual": 1000.0, "coste_total": 800.0},
            {"sector": "Tecnología", "valor_actual": 500.0, "coste_total": 400.0},
            {"sector": "Salud", "valor_actual": 300.0, "coste_total": 200.0},
        ]
        r = agrupar_por_campo(posiciones, "sector")
        assert r[0]["nombre"] == "Tecnología"
        assert r[0]["valor"] == 1500.0
        assert r[1]["nombre"] == "Salud"

    def test_campo_none_va_a_sin_clasificar(self):
        posiciones = [
            {"sector": None, "valor_actual": 500.0, "coste_total": 400.0},
        ]
        r = agrupar_por_campo(posiciones, "sector")
        assert r[0]["nombre"] == "Sin clasificar"

    def test_pesos_suman_100(self):
        posiciones = [
            {"tipo": "accion", "valor_actual": 600.0, "coste_total": 500.0},
            {"tipo": "etf", "valor_actual": 400.0, "coste_total": 300.0},
        ]
        r = agrupar_por_campo(posiciones, "tipo")
        total_pct = sum(g["peso_pct"] for g in r)
        assert total_pct == pytest.approx(100.0, abs=0.1)

    def test_sin_valor_actual_usa_coste(self):
        posiciones = [
            {"sector": "Energía", "valor_actual": None, "coste_total": 700.0},
        ]
        r = agrupar_por_campo(posiciones, "sector")
        assert r[0]["valor"] == 700.0

    def test_lista_vacia(self):
        r = agrupar_por_campo([], "sector")
        assert r == []

    def test_orden_descendente_por_valor(self):
        posiciones = [
            {"pais": "España", "valor_actual": 100.0, "coste_total": 80.0},
            {"pais": "EEUU", "valor_actual": 900.0, "coste_total": 700.0},
        ]
        r = agrupar_por_campo(posiciones, "pais")
        assert r[0]["nombre"] == "EEUU"
