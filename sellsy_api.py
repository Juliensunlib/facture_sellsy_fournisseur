import requests
import json
import time
import base64
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from config import SELLSY_CLIENT_ID, SELLSY_CLIENT_SECRET, SELLSY_API_URL, PDF_STORAGE_DIR

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sellsy_api")

class SellsySupplierAPI:
    def __init__(self):
        """Initialisation de l'API Sellsy pour les factures fournisseurs"""
        self.access_token = None
        self.token_expires_at = 0
        self.api_url = SELLSY_API_URL
        logger.info(f"Initialisation de l'API Sellsy: {self.api_url}")
        
        # Vérification des identifiants
        if not SELLSY_CLIENT_ID or not SELLSY_CLIENT_SECRET:
            logger.error("Identifiants Sellsy manquants dans les variables d'environnement")
            raise ValueError("Identifiants Sellsy manquants")
        
        # Création du répertoire de stockage des PDF
        if not os.path.exists(PDF_STORAGE_DIR):
            os.makedirs(PDF_STORAGE_DIR)
            logger.info(f"Répertoire de stockage des PDF créé: {PDF_STORAGE_DIR}")

    def get_access_token(self) -> str:
        """
        Obtient ou renouvelle le token d'accès Sellsy
        
        Returns:
            Token d'accès valide
        """
        current_time = time.time()
        
        # Utiliser le token existant s'il est encore valide
        if self.access_token and current_time < self.token_expires_at - 60:
            return self.access_token
        
        # Sinon, demander un nouveau token
        url = "https://login.sellsy.com/oauth2/access-tokens"
        
        # Authentification avec les identifiants client en Base64
        auth_string = f"{SELLSY_CLIENT_ID}:{SELLSY_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        data = "grant_type=client_credentials"
        
        logger.info(f"Demande de token d'accès Sellsy")
        
        try:
            response = requests.post(url, headers=headers, data=data, timeout=30)
            status_code = response.status_code
            logger.debug(f"Statut de la réponse: {status_code}")
            
            if status_code == 200:
                try:
                    token_data = response.json()
                    self.access_token = token_data["access_token"]
                    self.token_expires_at = current_time + token_data["expires_in"]
                    logger.info("Token d'accès obtenu avec succès")
                    return self.access_token
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Erreur de décodage JSON ou données manquantes: {e}")
                    raise Exception("Réponse de l'API Sellsy invalide")
            else:
                logger.error(f"Erreur d'authentification Sellsy: Code {status_code}")
                logger.debug(f"Réponse complète: {response.text[:200]}...")
                raise Exception(f"Échec de l'authentification Sellsy (code {status_code})")
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur de connexion à l'API Sellsy: {e}")
            raise Exception(f"Impossible de se connecter à l'API Sellsy")

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
        
        # Utiliser la méthode générique avec filtre de date
        return self.get_all_supplier_invoices(
            limit=10000,
            created_after=f"{start_date}T00:00:00Z",
            created_before=f"{end_date}T23:59:59Z"
        )

    def get_all_supplier_invoices(self, limit: int = 10000, **filters) -> List[Dict]:
        """
        Récupère toutes les factures fournisseur avec pagination
        
        Args:
            limit: Nombre maximum de factures à récupérer
            **filters: Filtres additionnels pour l'API
                - created_after: Date de début (format ISO)
                - created_before: Date de fin (format ISO)
                - status: Statut des factures
                
        Returns:
            Liste des factures fournisseur
        """
        # Configuration
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        all_invoices = []
        current_page = 1
        page_size = 100
        
        # Paramètres de gestion des erreurs
        max_retries = 5
        retry_delay = 5
        page_delay = 1
        
        logger.info(f"Récupération de toutes les factures fournisseur (limite: {limit})")
        if filters:
            logger.debug(f"Filtres appliqués: {filters}")
        
        # Boucle de pagination
        while len(all_invoices) < limit:
            # Paramètres de requête
            params = {
                "limit": page_size,
                "offset": (current_page - 1) * page_size,
                "order": "created",
                "direction": "desc"
            }
            
            # Ajout des filtres
            params.update(filters)
            
            # URL pour les factures fournisseur
            url = f"{self.api_url}/purchases/invoices"
            logger.info(f"Récupération de la page {current_page} (offset {params['offset']})")
            
            # Gestion des tentatives
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    response = requests.get(url, headers=headers, params=params, timeout=30)
                    status_code = response.status_code
                    
                    if status_code == 200:
                        # Traitement des données
                        response_data = response.json()
                        page_invoices = response_data.get("data", [])
                        
                        # Si la page est vide, on a fini
                        if not page_invoices:
                            logger.info("Page vide reçue, fin de la pagination")
                            return all_invoices[:limit]
                            
                        # Nombre de factures restantes à récupérer
                        remaining = limit - len(all_invoices)
                        invoices_to_add = page_invoices[:remaining]
                        all_invoices.extend(invoices_to_add)
                        
                        logger.info(f"Page {current_page}: {len(invoices_to_add)} factures récupérées (total: {len(all_invoices)}/{limit})")
                        
                        # Vérifier si on doit continuer
                        if len(all_invoices) >= limit or len(page_invoices) < page_size:
                            return all_invoices[:limit]
                        
                        # Passer à la page suivante
                        current_page += 1
                        success = True
                        
                        # Pause entre les pages
                        time.sleep(page_delay)
                        
                    elif status_code == 401:
                        # Token expiré
                        logger.warning("Token expiré, renouvellement...")
                        self.token_expires_at = 0
                        token = self.get_access_token()
                        headers["Authorization"] = f"Bearer {token}"
                        retry_count += 1
                    
                    elif status_code == 429:
                        # Rate limiting
                        wait_time = int(response.headers.get('Retry-After', 30))
                        logger.warning(f"Limitation de débit (429), attente de {wait_time} secondes...")
                        time.sleep(wait_time)
                        retry_count += 1
                    
                    else:
                        # Autres erreurs
                        logger.error(f"Erreur API (page {current_page}): {status_code} - {response.text[:200]}...")
                        retry_count += 1
                        
                        if retry_count >= max_retries:
                            logger.error(f"Nombre maximum de tentatives atteint pour la page {current_page}")
                        else:
                            time.sleep(retry_delay)
                
                except Exception as e:
                    logger.error(f"Exception lors de la récupération de la page {current_page}: {e}")
                    retry_count += 1
                    
                    if retry_count < max_retries:
                        time.sleep(retry_delay)
            
            # Si toutes les tentatives ont échoué
            if not success:
                logger.warning(f"Échec de récupération de la page {current_page}, retour des données partielles")
                return all_invoices[:limit]
    
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
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        url = f"{self.api_url}/purchases/invoices/{invoice_id}"
        logger.info(f"Récupération des détails de la facture fournisseur {invoice_id}")
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = requests.get(url, headers=headers, timeout=30)
                status_code = response.status_code
                
                if status_code == 200:
                    data = response.json()
                    # Vérifier le format de la réponse
                    if "data" in data:
                        logger.info(f"Détails de la facture fournisseur {invoice_id} récupérés")
                        return data.get("data", {})
                    else:
                        logger.info(f"Détails de la facture fournisseur {invoice_id} récupérés (format direct)")
                        return data
                
                elif status_code == 401:
                    # Renouveler le token
                    logger.warning("Token expiré, renouvellement...")
                    self.token_expires_at = 0
                    token = self.get_access_token()
                    headers["Authorization"] = f"Bearer {token}"
                    retry_count += 1
                
                elif status_code == 404:
                    logger.warning(f"Facture fournisseur {invoice_id} non trouvée (404)")
                    return None
                
                else:
                    logger.error(f"Erreur {status_code}: {response.text[:200]}...")
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(5)
            
            except Exception as e:
                logger.error(f"Exception lors de la récupération des détails: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(5)
        
        logger.error(f"Échec après {max_retries} tentatives pour la facture {invoice_id}")
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
        
        # Récupérer les détails pour obtenir le lien PDF
        invoice_details = self.get_supplier_invoice_details(invoice_id)
        if not invoice_details:
            logger.error(f"Impossible de récupérer les détails pour télécharger le PDF")
            return None
        
        # Extraire le lien PDF direct si disponible
        pdf_link = invoice_details.get("pdf_link")
        
        # Définir les méthodes de téléchargement à essayer
        methods = [
            {
                "name": "Lien direct",
                "url": pdf_link,
                "headers": {
                    "Authorization": f"Bearer {self.get_access_token()}",
                    "Accept": "application/pdf"
                },
                "skip_if_none": True
            },
            {
                "name": "API standard",
                "url": f"{self.api_url}/purchases/invoices/{invoice_id}/document",
                "headers": {
                    "Authorization": f"Bearer {self.get_access_token()}",
                    "Accept": "application/pdf"
                },
                "skip_if_none": False
            }
        ]
        
        # Essayer chaque méthode
        for method in methods:
            # Vérifier si
