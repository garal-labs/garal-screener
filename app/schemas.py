from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# ── Cartera ───────────────────────────────────────────────────────────────────

class CarteraCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class CarteraOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True


# ── Instrumento ───────────────────────────────────────────────────────────────

class InstrumentoOut(BaseModel):
    id: int
    isin: str
    ticker: Optional[str]
    nombre: Optional[str]
    tipo: Optional[str]
    sector: Optional[str]
    pais: Optional[str]
    moneda: Optional[str]
    exchange: Optional[str]
    class Config:
        from_attributes = True


# ── Movimiento ────────────────────────────────────────────────────────────────

class MovimientoCreate(BaseModel):
    cartera_id: int
    isin: str
    tipo: str                               # compra | venta
    fecha: date
    cantidad: float = Field(gt=0)
    precio: float = Field(gt=0)
    comision: Optional[float] = 0.0
    tipo_cambio: Optional[float] = None     # si es None, se asume moneda EUR
    notas: Optional[str] = None

class MovimientoOut(BaseModel):
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
    class Config:
        from_attributes = True


# ── Posición calculada ────────────────────────────────────────────────────────

class PosicionOut(BaseModel):
    instrumento: InstrumentoOut
    # FIFO
    cantidad_actual: float
    coste_total: float
    precio_medio: float
    plusvalia_realizada: float
    # Tiempo real
    precio_actual: Optional[float]
    valor_actual: Optional[float]
    plusvalia_latente: Optional[float]
    rentabilidad_pct: Optional[float]
    plusvalia_total: Optional[float]


# ── Resumen cartera ───────────────────────────────────────────────────────────

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


# ── Análisis / agrupaciones ───────────────────────────────────────────────────

class GrupoAnalisis(BaseModel):
    nombre: str
    valor: float
    peso_pct: float

class AnalisisCartera(BaseModel):
    por_sector: List[GrupoAnalisis]
    por_pais: List[GrupoAnalisis]
    por_tipo: List[GrupoAnalisis]
    por_moneda: List[GrupoAnalisis]
