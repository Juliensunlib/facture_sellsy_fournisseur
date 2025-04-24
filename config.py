import os
from dotenv import load_dotenv

# Charger les variables d'environnement à partir du fichier .env si disponible
load_dotenv()

# Configuration Sellsy v1 (OAuth 1.0a)
SELLSY_V1_CONSUMER_TOKEN = os.getenv("SELLSY_V1_CONSUMER_TOKEN")
SELLSY_V1_CONSUMER_SECRET = os.getenv("SELLSY_V1_CONSUMER_SECRET")
SELLSY_V1_USER_TOKEN = os.getenv("SELLSY_V1_USER_TOKEN")
SELLSY_V1_USER_SECRET = os.getenv("SELLSY_V1_USER_SECRET")
SELLSY_V1_API_URL = os.getenv("SELLSY_V1_API_URL", "https://apifeed.sellsy.com/0")

# Configuration Airtable
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_SUPPLIER_TABLE_NAME = os.getenv("AIRTABLE_SUPPLIER_TABLE_NAME")

# Configuration du webhook et stockage PDF
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PDF_STORAGE_DIR = os.getenv("PDF_STORAGE_DIR", "pdf_invoices_suppliers")

# Vérification des variables requises
required_vars = {
    "SELLSY_V1_CONSUMER_TOKEN": SELLSY_V1_CONSUMER_TOKEN,
    "SELLSY_V1_CONSUMER_SECRET": SELLSY_V1_CONSUMER_SECRET,
    "SELLSY_V1_USER_TOKEN": SELLSY_V1_USER_TOKEN,
    "SELLSY_V1_USER_SECRET": SELLSY_V1_USER_SECRET,
    "AIRTABLE_API_KEY": AIRTABLE_API_KEY,
    "AIRTABLE_BASE_ID": AIRTABLE_BASE_ID,
    "AIRTABLE_SUPPLIER_TABLE_NAME": AIRTABLE_SUPPLIER_TABLE_NAME
}

# Variables recommandées pour la production
production_vars = {
    "WEBHOOK_SECRET": WEBHOOK_SECRET
}

missing_vars = [name for name, value in required_vars.items() if not value]
missing_prod_vars = [name for name, value in production_vars.items() if not value]

if missing_vars:
    print(f"ERREUR: Variables d'environnement requises manquantes: {', '.join(missing_vars)}")
    print("Assurez-vous que ces variables sont définies dans le fichier .env ou dans les secrets GitHub.")

# Définir une variable pour indiquer si la configuration est complète
CONFIG_VALID = len(missing_vars) == 0

# Vérifier si on est en production
is_production = os.getenv("ENVIRONMENT", "").lower() == "production"

# Avertissement si des variables de production sont manquantes
if CONFIG_VALID and is_production and missing_prod_vars:
    print(f"AVERTISSEMENT CRITIQUE: Variables requises en production manquantes: {', '.join(missing_prod_vars)}")
    print("Cette configuration est DANGEREUSE pour un environnement de production!")
    if "WEBHOOK_SECRET" in missing_prod_vars:
        CONFIG_VALID = False
        print("La vérification des signatures webhook est OBLIGATOIRE en production.")
elif CONFIG_VALID and not WEBHOOK_SECRET:
    print("AVERTISSEMENT: WEBHOOK_SECRET non défini. La vérification des signatures webhook sera désactivée.")
    print("Cette configuration n'est pas recommandée pour un environnement de production.")

# Création du répertoire de stockage PDF si inexistant
if CONFIG_VALID and not os.path.exists(PDF_STORAGE_DIR):
    try:
        os.makedirs(PDF_STORAGE_DIR)
        print(f"Répertoire de stockage PDF créé: {PDF_STORAGE_DIR}")
    except Exception as e:
        print(f"ERREUR: Impossible de créer le répertoire {PDF_STORAGE_DIR}: {e}")
