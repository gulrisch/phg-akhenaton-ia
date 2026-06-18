from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from .database import Base


class TypeCommission(str, enum.Enum):
    vente = "vente"          # % sur chaque vente
    abonnement = "abonnement"  # mensuel auteur


class Commission(Base):
    __tablename__ = "commissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auteur_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    vente_id = Column(UUID(as_uuid=True), ForeignKey("ventes.id"), nullable=True)

    type = Column(Enum(TypeCommission), nullable=False)
    montant = Column(Float, nullable=False)
    taux = Column(Float)  # ex: 0.20 pour 20%
    description = Column(String)
    paye = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    auteur = relationship("User", back_populates="commissions")


class Abonnement(Base):
    __tablename__ = "abonnements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auteur_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    stripe_subscription_id = Column(String)
    plan = Column(String, default="starter")  # starter 9,99€ / pro 19,99€
    montant = Column(Float, default=9.99)
    actif = Column(Boolean, default=True)
    date_debut = Column(DateTime, default=datetime.utcnow)
    date_fin = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
