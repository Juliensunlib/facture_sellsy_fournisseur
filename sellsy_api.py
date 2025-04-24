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
        Récupère toutes les factures fournisseurs.
        """
        logger.info(f"🔄 Récupération de toutes les factures fournisseurs (limite: {limit})")
        params = {
            'limit': limit
        }
        return self._make_api_request('Accounting.getAllInvoices', params) or []

    def get_supplier_invoice_details(self, invoice_id: str) -> Dict:
        """
        Récupère les détails d'une facture spécifique par son ID.
        """
        logger.info(f"🔍 Récupération des détails de la facture {invoice_id}")

        params = {
            "id": invoice_id
        }

        # Appel à la méthode 'Accounting.getOne' pour récupérer les détails de la facture
        details = self._make_api_request("Accounting.getOne", params) or {}

        # Ajout d'un log pour afficher l'intégralité des détails de la facture récupérée
        logger.debug(f"Détails complets de la facture {invoice_id}: {json.dumps(details, indent=2)}")
        
        return details

    def download_pdf(self, invoice_id: str, pdf_url: str) -> None:
        """
        Télécharge le PDF de la facture à partir de l'URL fournie et l'enregistre dans le répertoire spécifié.
        """
        pdf_filename = os.path.join(PDF_STORAGE_DIR, f"{invoice_id}.pdf")
        response = requests.get(pdf_url)
        if response.status_code == 200:
            with open(pdf_filename, 'wb') as pdf_file:
                pdf_file.write(response.content)
            logger.info(f"Facture {invoice_id} PDF téléchargé avec succès.")
        else:
            logger.error(f"Échec du téléchargement du PDF pour la facture {invoice_id}")

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
                if invoice_id:
                    # Récupérer les détails de la facture
                    details = self.get_supplier_invoice_details(invoice_id)

                    # Inspection des montants et du statut
                    invoice_amount = details.get('invoice', {}).get('amount', 0)
                    invoice_status = details.get('invoice', {}).get('status', 'inconnu')

                    logger.info(f"Facture {invoice_id} - Montant: {invoice_amount} - Statut: {invoice_status}")

                    pdf_url = details.get('pdf_url')
                    if pdf_url:
                        self.download_pdf(invoice_id, pdf_url)
