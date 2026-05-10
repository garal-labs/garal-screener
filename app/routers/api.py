from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas
from app.services import calculos, precios

router = APIRouter()


# -- Carteras -----------------------------------------------------------------

@router.post("/carteras", response_model=schemas.CarteraOut)
def crear_cartera(data: schemas.CarteraCreate, db: Session = Depends(get_db)):
    cartera = models.Cartera(**data.model_dump())
    db.add(cartera)
    db.commit()
    db.refresh(cartera)
    return cartera


@router.get("/carteras", response_model=List[schemas.CarteraOut])
def listar_carteras(db: Session = Depends(get_db)):
    return db.query(models.Cartera).all()


@router.delete("/carteras/{cartera_id}")
def eliminar_cartera(cartera_id: int, db: Session = Depends(get_db)):
    cartera = db.query(models.Cartera).filter(models.Cartera.id == cartera_id).first()
    if not cartera:
        raise HTTPException(status_code=404, detail="Cartera no encontrada")
    # cascade="all, delete-orphan" en el modelo se encarga de borrar movimientos
    db.delete(cartera)
    db.commit()
    return {"ok": True}


# -- Instrumentos -------------------------------------------------------------

@router.get("/instrumentos/autodescubrir/{isin}", response_model=schemas.InstrumentoOut)
async def autodescubrir(isin: str, db: Session = Depends(get_db)):
    """Busca o crea un instrumento por ISIN usando IA + FMP."""
    isin = isin.strip().upper()
    instrumento = db.query(models.Instrumento).filter(models.Instrumento.isin == isin).first()
    if instrumento:
        return instrumento

    datos_ia = await precios.autodescubrir_instrumento(isin)
    ticker = await precios.buscar_ticker_por_isin(isin)

    instrumento = models.Instrumento(
        isin=isin,
        ticker=ticker,
        nombre=datos_ia.get("nombre"),
        tipo=datos_ia.get("tipo"),
        sector=datos_ia.get("sector"),
        pais=datos_ia.get("pais"),
        moneda=datos_ia.get("moneda"),
        exchange=datos_ia.get("exchange"),
    )
    db.add(instrumento)
    db.commit()
    db.refresh(instrumento)
    return instrumento


@router.patch("/instrumentos/{instrumento_id}", response_model=schemas.InstrumentoOut)
def actualizar_instrumento(
    instrumento_id: int,
    data: schemas.InstrumentoUpdate,   # schema Pydantic correcto, no dict
    db: Session = Depends(get_db)
):
    """Permite corregir manualmente cualquier campo del instrumento."""
    instrumento = db.query(models.Instrumento).filter(models.Instrumento.id == instrumento_id).first()
    if not instrumento:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(instrumento, campo, valor)
    db.commit()
    db.refresh(instrumento)
    return instrumento


@router.get("/instrumentos", response_model=List[schemas.InstrumentoOut])
def listar_instrumentos(db: Session = Depends(get_db)):
    return db.query(models.Instrumento).all()


# -- Movimientos --------------------------------------------------------------

@router.post("/movimientos", response_model=schemas.MovimientoOut)
async def crear_movimiento(data: schemas.MovimientoCreate, db: Session = Depends(get_db)):
    """Crea un movimiento. Autodescubre el instrumento si no existe."""
    cartera = db.query(models.Cartera).filter(models.Cartera.id == data.cartera_id).first()
    if not cartera:
        raise HTTPException(status_code=404, detail="Cartera no encontrada")

    isin_normalizado = data.isin.strip().upper()
    instrumento = db.query(models.Instrumento).filter(models.Instrumento.isin == isin_normalizado).first()
    if not instrumento:
        datos_ia = await precios.autodescubrir_instrumento(isin_normalizado)
        ticker = await precios.buscar_ticker_por_isin(isin_normalizado)
        instrumento = models.Instrumento(
            isin=isin_normalizado,
            ticker=ticker,
            nombre=datos_ia.get("nombre"),
            tipo=datos_ia.get("tipo"),
            sector=datos_ia.get("sector"),
            pais=datos_ia.get("pais"),
            moneda=datos_ia.get("moneda"),
            exchange=datos_ia.get("exchange"),
        )
        db.add(instrumento)
        db.flush()  # obtenemos instrumento.id sin hacer commit aun

    # Validar venta: no puedes vender mas de lo que tienes
    if data.tipo == "venta":
        movs = db.query(models.Movimiento).filter(
            models.Movimiento.instrumento_id == instrumento.id,
            models.Movimiento.cartera_id == data.cartera_id,
        ).all()
        posicion = calculos.calcular_posicion_fifo(movs)
        if data.cantidad > posicion["cantidad_actual"]:
            raise HTTPException(
                status_code=400,
                detail=f"No puedes vender {data.cantidad} unidades. Tienes {posicion['cantidad_actual']}"
            )

    movimiento = models.Movimiento(
        cartera_id=data.cartera_id,
        instrumento_id=instrumento.id,
        tipo=data.tipo,
        fecha=data.fecha,
        cantidad=data.cantidad,
        precio=data.precio,
        comision=data.comision or 0.0,
        tipo_cambio=data.tipo_cambio,
        notas=data.notas,
    )
    db.add(movimiento)
    db.commit()
    db.refresh(movimiento)
    return movimiento


