from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import time
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableAPI
from config import WEBHOOK_SECRET
import hmac
import hashlib
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webhook_handler")

app = FastAPI()
security = HTTPBearer(auto_error=False)  # Rendre l'authentification optionnelle pour les tests

# Initialisation des APIs
sellsy_api = SellsySupplierAPI()
airtable_api = AirtableAPI()

# Mode debug pour sauter la vérification de signature
DEBUG_SKIP_SIGNATURE = True  # Mettre à False en production

def verify_signature(signature: str, payload: bytes) -> bool:
    """
    Vérifie la signature du webhook Sellsy
    
    Args:
        signature: Signature reçue dans l'en-tête
        payload: Contenu brut de la requête
        
    Returns:
        True si la signature est valide, False sinon
    """
    # En mode debug, retourner toujours True
    if DEBUG_SKIP_SIGNATURE:
        logger.warning("⚠️ Mode DEBUG actif : vérification de signature désactivée")
        return True
        
    if not WEBHOOK_SECRET:
        logger.warning("⚠️ WEBHOOK_SECRET non défini, vérification désactivée mais non recommandée en production")
        return True
        
    try:
        # Calcul du hash HMAC SHA-256
        expected = hmac.new(
            WEBHOOK_SECRET.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Comparaison sécurisée pour éviter les attaques temporelles
        return hmac.compare_digest(signature, expected)
    except Exception as e:
        logger.error(f"Erreur lors de la vérification de la signature: {e}")
        return False

async def validate_webhook(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Valide la signature du webhook Sellsy
    
    Args:
        request: Requête FastAPI
        credentials: Informations d'authentification
        
    Returns:
        Le payload de la requête si la validation réussit
        
    Raises:
        HTTPException: Si la signature est invalide
    """
    payload = await request.body()
    
    # Si security est défini comme auto_error=False, credentials peut être None
    signature = credentials.credentials if credentials else ""
    
    if not verify_signature(signature, payload):
        logger.warning(f"Tentative d'accès non autorisé: signature invalide")
        raise HTTPException(status_code=401, detail="Signature invalide")
    
    return payload

# Le reste de votre code reste inchangé...
# ... (les endpoints et fonctions restent les mêmes)
