"""
Tests unitarios para app/services/precios.py

Todas las llamadas HTTP se mockean con unittest.mock.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.precios import (
    buscar_ticker_por_isin,
    obtener_precio_actual,
    obtener_precios_batch,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def mock_response(json_data, status_code=200):
    """Construye un mock de httpx.Response."""
    response = MagicMock()
    response.json.return_value = json_data
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        response.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
    return response


# ── _fmp_key / _anthropic_key ─────────────────────────────────────────────────


class TestKeys:
    def test_fmp_key_falla_sin_env(self, monkeypatch):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        from app.services import precios

        with pytest.raises(ValueError, match="FMP_API_KEY"):
            precios._fmp_key()

    def test_fmp_key_ok(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "test-key")
        from app.services import precios

        assert precios._fmp_key() == "test-key"


# ── obtener_precio_actual ─────────────────────────────────────────────────────


class TestObtenerPrecioActual:
    @pytest.mark.asyncio
    async def test_devuelve_precio(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        resp = mock_response([{"symbol": "AAPL", "price": 150.0}])
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            precio = await obtener_precio_actual("AAPL")
        assert precio == 150.0

    @pytest.mark.asyncio
    async def test_devuelve_none_en_error(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            precio = await obtener_precio_actual("AAPL")
        assert precio is None

    @pytest.mark.asyncio
    async def test_lista_vacia_devuelve_none(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        resp = mock_response([])
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            precio = await obtener_precio_actual("AAPL")
        assert precio is None


# ── obtener_precios_batch ─────────────────────────────────────────────────────


class TestObtenerPreciosBatch:
    @pytest.mark.asyncio
    async def test_batch_multiple_tickers(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        data = [
            {"symbol": "AAPL", "price": 150.0},
            {"symbol": "MSFT", "price": 300.0},
        ]
        resp = mock_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await obtener_precios_batch(["AAPL", "MSFT"])
        assert result == {"AAPL": 150.0, "MSFT": 300.0}

    @pytest.mark.asyncio
    async def test_lista_vacia_no_llama_api(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        with patch("httpx.AsyncClient") as mock_client:
            result = await obtener_precios_batch([])
        mock_client.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_item_sin_symbol_ignorado(self, monkeypatch):
        """Un item sin 'symbol' no debe romper el parseo."""
        monkeypatch.setenv("FMP_API_KEY", "key")
        data = [
            {"price": 100.0},  # sin symbol → ignorado
            {"symbol": "NVDA", "price": 500.0},
        ]
        resp = mock_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await obtener_precios_batch(["NVDA"])
        assert "NVDA" in result
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_error_devuelve_dict_vacio(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await obtener_precios_batch(["AAPL"])
        assert result == {}


# ── buscar_ticker_por_isin ────────────────────────────────────────────────────


class TestBuscarTickerPorIsin:
    @pytest.mark.asyncio
    async def test_devuelve_ticker(self, monkeypatch):
        # OpenFIGI devuelve lista con data: [{ticker, exchCode, ...}]
        data = [{"data": [{"ticker": "SAN", "exchCode": "SM"}]}]
        resp = mock_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=resp)))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("ES0113900J37")
        assert ticker == "SAN.MC"

    @pytest.mark.asyncio
    async def test_sin_resultados_devuelve_none(self, monkeypatch):
        # OpenFIGI responde pero sin data en el resultado
        data = [{}]
        resp = mock_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=resp)))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("XX0000000000")
        assert ticker is None

    @pytest.mark.asyncio
    async def test_error_devuelve_none(self, monkeypatch):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("network"))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("XX0000000000")
        assert ticker is None
