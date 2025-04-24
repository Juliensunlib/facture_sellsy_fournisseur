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

# Configuration du logging avec un format amélioré
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sellsy_api")

# Fonction utilitaire pour afficher du JSON formaté dans les logs
def log_json(data, label="JSON", level=logging.INFO):
    """Affiche un dict/liste sous forme de JSON formaté dans les logs"""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    
    # Séparer les lignes et les logger individuellement pour une meilleure lisibilité
    logger.log(level, f"=== DÉBUT {label} ===")
    for line in json_str.split('\n'):
        logger.log(level, line)
    logger.log(level, f"=== FIN {label} ===")

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
        
        # Log des paramètres de requête
        logger.debug(f"Requête API: {method}")
        logger.debug(f"Paramètres: {params}")

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

                        # Log de la réponse en JSON formaté
                        if logger.isEnabledFor(logging.DEBUG):
                            log_json(data, f"Réponse API {method}", logging.DEBUG)
                            
                        return data.get('response', data)

                    except json.JSONDecodeError as e:
                        logger.error(f"Erreur JSON: {e}")
                        logger.error(f"Contenu brut de la réponse: {response.text[:500]}...")
                else:
                    logger.error(f"Erreur HTTP {response.status_code}: {response.text[:200]}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Exception: {e}")

            logger.info(f"Tentative {attempt+1}/{retry} échouée, nouvelle tentative dans 5s")
            time.sleep(5)

        logger.error(f"Échec après {retry} tentatives pour la méthode {method}")
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
                # Afficher les infos basiques du résultat
                if isinstance(result, dict) and result:
                    log_json(result, "Infos API Sellsy")
                return True
            else:
                logger.warning("⚠️ Échec de la connexion à l'API Sellsy v1")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur lors du test de connexion à l'API Sellsy v1: {e}")
            return False

    def explore_api_methods(self):
        """
        Explore différentes méthodes de l'API pour trouver les bonnes données
        """
        logger.info("🔍 Exploration des méthodes API pour trouver les factures fournisseurs")
        
        methods_to_try = [
            # Méthodes liées aux achats/fournisseurs
            ("Purchase.getList", {}),
            ("Purchase.getSummary", {}),
            ("SupplierInvoice.getList", {}),
            ("Document.getList", {"doctype": "supplierinvoice"}),
            
            # Méthodes comptables
            ("Accounting.getAccountingDocuments", {"type": "supplierinvoice", "nbperpage": 5}),
            ("Accounting.getListFiltered", {"filtertype": "supplierinvoice", "pagenum": 1, "nbperpage": 5})
        ]
        
        results = {}
        
        for method, params in methods_to_try:
            logger.info(f"Essai de la méthode: {method}")
            result = self._make_api_request(method, params)
            
            if result:
                logger.info(f"✅ La méthode {method} a retourné des données")
                log_json(result, f"Résultat de {method}")
                results[method] = result
                
                # Sauvegarder dans un fichier pour analyse
                try:
                    debug_dir = "debug_json"
                    os.makedirs(debug_dir, exist_ok=True)
                    debug_file = os.path.join(debug_dir, f"{method.replace('.', '_')}_result.json")
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    logger.info(f"Résultat sauvegardé dans {debug_file}")
                except Exception as e:
                    logger.error(f"Impossible de sauvegarder le résultat: {e}")
            else:
                logger.warning(f"❌ La méthode {method} n'a pas retourné de données valides")
        
        return results

   def get_all_supplier_invoices(self, limit=1000, **filters):
    """
    Récupère toutes les factures fournisseur avec pagination robuste
    
    Args:
        limit: Nombre maximum de factures à récupérer (défaut: 1000)
        **filters: Filtres additionnels à passer à l'API Sellsy
                - created_after: Date de début (format ISO)
                - created_before: Date de fin (format ISO)
                - status: Statut des factures
    """
    token = self.get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    all_invoices = []
    current_page = 1
    page_size = 100  # La taille de page maximale généralement acceptée par Sellsy
    
    # Paramètres de pagination
    max_retries = 5        # Nombre maximum de tentatives par page
    retry_delay = 5        # Délai entre les tentatives en secondes
    page_delay = 1         # Délai entre les pages en secondes
    
    print(f"🚀 Récupération de toutes les factures fournisseur (limite: {limit})...")
    if filters:
        print(f"📋 Filtres appliqués: {filters}")
    
    # Boucle de pagination
    while len(all_invoices) < limit:
        # Construction des paramètres de la requête
        params = {
            "limit": page_size,
            "offset": (current_page - 1) * page_size,
            "order": "created",
            "direction": "desc"
        }
        
        # Ajout des filtres additionnels
        params.update(filters)
        
        # Endpoint des factures fournisseur
        url = f"{self.api_url}/supplier-invoices"
        print(f"📄 Récupération de la page {current_page} (offset {params['offset']}): {url}")
        
        # Gestion des tentatives pour cette page
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                response = requests.get(url, headers=headers, params=params)
                status_code = response.status_code
                print(f"📊 Statut de la réponse: {status_code}")
                
                if status_code == 200:
                    # Traitement des données en cas de succès
                    response_data = response.json()
                    page_invoices = response_data.get("data", [])
                    
                    # Si la page est vide, on a fini
                    if not page_invoices:
                        print("🏁 Page vide reçue, fin de la pagination")
                        return all_invoices[:limit]
                        
                    # Nombre de factures restantes à récupérer
                    remaining = limit - len(all_invoices)
                    
                    # Ajouter seulement les factures nécessaires
                    invoices_to_add = page_invoices[:remaining]
                    all_invoices.extend(invoices_to_add)
                    
                    print(f"✅ Page {current_page}: {len(invoices_to_add)} factures fournisseur récupérées (total: {len(all_invoices)}/{limit})")
                    
                    # Vérifier si on doit continuer la pagination
                    if len(all_invoices) >= limit:
                        print("🏁 Limite atteinte, fin de la récupération")
                        return all_invoices[:limit]
                    
                    if len(page_invoices) < page_size:
                        print("🏁 Dernière page atteinte (moins de résultats que la taille de page)")
                        return all_invoices[:limit]
                    
                    # Passer à la page suivante
                    current_page += 1
                    success = True
                    
                    # Pause entre les pages pour éviter de surcharger l'API
                    print(f"⏱️ Pause de {page_delay} seconde(s) entre les pages...")
                    time.sleep(page_delay)
                    
                elif status_code == 401:
                    # Token expiré, renouvellement
                    print("🔄 Token expiré, renouvellement...")
                    self.token_expires_at = 0
                    token = self.get_access_token()
                    headers["Authorization"] = f"Bearer {token}"
                    retry_count += 1
                    print(f"🔄 Nouveau token obtenu, tentative {retry_count}/{max_retries} pour la page {current_page}")
                
                elif status_code == 429:
                    # Rate limiting - attendre plus longtemps
                    wait_time = 30  # 30 secondes par défaut
                    if 'Retry-After' in response.headers:
                        try:
                            wait_time = int(response.headers['Retry-After'])
                        except ValueError:
                            pass
                    
                    print(f"⚠️ Limitation de débit (429), attente de {wait_time} secondes...")
                    time.sleep(wait_time)
                    retry_count += 1
                
                else:
                    # Autres erreurs
                    print(f"❌ Erreur lors de la récupération (page {current_page}): {status_code} - {response.text}")
                    retry_count += 1
                    
                    if retry_count >= max_retries:
                        print(f"❌ Nombre maximum de tentatives atteint pour la page {current_page}")
                    else:
                        print(f"⏱️ Tentative {retry_count}/{max_retries} après {retry_delay} secondes...")
                        time.sleep(retry_delay)
            
            except Exception as e:
                # Gestion des exceptions (problèmes réseau, etc.)
                print(f"❌ Exception lors de la récupération de la page {current_page}: {e}")
                retry_count += 1
                
                if retry_count >= max_retries:
                    print(f"❌ Nombre maximum de tentatives atteint pour la page {current_page}")
                else:
                    print(f"⏱️ Tentative {retry_count}/{max_retries} après {retry_delay} secondes...")
                    time.sleep(retry_delay)
        
        # Si toutes les tentatives ont échoué pour cette page
        if not success:
            print(f"⚠️ Impossible de récupérer la page {current_page} après {max_retries} tentatives")
            print(f"⚠️ Retour des {len(all_invoices)} factures déjà récupérées")
            return all_invoices[:limit]

    print(f"🎉 Total des factures fournisseur récupérées: {len(all_invoices)}")
    return all_invoices[:limit]

