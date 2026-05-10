"""
Servicio de precios (FMP) y autodescubrimiento de instrumentos (Claude IA).
"""
import httpx
import os
import json
from typing import Optional, Dict

FMP_KEY = os.getenv("FMP_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
FMP_BASE = "https://financialmodelingprep.com/api/v3"


# ── Precios en tiempo real ────────────────────────────────────────────────────

async def obtener_precio_actual(ticker: str) -> Optional[float]:
    """Devuelve el precio actual de un ticker via FMP."""
    if not FMP_KEY:
        raise ValueError("FMP_API_KEY no configurada")
    url = f"{FMP_BASE}/quote-short/{ticker}?apikey={FMP_KEY}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        data = r.json()
        if data and isinstance(data, list):
            return data[0].get("price")
    return None


async def obtener_precios_batch(tickers: list[str]) -> Dict[str, float]:
    """Obtiene precios de múltiples tickers en una sola llamada a FMP."""
    if not tickers or not FMP_KEY:
        return {}
    symbols = ",".join(tickers)
    url = f"{FMP_BASE}/quote-short/{symbols}?apikey={FMP_KEY}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        data = r.json()
        if isinstance(data, list):
            return {item["symbol"]: item["price"] for item in data if "price" in item}
    return {}


async def buscar_ticker_por_isin(isin: str) -> Optional[str]:
    """Busca el ticker en FMP dado un ISIN."""
    if not FMP_KEY:
        return None
    url = f"{FMP_BASE}/search?query={isin}&limit=5&apikey={FMP_KEY}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        data = r.json()
        if data and isinstance(data, list):
            return data[0].get("symbol")
    return None


# ── Autodescubrimiento por IA ─────────────────────────────────────────────────

async def autodescubrir_instrumento(isin: str, nombre_hint: str = "") -> Dict:
    """
    Usa Claude para obtener nombre, sector, país, moneda, tipo y exchange
    a partir del ISIN. Devuelve dict con los campos encontrados.
    """
    prompt = f"""Given this financial instrument:
ISIN: {isin}
Name hint: {nombre_hint or "unknown"}

Return ONLY a valid JSON object with these exact fields (no markdown, no explanation):
{{
  "nombre": "official full name of the instrument",
  "tipo": "accion | etf | fondo | otro",
  "sector": "sector in Spanish (Tecnología, Salud, Finanzas, Consumo Discrecional, Consumo Básico, Energía, Industria, Inmobiliario, Materiales, Utilities, Telecomunicaciones, Diversificado)",
  "pais": "country of origin in Spanish",
  "moneda": "ISO currency code (EUR, USD, JPY, GBP, CHF...)",
  "exchange": "main exchange where it trades (NYSE, NASDAQ, BME, XETRA, TSE, LSE, EURONEXT...)"
}}

If you are not sure about a field, use null. Be concise and accurate."""

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        data = r.json()
        text = data["content"][0]["text"]
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
