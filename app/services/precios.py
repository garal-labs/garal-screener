"""
Servicio de metadatos y precios de instrumentos financieros.

- Ticker desde ISIN  → OpenFIGI (gratuito, sin API key)
- Metadatos + precio → yfinance (Yahoo Finance, sin API key)
"""

import asyncio

import httpx
import yfinance as yf

_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) " "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Mapeo país del ISIN → (exchCode OpenFIGI, sufijo Yahoo Finance)
_ISIN_EXCHANGE_MAP = {
    "ES": ("SM", ".MC"),  # BME Madrid
    "DE": ("GR", ".DE"),  # XETRA
    "FR": ("FP", ".PA"),  # Euronext Paris
    "GB": ("LN", ".L"),  # LSE
    "IT": ("IM", ".MI"),  # Borsa Italiana
    "NL": ("NA", ".AS"),  # Euronext Amsterdam
    "PT": ("PL", ".LS"),  # Euronext Lisboa
    "CH": ("SW", ".SW"),  # SIX Swiss
    "JP": ("JT", ".T"),  # TSE
    "US": ("US", ""),  # NYSE/NASDAQ — sin sufijo
    "IE": ("NA", ".AS"),  # ETFs irlandeses → Euronext Amsterdam (más completo en Yahoo)
    "LU": ("NA", ".AS"),  # ETFs luxemburgueses → Euronext Amsterdam
}

async def enriquecer_por_isin(isin: str) -> dict | None:
    """
    Resuelve ISIN → metadatos completos con estrategia en cascada:
    1. OpenFIGI → ticker → yfinance
    2. Si falla: búsqueda directa por ISIN en Yahoo → yfinance
    Devuelve dict con ticker, nombre, tipo, sector, pais, moneda, exchange.
    Devuelve None si todas las fuentes fallan.
    """
    loop = asyncio.get_event_loop()

    # 1. Intentar via OpenFIGI
    ticker = await _buscar_ticker_en_openfigi(isin)
    if ticker:
        perfil = await loop.run_in_executor(None, _obtener_info_yfinance, ticker)
        if perfil:
            return {
                "ticker": ticker,
                "nombre": perfil.get("nombre"),
                "tipo": perfil.get("tipo"),
                "sector": perfil.get("sector"),
                "pais": perfil.get("pais"),
                "moneda": perfil.get("moneda"),
                "exchange": perfil.get("exchange"),
            }
        print(f"[yfinance] Ticker {ticker} no encontrado, intentando búsqueda directa por ISIN...")

    # 2. Fallback: búsqueda directa en Yahoo por ISIN, iterando candidatos
    candidatos = await _buscar_tickers_en_yahoo(isin)
    if not candidatos:
        print(f"[Yahoo Search] No se encontró ningún ticker para ISIN {isin}")
        return None

    for ticker in candidatos:
        perfil = await loop.run_in_executor(None, _obtener_info_yfinance, ticker)
        if perfil:
            return {
                "ticker": ticker,
                "nombre": perfil.get("nombre"),
                "tipo": perfil.get("tipo"),
                "sector": perfil.get("sector"),
                "pais": perfil.get("pais"),
                "moneda": perfil.get("moneda"),
                "exchange": perfil.get("exchange"),
            }

    print(f"[yfinance] Ningún candidato de Yahoo funcionó para ISIN {isin}: {candidatos}")
    return None

