from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.security import get_current_user, get_owned_cartera
from app.database import get_db

router = APIRouter(prefix="/carteras", tags=["Carteras"])


@router.post("", response_model=schemas.CarteraOut)
def crear_cartera(
    data: schemas.CarteraCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cartera = models.Cartera(**data.model_dump(), user_id=current_user.id)
    db.add(cartera)
    db.commit()
    db.refresh(cartera)
    return cartera


@router.get("", response_model=list[schemas.CarteraOut])
def listar_carteras(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Cartera).filter(models.Cartera.user_id == current_user.id).all()
    )


@router.delete("/{cartera_id}")
def eliminar_cartera(
    cartera: models.Cartera = Depends(get_owned_cartera),
    db: Session = Depends(get_db),
):
    # cascade="all, delete-orphan" en el modelo se encarga de borrar movimientos
    db.delete(cartera)
    db.commit()
    return {"ok": True}
