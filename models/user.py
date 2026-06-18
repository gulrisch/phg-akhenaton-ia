from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from .database import Base


class Role(str, enum.Enum):
    acheteur = "acheteur"
    auteur = "auteur"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    nom = Column(String, nullable=False)
    prenom = Column(String)
    role = Column(Enum(Role), default=Role.acheteur)
    bio = Column(String)
    pays = Column(String)
    stripe_customer_id = Column(String)
    stripe_account_id = Column(String)  # Pour payout auteurs
    is_active = Column(Boolean, default=True)
    abonnement_actif = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    oeuvres = relationship("Oeuvre", back_populates="auteur")
    ventes = relationship("Vente", back_populates="acheteur")
    commissions = relationship("Commission", back_populates="auteur")