@router.get("/carteras/{cartera_id}/movimientos", response_model=List[schemas.MovimientoOut])
def listar_movimientos(cartera_id: int, db: Session = Depends(get_db)):
    cartera = db.query(models.Cartera).filter(models.Cartera.id == cartera_id).first()
    if not cartera:
        raise HTTPException(status_code=404, detail="Cartera no encontrada")
    return (
        db.query(models.Movimiento)
        .filter(models.Movimiento.cartera_id == cartera_id)
        .order_by(models.Movimiento.fecha.desc())
        .all()
    )


@router.delete("/movimientos/{movimiento_id}")
def eliminar_movimiento(movimiento_id: int, db: Session = Depends(get_db)):
    mov = db.query(models.Movimiento).filter(models.Movimiento.id == movimiento_id).first()
    if not mov:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    db.delete(mov)
    db.commit()
    return {"ok": True}


# -- Posiciones y rentabilidades ----------------------------------------------

@router.get("/carteras/{cartera_id}/resumen", response_model=schemas.ResumenCartera)
async def resumen_cartera(cartera_id: int, db: Session = Depends(get_db)):
    """Posiciones con rentabilidades calculadas en tiempo real via FMP."""
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

    tickers = [i.ticker for i in instrumentos if i.ticker]
    precios_actuales = await precios.obtener_precios_batch(tickers) if tickers else {}

    posiciones_out = []
    plusvalia_realizada_cerradas = 0.0  # acumula P/L de posiciones ya cerradas

    for instrumento in instrumentos:
        movs = db.query(models.Movimiento).filter(
            models.Movimiento.instrumento_id == instrumento.id,
            models.Movimiento.cartera_id == cartera_id,
        ).all()

        posicion_fifo = calculos.calcular_posicion_fifo(movs)

        if posicion_fifo["cantidad_actual"] <= 0:
            # Posición cerrada: acumulamos su P/L realizada para el resumen global
            plusvalia_realizada_cerradas += posicion_fifo["plusvalia_realizada"]
            continue

        precio_actual = precios_actuales.get(instrumento.ticker) if instrumento.ticker else None

        plusvalias = {}
        if precio_actual is not None:
            plusvalias = calculos.calcular_plusvalia_latente(posicion_fifo, precio_actual)

        posiciones_out.append(schemas.PosicionOut(
            instrumento=instrumento,
            cantidad_actual=posicion_fifo["cantidad_actual"],
            coste_total=posicion_fifo["coste_total"],
            precio_medio=posicion_fifo["precio_medio"],
            plusvalia_realizada=posicion_fifo["plusvalia_realizada"],
            precio_actual=precio_actual,
            valor_actual=plusvalias.get("valor_actual"),
            plusvalia_latente=plusvalias.get("plusvalia_latente"),
            rentabilidad_pct=plusvalias.get("rentabilidad_pct"),
            plusvalia_total=plusvalias.get("plusvalia_total"),
        ))

    resumen = calculos.calcular_resumen_cartera([p.model_dump() for p in posiciones_out])
    # Sumar la plusvalía realizada de posiciones cerradas que no aparecen en posiciones_out
    resumen["plusvalia_realizada"] = round(
        resumen["plusvalia_realizada"] + plusvalia_realizada_cerradas, 2
    )
    resumen["plusvalia_total"] = round(
        resumen["plusvalia_latente"] + resumen["plusvalia_realizada"], 2
    )

    return schemas.ResumenCartera(
        cartera=cartera,
        posiciones=posiciones_out,
        **resumen,
    )


# -- Analisis / Desglose ------------------------------------------------------

@router.get("/carteras/{cartera_id}/analisis", response_model=schemas.AnalisisCartera)
async def analisis_cartera(cartera_id: int, db: Session = Depends(get_db)):
    """Desglose por sector, pais, tipo y moneda."""
    resumen = await resumen_cartera(cartera_id, db)
    posiciones = [p.model_dump() for p in resumen.posiciones]

    posiciones_enriquecidas = []
    for p in posiciones:
        instr = p["instrumento"]
        posiciones_enriquecidas.append({
            **p,
            "sector": instr.get("sector"),
            "pais": instr.get("pais"),
            "tipo": instr.get("tipo"),
            "moneda": instr.get("moneda"),
        })

    return schemas.AnalisisCartera(
        por_sector=calculos.agrupar_por_campo(posiciones_enriquecidas, "sector"),
        por_pais=calculos.agrupar_por_campo(posiciones_enriquecidas, "pais"),
        por_tipo=calculos.agrupar_por_campo(posiciones_enriquecidas, "tipo"),
        por_moneda=calculos.agrupar_por_campo(posiciones_enriquecidas, "moneda"),
    )