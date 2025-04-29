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

@app.post("/webhook/supplier-invoice")
async def supplier_invoice_webhook(payload: bytes = Depends(validate_webhook)):
    """
    Point de terminaison pour les webhooks de factures fournisseur Sellsy v2
    
    Args:
        payload: Contenu validé de la requête
        
    Returns:
        Dictionnaire avec le statut de l'opération
    """
    try:
        # Convertir le payload en JSON
        data = json.loads(payload.decode('utf-8'))
        
        # Afficher le payload complet pour déboguer
        logger.info(f"📩 Payload complet reçu: {json.dumps(data, indent=2)}")
        
        # NEW: Vérifier la structure du format Sellsy v2 (ancienne implémentation)
        if "relatedtype" in data and "relatedid" in data:
            # Format webhook ancien style Sellsy
            related_type = data.get("relatedtype", "").lower()
            invoice_id = data.get("relatedid")
            event_type = data.get("event", "")
            logger.info(f"Format ancien: Type: {related_type}, ID: {invoice_id}, Event: {event_type}")
            
            # Vérifier si c'est une facture fournisseur (purInvoice)
            if "purinvoice" not in related_type.lower():
                logger.warning(f"⚠️ Événement non lié aux factures fournisseur: {related_type}")
                return {"status": "ignored", "reason": f"event not related to supplier invoices: {related_type}"}
        else:
            # Format webhook nouveau style API v2
            event_type = data.get("action", "")
            resource = data.get("resource", {})
            resource_type = resource.get("type", "")
            
            logger.info(f"Format API v2: Action: {event_type}, Resource type: {resource_type}")
            
            # Vérification pour les factures fournisseur format API v2
            if not (resource_type and ("purchase" in resource_type.lower() or "supplier" in resource_type.lower() or "fournisseur" in resource_type.lower())):
                logger.warning(f"⚠️ Événement non lié aux factures fournisseur: {resource_type}/{event_type}")
                return {"status": "ignored", "reason": f"event not related to supplier invoices: {resource_type}/{event_type}"}
                
            # Extraction de l'ID dans le format API v2
            invoice_id = None
            if "id" in resource:
                invoice_id = resource["id"]
            elif "data" in data and "id" in data["data"]:
                invoice_id = data["data"]["id"]
            elif "id" in data:
                invoice_id = data["id"]
        
        # Si aucun ID trouvé, erreur
        if not invoice_id:
            logger.error("❌ Impossible d'extraire l'ID de facture fournisseur du webhook")
            return {"status": "error", "reason": "invoice id not found"}
        
        logger.info(f"🔍 Traitement de la facture fournisseur #{invoice_id}")
        
        # Récupération des détails complets de la facture fournisseur avec retry
        max_retries = 3
        retry_count = 0
        invoice_details = None
        
        while retry_count < max_retries and not invoice_details:
            try:
                # Utilisation de la méthode v2 pour récupérer les détails
                invoice_details = sellsy_api.get_supplier_invoice_details(invoice_id)
                if not invoice_details and retry_count < max_retries - 1:
                    retry_count += 1
                    logger.info(f"Tentative {retry_count+1}/{max_retries} pour récupérer les détails...")
                    time.sleep(2)  # Attendre avant de réessayer
            except Exception as e:
                logger.error(f"Erreur lors de la tentative {retry_count+1}: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(2)
        
        if not invoice_details:
            logger.error(f"❌ Impossible de récupérer les détails de la facture {invoice_id} après {max_retries} tentatives")
            return {"status": "error", "reason": "invoice details not found"}
        
        # Formatage des données pour Airtable
        formatted_invoice = airtable_api.format_invoice_for_airtable(invoice_details)
        
        if not formatted_invoice:
            logger.error(f"❌ Échec du formatage de la facture fournisseur {invoice_id}")
            return {"status": "error", "reason": "format error"}
        
        # Téléchargement du PDF avec gestion des erreurs
        pdf_path = None
        try:
            # Récupération du PDF de la facture
            pdf_path = sellsy_api.get_supplier_invoice_pdf(invoice_id)
            if pdf_path:
                logger.info(f"✅ PDF téléchargé: {pdf_path}")
        except Exception as e:
            logger.warning(f"⚠️ Problème lors du téléchargement du PDF: {e}")
            # Continuer sans PDF
        
        # Insertion ou mise à jour dans Airtable
        result = airtable_api.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
        
        if result:
            logger.info(f"✅ Facture fournisseur {invoice_id} synchronisée avec succès")
            return {"status": "success", "invoice_id": invoice_id, "airtable_id": result}
        else:
            logger.error(f"❌ Échec de la synchronisation de la facture fournisseur {invoice_id}")
            return {"status": "error", "reason": "airtable sync failed"}
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Erreur de décodage JSON: {e}")
        return {"status": "error", "reason": "invalid json payload"}
    except Exception as e:
        logger.error(f"❌ Erreur lors du traitement du webhook: {e}")
        logger.error(f"Détails de l'erreur: {str(e)}")
        # Ne pas révéler les détails de l'erreur dans la réponse
        return {"status": "error", "reason": "internal error"}

@app.get("/health")
async def health_check():
    """
    Point de terminaison de vérification de l'état du service
    
    Returns:
        Dictionnaire avec le statut et le timestamp
    """
    # Vérifier la connexion aux APIs
    apis_status = {"sellsy": "unknown", "airtable": "unknown"}
    
    try:
        # Test simple de l'API Sellsy v2 - Vérifier si le token est valide
        if sellsy_api.access_token:
            # Faire une requête simple pour vérifier la connexion
            test_result = sellsy_api._make_get("/myself")
            apis_status["sellsy"] = "ok" if test_result else "error"
        else:
            apis_status["sellsy"] = "error"
    except Exception as e:
        logger.warning(f"Problème avec l'API Sellsy: {e}")
        apis_status["sellsy"] = "error"
    
    try:
        # Test simple de l'API Airtable
        _ = airtable_api.table
        apis_status["airtable"] = "ok"
    except Exception as e:
        logger.warning(f"Problème avec l'API Airtable: {e}")
        apis_status["airtable"] = "error"
    
    return {
        "status": "ok" if all(s == "ok" for s in apis_status.values()) else "partial",
        "apis": apis_status,
        "timestamp": time.time()
    }

@app.get("/")
async def root():
    """
    Point de terminaison racine pour information
    
    Returns:
        Message d'information sur le service
    """
    return {
        "service": "Sellsy v2 to Airtable Synchronization Webhook",
        "endpoints": [
            "/webhook/supplier-invoice",
            "/health"
        ],
        "version": "2.0.2"
    }
