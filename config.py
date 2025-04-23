import os
from dotenv import load_dotenv

# Charger les variables d'environnement à partir du fichier .env si disponible
load_dotenv()

# Configuration Sellsy
SELLSY_CLIENT_ID = os.getenv("SELLSY_CLIENT_ID")
SELLSY_CLIENT_SECRET = os.getenv("SELLSY_CLIENT_SECRET")
SELLSY_API_URL = os.getenv("SELLSY_API_URL", "https://api.sellsy.com/v2")

# Configuration Airtable
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_SUPPLIER_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")

# Configuration du webhook
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "votre_secret_webhook")

# Répertoire pour stocker les PDF des factures
PDF_STORAGE_DIR = os.getenv("PDF_STORAGE_DIR", "pdf_invoices")

# Vérification des variables requises
missing_vars = []
for var_name in ["SELLSY_CLIENT_ID", "SELLSY_CLIENT_SECRET", "AIRTABLE_API_KEY", "AIRTABLE_BASE_ID", "AIRTABLE_TABLE_NAME"]:
    if not locals()[var_name]:
        missing_vars.append(var_name)

if missing_vars:
    print(f"ERREUR: Variables d'environnement manquantes: {', '.join(missing_vars)}")
    print("Assurez-vous que ces variables sont définies dans le fichier .env ou dans les secrets GitHub.")
