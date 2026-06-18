from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from .database import Base


class StatutVente(str, enum.Enum):
    en_attente = "en_attente"
    complete = "complete"
    rembourse = "rembourse"
    echec = "echec"


class Vente(Base):
    __tablename__ = "ventes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    oeuvre_id = Column(UUID(as_uuid=True), ForeignKey("oeuvres.id"), nullable=False)
    acheteur_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    montant = Column(Float, nullable=False)
    devise = Column(String, default="EUR")
    stripe_session_id = Column(String)
    stripe_payment_intent = Column(String)
    statut = Column(Enum(StatutVente), default=StatutVente.en_attente)

    # Répartition automatique
    montant_auteur = Column(Float)    # 80% de la vente
    montant_plateforme = Column(Float)  # 20% de la vente

    created_at = Column(DateTime, default=datetime.utcnow)

    oeuvre = relationship("Oeuvre", back_populates="ventes")
    acheteur = relationship("User", back_populates="ventes")
