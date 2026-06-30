import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import calculos, precios

router = APIRouter(prefix="/carteras", tags=["Posiciones"])


@router.get("/{cartera_id}/resumen", response_model=schemas.ResumenCartera)
async def resumen_cartera(cartera_id: int, db: Session = Depends(get_db)):
    """Posiciones con rentabilidades calculadas en tiempo real. Valores en EUR y moneda nativa."""
    cartera = db.query(models.Cartera).filter(models.Cartera.id == cartera_id).first()
    if not cartera:
        raise HTTPException(status_code=404, detail="Cartera no encontrada")

    instrumentos = (
        db.query(models.Instrumento)
        .join(models.Movimiento)
        .filter(models.Movimiento.cartera_id == cartera_id)
        .distinct()
        .all()
    )

    tickers = [str(i.ticker) for i in instrumentos if i.ticker]
    monedas = [i.moneda for i in instrumentos if i.moneda and i.moneda.upper() != "EUR"]

    # Fetch precios actuales y tipos de cambio en paralelo
    precios_actuales, fx_rates = await asyncio.gather(
        (
            precios.obtener_precios_batch(tickers)
            if tickers
            else asyncio.sleep(0, result={})
        ),
        precios.obtener_fx_batch(monedas) if monedas else asyncio.sleep(0, result={}),
    )

    posiciones_out = []
    plusvalia_realizada_cerradas = 0.0  # acumula P/L de posiciones ya cerradas

    for instrumento in instrumentos:
        movs = (
            db.query(models.Movimiento)
            .filter(
                models.Movimiento.instrumento_id == instrumento.id,
                models.Movimiento.cartera_id == cartera_id,
            )
            .all()
        )

        posicion_fifo = calculos.calcular_posicion_fifo(movs)

        if posicion_fifo["cantidad_actual"] <= 0:
            # Posición cerrada: acumulamos su P/L realizada para el resumen global
            plusvalia_realizada_cerradas += posicion_fifo["plusvalia_realizada"]
            continue

        precio_actual = (
            precios_actuales.get(str(instrumento.ticker))
            if instrumento.ticker
            else None
        )

        # Resolver FX actual: 1.0 para EUR o moneda desconocida
        moneda = instrumento.moneda
        fx = (
            fx_rates.get(moneda.upper(), 1.0)
            if moneda and moneda.upper() != "EUR"
            else 1.0
        )

        plusvalias = {}
        if precio_actual is not None:
            plusvalias = calculos.calcular_plusvalia_latente(
                posicion_fifo, precio_actual, fx_actual=fx
            )

        posiciones_out.append(
            schemas.PosicionOut(
                instrumento=schemas.InstrumentoOut.model_validate(instrumento),
                cantidad_actual=posicion_fifo["cantidad_actual"],
                coste_total=posicion_fifo["coste_total"],
                precio_medio=posicion_fifo["precio_medio"],
                plusvalia_realizada=posicion_fifo["plusvalia_realizada"],
                precio_actual=precio_actual,
                valor_actual=plusvalias.get("valor_actual"),
                plusvalia_latente=plusvalias.get("plusvalia_latente"),
                rentabilidad_pct=plusvalias.get("rentabilidad_pct"),
                plusvalia_total=plusvalias.get("plusvalia_total"),
                # Dual-currency
                valor_actual_eur=plusvalias.get("valor_actual_eur"),
                valor_actual_nativo=plusvalias.get("valor_actual_nativo"),
                moneda_nativa=moneda,
                fx_actual=fx if precio_actual is not None else None,
            )
        )

    resumen = calculos.calcular_resumen_cartera(
        [p.model_dump() for p in posiciones_out]
    )
    resumen["plusvalia_realizada"] = round(
        resumen["plusvalia_realizada"] + plusvalia_realizada_cerradas, 2
    )
    resumen["plusvalia_total"] = round(
        resumen["plusvalia_latente"] + resumen["plusvalia_realizada"], 2
    )

    return schemas.ResumenCartera(
        cartera=schemas.CarteraOut.model_validate(cartera),
        posiciones=posiciones_out,
        **resumen,
    )


@router.post("/{cartera_id}/backfill-fx")
async def backfill_fx(cartera_id: int, db: Session = Depends(get_db)):
    """
    Rellena el tipo_cambio histórico para movimientos sin él.
    Solo afecta a instrumentos con moneda != EUR.
    Útil para corregir movimientos importados sin tipo de cambio.
    """
    cartera = db.query(models.Cartera).filter(models.Cartera.id == cartera_id).first()
    if not cartera:
        raise HTTPException(status_code=404, detail="Cartera no encontrada")

    movimientos = (
        db.query(models.Movimiento)
        .join(models.Instrumento)
        .filter(
            models.Movimiento.cartera_id == cartera_id,
            models.Movimiento.tipo_cambio.is_(None),
            models.Instrumento.moneda.isnot(None),
            models.Instrumento.moneda != "EUR",
        )
        .all()
    )

    # Agrupar por (moneda, fecha) para minimizar llamadas a yfinance
    pares_unicos: set[tuple[str, object]] = {
        (mov.instrumento.moneda, mov.fecha) for mov in movimientos
    }

    fx_cache: dict[tuple, float | None] = {}
    for moneda, fecha in pares_unicos:
        fx_cache[(moneda, fecha)] = await precios.obtener_fx_by_date(moneda, fecha)

    actualizados = 0
    omitidos = 0
    for mov in movimientos:
        fx = fx_cache.get((mov.instrumento.moneda, mov.fecha))
        if fx is not None:
            mov.tipo_cambio = fx
            actualizados += 1
        else:
            omitidos += 1

    db.commit()
    return {"actualizados": actualizados, "omitidos": omitidos}


@router.get("/{cartera_id}/analisis", response_model=schemas.AnalisisCartera)
async def analisis_cartera(cartera_id: int, db: Session = Depends(get_db)):
    """Desglose por sector, pais, tipo y moneda."""
    resumen = await resumen_cartera(cartera_id, db)
    posiciones = [p.model_dump() for p in resumen.posiciones]

    posiciones_enriquecidas = []
    for p in posiciones:
        instr = p["instrumento"]
        posiciones_enriquecidas.append(
            {
                **p,
                "sector": instr.get("sector"),
                "pais": instr.get("pais"),
                "tipo": instr.get("tipo"),
                "moneda": instr.get("moneda"),
            }
        )

    return schemas.AnalisisCartera(
        por_sector=[
            schemas.GrupoAnalisis(**g)
            for g in calculos.agrupar_por_campo(posiciones_enriquecidas, "sector")
        ],
        por_pais=[
            schemas.GrupoAnalisis(**g)
            for g in calculos.agrupar_por_campo(posiciones_enriquecidas, "pais")
        ],
        por_tipo=[
            schemas.GrupoAnalisis(**g)
            for g in calculos.agrupar_por_campo(posiciones_enriquecidas, "tipo")
        ],
        por_moneda=[
            schemas.GrupoAnalisis(**g)
            for g in calculos.agrupar_por_campo(posiciones_enriquecidas, "moneda")
        ],
    )
