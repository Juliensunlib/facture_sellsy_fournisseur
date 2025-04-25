import os
from dotenv import load_dotenv

# Charger les variables d'environnement à partir du fichier .env
load_dotenv()

# Sellsy V2 - OAuth2 (utilisé aussi pour l'API V1)
SELLSY_CLIENT_ID = os.getenv("SELLSY_CLIENT_ID")
SELLSY_CLIENT_SECRET = os.getenv("SELLSY_CLIENT_SECRET")
SELLSY_V2_API_URL = os.getenv("SELLSY_V2_API_URL", "https://api.sellsy.com/v2")

# Airtable
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_SUPPLIER_TABLE_NAME = os.getenv("AIRTABLE_SUPPLIER_TABLE_NAME")

# Webhook & PDF
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PDF_STORAGE_DIR = os.getenv("PDF_STORAGE_DIR", "pdf_invoices_suppliers")

# Liste des variables obligatoires pour faire fonctionner l'app
required_vars = {
    "SELLSY_CLIENT_ID": SELLSY_CLIENT_ID,
    "SELLSY_CLIENT_SECRET": SELLSY_CLIENT_SECRET,
    "AIRTABLE_API_KEY": AIRTABLE_API_KEY,
    "AIRTABLE_BASE_ID": AIRTABLE_BASE_ID,
    "AIRTABLE_SUPPLIER_TABLE_NAME": AIRTABLE_SUPPLIER_TABLE_NAME,
}

# Variables critiques recommandées pour la prod
production_vars = {
    "WEBHOOK_SECRET": WEBHOOK_SECRET
}

# Vérifications
missing_vars = [name for name, value in required_vars.items() if not value]
missing_prod_vars = [name for name, value in production_vars.items() if not value]

if missing_vars:
    print("❌ ERREUR: Variables d'environnement manquantes :", ", ".join(missing_vars))
    print("➡️ Vérifiez votre .env ou les secrets GitHub/Render.")

# Indique si la configuration est utilisable
CONFIG_VALID = len(missing_vars) == 0

# Détection de l'environnement de prod
is_production = os.getenv("ENVIRONMENT", "").lower() == "production"

# Alerte si variables critiques manquantes en production
if CONFIG_VALID and is_production and missing_prod_vars:
    print("⚠️ AVERTISSEMENT CRITIQUE: Variables de sécurité manquantes :", ", ".join(missing_prod_vars))
    if "WEBHOOK_SECRET" in missing_prod_vars:
        CONFIG_VALID = False
        print("❌ Le WEBHOOK_SECRET est requis pour vérifier la signature des appels webhook.")
elif CONFIG_VALID and not WEBHOOK_SECRET:
    print("⚠️ AVERTISSEMENT: WEBHOOK_SECRET non défini, vérification des signatures webhook désactivée.")

# Création du répertoire de stockage PDF si inexistant
if CONFIG_VALID and not os.path.exists(PDF_STORAGE_DIR):
    try:
        os.makedirs(PDF_STORAGE_DIR)
        print(f"📁 Répertoire PDF créé : {PDF_STORAGE_DIR}")
    except Exception as e:
        print(f"❌ ERREUR: Impossible de créer le répertoire {PDF_STORAGE_DIR} : {e}")
