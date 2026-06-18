from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
import stripe
import os

from models.database import get_db
from models.oeuvre import Oeuvre
from models.vente import Vente, StatutVente
from models.user import User
from routers.auth import get_current_user

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

COMMISSION_RATE = 0.20  # 20% plateforme


class CheckoutRequest(BaseModel):
    oeuvre_id: str
    success_url: str = "https://gulrisch.com/merci"
    cancel_url: str = "https://gulrisch.com/catalogue"


@router.post("/checkout", summary="Créer une session de paiement Stripe")
def create_checkout(
    data: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    oeuvre = db.query(Oeuvre).filter(Oeuvre.id == data.oeuvre_id).first()
    if not oeuvre:
        raise HTTPException(status_code=404, detail="Œuvre introuvable")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {
                    "name": oeuvre.titre,
                    "description": oeuvre.description[:100] if oeuvre.description else "",
                },
                "unit_amount": int(oeuvre.prix * 100),
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=data.success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=data.cancel_url,
        metadata={
            "oeuvre_id": str(oeuvre.id),
            "acheteur_id": str(current_user.id)
        }
    )

    # Créer la vente en attente
    vente = Vente(
        oeuvre_id=oeuvre.id,
        acheteur_id=current_user.id,
        montant=oeuvre.prix,
        stripe_session_id=session.id,
        statut=StatutVente.en_attente,
        montant_auteur=oeuvre.prix * (1 - COMMISSION_RATE),
        montant_plateforme=oeuvre.prix * COMMISSION_RATE
    )
    db.add(vente)
    db.commit()

    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/webhook", summary="Webhook Stripe — confirmation paiement")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook invalide")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        vente = db.query(Vente).filter(
            Vente.stripe_session_id == session["id"]
        ).first()
        if vente:
            vente.statut = StatutVente.complete
            vente.stripe_payment_intent = session.get("payment_intent")
            # Incrémenter les ventes de l'œuvre
            oeuvre = db.query(Oeuvre).filter(Oeuvre.id == vente.oeuvre_id).first()
            if oeuvre:
                oeuvre.nb_ventes += 1
            db.commit()

    return {"received": True}


@router.get("/mes-achats", summary="Œuvres achetées par l'utilisateur")
def mes_achats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ventes = db.query(Vente).filter(
        Vente.acheteur_id == current_user.id,
        Vente.statut == StatutVente.complete
    ).all()
    return [{"oeuvre_id": str(v.oeuvre_id), "date": str(v.created_at)} for v in ventes]
