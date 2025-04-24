import requests
import json
import time
import os
import logging
import random
import string
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

                            if isinstance(error_msg, str) and 'rate limit' in error_msg.lower():
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

    def test_connection(self) -> bool:
        """
        Teste la connexion à l'API Sellsy
        
        Returns:
            True si la connexion est établie avec succès, False sinon
        """
        logger.info("Test de connexion à l'API Sellsy v1")
        try:
            # Appel à une méthode simple pour tester la connexion
            result = self._make_api_request("Infos.getInfos", {})
            
            # Si on obtient un résultat, la connexion est établie
            if result is not None:
                logger.info("✅ Connexion à l'API Sellsy v1 établie avec succès")
                return True
            else:
                logger.warning("⚠️ Échec de la connexion à l'API Sellsy v1")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur lors du test de connexion à l'API Sellsy v1: {e}")
            return False

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

    def get_supplier_invoice_details(self, invoice_id: str) -> Dict:
        """
        Récupère les détails d'une facture spécifique par son ID.
        """
        logger.info(f"🔍 Récupération des détails de la facture {invoice_id}")

        params = {
            "id": invoice_id
        }

        invoice_details = self._make_api_request("Purchase.getOne", params) or {}
        logger.info(f"Détails de la facture {invoice_id}: {invoice_details}")

        # Lister tous les champs présents dans la réponse
        logger.info(f"Champs disponibles dans la réponse : {invoice_details.keys()}")
        return invoice_details

    def download_supplier_invoice_pdf(self, invoice_id: str) -> Optional[str]:
        """
        Télécharge le PDF d'une facture fournisseur et le stocke localement.
        
        Args:
            invoice_id: ID de la facture fournisseur
            
        Returns:
            Chemin du fichier PDF téléchargé ou None en cas d'erreur
        """
        logger.info(f"Téléchargement du PDF pour la facture fournisseur {invoice_id}")
        
        try:
            # Récupérer les détails de la facture pour obtenir l'URL du PDF
            invoice_details = self.get_supplier_invoice_details(invoice_id)
            
            if not invoice_details:
                logger.warning(f"Détails de la facture {invoice_id} non trouvés")
                return None
            
            # Chercher l'URL du PDF dans différents champs possibles
            pdf_url = None
            pdf_fields = ["pdf_url", "pdfUrl", "pdf_link", "downloadUrl", "public_link", "pdf"]
            
            for field in pdf_fields:
                if field in invoice_details and invoice_details[field]:
                    pdf_url = invoice_details[field]
                    logger.info(f"URL PDF trouvée via champ {field}: {pdf_url}")
                    break
            
            if not pdf_url:
                logger.warning(f"URL PDF non trouvée pour la facture {invoice_id}")
                return None
            
            # Créer le chemin de destination
            pdf_path = os.path.join(PDF_STORAGE_DIR, f"invoice_{invoice_id}.pdf")
            
            # Télécharger le PDF
            response = requests.get(pdf_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Vérifier que c'est bien un PDF
            content_type = response.headers.get('Content-Type', '')
            if 'application/pdf' not in content_type and not pdf_url.endswith('.pdf'):
                logger.warning(f"Le contenu téléchargé ne semble pas être un PDF: {content_type}")
            
            # Sauvegarder le fichier
            with open(pdf_path, 'wb') as pdf_file:
                for chunk in response.iter_content(chunk_size=8192):
                    pdf_file.write(chunk)
            
            logger.info(f"PDF téléchargé et sauvegardé: {pdf_path}")
            return pdf_path
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors du téléchargement du PDF: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur inattendue lors du téléchargement du PDF: {e}")
            return None

# Exemple d'utilisation
if __name__ == "__main__":
    sellsy_api = SellsySupplierAPI()
    if sellsy_api.test_connection():
        invoices = sellsy_api.get_all_supplier_invoices()
        for invoice in invoices:
            invoice_id = invoice.get('id')
            if invoice_id:
                details = sellsy_api.get_supplier_invoice_details(invoice_id)
                logger.info(f"Facture {invoice_id} - Détails: {details}")
                sellsy_api.download_supplier_invoice_pdf(invoice_id)
