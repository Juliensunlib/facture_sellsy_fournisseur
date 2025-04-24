import requests
import json
import time
import os
import logging
import random
import string
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import (
    SELLSY_V1_CONSUMER_TOKEN,
    SELLSY_V1_CONSUMER_SECRET,
    SELLSY_V1_USER_TOKEN,
    SELLSY_V1_USER_SECRET,
    SELLSY_V1_API_URL,
    PDF_STORAGE_DIR
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sellsy_api")

class SellsySupplierAPI:
    def __init__(self):
        self.api_url = SELLSY_V1_API_URL
        logger.info(f"Initialisation de l'API Sellsy v1: {self.api_url}")

        if not all([SELLSY_V1_CONSUMER_TOKEN, SELLSY_V1_CONSUMER_SECRET,
                    SELLSY_V1_USER_TOKEN, SELLSY_V1_USER_SECRET]):
            logger.error("Identifiants Sellsy v1 manquants")
            raise ValueError("Identifiants Sellsy v1 manquants")

        os.makedirs(PDF_STORAGE_DIR, exist_ok=True)
        logger.info(f"Répertoire de stockage des PDF: {PDF_STORAGE_DIR}")

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
                    try:
                        data = response.json()

                        if isinstance(data, dict) and data.get('status') == 'error':
                            error_msg = data.get('error', 'Erreur inconnue')
                            logger.error(f"Erreur API Sellsy v1: {error_msg}")

                            if 'rate limit' in error_msg.lower():
                                logger.warning("Limite atteinte, nouvelle tentative après 60s")
                                time.sleep(60)
                                continue

                            return None

                        return data.get('response', data)

                    except json.JSONDecodeError as e:
                        logger.error(f"Erreur JSON: {e}")
                else:
                    logger.error(f"Erreur HTTP {response.status_code}: {response.text[:200]}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Exception: {e}")

            time.sleep(5)

        return None

    def get_all_supplier_invoices(self, limit: int = 1000) -> List[Dict]:
        """
        Récupère toutes les factures fournisseurs jusqu'à la limite spécifiée.
        """
        logger.info(f"🔄 Récupération de toutes les factures fournisseurs (limite: {limit})")

        params = {
            "filters": {
                "documentType": "supplierinvoice"
            },
            "pagination": {
                "pagenum": 1,
                "pagesize": limit
            }
        }

        result = self._make_api_request("Accounting.getList", params)
        if isinstance(result, dict):
            return list(result.values())
        return []

    def sync_missing_supplier_invoices(self, limit: int = 1000) -> None:
        """
        Synchronise les factures manquantes en récupérant toutes les factures fournisseurs
        et en les sauvegardant dans un répertoire local.
        """
        logger.info("Début de la synchronisation des factures manquantes...")
        invoices = self.get_all_supplier_invoices(limit)
        
        if invoices:
            for invoice in invoices:
                invoice_id = invoice.get('id')
                pdf_url = invoice.get('pdf_url')
                if invoice_id and pdf_url:
                    self.download_pdf(invoice_id, pdf_url)

    def download_pdf(self, invoice_id: str, pdf_url: str) -> None:
        """
        Télécharge le PDF de la facture et l'enregistre dans le répertoire spécifié.
        """
        try:
            logger.info(f"Téléchargement de la facture {invoice_id} depuis {pdf_url}")
            response = requests.get(pdf_url, stream=True)
            response.raise_for_status()  # Vérifie si la requête est réussie

            pdf_path = os.path.join(PDF_STORAGE_DIR, f"invoice_{invoice_id}.pdf")
            with open(pdf_path, 'wb') as pdf_file:
                for chunk in response.iter_content(chunk_size=8192):
                    pdf_file.write(chunk)

            logger.info(f"Facture {invoice_id} téléchargée et sauvegardée à {pdf_path}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors du téléchargement du PDF pour la facture {invoice_id}: {e}")
