from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

TIPOS_MOVIMIENTO = {"compra", "venta"}
TIPOS_INSTRUMENTO = {"accion", "etf", "fondo", "otro"}


class Cartera(Base):
    __tablename__ = "carteras"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # cascade="all, delete-orphan" -> al borrar cartera se borran sus movimientos
    movimientos = relationship("Movimiento", back_populates="cartera", cascade="all, delete-orphan")


class Instrumento(Base):
    __tablename__ = "instrumentos"

    id = Column(Integer, primary_key=True, index=True)
    isin = Column(String, unique=True, index=True, nullable=False)
    ticker = Column(String, nullable=True)
    nombre = Column(String, nullable=True)
    tipo = Column(String, nullable=True)  # accion | etf | fondo | otro
    sector = Column(String, nullable=True)
    pais = Column(String, nullable=True)
    moneda = Column(String, nullable=True)  # EUR, USD, JPY...
    exchange = Column(String, nullable=True)  # NYSE, BME, XETRA...
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movimientos = relationship("Movimiento", back_populates="instrumento")


class Movimiento(Base):
    __tablename__ = "movimientos"

    id = Column(Integer, primary_key=True, index=True)
    cartera_id = Column(Integer, ForeignKey("carteras.id", ondelete="CASCADE"), nullable=False)
    instrumento_id = Column(Integer, ForeignKey("instrumentos.id"), nullable=False)
    tipo = Column(String, nullable=False)  # compra | venta
    fecha = Column(Date, nullable=False)
    cantidad = Column(Float, nullable=False)
    precio = Column(Float, nullable=False)  # en moneda original del instrumento
    comision = Column(Float, default=0.0)  # opcional, default 0
    tipo_cambio = Column(Float, nullable=True)  # opcional, EUR/moneda en la fecha
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cartera = relationship("Cartera", back_populates="movimientos")
    instrumento = relationship("Instrumento", back_populates="movimientos")
