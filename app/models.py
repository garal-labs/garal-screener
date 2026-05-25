from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, declarative_base, relationship

Base = declarative_base()

TIPOS_MOVIMIENTO = {"compra", "venta"}
TIPOS_INSTRUMENTO = {"accion", "etf", "fondo", "otro"}


class Cartera(Base):
    __tablename__ = "carteras"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = Column(String, nullable=False)
    descripcion: Mapped[str | None] = Column(Text, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)

    # cascade="all, delete-orphan" -> al borrar cartera se borran sus movimientos
    movimientos: Mapped[list["Movimiento"]] = relationship("Movimiento", back_populates="cartera", cascade="all, delete-orphan")


class Instrumento(Base):
    __tablename__ = "instrumentos"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    isin: Mapped[str] = Column(String, unique=True, index=True, nullable=False)
    ticker: Mapped[str | None] = Column(String, nullable=True)
    nombre: Mapped[str | None] = Column(String, nullable=True)
    tipo: Mapped[str | None] = Column(String, nullable=True)  # accion | etf | fondo | otro
    sector: Mapped[str | None] = Column(String, nullable=True)
    pais: Mapped[str | None] = Column(String, nullable=True)
    moneda: Mapped[str | None] = Column(String, nullable=True)  # EUR, USD, JPY...
    exchange: Mapped[str | None] = Column(String, nullable=True)  # NYSE, BME, XETRA...
    updated_at: Mapped[datetime | None] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movimientos: Mapped[list["Movimiento"]] = relationship("Movimiento", back_populates="instrumento")


class Movimiento(Base):
    __tablename__ = "movimientos"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    cartera_id: Mapped[int] = Column(Integer, ForeignKey("carteras.id", ondelete="CASCADE"), nullable=False)
    instrumento_id: Mapped[int] = Column(Integer, ForeignKey("instrumentos.id"), nullable=False)
    tipo: Mapped[str] = Column(String, nullable=False)  # compra | venta
    fecha: Mapped[Date] = Column(Date, nullable=False)
    cantidad: Mapped[float] = Column(Float, nullable=False)
    precio: Mapped[float] = Column(Float, nullable=False)  # en moneda original del instrumento
    comision: Mapped[float] = Column(Float, default=0.0)  # opcional, default 0
    tipo_cambio: Mapped[float | None] = Column(Float, nullable=True)  # opcional, EUR/moneda en la fecha
    notas: Mapped[str | None] = Column(Text, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)

    cartera: Mapped["Cartera"] = relationship("Cartera", back_populates="movimientos")
    instrumento: Mapped["Instrumento"] = relationship("Instrumento", back_populates="movimientos")
