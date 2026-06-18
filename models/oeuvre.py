from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Integer, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from .database import Base


class Oeuvre(Base):
    __tablename__ = "oeuvres"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auteur_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    titre = Column(String, nullable=False)
    description = Column(Text)
    categorie = Column(String)           # roman, poésie, business, développement perso...
    langue = Column(String, default="fr")
    tags = Column(String)                # JSON string des tags
    couverture_url = Column(String)      # R2 URL
    prix = Column(Float, nullable=False)
    devise = Column(String, default="EUR")

    # Fichiers stockés sur Cloudflare R2
    fichier_pdf_url = Column(String)
    fichier_epub_url = Column(String)
    fichier_mp3_url = Column(String)
    fichier_mp4_url = Column(String)
    fichier_autre_url = Column(String)

    # Stats
    nb_ventes = Column(Integer, default=0)
    nb_vues = Column(Integer, default=0)
    note_moyenne = Column(Float, default=0.0)

    is_published = Column(Boolean, default=False)
    is_featured = Column(Boolean, default=False)  # Mis en avant par admin
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    auteur = relationship("User", back_populates="oeuvres")
    ventes = relationship("Vente", back_populates="oeuvre")
