"""
Tests unitarios para app/services/precios.py

Todas las llamadas HTTP se mockean con unittest.mock.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.precios import (
    obtener_precio_actual,
    obtener_precios_batch,
    buscar_ticker_por_isin,
    autodescubrir_instrumento,
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
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    return response


# ── _fmp_key / _anthropic_key ─────────────────────────────────────────────────

class TestKeys:
    def test_fmp_key_falla_sin_env(self, monkeypatch):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        from app.services import precios
        with pytest.raises(ValueError, match="FMP_API_KEY"):
            precios._fmp_key()

    def test_anthropic_key_falla_sin_env(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from app.services import precios
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            precios._anthropic_key()

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
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=resp)
            ))
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
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=resp)
            ))
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
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=resp)
            ))
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
            {"price": 100.0},               # sin symbol → ignorado
            {"symbol": "NVDA", "price": 500.0},
        ]
        resp = mock_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=resp)
            ))
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
        monkeypatch.setenv("FMP_API_KEY", "key")
        data = [{"symbol": "AAPL", "name": "Apple Inc."}]
        resp = mock_response(data)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("US0378331005")
        assert ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_sin_resultados_devuelve_none(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        resp = mock_response([])
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("XX0000000000")
        assert ticker is None

    @pytest.mark.asyncio
    async def test_error_devuelve_none(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "key")
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("network"))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            ticker = await buscar_ticker_por_isin("XX0000000000")
        assert ticker is None


# ── autodescubrir_instrumento ─────────────────────────────────────────────────

class TestAutodescubrir:

    _RESP_VALIDA = {
        "nombre": "Apple Inc.",
        "tipo": "accion",
        "sector": "Tecnología",
        "pais": "Estados Unidos",
        "moneda": "USD",
        "exchange": "NASDAQ",
    }

    def _mock_anthropic(self, payload):
        return mock_response({
            "content": [{"text": json.dumps(payload)}]
        })

    @pytest.mark.asyncio
    async def test_parseo_correcto(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        resp = self._mock_anthropic(self._RESP_VALIDA)
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await autodescubrir_instrumento("US0378331005")
        assert result["nombre"] == "Apple Inc."
        assert result["sector"] == "Tecnología"

    @pytest.mark.asyncio
    async def test_respuesta_con_markdown_se_limpia(self, monkeypatch):
        """Claude a veces devuelve el JSON envuelto en ```json ... ```."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        raw = f"```json\n{json.dumps(self._RESP_VALIDA)}\n```"
        resp = mock_response({"content": [{"text": raw}]})
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await autodescubrir_instrumento("US0378331005")
        assert result["nombre"] == "Apple Inc."

    @pytest.mark.asyncio
    async def test_error_devuelve_dict_vacio(self, monkeypatch):
        """Si la IA falla, el flujo no debe romperse."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await autodescubrir_instrumento("US0378331005")
        assert result == {}

    @pytest.mark.asyncio
    async def test_json_malformado_devuelve_dict_vacio(self, monkeypatch):
        """Si Claude responde texto que no es JSON, no debe explotar."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        resp = mock_response({"content": [{"text": "lo siento, no sé"}]})
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await autodescubrir_instrumento("US0378331005")
        assert result == {}