def get_supplier_invoice_details(self, invoice_id):
    """Récupère les détails d'une facture fournisseur spécifique"""
    if not invoice_id:
        print("❌ ID de facture fournisseur invalide")
        return None
        
    invoice_id = str(invoice_id)  # Conversion en chaîne
    token = self.get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    url = f"{self.api_url}/supplier-invoices/{invoice_id}"
    print(f"🔍 Récupération des détails de la facture fournisseur {invoice_id}: {url}")
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            response = requests.get(url, headers=headers)
            status_code = response.status_code
            print(f"📊 Statut: {status_code}")
            
            if status_code == 200:
                data = response.json()
                # Vérifier le format de la réponse
                if "data" in data:
                    print(f"✅ Détails de la facture fournisseur {invoice_id} récupérés (format avec data)")
                    return data.get("data", {})
                else:
                    print(f"✅ Détails de la facture fournisseur {invoice_id} récupérés (format direct)")
                    return data
            
            elif status_code == 401:
                # Renouveler le token et réessayer
                print("🔄 Token expiré, renouvellement...")
                self.token_expires_at = 0
                token = self.get_access_token()
                headers["Authorization"] = f"Bearer {token}"
                retry_count += 1
            
            elif status_code == 404:
                print(f"❌ Facture fournisseur {invoice_id} non trouvée (404)")
                return None
            
            else:
                print(f"❌ Erreur {status_code}: {response.text}")
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 5  # 5 secondes entre les tentatives
                    print(f"⏱️ Tentative {retry_count}/{max_retries} dans {wait_time} secondes...")
                    time.sleep(wait_time)
        
        except Exception as e:
            print(f"❌ Exception lors de la récupération des détails: {e}")
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 5
                print(f"⏱️ Tentative {retry_count}/{max_retries} dans {wait_time} secondes...")
                time.sleep(wait_time)
    
    print(f"❌ Échec après {max_retries} tentatives pour la facture fournisseur {invoice_id}")
    return None

