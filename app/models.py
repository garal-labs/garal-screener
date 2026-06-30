from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()

TIPOS_MOVIMIENTO = {"compra", "venta"}
TIPOS_INSTRUMENTO = {"accion", "etf", "fondo", "otro"}


class Cartera(Base):
    __tablename__ = "carteras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String)
    descripcion: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())

    # cascade="all, delete-orphan" -> al borrar cartera se borran sus movimientos
    movimientos: Mapped[list["Movimiento"]] = relationship(
        "Movimiento", back_populates="cartera", cascade="all, delete-orphan"
    )


class Instrumento(Base):
    __tablename__ = "instrumentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    isin: Mapped[str] = mapped_column(String, unique=True, index=True)
    ticker: Mapped[str | None] = mapped_column(String)
    nombre: Mapped[str | None] = mapped_column(String)
    tipo: Mapped[str | None] = mapped_column(String)  # accion | etf | fondo | otro
    sector: Mapped[str | None] = mapped_column(String)
    pais: Mapped[str | None] = mapped_column(String)
    moneda: Mapped[str | None] = mapped_column(String)  # EUR, USD, JPY...
    exchange: Mapped[str | None] = mapped_column(String)  # NYSE, BME, XETRA...
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.now(), onupdate=datetime.now()
    )

    movimientos: Mapped[list["Movimiento"]] = relationship(
        "Movimiento", back_populates="instrumento"
    )


class Movimiento(Base):
    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cartera_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("carteras.id", ondelete="CASCADE")
    )
    instrumento_id: Mapped[int] = mapped_column(Integer, ForeignKey("instrumentos.id"))
    tipo: Mapped[str] = mapped_column(String)  # compra | venta
    fecha: Mapped[date] = mapped_column(Date)
    cantidad: Mapped[float] = mapped_column(Float)
    precio: Mapped[float] = mapped_column(Float)  # en moneda original del instrumento
    comision: Mapped[float] = mapped_column(Float, default=0.0)  # opcional, default 0
    tipo_cambio: Mapped[float | None] = mapped_column(
        Float
    )  # opcional, EUR/moneda en la fecha
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())

    cartera: Mapped["Cartera"] = relationship("Cartera", back_populates="movimientos")
    instrumento: Mapped["Instrumento"] = relationship(
        "Instrumento", back_populates="movimientos"
    )
