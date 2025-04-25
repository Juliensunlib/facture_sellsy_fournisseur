import os
import time
import logging
import requests
import base64
from typing import List, Dict, Optional, Any
from config import (
    SELLSY_CLIENT_ID,
    SELLSY_CLIENT_SECRET,
    SELLSY_V2_API_URL,
    PDF_STORAGE_DIR
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sellsy_supplier_api")

class SellsySupplierAPI:
    def __init__(self):
        self.api_url = SELLSY_V2_API_URL
        self.token_url = "https://login.sellsy.com/oauth2/access-tokens"
        self.access_token = self.get_access_token()

        if not self.access_token:
            raise ValueError("Impossible d'obtenir un token OAuth2 depuis Sellsy.")

        os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

    def get_access_token(self) -> Optional[str]:
        logger.info("🔐 Récupération du token OAuth2 Sellsy")
        try:
            auth_string = f"{SELLSY_CLIENT_ID}:{SELLSY_CLIENT_SECRET}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }

            data = "grant_type=client_credentials"
            response = requests.post(self.token_url, headers=headers, data=data)

            if response.status_code == 200:
                token_data = response.json()
                return token_data.get("access_token")
            else:
                logger.error(f"Erreur OAuth2 : {response.status_code} {response.text}")
        except requests.RequestException as e:
            logger.error(f"Erreur de requête OAuth2 : {e}")
        return None

    def _make_get(self, endpoint: str, params: Dict = {}) -> Optional[Dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        try:
            response = requests.get(f"{self.api_url}{endpoint}", headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
            logger.error(f"Erreur API GET {endpoint}: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Exception API GET: {e}")
        return None

    def _make_post(self, endpoint: str, json_data: Dict) -> Optional[Dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(f"{self.api_url}{endpoint}", headers=headers, json=json_data)
            if response.status_code == 200:
                return response.json()
            logger.error(f"Erreur API POST {endpoint}: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Exception API POST: {e}")
        return None

    def search_purchase_invoices(self, limit: int = 100) -> List[Dict]:
        logger.info("📥 Recherche des factures d'achat OCR avec filtre (POST)...")
        offset = 0
        invoices = []

        while len(invoices) < limit:
            payload = {
                "filters": {},
                "limit": min(limit - len(invoices), 100),
                "offset": offset,
                "order": "created_at",
                "direction": "desc"
            }

            data = self._make_post("/ocr/pur-invoice/search", json_data=payload)
            if not data or "data" not in data:
                break

            batch = data["data"]
            invoices.extend(batch)
            if len(batch) < 100:
                break
            offset += len(batch)

        return invoices[:limit]

    def get_invoice_details(self, invoice_id: str) -> Optional[Dict]:
        logger.info(f"🔍 Détails de la facture {invoice_id}")
        return self._make_get(f"/ocr/pur-invoice/{invoice_id}")

    def download_invoice_pdf(self, pdf_url: str, invoice_id: str) -> Optional[str]:
        logger.info(f"⬇️ Téléchargement du PDF pour la facture {invoice_id}")
        try:
            response = requests.get(pdf_url)
            if response.status_code == 200:
                file_path = os.path.join(PDF_STORAGE_DIR, f"invoice_{invoice_id}.pdf")
                with open(file_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"📄 PDF enregistré: {file_path}")
                return file_path
            else:
                logger.error(f"Erreur téléchargement PDF: {response.status_code}")
        except requests.RequestException as e:
            logger.error(f"Erreur lors du téléchargement du PDF: {e}")
        return None
