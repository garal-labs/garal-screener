"""
Tests unitarios para app/services/precios.py

Las llamadas a yfinance se mockean via unittest.mock.
Las llamadas a httpx (OpenFIGI) se mockean con AsyncMock.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import pandas as pd

from app.services.precios import (
    buscar_ticker_por_isin,
    obtener_fx,
    obtener_fx_batch,
    obtener_fx_by_date,
    obtener_precio_actual,
    obtener_precios_batch,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def mock_httpx_response(json_data, status_code=200):
    """Construye un mock de httpx.Response."""
    response = MagicMock()
    response.json.return_value = json_data
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    return response


# ── obtener_precio_actual ─────────────────────────────────────────────────────


class TestObtenerPrecioActual:
    @pytest.mark.asyncio
    async def test_devuelve_precio(self):
        perfil = {"precio": 150.0, "nombre": "Apple", "tipo": "accion"}
        with patch("app.services.precios._obtener_info_yfinance", return_value=perfil):
            precio = await obtener_precio_actual("AAPL")
        assert precio == 150.0

    @pytest.mark.asyncio
    async def test_devuelve_none_cuando_yfinance_falla(self):
        with patch("app.services.precios._obtener_info_yfinance", return_value=None):
            precio = await obtener_precio_actual("TICKER_INVALIDO")
        assert precio is None

    @pytest.mark.asyncio
    async def test_ticker_vacio_devuelve_none(self):
        precio = await obtener_precio_actual("")
        assert precio is None

    @pytest.mark.asyncio
    async def test_perfil_sin_precio_devuelve_none(self):
        perfil = {"nombre": "Sin precio", "tipo": "accion", "precio": None}
        with patch("app.services.precios._obtener_info_yfinance", return_value=perfil):
            precio = await obtener_precio_actual("AAPL")
        assert precio is None


# ── obtener_precios_batch ─────────────────────────────────────────────────────


class TestObtenerPreciosBatch:
    @pytest.mark.asyncio
    async def test_batch_multiple_tickers(self):
        perfiles = {
            "AAPL": {"precio": 150.0},
            "MSFT": {"precio": 300.0},
        }

        def fake_yfinance(ticker):
            return perfiles.get(ticker)

        with patch(
            "app.services.precios._obtener_info_yfinance", side_effect=fake_yfinance
        ):
            result = await obtener_precios_batch(["AAPL", "MSFT"])
        assert result == {"AAPL": 150.0, "MSFT": 300.0}

    @pytest.mark.asyncio
    async def test_lista_vacia_no_llama_yfinance(self):
        with patch("app.services.precios._obtener_info_yfinance") as mock_yf:
            result = await obtener_precios_batch([])
        mock_yf.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_ticker_sin_precio_excluido(self):
        """Un ticker cuyo yfinance devuelve None no aparece en el resultado."""
        perfiles = {
            "NVDA": {"precio": 500.0},
            "UNKNOWN": None,
        }

        def fake_yfinance(ticker):
            return perfiles.get(ticker)

        with patch(
            "app.services.precios._obtener_info_yfinance", side_effect=fake_yfinance
        ):
            result = await obtener_precios_batch(["NVDA", "UNKNOWN"])
        assert result == {"NVDA": 500.0}

    @pytest.mark.asyncio
    async def test_error_en_yfinance_excluye_ticker(self):
        """Si yfinance lanza excepción en un ticker, ese ticker se excluye."""
        call_count = 0

        def fake_yfinance(ticker):
            nonlocal call_count
            call_count += 1
            if ticker == "BAD":
                raise RuntimeError("network error")
            return {"precio": 100.0}

        with patch(
            "app.services.precios._obtener_info_yfinance", side_effect=fake_yfinance
        ):
            result = await obtener_precios_batch(["AAPL", "BAD"])
        assert "AAPL" in result
        assert "BAD" not in result


# ── buscar_ticker_por_isin ────────────────────────────────────────────────────


class TestBuscarTickerPorIsin:
    @pytest.mark.asyncio
    async def test_devuelve_ticker(self):
        # OpenFIGI devuelve lista con data: [{ticker, exchCode, ...}]
        data = [{"data": [{"ticker": "SAN", "exchCode": "SM"}]}]
        resp = mock_httpx_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(return_value=resp))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("ES0113900J37")
        assert ticker == "SAN.MC"

    @pytest.mark.asyncio
    async def test_sin_resultados_devuelve_none(self):
        # OpenFIGI responde pero sin data en el resultado
        data = [{}]
        resp = mock_httpx_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(return_value=resp))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("XX0000000000")
        assert ticker is None

    @pytest.mark.asyncio
    async def test_error_devuelve_none(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("network")
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("XX0000000000")
        assert ticker is None


# ── obtener_fx_historico ──────────────────────────────────────────────────────

from datetime import date as _date


class TestObtenerFxHistorico:
    @pytest.mark.asyncio
    async def test_devuelve_float_cuando_hay_datos(self):
        df = pd.DataFrame({"Close": [1.085]})
        with patch("app.services.precios._fetch_fx_historico", return_value=1.085):
            result = await obtener_fx_by_date("USD", _date(2024, 1, 15))
        assert result == pytest.approx(1.085)

    @pytest.mark.asyncio
    async def test_eur_devuelve_1_sin_llamar_yfinance(self):
        with patch("app.services.precios._fetch_fx_historico") as mock_fetch:
            result = await obtener_fx_by_date("EUR", _date(2024, 1, 15))
        assert result == 1.0
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_devuelve_none_cuando_no_hay_datos(self):
        with patch("app.services.precios._fetch_fx_historico", return_value=None):
            result = await obtener_fx_by_date("USD", _date(2024, 1, 15))
        assert result is None

    @pytest.mark.asyncio
    async def test_eur_mayusculas_minusculas(self):
        with patch("app.services.precios._fetch_fx_historico") as mock_fetch:
            result = await obtener_fx_by_date("eur", _date(2024, 1, 15))
        assert result == 1.0
        mock_fetch.assert_not_called()

    def test_fetch_fx_historico_dataframe_vacio_devuelve_none(self):
        from app.services.precios import _fetch_fx_by_date

        empty_df = pd.DataFrame({"Close": []})
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = empty_df
            result = _fetch_fx_by_date("EURUSD=X", _date(2024, 1, 15))
        assert result is None

    def test_fetch_fx_historico_devuelve_primer_cierre(self):
        from app.services.precios import _fetch_fx_by_date

        df = pd.DataFrame({"Close": [1.085, 1.090, 1.092]})
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = df
            result = _fetch_fx_by_date("EURUSD=X", _date(2024, 1, 15))
        assert result == pytest.approx(1.085)


# ── obtener_fx_actual ─────────────────────────────────────────────────────────


class TestObtenerFxActual:
    @pytest.mark.asyncio
    async def test_devuelve_float(self):
        with patch("app.services.precios._fetch_fx_actual", return_value=1.085):
            result = await obtener_fx("USD")
        assert result == pytest.approx(1.085)

    @pytest.mark.asyncio
    async def test_eur_devuelve_1_sin_llamar_yfinance(self):
        with patch("app.services.precios._fetch_fx_actual") as mock_fetch:
            result = await obtener_fx("EUR")
        assert result == 1.0
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_devuelve_none_cuando_falla(self):
        with patch("app.services.precios._fetch_fx_actual", return_value=None):
            result = await obtener_fx("GBP")
        assert result is None


# ── obtener_fx_batch ──────────────────────────────────────────────────────────


class TestObtenerFxBatch:
    @pytest.mark.asyncio
    async def test_devuelve_dict_con_monedas(self):
        fx_map = {"USD": 1.085, "GBP": 0.857}

        async def fake_fx_actual(moneda):
            return fx_map.get(moneda.upper())

        with patch("app.services.precios.obtener_fx_actual", side_effect=fake_fx_actual):
            result = await obtener_fx_batch(["USD", "GBP"])
        assert result == {"USD": pytest.approx(1.085), "GBP": pytest.approx(0.857)}

    @pytest.mark.asyncio
    async def test_lista_vacia_devuelve_dict_vacio(self):
        with patch("app.services.precios.obtener_fx_actual") as mock_fx:
            result = await obtener_fx_batch([])
        mock_fx.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_eur_excluido_del_batch(self):
        with patch("app.services.precios.obtener_fx_actual") as mock_fx:
            result = await obtener_fx_batch(["EUR"])
        mock_fx.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_moneda_sin_datos_excluida(self):
        async def fake_fx_actual(moneda):
            return 1.085 if moneda == "USD" else None

        with patch("app.services.precios.obtener_fx_actual", side_effect=fake_fx_actual):
            result = await obtener_fx_batch(["USD", "JPY"])
        assert "USD" in result
        assert "JPY" not in result

    @pytest.mark.asyncio
    async def test_deduplicacion_monedas_repetidas(self):
        calls = []

        async def fake_fx_actual(moneda):
            calls.append(moneda)
            return 1.085

        with patch("app.services.precios.obtener_fx_actual", side_effect=fake_fx_actual):
            await obtener_fx_batch(["USD", "USD", "usd"])
        # Solo debe llamarse una vez (set de monedas únicas)
        assert len(calls) == 1
