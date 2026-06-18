from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import stripe
import os

from models.database import get_db
from models.commission import Commission, Abonnement, TypeCommission
from models.user import User
from routers.auth import get_current_user

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Plans abonnement auteur
PLANS = {
    "starter": {
        "nom": "Starter Auteur",
        "prix": 9.99,
        "stripe_price_id": os.getenv("STRIPE_PRICE_STARTER_AUTEUR", ""),
        "avantages": ["Jusqu'à 5 œuvres", "Stats basiques", "Commission 20%"]
    },
    "pro": {
        "nom": "Pro Auteur",
        "prix": 19.99,
        "stripe_price_id": os.getenv("STRIPE_PRICE_PRO_AUTEUR", ""),
        "avantages": ["Œuvres illimitées", "Stats avancées", "Commission 15%", "Badge Auteur PHG"]
    }
}


@router.get("/plans", summary="Plans d'abonnement auteur disponibles")
def get_plans():
    return PLANS


@router.post("/souscrire/{plan}", summary="Souscrire à un abonnement auteur")
def souscrire(
    plan: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Plan invalide")

    plan_data = PLANS[plan]
    if not plan_data["stripe_price_id"]:
        raise HTTPException(status_code=503, detail="Plan non encore configuré sur Stripe")

    # Créer ou récupérer customer Stripe
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            name=f"{current_user.prenom} {current_user.nom}"
        )
        current_user.stripe_customer_id = customer.id
        db.commit()

    subscription = stripe.Subscription.create(
        customer=current_user.stripe_customer_id,
        items=[{"price": plan_data["stripe_price_id"]}],
        payment_behavior="default_incomplete",
        expand=["latest_invoice.payment_intent"]
    )

    abo = Abonnement(
        auteur_id=current_user.id,
        stripe_subscription_id=subscription.id,
        plan=plan,
        montant=plan_data["prix"]
    )
    db.add(abo)
    current_user.abonnement_actif = True
    db.commit()

    return {
        "subscription_id": subscription.id,
        "client_secret": subscription.latest_invoice.payment_intent.client_secret,
        "plan": plan
    }


@router.get("/mes-commissions", summary="Commissions et revenus de l'auteur")
def mes_commissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    commissions = db.query(Commission).filter(
        Commission.auteur_id == current_user.id
    ).all()

    total_gagné = sum(c.montant for c in commissions if c.paye)
    total_en_attente = sum(c.montant for c in commissions if not c.paye)

    return {
        "total_gagné": total_gagné,
        "total_en_attente": total_en_attente,
        "commissions": [
            {
                "id": str(c.id),
                "type": c.type,
                "montant": c.montant,
                "paye": c.paye,
                "date": str(c.created_at)
            }
            for c in commissions
        ]
    }


@router.get("/dashboard", summary="Dashboard complet auteur")
def dashboard_auteur(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from models.oeuvre import Oeuvre
    from models.vente import Vente, StatutVente

    oeuvres = db.query(Oeuvre).filter(Oeuvre.auteur_id == current_user.id).all()
    total_ventes = sum(o.nb_ventes for o in oeuvres)
    total_vues = sum(o.nb_vues for o in oeuvres)

    commissions = db.query(Commission).filter(
        Commission.auteur_id == current_user.id
    ).all()
    revenus_total = sum(c.montant for c in commissions)

    return {
        "auteur": {
            "nom": f"{current_user.prenom} {current_user.nom}",
            "abonnement": current_user.abonnement_actif
        },
        "oeuvres": len(oeuvres),
        "total_ventes": total_ventes,
        "total_vues": total_vues,
        "revenus_total": revenus_total,
        "catalogue": [
            {
                "id": str(o.id),
                "titre": o.titre,
                "prix": o.prix,
                "ventes": o.nb_ventes,
                "vues": o.nb_vues
            }
            for o in oeuvres
        ]
    }
