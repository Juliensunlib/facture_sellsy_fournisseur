from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import time
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableSupplierAPI
from config import WEBHOOK_SECRET
import hmac
import hashlib

app = FastAPI()
security = HTTPBearer()

# Initialisation des APIs
sellsy_api = SellsySupplierAPI()
airtable_api = AirtableSupplierAPI()

def verify_signature(signature: str, payload: bytes) -> bool:
    """Vérifie la signature du webhook Sellsy"""
    if not WEBHOOK_SECRET:
        print("⚠️ WEBHOOK_SECRET non défini, vérification désactivée")
        return True
        
    expected = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)

async def validate_webhook(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Valide la signature du webhook Sellsy"""
    payload = await request.body()
    signature = credentials.credentials if credentials else ""
    
    if not verify_signature(signature, payload):
        raise HTTPException(status_code=401, detail="Signature invalide")
    
    return payload

@app.post("/webhook/supplier-invoice")
async def supplier_invoice_webhook(payload: bytes = Depends(validate_webhook)):
    """Point de terminaison pour les webhooks de factures fournisseur Sellsy"""
    try:
        # Convertir le payload en JSON
        data = json.loads(payload.decode('utf-8'))
        
        print(f"📩 Webhook reçu pour une facture fournisseur: {data.get('event', 'unknown')}")
        
        # Vérifier le type d'événement
        event_type = data.get("event", "")
        if not event_type.startswith("purchase.invoice"):
            print(f"⚠️ Événement non lié aux factures fournisseur: {event_type}")
            return {"status": "ignored", "reason": "event not related to supplier invoices"}
        
        # Extraction de l'ID de facture fournisseur
        invoice_id = None
        if "data" in data and "id" in data["data"]:
            invoice_id = data["data"]["id"]
        elif "entityid" in data:
            invoice_id = data["entityid"]
            
        if not invoice_id:
            print("❌ Impossible d'extraire l'ID de facture fournisseur du webhook")
            return {"status": "error", "reason": "invoice id not found"}
        
        print(f"🔍 Traitement de la facture fournisseur #{invoice_id}")
        
        # Récupération des détails complets de la facture fournisseur
        invoice_details = sellsy_api.get_supplier_invoice_details(invoice_id)
        
        if not invoice_details:
            print(f"❌ Impossible de récupérer les détails de la facture fournisseur {invoice_id}")
            return {"status": "error", "reason": "invoice details not found"}
        
        # Formatage des données pour Airtable
        formatted_invoice = airtable_api.format_supplier_invoice_for_airtable(invoice_details)
        
        if not formatted_invoice:
            print(f"❌ Échec du formatage de la facture fournisseur {invoice_id}")
            return {"status": "error", "reason": "format error"}
        
        # Téléchargement du PDF
        pdf_path = sellsy_api.download_supplier_invoice_pdf(invoice_id)
        
        # Insertion ou mise à jour dans Airtable
        result = airtable_api.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
        
        if result:
            print(f"✅ Facture fournisseur {invoice_id} synchronisée avec succès")
            return {"status": "success", "invoice_id": invoice_id, "airtable_id": result}
        else:
            print(f"❌ Échec de la synchronisation de la facture fournisseur {invoice_id}")
            return {"status": "error", "reason": "airtable sync failed"}
        
    except Exception as e:
        print(f"❌ Erreur lors du traitement du webhook: {e}")
        # Ne pas révéler les détails de l'erreur dans la réponse
        return {"status": "error", "reason": "internal error"}

@app.get("/health")
async def health_check():
    """Point de terminaison de vérification de l'état du service"""
    return {"status": "ok", "timestamp": time.time()}
