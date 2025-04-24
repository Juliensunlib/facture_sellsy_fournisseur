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
        auth_data = self._generate_oauth_signature(method, params or {})
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        for attempt in range(retry):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    data=auth_data['request'],
                    params=auth_data['oauth_params'],
                    timeout=30
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'error':
                        error_msg = data.get('error', 'Erreur inconnue')
                        logger.error(f"Erreur API: {error_msg}")
                        if 'rate limit' in error_msg.lower():
                            time.sleep(60)
                            continue
                        return None
                    return data.get('response', data)
                logger.error(f"Erreur HTTP {response.status_code}: {response.text[:200]}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Exception: {e}")
            time.sleep(5)
        return None
        
        # Vérification des identifiants
        if not all([SELLSY_V1_CONSUMER_TOKEN, SELLSY_V1_CONSUMER_SECRET, 
                   SELLSY_V1_USER_TOKEN, SELLSY_V1_USER_SECRET]):
            logger.error("Identifiants Sellsy v1 manquants dans les variables d'environnement")
            raise ValueError("Identifiants Sellsy v1 manquants")
        
        # Création du répertoire de stockage des PDF
        if not os.path.exists(PDF_STORAGE_DIR):
            os.makedirs(PDF_STORAGE_DIR)
            logger.info(f"Répertoire de stockage des PDF créé: {PDF_STORAGE_DIR}")

    def _generate_oauth_signature(self, method: str, request_params: Dict) -> Dict:
        """
        Génère les en-têtes OAuth 1.0a pour l'API Sellsy v1
        
        Args:
            method: Méthode d'API Sellsy (ex: 'PurchaseOrder.getList')
            request_params: Paramètres de la requête
            
        Returns:
            En-têtes OAuth complets pour l'authentification
        """
        # Création d'un nonce aléatoire
        nonce = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(20))
        timestamp = str(int(time.time()))
        
        # Construction des paramètres OAuth
        oauth_params = {
            'oauth_consumer_key': SELLSY_V1_CONSUMER_TOKEN,
            'oauth_token': SELLSY_V1_USER_TOKEN,
            'oauth_signature_method': 'PLAINTEXT',
            'oauth_timestamp': timestamp,
            'oauth_nonce': nonce,
            'oauth_version': '1.0',
            'oauth_signature': f"{SELLSY_V1_CONSUMER_SECRET}&{SELLSY_V1_USER_SECRET}"
        }
        
        # Construction des paramètres de la requête
        request = {
            'request': 1,
            'io_mode': 'json',
            'do_in': json.dumps({
                'method': method,
                'params': request_params
            })
        }
        
        return {'oauth_params': oauth_params, 'request': request}

    def _make_api_request(self, method: str, params: Dict = None, retry: int = 3) -> Optional[Dict]:
        """
        Effectue une requête à l'API Sellsy v1
        
        Args:
            method: Méthode d'API Sellsy (ex: 'PurchaseOrder.getList')
            params: Paramètres de la requête
            retry: Nombre de tentatives en cas d'échec
            
        Returns:
            Réponse de l'API ou None en cas d'échec
        """
        if params is None:
            params = {}
        
        # Génération des paramètres OAuth
        auth_data = self._generate_oauth_signature(method, params)
        oauth_params = auth_data['oauth_params']
        request_params = auth_data['request']
        
        # Construction des en-têtes
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        # Tentatives de requête avec gestion des erreurs
        for attempt in range(retry):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    data=request_params,
                    params=oauth_params,
                    timeout=30
                )
                
                # Vérification du code de statut
                if response.status_code == 200:
                    try:
                        data = response.json()
                        
                        # Dans l'API v1, les réponses d'erreur ont un status 
                        if isinstance(data, dict) and data.get('status') == 'error':
                            error_msg = data.get('error', 'Erreur inconnue')
                            logger.error(f"Erreur API Sellsy v1: {error_msg}")
                            
                            # Gestion des erreurs de rate limiting
                            if 'rate limit' in error_msg.lower():
                                wait_time = 60
                                logger.warning(f"Limitation de débit, attente de {wait_time} secondes...")
                                time.sleep(wait_time)
                                continue
                                
                            return None
                        
                        return data.get('response', data)
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Erreur de décodage JSON: {e}")
                        if attempt < retry - 1:
                            time.sleep(5)
                        else:
                            return None
                else:
                    logger.error(f"Erreur HTTP {response.status_code}: {response.text[:200]}...")
                    if attempt < retry - 1:
                        time.sleep(5)
                    else:
                        return None
                        
            except requests.exceptions.RequestException as e:
                logger.error(f"Exception lors de la requête: {e}")
                if attempt < retry - 1:
                    time.sleep(5)
                else:
                    return None
        
        return None

    def get_supplier_invoices(self, days: int = 365) -> List[Dict]:
        """
        Récupère les factures fournisseur des derniers jours spécifiés
        
        Args:
            days: Nombre de jours dans le passé à considérer (défaut: 365)
            
        Returns:
            Liste des factures fournisseur
        """
        # Calcul de la période
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Récupération des factures fournisseur du {start_date} au {end_date}")
        
        return self.get_all_supplier_invoices(
            filters={
                'dateFrom': f"{start_date} 00:00:00",
                'dateTo': f"{end_date} 23:59:59"
            }
        )

    def get_all_supplier_invoices(self, limit: int = 10000, filters: Dict = None) -> List[Dict]:
        """
        Récupère toutes les factures fournisseur avec pagination
        
        Args:
            limit: Nombre maximum de factures à récupérer
            filters: Filtres additionnels pour l'API
                
        Returns:
            Liste des factures fournisseur
        """
        if filters is None:
            filters = {}
        
        all_invoices = []
        current_page = 1
        page_size = 100
        
        logger.info(f"Récupération de toutes les factures fournisseur (limite: {limit})")
        if filters:
            logger.debug(f"Filtres appliqués: {filters}")
        
        # Boucle de pagination
        while len(all_invoices) < limit:
            # Paramètres de requête pour l'API v1
            params = {
                'pagination': {
                    'nbperpage': page_size,
                    'pagenum': current_page
                },
                'search': filters
            }
            
            logger.info(f"Récupération de la page {current_page}")
            
            # Requête à l'API v1
            response_data = self._make_api_request('PurchaseOrder.getList', params)
            
            if not response_data:
                logger.error(f"Échec de récupération de la page {current_page}")
                break
                
            # Extraction des factures
            page_invoices = []
            if isinstance(response_data, dict) and 'result' in response_data:
                for invoice_id, invoice_data in response_data['result'].items():
                    if invoice_id.isdigit():  # Ignorer les métadonnées
                        page_invoices.append(invoice_data)
            
            # Si la page est vide, on a fini
            if not page_invoices:
                logger.info("Page vide reçue, fin de la pagination")
                break
                
            # Nombre de factures restantes à récupérer
            remaining = limit - len(all_invoices)
            invoices_to_add = page_invoices[:remaining]
            all_invoices.extend(invoices_to_add)
            
            logger.info(f"Page {current_page}: {len(invoices_to_add)} factures récupérées (total: {len(all_invoices)}/{limit})")
            
            # Vérifier si on doit continuer
            if len(all_invoices) >= limit or len(page_invoices) < page_size:
                break
            
            # Passer à la page suivante
            current_page += 1
            
            # Pause entre les pages
            time.sleep(1)
    
        return all_invoices[:limit]

    def get_supplier_invoice_details(self, invoice_id: str) -> Optional[Dict]:
        """
        Récupère les détails d'une facture fournisseur spécifique
        
        Args:
            invoice_id: ID de la facture fournisseur
            
        Returns:
            Détails de la facture ou None en cas d'erreur
        """
        if not invoice_id:
            logger.error("ID de facture fournisseur invalide")
            return None
            
        invoice_id = str(invoice_id)
        
        params = {
            'docid': invoice_id
        }
        
        logger.info(f"Récupération des détails de la facture fournisseur {invoice_id}")
        
        # Requête à l'API v1
        response_data = self._make_api_request('PurchaseOrder.getOne', params)
        
        if response_data:
            # Dans l'API v1, les détails sont directement dans la réponse
            logger.info(f"Détails de la facture fournisseur {invoice_id} récupérés")
            return response_data
        else:
            logger.error(f"Échec de récupération des détails pour la facture {invoice_id}")
            return None
    
    def download_supplier_invoice_pdf(self, invoice_id: str) -> Optional[str]:
        """
        Télécharge le PDF d'une facture fournisseur
        
        Args:
            invoice_id: ID de la facture fournisseur
            
        Returns:
            Chemin du fichier PDF ou None en cas d'erreur
        """
        if not invoice_id:
            logger.error("ID de facture fournisseur invalide pour le téléchargement du PDF")
            return None
        
        invoice_id = str(invoice_id)
        
        # Définir le chemin du fichier
        pdf_filename = f"facture_fournisseur_{invoice_id}.pdf"
        pdf_path = os.path.join(PDF_STORAGE_DIR, pdf_filename)
        
        # Vérifier si le fichier existe déjà et est valide
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:  # Au moins 1KB
            logger.info(f"PDF déjà existant: {pdf_path} ({os.path.getsize(pdf_path)} octets)")
            return pdf_path
        elif os.path.exists(pdf_path):
            logger.warning(f"PDF existant mais potentiellement corrompu, retéléchargement...")
        
        # Paramètres de requête pour l'API v1
        params = {
            'docid': invoice_id,
            'doctype': 'purchaseorder'  # Type pour les factures fournisseurs dans l'API v1
        }
        
        logger.info(f"Téléchargement du PDF pour la facture fournisseur {invoice_id}")
        
        # Générer les paramètres OAuth pour une requête de document
        auth_data = self._generate_oauth_signature('Document.getFile', params)
        oauth_params = auth_data['oauth_params']
        request_params = auth_data['request']
        
        # Construction de l'URL avec les paramètres OAuth
        oauth_query = '&'.join([f"{k}={urllib.parse.quote(v)}" for k, v in oauth_params.items()])
        request_query = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in request_params.items()])
        pdf_url = f"{self.api_url}?{oauth_query}&{request_query}"
        
        try:
            response = requests.get(pdf_url, timeout=60)
            
            if response.status_code == 200 and response.headers.get('Content-Type', '').startswith('application/pdf'):
                # Écriture du fichier PDF
                with open(pdf_path, 'wb') as f:
                    f.write(response.content)
                
                # Vérification de la taille du fichier
                file_size = os.path.getsize(pdf_path)
                if file_size > 1000:  # Au moins 1KB
                    logger.info(f"PDF téléchargé avec succès ({file_size} octets): {pdf_path}")
                    return pdf_path
                else:
                    logger.warning(f"PDF téléchargé mais trop petit ({file_size} octets), considéré comme invalide")
                    os.remove(pdf_path)  # Supprimer le fichier invalide
                    return None
            else:
                logger.error(f"Échec du téléchargement du PDF: {response.status_code}")
                # On peut essayer de récupérer le message d'erreur si la réponse est en JSON
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict) and 'error' in error_data:
                        logger.error(f"Erreur API: {error_data['error']}")
                except:
                    logger.error(f"Réponse non-PDF: {response.text[:200]}...")
                return None
                
        except Exception as e:
            logger.error(f"Exception lors du téléchargement du PDF: {e}")
            return None

    def search_supplier_invoices(self, query: str, limit: int = 100) -> List[Dict]:
        """
        Recherche des factures fournisseur par terme de recherche
        
        Args:
            query: Terme de recherche (numéro, nom du fournisseur...)
            limit: Nombre maximum de résultats
            
        Returns:
            Liste des factures fournisseur correspondantes
        """
        if not query or len(query.strip()) < 3:
            logger.warning("Terme de recherche trop court ou vide")
            return []
            
        # Dans l'API v1, la recherche se fait via le paramètre search
        filters = {
            'keywords': query.strip()
        }
        
        logger.info(f"Recherche de factures fournisseur avec le terme '{query}'")
        
        # Utiliser la méthode existante avec les filtres de recherche
        return self.get_all_supplier_invoices(limit=limit, filters=filters)

    def create_supplier_credit_note(self, invoice_id: str, credit_data: Dict) -> Optional[str]:
        """
        Crée un avoir pour une facture fournisseur
        
        Args:
            invoice_id: ID de la facture fournisseur
            credit_data: Données de l'avoir
            
        Returns:
            ID de l'avoir créé ou None en cas d'erreur
        """
        # Vérifications de sécurité
        if not invoice_id or not credit_data:
            logger.error("ID de facture ou données d'avoir manquantes")
            return None
            
        # Construction des données pour l'API v1
        params = {
            'docid': str(invoice_id),
            'doctype': 'purchaseorder',
            'note': credit_data.get('note', 'Avoir automatique')
        }
        
        # Ajouter les items si présents
        if 'items' in credit_data and credit_data['items']:
            params['items'] = credit_data['items']
        
        # Ajouter la date si présente
        if 'date' in credit_data:
            params['date'] = credit_data['date']
        
        logger.info(f"Création d'un avoir pour la facture fournisseur {invoice_id}")
        
        # Requête à l'API v1
        response_data = self._make_api_request('PurchaseOrder.createCredit', params)
        
        if response_data:
            # Récupérer l'ID de l'avoir créé
            credit_note_id = None
            
            if isinstance(response_data, dict):
                credit_note_id = response_data.get('credit_docid')
            
            if credit_note_id:
                logger.info(f"Avoir créé avec succès: {credit_note_id}")
                return str(credit_note_id)
            else:
                logger.error("Impossible d'extraire l'ID de l'avoir créé")
                return None
        else:
            logger.error("Échec de la création de l'avoir")
            return None

    def get_all_suppliers(self, limit: int = 1000) -> List[Dict]:
        """
        Récupère la liste des fournisseurs
        
        Args:
            limit: Nombre maximum de fournisseurs à récupérer
            
        Returns:
            Liste des fournisseurs
        """
        all_suppliers = []
        current_page = 1
        page_size = 100
        
        logger.info(f"Récupération de la liste des fournisseurs (limite: {limit})")
        
        # Boucle de pagination
        while len(all_suppliers) < limit:
            # Paramètres de requête pour l'API v1
            params = {
                'pagination': {
                    'nbperpage': page_size,
                    'pagenum': current_page
                },
                'search': {
                    'types': ['supplier']  # Filtrer uniquement les fournisseurs
                }
            }
            
            logger.info(f"Récupération de la page {current_page} des fournisseurs")
            
            # Requête à l'API v1
            response_data = self._make_api_request('Client.getList', params)
            
            if not response_data:
                logger.error(f"Échec de récupération de la page {current_page} des fournisseurs")
                break
                
            # Extraction des fournisseurs
            page_suppliers = []
            if isinstance(response_data, dict) and 'result' in response_data:
                for supplier_id, supplier_data in response_data['result'].items():
                    if supplier_id.isdigit():  # Ignorer les métadonnées
                        page_suppliers.append(supplier_data)
            
            # Si la page est vide, on a fini
            if not page_suppliers:
                logger.info("Page vide reçue, fin de la pagination")
                break
                
            # Nombre de fournisseurs restants à récupérer
            remaining = limit - len(all_suppliers)
            suppliers_to_add = page_suppliers[:remaining]
            all_suppliers.extend(suppliers_to_add)
            
            logger.info(f"Page {current_page}: {len(suppliers_to_add)} fournisseurs récupérés (total: {len(all_suppliers)}/{limit})")
            
            # Vérifier si on doit continuer
            if len(all_suppliers) >= limit or len(page_suppliers) < page_size:
                break
            
            # Passer à la page suivante
            current_page += 1
            
            # Pause entre les pages
            time.sleep(1)
    
        return all_suppliers[:limit]
