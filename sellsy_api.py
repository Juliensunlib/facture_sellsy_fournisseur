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
        
        # Journalisation de la liste brute des factures
        log_json(result, "Liste brute des factures fournisseurs")
        
        # Sauvegarde également dans un fichier pour consultation ultérieure
        try:
            debug_dir = "debug_json"
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, "all_invoices_raw.json")
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"Liste brute des factures sauvegardée dans {debug_file}")
        except Exception as e:
            logger.error(f"Impossible de sauvegarder la liste brute: {e}")
        
        if isinstance(result, dict):
            invoices = list(result.values())
            normalized_invoices = [self.normalize_invoice_data(invoice) for invoice in invoices]
            logger.info(f"Nombre de factures récupérées: {len(normalized_invoices)}")
            return normalized_invoices
        
        logger.warning("Aucune facture trouvée ou format de réponse inattendu")
        return []

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
        
        # Champs de base - direct mapping
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
            "deliverystep", "isDeposit", "dueAmount", "externalident", "countrycode"
        ]
        
        for field in base_fields:
            if field in invoice_details:
                normalized_data[field] = invoice_details[field]
        
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
        
        return normalized_data

    def get_supplier_invoice_details(self, invoice_id: str) -> Dict:
        """
        Récupère les détails d'une facture spécifique par son ID.
        """
        logger.info(f"🔍 Récupération des détails de la facture {invoice_id}")

        params = {
            "id": invoice_id
        }

        raw_invoice_details = self._make_api_request("Purchase.getOne", params) or {}
        
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
            raw_invoice_details = self._make_api_request("Purchase.getOne", {"id": invoice_id}) or {}
            
            if not raw_invoice_details:
                logger.warning(f"Détails de la facture {invoice_id} non trouvés")
                return None
            
            # Chercher l'URL du PDF dans différents champs possibles
            pdf_url = None
            pdf_fields = ["pdf_url", "pdfUrl", "pdf_link", "downloadUrl", "public_link", "pdf"]
            
            for field in pdf_fields:
                if field in raw_invoice_details and raw_invoice_details[field]:
                    pdf_url = raw_invoice_details[field]
                    logger.info(f"URL PDF trouvée via champ {field}: {pdf_url}")
                    break
            
            if not pdf_url:
                # Chercher dans des structures imbriquées
                for field in ["file", "document", "attachment"]:
                    if field in raw_invoice_details and isinstance(raw_invoice_details[field], dict):
                        for pdf_field in pdf_fields:
                            if pdf_field in raw_invoice_details[field]:
                                pdf_url = raw_invoice_details[field][pdf_field]
                                logger.info(f"URL PDF trouvée via {field}.{pdf_field}: {pdf_url}")
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
            
    def get_invoice_items(self, invoice_id: str) -> List[Dict]:
        """
        Récupère les lignes de la facture (articles/services)
        
        Args:
            invoice_id: ID de la facture
            
        Returns:
            Liste des lignes de la facture
        """
        logger.info(f"Récupération des lignes pour la facture {invoice_id}")
        
        # On récupère d'abord les détails complets de la facture
        raw_invoice_details = self._make_api_request("Purchase.getOne", {"id": invoice_id}) or {}
        
        items = []
        
        # Chercher les lignes dans les champs possibles
        item_fields = ["rows", "items", "lines", "details"]
        
        for field in item_fields:
            if field in raw_invoice_details and raw_invoice_details[field]:
                raw_items = raw_invoice_details[field]
                
                # Si c'est un dictionnaire (cas courant dans l'API Sellsy)
                if isinstance(raw_items, dict):
                    # Ignorer les clés spéciales et traiter les autres comme des items
                    for key, item in raw_items.items():
                        if key != "_xml_childtag" and isinstance(item, dict):
                            normalized_item = self.normalize_item_data(item)
                            items.append(normalized_item)
                
                # Si c'est une liste (moins courant)
                elif isinstance(raw_items, list):
                    for item in raw_items:
                        if isinstance(item, dict):
                            normalized_item = self.normalize_item_data(item)
                            items.append(normalized_item)
        
        # Afficher les items dans les logs
        if items:
            log_json(items, f"Lignes de la facture {invoice_id}")
        
        logger.info(f"Récupéré {len(items)} lignes pour la facture {invoice_id}")
        return items
    
    def normalize_item_data(self, item: Dict) -> Dict:
        """
        Normalise les données d'une ligne de facture
        
        Args:
            item: Données brutes de la ligne
            
        Returns:
            Données normalisées de la ligne
        """
        normalized_item = {}
        
        # Champs courants des lignes d'articles
        item_fields = [
            "id", "row_type", "type", "item_id", "product_id", "service_id", "name", 
            "notes", "unitAmount", "qt", "taxid", "tax_rate", "discount_rate", 
            "discount_amount", "rowAmount", "rowTaxAmount", "rowAmountTaxesFree"
        ]
        
        # Mapper les champs de base
        for field in item_fields:
            if field in item:
                normalized_item[field] = item[field]
        
        # Ajouter quelques champs calculés utiles
        if "unitAmount" in item and "qt" in item:
            try:
                unit_amount = float(item["unitAmount"])
                quantity = float(item["qt"])
                normalized_item["total_amount"] = unit_amount * quantity
            except (ValueError, TypeError):
                pass
        
        return normalized_item


# Exemple d'utilisation avec debug activé pour voir les JSON
if __name__ == "__main__":
    # Activer les logs DEBUG pour voir tous les détails JSON
    logger.setLevel(logging.DEBUG)
    
    # Configurer un handler pour la console avec un format lisible
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # Supprimer les anciens handlers et ajouter le nouveau
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.addHandler(console_handler)
    
    # Initialiser l'API et tester
    sellsy_api = SellsySupplierAPI()
    if sellsy_api.test_connection():
        invoices = sellsy_api.get_all_supplier_invoices(limit=2)  # Limité à 2 pour les tests
        for invoice in invoices:
            invoice_id = invoice.get('id')
            if invoice_id:
                logger.info(f"==== Traitement de la facture {invoice_id} ====")
                
                # Récupérer les détails complets
                details = sellsy_api.get_supplier_invoice_details(invoice_id)
                logger.info(f"Facture {invoice_id} - Nombre de champs: {len(details)}")
                
                # Récupérer les lignes de la facture
                items = sellsy_api.get_invoice_items(invoice_id)
                logger.info(f"Facture {invoice_id} - Nombre d'articles: {len(items)}")
                
                # Télécharger le PDF
                pdf_path = sellsy_api.download_supplier_invoice_pdf(invoice_id)
                if pdf_path:
                    logger.info(f"PDF sauvegardé: {pdf_path}")
