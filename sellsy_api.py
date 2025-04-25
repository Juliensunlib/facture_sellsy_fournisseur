import os
import time
import logging
import requests
import base64
import json
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
        self.api_v2_url = SELLSY_V2_API_URL
        self.api_v1_url = "https://apifeed.sellsy.com"  # URL pour l'API v1
        self.token_url = "https://login.sellsy.com/oauth2/access-tokens"
        self.access_token = self.get_access_token()

        if not self.access_token:
            raise ValueError("Impossible d'obtenir un token OAuth2 depuis Sellsy.")

        os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

    def get_access_token(self) -> Optional[str]:
        logger.info("\ud83d\udd10 R\u00e9cup\u00e9ration du token OAuth2 Sellsy")
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
            logger.error(f"Erreur de requ\u00eate OAuth2 : {e}")
        return None

    def _make_get(self, endpoint: str, params: Dict = {}) -> Optional[Dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        try:
            response = requests.get(f"{self.api_v2_url}{endpoint}", headers=headers, params=params)
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
            response = requests.post(f"{self.api_v2_url}{endpoint}", headers=headers, json=json_data)
            if response.status_code == 200:
                return response.json()
            logger.error(f"Erreur API POST {endpoint}: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Exception API POST: {e}")
        return None

    def _make_v1_request(self, method: str, params: Dict = {}) -> Optional[Dict[str, Any]]:
        """
        Effectue une requête vers l'API v1 de Sellsy en utilisant l'authentification OAuth2.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # Formatage correct du payload avec la clé 'do_in'
        payload = {
            "method": method,
            "io_mode": "json",  # Toujours utiliser json comme io_mode
            "do_in": json.dumps({
                "method": method,
                "params": params
            })  # Utilisation de 'do_in' comme clé pour la requête
        }

        logger.info(f"Requête API v1 vers {self.api_v1_url} - Méthode: {method}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(self.api_v1_url, headers=headers, data=payload)
            logger.info(f"Code de statut de la réponse: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Réponse réussie: {json.dumps(result, indent=2)[:500]}...")
                return result

            logger.error(f"Erreur API v1 {method}: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Exception API v1: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de décodage JSON: {e}")
            logger.error(f"Contenu de la réponse: {response.text[:500]}...")

        return None

    def get_supplier_invoices(self, limit: int = 100) -> List[Dict]:
        logger.info("\ud83d\udcc5 Recherche des factures fournisseur via API v1...")

        params = {
            "pagination": {
                "nbperpage": min(limit, 100),
                "pagenum": 1
            },
            "order": {
                "direction": "DESC",
                "field": "doc_date"
            }
        }

        invoices = []
        total_pages = 1
        current_page = 1

        while current_page <= total_pages and len(invoices) < limit:
            params["pagination"]["pagenum"] = current_page

            response = self._make_v1_request("Purchase.getList", params)

            if not response or response.get("status") != "success" or "response" not in response:
                logger.error("Erreur lors de la r\u00e9cup\u00e9ration des factures fournisseur")
                break

            data = response["response"]

            if current_page == 1 and "infos" in data and "nbpages" in data["infos"]:
                total_pages = data["infos"]["nbpages"]

            if "result" in data:
                batch = list(data["result"].values()) if isinstance(data["result"], dict) else []
                invoices.extend(batch)

            current_page += 1

            if len(invoices) >= limit:
                invoices = invoices[:limit]
                break

        logger.info(f"\ud83d\udccb {len(invoices)} factures fournisseur trouv\u00e9es")
        return invoices

    def get_supplier_invoice_details(self, invoice_id: str) -> Optional[Dict]:
        logger.info(f"\ud83d\udd0d D\u00e9tails de la facture fournisseur {invoice_id}")

        params = {
            "id": invoice_id
        }

        return self._make_v1_request("Purchase.getOne", params)

    def search_purchase_invoices(self, limit: int = 100) -> List[Dict]:
        logger.info("\ud83d\udcc5 Recherche des factures d'achat OCR avec filtre (POST)...")
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
        logger.info(f"\ud83d\udd0d D\u00e9tails de la facture OCR {invoice_id}")
        return self._make_get(f"/ocr/pur-invoice/{invoice_id}")

    def download_invoice_pdf(self, pdf_url: str, invoice_id: str) -> Optional[str]:
        logger.info(f"\u2b07\ufe0f T\u00e9l\u00e9chargement du PDF pour la facture {invoice_id}")
        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            response = requests.get(pdf_url, headers=headers)
            if response.status_code == 200:
                file_path = os.path.join(PDF_STORAGE_DIR, f"invoice_{invoice_id}.pdf")
                with open(file_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"\ud83d\udcc4 PDF enregistr\u00e9: {file_path}")
                return file_path
            else:
                logger.error(f"Erreur t\u00e9l\u00e9chargement PDF: {response.status_code}")
        except requests.RequestException as e:
            logger.error(f"Erreur lors du t\u00e9l\u00e9chargement du PDF: {e}")
        return None

    def get_supplier_invoice_pdf(self, invoice_id: str) -> Optional[str]:
        logger.info(f"\ud83d\udcc4 R\u00e9cup\u00e9ration du PDF pour la facture fournisseur {invoice_id}")

        params = {
            "docid": invoice_id,
            "filetype": "pdf"
        }

        response = self._make_v1_request("Purchase.getDocumentLink", params)

        if response and response.get("status") == "success" and "response" in response:
            pdf_url = response["response"].get("download_url")
            if pdf_url:
                return self.download_invoice_pdf(pdf_url, invoice_id)

        logger.error(f"Impossible d'obtenir l'URL du PDF pour la facture {invoice_id}")
        return None
