from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers.api import router

app = FastAPI(
    title="Mi Cartera API",
    description="Backend para gestión de cartera de inversión personal",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción cambia esto a tu dominio de Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
