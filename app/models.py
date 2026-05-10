from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum

Base = declarative_base()


class TipoMovimiento(str, enum.Enum):
    compra = "compra"
    venta = "venta"


class TipoInstrumento(str, enum.Enum):
    accion = "accion"
    etf = "etf"
    fondo = "fondo"
    otro = "otro"


class Cartera(Base):
    __tablename__ = "carteras"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    movimientos = relationship("Movimiento", back_populates="cartera")


class Instrumento(Base):
    __tablename__ = "instrumentos"

    id = Column(Integer, primary_key=True, index=True)
    isin = Column(String, unique=True, index=True, nullable=False)
    ticker = Column(String, nullable=True)           # autodescubierto por IA
    nombre = Column(String, nullable=True)           # autodescubierto por IA
    tipo = Column(String, nullable=True)             # autodescubierto por IA
    sector = Column(String, nullable=True)           # autodescubierto por IA
    pais = Column(String, nullable=True)             # autodescubierto por IA
    moneda = Column(String, nullable=True)           # autodescubierto por IA (EUR, USD, JPY...)
    exchange = Column(String, nullable=True)         # autodescubierto por IA
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movimientos = relationship("Movimiento", back_populates="instrumento")


class Movimiento(Base):
    __tablename__ = "movimientos"

    id = Column(Integer, primary_key=True, index=True)
    cartera_id = Column(Integer, ForeignKey("carteras.id"), nullable=False)
    instrumento_id = Column(Integer, ForeignKey("instrumentos.id"), nullable=False)
    tipo = Column(String, nullable=False)            # compra / venta
    fecha = Column(Date, nullable=False)
    cantidad = Column(Float, nullable=False)
    precio = Column(Float, nullable=False)           # en moneda original del instrumento
    comision = Column(Float, default=0.0)            # opcional, default 0
    tipo_cambio = Column(Float, nullable=True)       # opcional, EUR/moneda en la fecha
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cartera = relationship("Cartera", back_populates="movimientos")
    instrumento = relationship("Instrumento", back_populates="movimientos")
