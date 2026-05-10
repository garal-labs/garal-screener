import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()  # carga .env en local; en Railway las vars vienen del entorno directamente

from app.database import init_db
from app.routers.api import router


def _allowed_origins() -> list[str]:
    """
    Lee ALLOWED_ORIGINS del entorno.
    Acepta '*' o una lista de dominios separados por coma:
      ALLOWED_ORIGINS=https://garal.vercel.app,https://staging.garal.vercel.app
    """
    raw = os.getenv("ALLOWED_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Garal Cartera API",
    description="Backend para gestión de cartera de inversión personal",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}