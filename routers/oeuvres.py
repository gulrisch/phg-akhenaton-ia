from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import boto3
import os
import uuid

from models.database import get_db
from models.oeuvre import Oeuvre
from models.user import User, Role
from routers.auth import get_current_user

router = APIRouter()

# Cloudflare R2
def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto"
    )

R2_BUCKET = os.getenv("R2_BUCKET", "phg-akhenaton")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")  # ex: https://pub-xxx.r2.dev


def upload_to_r2(file: UploadFile, folder: str) -> str:
    r2 = get_r2_client()
    ext = file.filename.split(".")[-1]
    key = f"{folder}/{uuid.uuid4()}.{ext}"
    r2.upload_fileobj(
        file.file,
        R2_BUCKET,
        key,
        ExtraArgs={"ContentType": file.content_type}
    )
    return f"{R2_PUBLIC_URL}/{key}"


# ─── CRUD ────────────────────────────────────────────────

@router.get("/", summary="Lister toutes les œuvres publiées")
def lister_oeuvres(
    categorie: Optional[str] = None,
    langue: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    query = db.query(Oeuvre).filter(Oeuvre.is_published == True)
    if categorie:
        query = query.filter(Oeuvre.categorie == categorie)
    if langue:
        query = query.filter(Oeuvre.langue == langue)
    oeuvres = query.offset(skip).limit(limit).all()
    return [_format_oeuvre(o) for o in oeuvres]


@router.get("/{oeuvre_id}", summary="Détail d'une œuvre")
def detail_oeuvre(oeuvre_id: str, db: Session = Depends(get_db)):
    oeuvre = db.query(Oeuvre).filter(Oeuvre.id == oeuvre_id).first()
    if not oeuvre:
        raise HTTPException(status_code=404, detail="Œuvre introuvable")
    oeuvre.nb_vues += 1
    db.commit()
    return _format_oeuvre(oeuvre)


@router.post("/", summary="Publier une nouvelle œuvre")
async def creer_oeuvre(
    titre: str = Form(...),
    description: str = Form(""),
    categorie: str = Form(""),
    langue: str = Form("fr"),
    prix: float = Form(...),
    tags: str = Form(""),
    couverture: Optional[UploadFile] = File(None),
    fichier_pdf: Optional[UploadFile] = File(None),
    fichier_epub: Optional[UploadFile] = File(None),
    fichier_mp3: Optional[UploadFile] = File(None),
    fichier_mp4: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [Role.auteur, Role.admin]:
        raise HTTPException(status_code=403, detail="Réservé aux auteurs")

    oeuvre = Oeuvre(
        auteur_id=current_user.id,
        titre=titre,
        description=description,
        categorie=categorie,
        langue=langue,
        prix=prix,
        tags=tags
    )

    if couverture:
        oeuvre.couverture_url = upload_to_r2(couverture, "couvertures")
    if fichier_pdf:
        oeuvre.fichier_pdf_url = upload_to_r2(fichier_pdf, "pdf")
    if fichier_epub:
        oeuvre.fichier_epub_url = upload_to_r2(fichier_epub, "epub")
    if fichier_mp3:
        oeuvre.fichier_mp3_url = upload_to_r2(fichier_mp3, "audio")
    if fichier_mp4:
        oeuvre.fichier_mp4_url = upload_to_r2(fichier_mp4, "video")

    oeuvre.is_published = True
    db.add(oeuvre)
    db.commit()
    db.refresh(oeuvre)
    return _format_oeuvre(oeuvre)


@router.delete("/{oeuvre_id}", summary="Supprimer une œuvre")
def supprimer_oeuvre(
    oeuvre_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    oeuvre = db.query(Oeuvre).filter(Oeuvre.id == oeuvre_id).first()
    if not oeuvre:
        raise HTTPException(status_code=404, detail="Œuvre introuvable")
    if str(oeuvre.auteur_id) != str(current_user.id) and current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Non autorisé")
    db.delete(oeuvre)
    db.commit()
    return {"message": "Œuvre supprimée"}


def _format_oeuvre(o: Oeuvre) -> dict:
    return {
        "id": str(o.id),
        "titre": o.titre,
        "description": o.description,
        "categorie": o.categorie,
        "langue": o.langue,
        "prix": o.prix,
        "couverture_url": o.couverture_url,
        "formats": {
            "pdf": bool(o.fichier_pdf_url),
            "epub": bool(o.fichier_epub_url),
            "audio": bool(o.fichier_mp3_url),
            "video": bool(o.fichier_mp4_url),
        },
        "nb_ventes": o.nb_ventes,
        "nb_vues": o.nb_vues,
        "note_moyenne": o.note_moyenne,
        "auteur_id": str(o.auteur_id),
        "created_at": str(o.created_at)
    }
