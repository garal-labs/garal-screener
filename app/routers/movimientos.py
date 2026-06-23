from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import calculos, precios

router = APIRouter(tags=["Movimientos"])

@router.post("/movimientos", response_model=schemas.MovimientoOut)
async def crear_movimiento(
    data: schemas.MovimientoCreate, db: Session = Depends(get_db)
):
    """Crea un movimiento. Autodescubre el instrumento si no existe."""
    cartera = (
        db.query(models.Cartera).filter(models.Cartera.id == data.cartera_id).first()
    )
    if not cartera:
        raise HTTPException(status_code=404, detail="Cartera no encontrada")

    isin_normalizado = data.isin.strip().upper()
    instrumento = (
        db.query(models.Instrumento)
        .filter(models.Instrumento.isin == isin_normalizado)
        .first()
    )
    if not instrumento:
        datos = await precios.enriquecer_por_isin(isin_normalizado)
        if not datos:
            raise HTTPException(
                status_code=404,
                detail=f"No se pudieron obtener datos para el ISIN {isin_normalizado}. Comprueba que el ISIN es correcto.",
            )

        instrumento = models.Instrumento(
            isin=isin_normalizado,
            ticker=datos.get("ticker"),
            nombre=datos.get("nombre"),
            tipo=datos.get("tipo"),
            sector=datos.get("sector"),
            pais=datos.get("pais"),
            moneda=datos.get("moneda"),
            exchange=datos.get("exchange"),
        )
        db.add(instrumento)
        db.flush()  # obtenemos instrumento.id sin hacer commit aun

    # Validar venta: no puedes vender mas de lo que tienes
    if data.tipo == "venta":
        movs = (
            db.query(models.Movimiento)
            .filter(
                models.Movimiento.instrumento_id == instrumento.id,
                models.Movimiento.cartera_id == data.cartera_id,
            )
            .all()
        )
        posicion = calculos.calcular_posicion_fifo(movs)
        if data.cantidad > posicion["cantidad_actual"]:
            raise HTTPException(
                status_code=400,
                detail=f"No puedes vender {data.cantidad} unidades. Tienes {posicion['cantidad_actual']}",
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

@router.get(
    "/carteras/{cartera_id}/movimientos", response_model=list[schemas.MovimientoOut]
)
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
    mov = (
        db.query(models.Movimiento)
        .filter(models.Movimiento.id == movimiento_id)
        .first()
    )
    if not mov:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    db.delete(mov)
    db.commit()
    return {"ok": True}
