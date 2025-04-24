import requests
import json
import time
import os
import logging
import random
import string
from typing import List, Dict, Optional, Any
from config import (
    SELLSY_V1_CONSUMER_TOKEN,
    SELLSY_V1_CONSUMER_SECRET,
    SELLSY_V1_USER_TOKEN,
    SELLSY_V1_USER_SECRET,
    SELLSY_V1_API_URL,
    PDF_STORAGE_DIR
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sellsy_supplier_api")

class SellsySupplierAPI:
    def __init__(self):
        self.api_url = SELLSY_V1_API_URL

        if not all([SELLSY_V1_CONSUMER_TOKEN, SELLSY_V1_CONSUMER_SECRET,
                    SELLSY_V1_USER_TOKEN, SELLSY_V1_USER_SECRET]):
            raise ValueError("Identifiants Sellsy v1 manquants")

        os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

    def _generate_oauth_signature(self, method: str, request_params: Dict) -> Dict:
        nonce = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
        timestamp = str(int(time.time()))

        oauth_params = {
            'oauth_consumer_key': SELLSY_V1_CONSUMER_TOKEN,
            'oauth_token': SELLSY_V1_USER_TOKEN,
            'oauth_signature_method': 'PLAINTEXT',
            'oauth_timestamp': timestamp,
            'oauth_nonce': nonce,
            'oauth_version': '1.0',
            'oauth_signature': f"{SELLSY_V1_CONSUMER_SECRET}&{SELLSY_V1_USER_SECRET}"
        }

        request = {
            'request': 1,
            'io_mode': 'json',
            'do_in': json.dumps({
                'method': method,
                'params': request_params or {}
            })
        }

        return {'oauth_params': oauth_params, 'request': request}

    def _make_api_request(self, method: str, params: Dict = None, retry: int = 3) -> Optional[Dict]:
        if params is None:
            params = {}

        auth_data = self._generate_oauth_signature(method, params)
        oauth_params = auth_data['oauth_params']
        request_params = auth_data['request']

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        for attempt in range(retry):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    data=request_params,
                    params=oauth_params,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'error':
                        logger.error(f"Erreur API: {data.get('error')}")
                        return None
                    return data.get('response', data)
                else:
                    logger.error(f"Erreur HTTP {response.status_code}: {response.text}")
            except requests.RequestException as e:
                logger.error(f"Exception API: {e}")
            time.sleep(5)
        return None

    def get_supplier_invoices(self, limit: int = 100) -> List[Dict]:
        logger.info("Récupération des factures fournisseurs...")
        invoices = []
        page = 1
        per_page = 100

        while len(invoices) < limit:
            params = {
                "pagination": {
                    "nbperpage": per_page,
                    "pagenum": page
                },
                "search": {
                    "doctype": "supplierinvoice",
                    "steps": ["due", "paid", "late"]
                }
            }
            result = self._make_api_request("Document.getList", params)
            if not result or not isinstance(result, dict):
                break

            page_items = list(result.values())
            if not page_items:
                break

            invoices.extend(page_items)
            if len(page_items) < per_page:
                break
            page += 1
        return invoices[:limit]

    def get_supplier_invoice_details(self, invoice_id: str) -> Optional[Dict]:
        logger.info(f"Récupération des détails de la facture {invoice_id}")
        result = self._make_api_request("Document.getOne", {"id": invoice_id})
        if not result:
            logger.warning(f"Facture {invoice_id} non trouvée")
            return None
        return result.get(invoice_id)

    def download_supplier_invoice_pdf(self, invoice_id: str) -> Optional[str]:
        logger.info(f"Téléchargement du PDF de la facture {invoice_id}")
        result = self._make_api_request("Document.getPdf", {
            "docid": invoice_id,
            "doctype": "supplierinvoice"
        })
        if not result or "downloadUrl" not in result:
            logger.warning(f"Lien PDF non trouvé pour {invoice_id}")
            return None

        pdf_url = result["downloadUrl"]
        response = requests.get(pdf_url)
        if response.status_code != 200:
            logger.error(f"Erreur lors du téléchargement du PDF: {response.status_code}")
            return None

        pdf_path = os.path.join(PDF_STORAGE_DIR, f"invoice_{invoice_id}.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"PDF enregistré: {pdf_path}")
        return pdf_path
