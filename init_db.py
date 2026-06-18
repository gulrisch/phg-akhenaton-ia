"""
Script d'initialisation de la base de données PHG AKHENATON IA
Lance une seule fois au premier déploiement
"""
from models.database import Base, engine
from models.user import User
from models.oeuvre import Oeuvre
from models.vente import Vente
from models.commission import Commission, Abonnement

print("🏛️  PHG AKHENATON IA — Initialisation de la base de données...")
Base.metadata.create_all(bind=engine)
print("✅  Tables créées avec succès !")
print("   → users, oeuvres, ventes, commissions, abonnements")
