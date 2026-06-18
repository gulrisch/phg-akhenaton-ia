from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import anthropic
import os

from models.database import get_db
from models.oeuvre import Oeuvre
from models.vente import Vente, StatutVente
from models.user import User
from routers.auth import get_current_user

router = APIRouter()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class Message(BaseModel):
    role: str  # "user" ou "assistant"
    content: str


class ChatRequest(BaseModel):
    oeuvre_id: str
    messages: List[Message]


@router.post("/", summary="Chatbot IA contextualisé par œuvre")
def chat_avec_livre(
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Vérifier que l'utilisateur a acheté l'œuvre
    oeuvre = db.query(Oeuvre).filter(Oeuvre.id == data.oeuvre_id).first()
    if not oeuvre:
        raise HTTPException(status_code=404, detail="Œuvre introuvable")

    achat = db.query(Vente).filter(
        Vente.oeuvre_id == data.oeuvre_id,
        Vente.acheteur_id == current_user.id,
        Vente.statut == StatutVente.complete
    ).first()

    if not achat:
        raise HTTPException(
            status_code=403,
            detail="Vous devez acheter cette œuvre pour accéder au chatbot"
        )

    system_prompt = f"""Tu es l'assistant IA de l'œuvre "{oeuvre.titre}" sur la plateforme PHG AKHENATON IA.

Description de l'œuvre : {oeuvre.description}
Catégorie : {oeuvre.categorie}
Langue : {oeuvre.langue}

Tu aides le lecteur à mieux comprendre et explorer cette œuvre. Tu peux :
- Répondre aux questions sur les thèmes abordés
- Proposer des réflexions approfondies
- Donner le contexte culturel et intellectuel
- Suggérer d'autres œuvres similaires sur PHG AKHENATON IA

Tu représentes la puissance de l'édition africaine francophone. Sois éloquent, inspirant et précis.
Réponds toujours en {oeuvre.langue if oeuvre.langue != 'fr' else 'français'}."""

    messages = [{"role": m.role, "content": m.content} for m in data.messages]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=system_prompt,
        messages=messages
    )

    return {
        "response": response.content[0].text,
        "oeuvre": oeuvre.titre,
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens
    }


@router.get("/preview/{oeuvre_id}", summary="Preview chatbot sans achat (3 messages gratuits)")
def chat_preview(
    oeuvre_id: str,
    question: str,
    db: Session = Depends(get_db)
):
    oeuvre = db.query(Oeuvre).filter(Oeuvre.id == oeuvre_id).first()
    if not oeuvre:
        raise HTTPException(status_code=404, detail="Œuvre introuvable")

    system_prompt = f"""Tu es l'assistant IA de l'œuvre "{oeuvre.titre}".
Description : {oeuvre.description[:500] if oeuvre.description else ""}
Donne une réponse courte et engageante qui donne envie d'acheter l'œuvre.
À la fin, invite l'utilisateur à acheter l'œuvre pour accéder au chatbot complet."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": question}]
    )

    return {
        "response": response.content[0].text,
        "preview": True,
        "cta": f"Achetez '{oeuvre.titre}' pour {oeuvre.prix}€ et accédez au chatbot complet !"
    }
