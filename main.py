"""
PHG AKHENATON IA — Marketplace d'œuvres numériques africaine francophone
FastAPI Backend — Railway deployment
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
import uvicorn

from routers import auth, auteurs, oeuvres, ventes, commissions, chatbot, audio

app = FastAPI(
    title="PHG AKHENATON IA",
    description="Marketplace numérique africaine francophone — GULRISCH Empire",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Authentification"])
app.include_router(auteurs.router, prefix="/auteurs", tags=["Auteurs"])
app.include_router(oeuvres.router, prefix="/oeuvres", tags=["Œuvres"])
app.include_router(ventes.router, prefix="/ventes", tags=["Ventes"])
app.include_router(commissions.router, prefix="/commissions", tags=["Commissions"])
app.include_router(chatbot.router, prefix="/chatbot", tags=["Chatbot IA"])
app.include_router(audio.router, prefix="/audio", tags=["Audio ElevenLabs"])


@app.get("/")
async def root():
    return {
        "platform": "PHG AKHENATON IA",
        "empire": "GULRISCH Empire — PUISSANCE HUMAINE GLOBALE",
        "status": "En ligne 🟢",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
