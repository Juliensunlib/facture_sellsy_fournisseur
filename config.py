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
# Correction du nom de variable pour assurer la cohérence
AIRTABLE_SUPPLIER_TABLE_NAME = os.getenv("AIRTABLE_SUPPLIER_TABLE_NAME")

# Configuration du webhook
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Répertoire pour stocker les PDF des factures - aligné avec le .gitignore
PDF_STORAGE_DIR = os.getenv("PDF_STORAGE_DIR", "pdf_invoices_suppliers")

# Vérification des variables requises
required_vars = {
    "SELLSY_CLIENT_ID": SELLSY_CLIENT_ID,
    "SELLSY_CLIENT_SECRET": SELLSY_CLIENT_SECRET,
    "AIRTABLE_API_KEY": AIRTABLE_API_KEY,
    "AIRTABLE_BASE_ID": AIRTABLE_BASE_ID,
    "AIRTABLE_SUPPLIER_TABLE_NAME": AIRTABLE_SUPPLIER_TABLE_NAME
}

missing_vars = [name for name, value in required_vars.items() if not value]

if missing_vars:
    print(f"ERREUR: Variables d'environnement manquantes: {', '.join(missing_vars)}")
    print("Assurez-vous que ces variables sont définies dans le fichier .env ou dans les secrets GitHub.")
    
# Définir une variable pour indiquer si la configuration est complète
CONFIG_VALID = len(missing_vars) == 0

# Si WEBHOOK_SECRET n'est pas défini, émettre un avertissement
if not WEBHOOK_SECRET and CONFIG_VALID:
    print("AVERTISSEMENT: WEBHOOK_SECRET non défini. La vérification des signatures webhook sera désactivée.")
    print("Cette configuration n'est pas recommandée pour un environnement de production.")
