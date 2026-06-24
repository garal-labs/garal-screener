from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/carteras", tags=["Carteras"])


@router.post("", response_model=schemas.CarteraOut)
def crear_cartera(data: schemas.CarteraCreate, db: Session = Depends(get_db)):
    cartera = models.Cartera(**data.model_dump())
    db.add(cartera)
    db.commit()
    db.refresh(cartera)
    return cartera


@router.get("", response_model=list[schemas.CarteraOut])
def listar_carteras(db: Session = Depends(get_db)):
    return db.query(models.Cartera).all()


@router.delete("/{cartera_id}")
def eliminar_cartera(cartera_id: int, db: Session = Depends(get_db)):
    cartera = db.query(models.Cartera).filter(models.Cartera.id == cartera_id).first()
    if not cartera:
        raise HTTPException(status_code=404, detail="Cartera no encontrada")
    # cascade="all, delete-orphan" en el modelo se encarga de borrar movimientos
    db.delete(cartera)
    db.commit()
    return {"ok": True}
