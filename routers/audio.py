from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
import httpx
import os

from models.database import get_db
from models.oeuvre import Oeuvre
from models.user import User, Role
from routers.auth import get_current_user

router = APIRouter()

N8N_WEBHOOK_AUDIO = os.getenv("N8N_WEBHOOK_AUDIO", "")


class AudioRequest(BaseModel):
    oeuvre_id: str
    texte: str  # Extrait à convertir en audio


@router.post("/generer", summary="Générer audio ElevenLabs via n8n")
async def generer_audio(
    data: AudioRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [Role.auteur, Role.admin]:
        raise HTTPException(status_code=403, detail="Réservé aux auteurs")

    oeuvre = db.query(Oeuvre).filter(
        Oeuvre.id == data.oeuvre_id,
        Oeuvre.auteur_id == current_user.id
    ).first()
    if not oeuvre:
        raise HTTPException(status_code=404, detail="Œuvre introuvable")

    if not N8N_WEBHOOK_AUDIO:
        raise HTTPException(status_code=503, detail="Webhook n8n non configuré")

    # Envoyer à n8n en arrière-plan
    background_tasks.add_task(
        _trigger_n8n_audio,
        oeuvre_id=str(oeuvre.id),
        titre=oeuvre.titre,
        texte=data.texte,
        auteur=f"{current_user.prenom} {current_user.nom}"
    )

    return {
        "message": "Génération audio lancée",
        "oeuvre": oeuvre.titre,
        "statut": "en_cours",
        "info": "Le fichier MP3 sera disponible dans quelques minutes"
    }


async def _trigger_n8n_audio(oeuvre_id: str, titre: str, texte: str, auteur: str):
    async with httpx.AsyncClient() as client:
        await client.post(N8N_WEBHOOK_AUDIO, json={
            "oeuvre_id": oeuvre_id,
            "titre": titre,
            "texte": texte,
            "auteur": auteur,
            "action": "generate_audio"
        }, timeout=30)


@router.get("/statut/{oeuvre_id}", summary="Statut de génération audio")
def statut_audio(
    oeuvre_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    oeuvre = db.query(Oeuvre).filter(Oeuvre.id == oeuvre_id).first()
    if not oeuvre:
        raise HTTPException(status_code=404, detail="Œuvre introuvable")

    return {
        "oeuvre_id": oeuvre_id,
        "titre": oeuvre.titre,
        "audio_disponible": bool(oeuvre.fichier_mp3_url),
        "url": oeuvre.fichier_mp3_url
    }
