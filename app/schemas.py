from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# -- Cartera ------------------------------------------------------------------

class CarteraCreate(BaseModel):
    nombre: str
    descripcion: str | None = None

class CarteraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None
    created_at: datetime

# -- Instrumento --------------------------------------------------------------

class InstrumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    isin: str
    ticker: str | None = None
    nombre: str | None = None
    tipo: str | None = None
    sector: str | None = None
    pais: str | None = None
    moneda: str | None = None
    exchange: str | None = None

class InstrumentoUpdate(BaseModel):
    """Schema para PATCH /instrumentos/{id} — todos los campos opcionales."""

    ticker: str | None = None
    nombre: str | None = None
    tipo: str | None = None
    sector: str | None = None
    pais: str | None = None
    moneda: str | None = None
    exchange: str | None = None

# -- Movimiento ---------------------------------------------------------------

class MovimientoCreate(BaseModel):
    cartera_id: int
    isin: str
    tipo: str = Field(pattern="^(compra|venta)$")  # validacion en schema
    fecha: date
    cantidad: float = Field(gt=0)
    precio: float = Field(gt=0)
    comision: float | None = Field(default=0.0, ge=0)
    tipo_cambio: float | None = Field(default=None, gt=0)
    notas: str | None = None

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
    tipo_cambio: float | None
    notas: str | None
    created_at: datetime

# -- Posicion calculada -------------------------------------------------------

class PosicionOut(BaseModel):
    instrumento: InstrumentoOut
    cantidad_actual: float
    coste_total: float
    precio_medio: float
    plusvalia_realizada: float
    precio_actual: float | None = None
    valor_actual: float | None = None
    plusvalia_latente: float | None = None
    rentabilidad_pct: float | None = None
    plusvalia_total: float | None = None

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
    posiciones: list[PosicionOut]

# -- Analisis / agrupaciones --------------------------------------------------

class GrupoAnalisis(BaseModel):
    nombre: str
    valor: float
    peso_pct: float

class AnalisisCartera(BaseModel):
    por_sector: list[GrupoAnalisis]
    por_pais: list[GrupoAnalisis]
    por_tipo: list[GrupoAnalisis]
    por_moneda: list[GrupoAnalisis]
