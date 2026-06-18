from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from models.database import get_db
from models.user import User, Role
from routers.auth import get_current_user

router = APIRouter()


class ProfilUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    bio: Optional[str] = None
    pays: Optional[str] = None


@router.get("/", summary="Lister tous les auteurs")
def lister_auteurs(db: Session = Depends(get_db)):
    auteurs = db.query(User).filter(User.role == Role.auteur, User.is_active == True).all()
    return [_format_auteur(a) for a in auteurs]


@router.get("/{auteur_id}", summary="Profil public d'un auteur")
def profil_auteur(auteur_id: str, db: Session = Depends(get_db)):
    auteur = db.query(User).filter(User.id == auteur_id).first()
    if not auteur:
        raise HTTPException(status_code=404, detail="Auteur introuvable")
    return _format_auteur(auteur)


@router.put("/profil", summary="Mettre à jour son profil auteur")
def update_profil(
    data: ProfilUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if data.nom:
        current_user.nom = data.nom
    if data.prenom:
        current_user.prenom = data.prenom
    if data.bio:
        current_user.bio = data.bio
    if data.pays:
        current_user.pays = data.pays
    db.commit()
    return {"message": "Profil mis à jour", "profil": _format_auteur(current_user)}


@router.post("/devenir-auteur", summary="Passer au statut auteur")
def devenir_auteur(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    current_user.role = Role.auteur
    db.commit()
    return {
        "message": "Bienvenue dans la famille des auteurs PHG AKHENATON IA !",
        "prochaine_etape": "Souscrivez à un plan auteur pour publier vos œuvres"
    }


def _format_auteur(u: User) -> dict:
    return {
        "id": str(u.id),
        "nom": u.nom,
        "prenom": u.prenom,
        "bio": u.bio,
        "pays": u.pays,
        "abonnement_actif": u.abonnement_actif
    }
