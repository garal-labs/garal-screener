from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date, datetime


# -- Cartera ------------------------------------------------------------------

class CarteraCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class CarteraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: Optional[str]
    created_at: datetime


# -- Instrumento --------------------------------------------------------------

class InstrumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    isin: str
    ticker: Optional[str] = None
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    sector: Optional[str] = None
    pais: Optional[str] = None
    moneda: Optional[str] = None
    exchange: Optional[str] = None

class InstrumentoUpdate(BaseModel):
    """Schema para PATCH /instrumentos/{id} — todos los campos opcionales."""
    ticker: Optional[str] = None
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    sector: Optional[str] = None
    pais: Optional[str] = None
    moneda: Optional[str] = None
    exchange: Optional[str] = None


# -- Movimiento ---------------------------------------------------------------

class MovimientoCreate(BaseModel):
    cartera_id: int
    isin: str
    tipo: str = Field(pattern="^(compra|venta)$")   # validacion en schema
    fecha: date
    cantidad: float = Field(gt=0)
    precio: float = Field(gt=0)
    comision: Optional[float] = Field(default=0.0, ge=0)
    tipo_cambio: Optional[float] = Field(default=None, gt=0)
    notas: Optional[str] = None

class MovimientoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cartera_id: int
    instrumento: InstrumentoOut
    tipo: str
    fecha: date
    cantidad: float
    precio: float
    comision: float
    tipo_cambio: Optional[float]
    notas: Optional[str]
    created_at: datetime


# -- Posicion calculada -------------------------------------------------------

class PosicionOut(BaseModel):
    instrumento: InstrumentoOut
    cantidad_actual: float
    coste_total: float
    precio_medio: float
    plusvalia_realizada: float
    precio_actual: Optional[float] = None
    valor_actual: Optional[float] = None
    plusvalia_latente: Optional[float] = None
    rentabilidad_pct: Optional[float] = None
    plusvalia_total: Optional[float] = None


# -- Resumen cartera ----------------------------------------------------------

class ResumenCartera(BaseModel):
    cartera: CarteraOut
    valor_total: float
    coste_total: float
    plusvalia_latente: float
    plusvalia_realizada: float
    plusvalia_total: float
    rentabilidad_pct: float
    num_posiciones: int
    posiciones: List[PosicionOut]


# -- Analisis / agrupaciones --------------------------------------------------

class GrupoAnalisis(BaseModel):
    nombre: str
    valor: float
    peso_pct: float

class AnalisisCartera(BaseModel):
    por_sector: List[GrupoAnalisis]
    por_pais: List[GrupoAnalisis]
    por_tipo: List[GrupoAnalisis]
    por_moneda: List[GrupoAnalisis]