def download_supplier_invoice_pdf(self, invoice_id):
    """Télécharge le PDF d'une facture fournisseur et retourne le chemin du fichier"""
    if not invoice_id:
        print("❌ ID de facture fournisseur invalide pour le téléchargement du PDF")
        return None
    
    # Conversion explicite en string
    invoice_id = str(invoice_id)
    
    # Définir le chemin du fichier PDF
    pdf_filename = f"facture_fournisseur_{invoice_id}.pdf"
    pdf_path = os.path.join(PDF_STORAGE_DIR, pdf_filename)
    
    # Vérifier si le fichier existe déjà
    if os.path.exists(pdf_path):
        file_size = os.path.getsize(pdf_path)
        if file_size > 0:
            print(f"📄 PDF déjà existant pour la facture fournisseur {invoice_id}: {pdf_path} ({file_size} octets)")
            return pdf_path
        else:
            print(f"⚠️ Fichier PDF existant mais vide, retéléchargement...")
    
    # Si non, d'abord récupérer les détails de la facture pour obtenir le lien PDF direct
    invoice_details = self.get_supplier_invoice_details(invoice_id)
    if not invoice_details:
        print(f"❌ Impossible de récupérer les détails pour télécharger le PDF")
        return None
    
    # Vérifier si le lien PDF est disponible directement dans les détails de la facture
    pdf_link = invoice_details.get("pdf_link")
    if not pdf_link:
        print(f"⚠️ Lien PDF non trouvé dans les détails de la facture fournisseur {invoice_id}")
        # Essayer l'URL standard quand même
    else:
        print(f"🔗 Lien PDF trouvé: {pdf_link}")
    
    # Méthodes de téléchargement à essayer
    methods = [
        {
            "name": "Lien direct",
            "url": pdf_link,
            "headers": {
                "Authorization": f"Bearer {self.get_access_token()}",
                "Accept": "application/pdf"
            },
            "skip_if_none": True  # Ignorer si pdf_link est None
        },
        {
            "name": "API standard",
            "url": f"{self.api_url}/supplier-invoices/{invoice_id}/document",
            "headers": {
                "Authorization": f"Bearer {self.get_access_token()}",
                "Accept": "application/pdf"
            },
            "skip_if_none": False
        }
    ]
    
    # Essayer chaque méthode jusqu'à ce qu'une fonctionne
    for method in methods:
        # Vérifier si on doit sauter cette méthode
        if method["skip_if_none"] and not method["url"]:
            continue
            
        url = method["url"]
        name = method["name"]
        print(f"📥 Téléchargement par {name}: {url}")
        
        try:
            response = requests.get(url, headers=method["headers"])
            status_code = response.status_code
            print(f"📊 Statut: {status_code}")
            
            if status_code == 200:
                # Vérifier que c'est bien un PDF
                content_type = response.headers.get('Content-Type', '')
                content_length = len(response.content)
                
                if ('pdf' not in content_type.lower() and 
                    content_length < 1000 and 
                    not response.content.startswith(b'%PDF')):
                    print(f"⚠️ Contenu non PDF reçu: {content_type}, taille: {content_length}")
                    continue
                
                # Sauvegarder le PDF
                with open(pdf_path, 'wb') as f:
                    f.write(response.content)
                
                file_size = os.path.getsize(pdf_path)
                print(f"✅ PDF téléchargé avec succès: {pdf_path} ({file_size} octets)")
                return pdf_path
            
            elif status_code == 401:
                # Renouveler le token et réessayer une fois
                print("🔄 Token expiré, renouvellement...")
                self.token_expires_at = 0
                new_token = self.get_access_token()
                method["headers"]["Authorization"] = f"Bearer {new_token}"
                
                # Nouvel essai avec le token renouvelé
                response = requests.get(url, headers=method["headers"])
                if response.status_code == 200:
                    with open(pdf_path, 'wb') as f:
                        f.write(response.content)
                    file_size = os.path.getsize(pdf_path)
                    print(f"✅ PDF téléchargé après renouvellement: {pdf_path} ({file_size} octets)")
                    return pdf_path
            
            print(f"❌ Échec du téléchargement par {name}: {status_code}")
            
        except Exception as e:
            print(f"❌ Exception lors du téléchargement par {name}: {e}")
    
    # Si toutes les méthodes ont échoué, créer un fichier vide
    print("❌ Toutes les méthodes de téléchargement ont échoué")
    with open(pdf_path, 'w') as f:
        f.write("")
    print(f"⚠️ Fichier vide créé: {pdf_path}")
    return pdf_path

    def get_nested_value(self, data: Dict, key_path: str, default: Any = None) -> Any:
        """
        Récupère une valeur imbriquée dans un dictionnaire en utilisant un chemin avec des points.
        Exemple: get_nested_value(data, "relateds.0.relatedAmount", "")
        """
        keys = key_path.split('.')
        value = data
        
        try:
            for key in keys:
                # Si la clé est un nombre, on traite comme un index de liste
                if key.isdigit() and isinstance(value, (list, tuple)):
                    value = value[int(key)]
                # Si c'est une valeur spéciale pour accéder à la première clé d'un dict
                elif key == "first" and isinstance(value, dict) and value:
                    value = next(iter(value.values()))
                else:
                    value = value[key]
                    
            return value
        except (KeyError, IndexError, TypeError, StopIteration):
            return default

    def extract_relateds(self, relateds_data: Dict) -> List[Dict]:
        """
        Extrait les données de paiements liés à partir de la structure 'relateds'
        """
        payments = []
        if not relateds_data:
            return payments
            
        # Si c'est un dictionnaire avec des clés numériques ou avec un tag _xml_childtag
        if '_xml_childtag' in relateds_data:
            # Ignorer la clé _xml_childtag et traiter les autres clés comme indices
            for key, related in relateds_data.items():
                if key != '_xml_childtag' and isinstance(related, dict):
                    payment = self.extract_payment_data(related)
                    if payment:
                        payments.append(payment)
        else:
            # Parcourir directement les valeurs du dictionnaire
            for related in relateds_data.values():
                if isinstance(related, dict):
                    payment = self.extract_payment_data(related)
                    if payment:
                        payments.append(payment)
                        
        return payments
        
    def extract_payment_data(self, related: Dict) -> Optional[Dict]:
        """
        Extrait les informations de paiement d'un élément 'related'
        """
        if not isinstance(related, dict):
            return None
            
        if 'relatedType' in related and related.get('relatedType') == 'payment':
            return {
                "id": related.get("relatedId", ""),
                "date": related.get("relatedDate", ""),
                "amount": related.get("relatedAmount", ""),
                "medium": related.get("relatedMediumTxt", ""),
                "notes": related.get("relatedNotes", ""),
                "ident": related.get("relatedIdent", "")
            }
        return None
        
    def extract_address_data(self, address_data: Dict) -> str:
        """
        Extrait et formate une adresse à partir d'un dictionnaire d'adresse
        """
        if not isinstance(address_data, dict):
            return ""
            
        address_parts = []
        
        # Extraire les parties principales
        for part in ["name", "part1", "part2", "part3", "part4"]:
            if part in address_data and address_data[part]:
                address_parts.append(address_data[part])
        
        # Ajouter le code postal et la ville
        zip_town = []
        if "zip" in address_data and address_data["zip"]:
            zip_town.append(address_data["zip"])
        
        if "town" in address_data and address_data["town"]:
            zip_town.append(address_data["town"])
            
        if zip_town:
            address_parts.append(" ".join(zip_town))
        
        # Ajouter l'état si présent
        if "state" in address_data and address_data["state"]:
            address_parts.append(address_data["state"])
        
        # Ajouter le pays
        if "countrycode" in address_data and address_data["countrycode"]:
            address_parts.append(address_data["countrycode"])
            
        # Essayer d'extraire les parties depuis partsToDisplay si elles existent
        if "partsToDisplay" in address_data and isinstance(address_data["partsToDisplay"], dict):
            parts_to_display = address_data["partsToDisplay"]
            if "_xml_childtag" in parts_to_display and parts_to_display.get("_xml_childtag") == "part":
                for _, part_data in parts_to_display.items():
                    if isinstance(part_data, dict) and "txt" in part_data and part_data["txt"]:
                        txt = part_data["txt"].strip()
                        if txt and txt != " " and txt not in address_parts:
                            address_parts.append(txt)
        
        return ", ".join(filter(None, address_parts))

    def normalize_invoice_data(self, invoice_details: Dict) -> Dict:
        """
        Normalise les données de facture pour Airtable en extrayant tous les champs pertinents
        de manière cohérente, quelle que soit la structure de la réponse.
        """
        if not invoice_details:
            return {}
            
        normalized_data = {}
        
        # Afficher toutes les clés disponibles pour le débogage
        logger.debug(f"Clés disponibles dans les détails bruts: {list(invoice_details.keys())}")
        
        # Champs de base - direct mapping avec vérification d'existence
        base_fields = [
            "id", "corpid", "ownerid", "purdocmapid", "prefsid", "linkedtype", "linkedid", 
            "parentid", "thirdid", "hasVat", "status", "fileid", "filename", "nbpages", 
            "ident", "thirdident", "created", "displayedDate", "currencysymbol", 
            "docspeakerStaffId", "docspeakerStaffFullName", "ownerFullName", "subject", 
            "rowsAmount", "discountPercent", "discountAmount", "rowsAmountDiscounted", 
            "offerAmount", "rowsAmountAllInc", "packagingsAmount", "shippingsAmount", 
            "totalAmountTaxesFree", "taxesAmountSum", "totalAmount", "totalEcoTaxFree", 
            "totalEcoTaxInc", "ecoTaxId", "shippingNbParcels", "shippingWeight", 
            "shippingWeightUnit", "shippingVolume", "shippingTrackingNumber", 
            "shippingTrackingUrl", "shippingDate", "notes", "nbExpireDays", "step",
            "deliverystep", "isDeposit", "dueAmount", "externalident", "countrycode",
            # Ajout de champs supplémentaires qui pourraient être présents
            "reference", "supplierref", "docnum", "date", "dueDate", "doctype", "supplier",
            "supplierName", "supplierContactName", "total_amount", "vat_amount", "currency",
            "third_id", "third_name", "docNumber", "third_contact_name", "third_name"
        ]
        
        for field in base_fields:
            if field in invoice_details:
                normalized_data[field] = invoice_details[field]
        
        # Si l'ID est manquant mais qu'un identifiant alternatif est présent
        if "id" not in normalized_data:
            for alt_id_field in ["docid", "document_id", "invoice_id", "ident"]:
                if alt_id_field in invoice_details:
                    normalized_data["id"] = invoice_details[alt_id_field]
                    break
        
        # Extraire les taxes détaillées
        if "taxesAmountDetails" in invoice_details:
            tax_details = invoice_details["taxesAmountDetails"]
            # Si c'est une chaîne, essayer de la parser
            if isinstance(tax_details, str):
                try:
                    if tax_details.startswith('a:'):
                        # Format PHP serialized array
                        normalized_data["taxesAmountDetails_str"] = tax_details
                        # Extraire les valeurs avec une regex simple
                        # Note: ceci est une approximation, un parser PHP serait plus précis
                        import re
                        matches = re.findall(r'"(\d+\.\d+)"', tax_details)
                        if matches:
                            normalized_data["taxesAmountDetails_extracted"] = ", ".join(matches)
                    else:
                        # Essayer de parser comme JSON
                        tax_dict = json.loads(tax_details)
                        normalized_data["taxesAmountDetails_dict"] = tax_dict
                except (json.JSONDecodeError, ValueError):
                    normalized_data["taxesAmountDetails_str"] = tax_details
            elif isinstance(tax_details, dict):
                normalized_data["taxesAmountDetails_dict"] = tax_details
        
        # Extraction des données de paiement
        if "relateds" in invoice_details:
            relateds = invoice_details["relateds"]
            payments = self.extract_relateds(relateds)
            if payments:
                normalized_data["payments"] = payments
                normalized_data["payments_count"] = len(payments)
                normalized_data["payments_total"] = sum(float(p.get("amount", 0)) for p in payments)
                
                # Ajouter les détails du premier paiement pour faciliter l'accès
                if payments:
                    first_payment = payments[0]
                    normalized_data["first_payment_date"] = first_payment.get("date", "")
                    normalized_data["first_payment_amount"] = first_payment.get("amount", "")
                    normalized_data["first_payment_medium"] = first_payment.get("medium", "")
        
        # Traitement des adresses
        address_types = {
            "corpAddress": "address_company", 
            "thirdAddress": "address_third", 
            "shipAddress": "address_shipping"
        }
        
        for src_key, dest_key in address_types.items():
            if src_key in invoice_details:
                address_text = self.extract_address_data(invoice_details[src_key])
                normalized_data[dest_key] = address_text
        
        # Recherche d'informations supplémentaires dans les structures imbriquées
        # Par exemple, si les informations du fournisseur sont dans un sous-objet
        if "supplier" in invoice_details and isinstance(invoice_details["supplier"], dict):
            supplier = invoice_details["supplier"]
            normalized_data["supplier_name"] = supplier.get("name", "")
            normalized_data["supplier_email"] = supplier.get("email", "")
            normalized_data["supplier_phone"] = supplier.get("tel", "")
        
        # Recherche du montant total si non trouvé directement
        if "totalAmount" not in normalized_data:
            for amount_field in ["total", "amount", "total_amount", "invoice_amount"]:
                if amount_field in invoice_details:
                    normalized_data["totalAmount"] = invoice_details[amount_field]
                    break
        
        return normalized_data

    def get_supplier_invoice_details(self, invoice_id: str) -> Dict:
        """
        Récupère les détails d'une facture spécifique par son ID.
        """
        logger.info(f"🔍 Récupération des détails de la facture {invoice_id}")

        params = {
            "id": invoice_id
        }

        # CORRECTION: Essayer plusieurs méthodes pour obtenir les détails
        methods_to_try = [
            "Purchase.getOne",
            "Document.getOne",
            "SupplierInvoice.getOne",
            "Accounting.getDocumentDetails"
        ]
        
        raw_invoice_details = None
        
        for method in methods_to_try:
            logger.info(f"Essai de récupération des détails avec la méthode {method}")
            result = self._make_api_request(method, params)
            
            if result and isinstance(result, dict) and len(result) > 0:
                logger.info(f"✅ Récupération réussie avec la méthode {method}")
                raw_invoice_details = result
                break
            else:
                logger.warning(f"❌ Méthode {method} infructueuse")
        
        if not raw_invoice_details:
            logger.error(f"⚠️ Impossible de récupérer les détails de la facture {invoice_id}")
            return {}
        
        # Afficher directement la réponse JSON dans les logs
        log_json(raw_invoice_details, f"Détails bruts de la facture {invoice_id}")
        
        # Sauvegarde également dans un fichier pour consultation ultérieure
        try:
            debug_dir = "debug_json"
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, f"invoice_{invoice_id}_raw.json")
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(raw_invoice_details, f, indent=2, ensure_ascii=False)
            logger.info(f"Réponse brute sauvegardée dans {debug_file}")
        except Exception as e:
            logger.error(f"Impossible de sauvegarder la réponse brute: {e}")
        
        # Logs pour le debugging
        if raw_invoice_details:
            logger.debug(f"Champs disponibles dans la réponse brute: {list(raw_invoice_details.keys())}")
        else:
            logger.warning(f"Aucun détail reçu pour la facture {invoice_id}")
        
        # Normalisation des données pour Airtable
        normalized_data = self.normalize_invoice_data(raw_invoice_details)
        
        # Log des données normalisées
        log_json(normalized_data, f"Facture {invoice_id} normalisée")
        
        return normalized_data

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
            # Récupérer les détails bruts de la facture pour obtenir l'URL du PDF
            # On utilise les détails bruts car l'URL du PDF peut être dans n'importe quel champ
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
                # Essayer de générer l'URL du PDF via une API dédiée
                logger.info("Tentative de génération du PDF via l'API")
                pdf_params = {
                    "docid": invoice_id,
                    "doctype": "supplierinvoice"
                }
                pdf_result = self._make_api_request("Document.getPdf", pdf_params)
                
                if pdf_result and isinstance(pdf_result, dict) and "downloadUrl" in pdf_result:
                    pdf_url = pdf_result["downloadUrl"]
                    logger.info(f"URL PDF générée: {pdf_url}")
            
            if not pdf_url:
                logger.warning(f"URL PDF non trouvée pour la facture {invoice_id}")
                return None
            
            # Créer le chemin de destination
            pdf_path = os.path.join(PDF_STORAGE_DIR, f"invoice_{invoice_id}.pdf")
            
            # Télécharger le PDF
            logger.info(f"Téléchargement du PDF depuis {pdf_url}")
            
            response = requests.get(pdf_url, timeout=60)
            if response.status_code == 200:
                with open(pdf_path, 'wb') as f:
                    f.write(response.content)
                    
                logger.info(f"✅ PDF téléchargé et enregistré dans {pdf_path}")
                return pdf_path
            else:
                logger.error(f"❌ Échec du téléchargement du PDF: code HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Exception lors du téléchargement du PDF: {str(e)}")
            return None

    def update_supplier_invoice_status(self, invoice_id: str, new_status: str) -> bool:
        """
        Met à jour le statut d'une facture fournisseur
        
        Args:
            invoice_id: ID de la facture à mettre à jour
            new_status: Nouveau statut (par exemple: "paid", "pending", "validated")
        
        Returns:
            True si la mise à jour a réussi, False sinon
        """
        logger.info(f"Mise à jour du statut de la facture {invoice_id} vers '{new_status}'")
        
        params = {
            "id": invoice_id,
            "status": new_status
        }
        
        # Essayer différentes méthodes pour mettre à jour le statut
        methods_to_try = [
            "Purchase.updateStatus",
            "Document.updateStatus",
            "SupplierInvoice.updateStatus"
        ]
        
        for method in methods_to_try:
            logger.info(f"Tentative de mise à jour avec la méthode {method}")
            result = self._make_api_request(method, params)
            
            if result and isinstance(result, dict) and result.get("status") == "success":
                logger.info(f"✅ Statut de la facture {invoice_id} mis à jour avec succès")
                return True
                
        logger.error(f"❌ Échec de la mise à jour du statut de la facture {invoice_id}")
        return False
    
    def get_invoice_payments(self, invoice_id: str) -> List[Dict]:
        """
        Récupère tous les paiements associés à une facture
        
        Args:
            invoice_id: ID de la facture
            
        Returns:
            Liste des paiements associés à la facture
        """
        logger.info(f"Récupération des paiements pour la facture {invoice_id}")
        
        # D'abord récupérer les détails de la facture qui contiennent les paiements
        invoice_details = self.get_supplier_invoice_details(invoice_id)
        
        if not invoice_details:
            logger.warning(f"Aucun détail trouvé pour la facture {invoice_id}")
            return []
            
        # Extraction des paiements si présent dans la structure 'relateds'
        payments = []
        if "payments" in invoice_details:
            payments = invoice_details["payments"]
        elif "relateds" in invoice_details:
            payments = self.extract_relateds(invoice_details["relateds"])
        
        logger.info(f"Nombre de paiements trouvés: {len(payments)}")
        return payments

    def create_payment(self, invoice_id: str, amount: float, date: str, 
                      medium: str = "manual", notes: str = "") -> bool:
        """
        Crée un paiement pour une facture fournisseur
        
        Args:
            invoice_id: ID de la facture
            amount: Montant du paiement
            date: Date du paiement (format: YYYY-MM-DD)
            medium: Moyen de paiement (par exemple: "manual", "bank", "check")
            notes: Notes associées au paiement
            
        Returns:
            True si la création a réussi, False sinon
        """
        logger.info(f"Création d'un paiement de {amount} pour la facture {invoice_id}")
        
        params = {
            "linkedid": invoice_id,
            "linkedtype": "supplierinvoice",
            "amount": amount,
            "date": date,
            "medium": medium,
            "notes": notes
        }
        
        # Essayer différentes méthodes pour créer un paiement
        methods_to_try = [
            "Purchase.createPayment",
            "Payment.create",
            "SupplierInvoice.createPayment"
        ]
        
        for method in methods_to_try:
            logger.info(f"Tentative de création avec la méthode {method}")
            result = self._make_api_request(method, params)
            
            if result:
                logger.info(f"✅ Paiement créé avec succès pour la facture {invoice_id}")
                return True
                
        logger.error(f"❌ Échec de la création du paiement pour la facture {invoice_id}")
        return False