async def _buscar_ticker_en_openfigi(isin: str) -> str | None:
    """
    Resuelve ISIN → ticker via OpenFIGI (gratuito, sin API key).
    Prioriza el exchange del país de origen del ISIN.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.openfigi.com/v3/mapping",
                headers={"Content-Type": "application/json"},
                json=[{"idType": "ID_ISIN", "idValue": isin}],
            )
            r.raise_for_status()
            data = r.json()
            if not data or "data" not in data[0]:
                return None

            resultados = data[0]["data"]
            pais = isin[:2].upper()
            exch_code, sufijo = _ISIN_EXCHANGE_MAP.get(pais, ("", ""))

            # 1. Buscar en el exchange preferido del país de origen
            if exch_code:
                for item in resultados:
                    if item.get("exchCode") == exch_code:
                        return str(item.get("ticker", "")) + sufijo

            # 2. Fallback: preferir exchange US (NYSE/NASDAQ) si existe
            for item in resultados:
                if item.get("exchCode") == "US":
                    return str(item.get("ticker", ""))

            # 3. Último recurso: primer resultado
            ticker = resultados[0].get("ticker")
            return str(ticker) if ticker is not None else None
    except Exception as e:
        print(f"[OpenFIGI] Error resolviendo ISIN {isin}: {e}")
        return None

async def _buscar_tickers_en_yahoo(isin: str) -> list[str]:
    """
    Busca todos los tickers candidatos en Yahoo Finance por ISIN.
    Devuelve lista ordenada por relevancia para iterar hasta encontrar uno válido.
    """
    try:
        async with httpx.AsyncClient(timeout=10, headers=_YAHOO_HEADERS, follow_redirects=True) as client:
            r = await client.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={"q": isin, "lang": "en-US", "type": "quotes"},
            )
            r.raise_for_status()
            quotes = r.json().get("quotes", [])
            return [q["symbol"] for q in quotes if q.get("symbol")]
    except Exception as e:
        print(f"[Yahoo Search] Error buscando ISIN {isin}: {e}")
        return []

def _obtener_info_yfinance(ticker: str) -> dict | None:
    """
    Obtiene metadatos + precio via yfinance (síncrono).
    Se ejecuta en un executor para no bloquear el event loop.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info

        if not info or info.get("trailingPegRatio") is None and not info.get("longName"):
            # yfinance devuelve un dict vacío o inútil si el ticker no existe
            return None

        quote_type = info.get("quoteType", "")
        tipo = _tipo_desde_quote_type(quote_type)

        precio = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")

        return {
            "nombre": info.get("longName") or info.get("shortName"),
            "tipo": tipo,
            "sector": info.get("sector"),
            "pais": info.get("country"),
            "moneda": info.get("currency"),
            "exchange": info.get("exchange"),
            "precio": float(precio) if precio else None,
        }
    except Exception as e:
        print(f"[yfinance] Error obteniendo info de {ticker}: {e}")
        return None

def _tipo_desde_quote_type(quote_type: str) -> str:
    mapping = {
        "EQUITY": "accion",
        "ETF": "etf",
        "MUTUALFUND": "fondo",
    }
    return mapping.get((quote_type or "").upper(), "otro")

async def obtener_precios_batch(tickers: list[str]) -> dict[str, float]:
    """Obtiene precios de múltiples tickers en paralelo via yfinance."""
    if not tickers:
        return {}

    resultados = await asyncio.gather(*[_obtener_precio_actual(ticker) for ticker in tickers], return_exceptions=True)
    # Sino existe ticker en yahoo no vamos a encontrar precios
    return {ticker: precio for ticker, precio in zip(tickers, resultados) if isinstance(precio, float)}  # noqa: B905

async def _obtener_precio_actual(ticker: str) -> float | None:
    """Obtiene el precio actual de un ticker via yfinance."""
    if not ticker:
        return None
    loop = asyncio.get_event_loop()
    perfil = await loop.run_in_executor(None, _obtener_info_yfinance, ticker)
    return perfil.get("precio") if perfil else None


# ── Public aliases (backwards-compatible API) ─────────────────────────────────


async def buscar_ticker_por_isin(isin: str) -> str | None:
    """Public alias for _buscar_ticker_en_openfigi."""
    return await _buscar_ticker_en_openfigi(isin)


async def obtener_precio_actual(ticker: str) -> float | None:
    """Public alias for _obtener_precio_actual."""
    return await _obtener_precio_actual(ticker)
