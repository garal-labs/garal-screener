"""
Servicio de precios (FMP) y autodescubrimiento de instrumentos (Claude IA).
"""
import httpx
import os
import json
from typing import Optional, Dict

FMP_BASE = "https://financialmodelingprep.com/api/v3"


def _fmp_key() -> str:
    key = os.getenv("FMP_API_KEY")
    if not key:
        raise ValueError("FMP_API_KEY no está configurada en las variables de entorno")
    return key


def _anthropic_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY no está configurada en las variables de entorno")
    return key


# -- Precios en tiempo real ---------------------------------------------------

async def obtener_precio_actual(ticker: str) -> Optional[float]:
    """Devuelve el precio actual de un ticker via FMP."""
    try:
        url = f"{FMP_BASE}/quote-short/{ticker}?apikey={_fmp_key()}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            if data and isinstance(data, list):
                return data[0].get("price")
    except Exception:
        return None
    return None


async def obtener_precios_batch(tickers: list[str]) -> Dict[str, float]:
    """Obtiene precios de múltiples tickers en una sola llamada a FMP."""
    if not tickers:
        return {}
    try:
        symbols = ",".join(tickers)
        url = f"{FMP_BASE}/quote-short/{symbols}?apikey={_fmp_key()}"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                return {
                    item["symbol"]: item["price"]
                    for item in data
                    if "symbol" in item and "price" in item
                }
    except Exception:
        return {}
    return {}


async def buscar_ticker_por_isin(isin: str) -> Optional[str]:
    """Busca el ticker en FMP dado un ISIN."""
    try:
        url = f"{FMP_BASE}/search?query={isin}&limit=5&apikey={_fmp_key()}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            if data and isinstance(data, list):
                return data[0].get("symbol")
    except Exception:
        return None
    return None


# -- Autodescubrimiento por IA ------------------------------------------------

async def autodescubrir_instrumento(isin: str, nombre_hint: str = "") -> Dict:
    """
    Usa Claude para obtener nombre, sector, pais, moneda, tipo y exchange
    a partir del ISIN. Devuelve dict con los campos encontrados.
    Si falla por cualquier motivo devuelve dict vacío (nunca rompe el flujo).
    """
    prompt = f"""Given this financial instrument:
ISIN: {isin}
Name hint: {nombre_hint or "unknown"}

Return ONLY a valid JSON object with these exact fields (no markdown, no explanation):
{{
  "nombre": "official full name of the instrument",
  "tipo": "accion | etf | fondo | otro",
  "sector": "sector in Spanish (Tecnologia, Salud, Finanzas, Consumo Discrecional, Consumo Basico, Energia, Industria, Inmobiliario, Materiales, Utilities, Telecomunicaciones, Diversificado)",
  "pais": "country of origin in Spanish",
  "moneda": "ISO currency code (EUR, USD, JPY, GBP, CHF...)",
  "exchange": "main exchange where it trades (NYSE, NASDAQ, BME, XETRA, TSE, LSE, EURONEXT...)"
}}

If you are not sure about a field, use null. Be concise and accurate."""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": _anthropic_key(),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
            data = r.json()
            text = data["content"][0]["text"]
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
    except Exception:
        # Si la IA falla, devolvemos dict vacío — el instrumento se crea igualmente
        # y el usuario puede rellenar los datos manualmente via PATCH
        return {}