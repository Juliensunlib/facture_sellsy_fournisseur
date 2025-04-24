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

    def get_all_supplier_invoices(self, limit: int = 1000) -> List[Dict]:
        """
        Récupère toutes les factures fournisseurs jusqu'à la limite spécifiée.
        Utilise la méthode Purchase.getList qui est plus appropriée pour les factures fournisseurs.
        """
        logger.info(f"🔄 Récupération de toutes les factures fournisseurs (limite: {limit})")

        # CORRECTION: Utilisation de Purchase.getList au lieu de Accounting.getList
        params = {
            "pagination": {
                "nbperpage": limit,
                "pagenum": 1
            },
            "search": {
                "doctype": "supplierinvoice"  # Filtre pour les factures fournisseurs
            }
        }

        result = self._make_api_request("Purchase.getList", params)
        
        # Si la première méthode ne fonctionne pas, essayer une alternative
        if not result or not isinstance(result, dict) or len(result) == 0:
            logger.warning("Première méthode infructueuse, essai avec une méthode alternative")
            
            # Méthode alternative 1
            params = {
                "type": "supplierinvoice",
                "nbperpage": limit
            }
            result = self._make_api_request("Accounting.getAccountingDocuments", params)
            
            # Si toujours pas de résultat, essayer une autre méthode
            if not result or not isinstance(result, dict) or len(result) == 0:
                logger.warning("Deuxième méthode infructueuse, essai avec une autre méthode")
                
                # Méthode alternative 2
                params = {
                    "doctype": "supplierinvoice"
                }
                result = self._make_api_request("Document.getList", params)
        
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
        
        # Traitement des résultats selon leur structure
        invoices = []
        
        if isinstance(result, dict):
            # Structure possible 1: dictionnaire avec des clés numériques
            if all(k.isdigit() for k in result.keys() if k != '_xml_childtag'):
                logger.info("Structure détectée: dictionnaire avec clés numériques")
                for k, v in result.items():
                    if k != '_xml_childtag' and isinstance(v, dict):
                        invoices.append(self.normalize_invoice_data(v))
            
            # Structure possible 2: liste dans un champ spécifique
            elif any(field in result for field in ['result', 'list', 'data', 'invoices', 'documents']):
                logger.info("Structure détectée: liste dans un champ spécifique")
                for field in ['result', 'list', 'data', 'invoices', 'documents']:
                    if field in result and result[field]:
                        if isinstance(result[field], dict):
                            for k, v in result[field].items():
                                if k != '_xml_childtag' and isinstance(v, dict):
                                    invoices.append(self.normalize_invoice_data(v))
                        elif isinstance(result[field], list):
                            for item in result[field]:
                                if isinstance(item, dict):
                                    invoices.append(self.normalize_invoice_data(item))
            
            # Structure possible 3: résultat direct
            else:
                logger.info("Structure détectée: structure inconnue, tentative de normalisation directe")
                invoices = [self.normalize_invoice_data(result)]
                
        elif isinstance(result, list):
            logger.info("Structure détectée: liste directe")
            invoices = [self.normalize_invoice_data(item) for item in result if isinstance(item, dict)]
        
        logger.info(f"Nombre de factures récupérées après traitement: {len(invoices)}")
        return invoices

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
        logger.error(f"❌ Erreur lors du téléchargement du PDF: {e}")
        return None

def get_supplier_invoices_by_date_range(self, start_date: str, end_date: str, limit: int = 1000) -> List[Dict]:
    """
    Récupère les factures fournisseurs dans une plage de dates spécifique.
    
    Args:
        start_date: Date de début au format YYYY-MM-DD
        end_date: Date de fin au format YYYY-MM-DD
        limit: Nombre maximum de factures à récupérer
        
    Returns:
        Liste des factures fournisseurs dans la plage de dates
    """
    logger.info(f"Récupération des factures fournisseurs du {start_date} au {end_date}")
    
    # CORRECTION: Utilisation de Purchase.getList au lieu de Accounting.getList
    params = {
        "pagination": {
            "nbperpage": limit,
            "pagenum": 1
        },
        "search": {
            "doctype": "supplierinvoice",
            "periodecreated_start": start_date,
            "periodecreated_end": end_date
        }
    }
    
    result = self._make_api_request("Purchase.getList", params)
    
    # Si la première méthode ne fonctionne pas, essayer une alternative
    if not result or not isinstance(result, dict) or len(result) == 0:
        logger.warning("Première méthode infructueuse, essai avec une méthode alternative")
        
        # Méthode alternative 1
        params = {
            "type": "supplierinvoice",
            "nbperpage": limit,
            "search": {
                "created_start": start_date,
                "created_end": end_date
            }
        }
        result = self._make_api_request("Accounting.getAccountingDocuments", params)
    
    # Traitement identique à get_all_supplier_invoices
    invoices = []
    
    if isinstance(result, dict):
        # Structure possible 1: dictionnaire avec des clés numériques
        if all(k.isdigit() for k in result.keys() if k != '_xml_childtag'):
            logger.info("Structure détectée: dictionnaire avec clés numériques")
            for k, v in result.items():
                if k != '_xml_childtag' and isinstance(v, dict):
                    invoices.append(self.normalize_invoice_data(v))
        
        # Structure possible 2: liste dans un champ spécifique
        elif any(field in result for field in ['result', 'list', 'data', 'invoices', 'documents']):
            logger.info("Structure détectée: liste dans un champ spécifique")
            for field in ['result', 'list', 'data', 'invoices', 'documents']:
                if field in result and result[field]:
                    if isinstance(result[field], dict):
                        for k, v in result[field].items():
                            if k != '_xml_childtag' and isinstance(v, dict):
                                invoices.append(self.normalize_invoice_data(v))
                    elif isinstance(result[field], list):
                        for item in result[field]:
                            if isinstance(item, dict):
                                invoices.append(self.normalize_invoice_data(item))
        
        # Structure possible 3: résultat direct
        else:
            logger.info("Structure détectée: structure inconnue, tentative de normalisation directe")
            invoices = [self.normalize_invoice_data(result)]
            
    elif isinstance(result, list):
        logger.info("Structure détectée: liste directe")
        invoices = [self.normalize_invoice_data(item) for item in result if isinstance(item, dict)]
    
    logger.info(f"Nombre de factures récupérées après traitement: {len(invoices)}")
    return invoices

def get_suppliers(self, limit: int = 1000) -> List[Dict]:
    """
    Récupère la liste des fournisseurs depuis Sellsy.
    
    Args:
        limit: Nombre maximum de fournisseurs à récupérer
        
    Returns:
        Liste des fournisseurs
    """
    logger.info(f"Récupération de la liste des fournisseurs (limite: {limit})")
    
    params = {
        "pagination": {
            "nbperpage": limit,
            "pagenum": 1
        },
        "search": {
            "isSupplier": "Y"  # Filtrer uniquement les fournisseurs
        }
    }
    
    result = self._make_api_request("People.getList", params)
    
    suppliers = []
    
    # Traitement des résultats selon leur structure
    if isinstance(result, dict):
        # Structure possible 1: dictionnaire avec des clés numériques
        if all(k.isdigit() for k in result.keys() if k != '_xml_childtag'):
            for k, v in result.items():
                if k != '_xml_childtag' and isinstance(v, dict):
                    suppliers.append(self.normalize_supplier_data(v))
        
        # Structure possible 2: liste dans un champ spécifique
        elif any(field in result for field in ['result', 'list', 'data']):
            for field in ['result', 'list', 'data']:
                if field in result and result[field]:
                    if isinstance(result[field], dict):
                        for k, v in result[field].items():
                            if k != '_xml_childtag' and isinstance(v, dict):
                                suppliers.append(self.normalize_supplier_data(v))
                    elif isinstance(result[field], list):
                        for item in result[field]:
                            if isinstance(item, dict):
                                suppliers.append(self.normalize_supplier_data(item))
    
    elif isinstance(result, list):
        suppliers = [self.normalize_supplier_data(item) for item in result if isinstance(item, dict)]
    
    logger.info(f"Nombre de fournisseurs récupérés: {len(suppliers)}")
    return suppliers

def normalize_supplier_data(self, supplier_details: Dict) -> Dict:
    """
    Normalise les données d'un fournisseur pour un usage cohérent.
    
    Args:
        supplier_details: Dictionnaire contenant les détails du fournisseur
        
    Returns:
        Dictionnaire normalisé des détails du fournisseur
    """
    if not supplier_details:
        return {}
        
    normalized_data = {}
    
    # Champs de base - direct mapping avec vérification d'existence
    base_fields = [
        "id", "corpid", "ownerid", "type", "status", "name", "web", "siret", 
        "siren", "vat", "rcs", "fax", "tel", "mobile", "email", "apenaf", 
        "rna", "ident", "joindate", "auxCode", "picture", "phonecall", 
        "isclientofsellsy", "maincontactid", "maincontactcivility", 
        "maincontactname", "maincontactlinkid", "simpleDesc", "source",
        "capital", "accountingCode", "auxCode", "buyer_account_id"
    ]
    
    for field in base_fields:
        if field in supplier_details:
            normalized_data[field] = supplier_details[field]
    
    # Si l'ID est manquant mais qu'un identifiant alternatif est présent
    if "id" not in normalized_data:
        for alt_id_field in ["peopleid", "supplier_id", "thirdid"]:
            if alt_id_field in supplier_details:
                normalized_data["id"] = supplier_details[alt_id_field]
                break
    
    # Traitement des adresses
    if "address" in supplier_details and isinstance(supplier_details["address"], dict):
        normalized_data["address"] = self.extract_address_data(supplier_details["address"])
    
    # Récupération des contacts liés
    if "contacts" in supplier_details and isinstance(supplier_details["contacts"], dict):
        contacts = []
        for k, v in supplier_details["contacts"].items():
            if k != '_xml_childtag' and isinstance(v, dict):
                contact = {
                    "id": v.get("id", ""),
                    "name": v.get("name", ""),
                    "email": v.get("email", ""),
                    "tel": v.get("tel", ""),
                    "mobile": v.get("mobile", ""),
                    "position": v.get("position", "")
                }
                contacts.append(contact)
        
        normalized_data["contacts"] = contacts
        
        # Ajouter le premier contact pour un accès facile
        if contacts:
            first_contact = contacts[0]
            normalized_data["contact_name"] = first_contact.get("name", "")
            normalized_data["contact_email"] = first_contact.get("email", "")
            normalized_data["contact_tel"] = first_contact.get("tel", "")
    
    return normalized_data

def get_supplier_payments(self, supplier_id: str = None, start_date: str = None, end_date: str = None, limit: int = 1000) -> List[Dict]:
    """
    Récupère les paiements des fournisseurs, avec des filtres optionnels.
    
    Args:
        supplier_id: ID du fournisseur (optionnel)
        start_date: Date de début au format YYYY-MM-DD (optionnel)
        end_date: Date de fin au format YYYY-MM-DD (optionnel)
        limit: Nombre maximum de paiements à récupérer
        
    Returns:
        Liste des paiements fournisseurs
    """
    logger.info(f"Récupération des paiements fournisseurs")
    
    params = {
        "pagination": {
            "nbperpage": limit,
            "pagenum": 1
        },
        "search": {
            "accounting": "supplier"  # Filtrer pour les paiements fournisseurs
        }
    }
    
    # Ajouter les filtres optionnels
    if supplier_id:
        params["search"]["thirdid"] = supplier_id
    
    if start_date:
        params["search"]["periodecreated_start"] = start_date
    
    if end_date:
        params["search"]["periodecreated_end"] = end_date
    
    result = self._make_api_request("Accounting.getPaymentsList", params)
    
    payments = []
    
    # Traitement des résultats selon leur structure
    if isinstance(result, dict):
        # Structure possible 1: dictionnaire avec des clés numériques
        if all(k.isdigit() for k in result.keys() if k != '_xml_childtag'):
            for k, v in result.items():
                if k != '_xml_childtag' and isinstance(v, dict):
                    payments.append(self.normalize_payment_data(v))
        
        # Structure possible 2: liste dans un champ spécifique
        elif any(field in result for field in ['result', 'list', 'data', 'payments']):
            for field in ['result', 'list', 'data', 'payments']:
                if field in result and result[field]:
                    if isinstance(result[field], dict):
                        for k, v in result[field].items():
                            if k != '_xml_childtag' and isinstance(v, dict):
                                payments.append(self.normalize_payment_data(v))
                    elif isinstance(result[field], list):
                        for item in result[field]:
                            if isinstance(item, dict):
                                payments.append(self.normalize_payment_data(item))
    
    elif isinstance(result, list):
        payments = [self.normalize_payment_data(item) for item in result if isinstance(item, dict)]
    
    logger.info(f"Nombre de paiements récupérés: {len(payments)}")
    return payments

def normalize_payment_data(self, payment_details: Dict) -> Dict:
    """
    Normalise les données d'un paiement pour un usage cohérent.
    
    Args:
        payment_details: Dictionnaire contenant les détails du paiement
        
    Returns:
        Dictionnaire normalisé des détails du paiement
    """
    if not payment_details:
        return {}
        
    normalized_data = {}
    
    # Champs de base - direct mapping avec vérification d'existence
    base_fields = [
        "id", "parentid", "corpid", "thirdid", "date", "amount", 
        "amount_convertedlocal", "amount_convertedeuro", "currency", 
        "currencysymbol", "medium", "sysCreated", "sysModified", 
        "accOwner", "accOwnerName", "isPaybackForThird", "isPaybackFromThird", 
        "isDeposit", "ident", "refAccounting", "validated", "linked", 
        "note", "idPaymentMethod", "linkedAmount", "unlinkedAmount"
    ]
    
    for field in base_fields:
        if field in payment_details:
            normalized_data[field] = payment_details[field]
    
    # Si l'ID est manquant mais qu'un identifiant alternatif est présent
    if "id" not in normalized_data:
        for alt_id_field in ["paymentid", "payment_id"]:
            if alt_id_field in payment_details:
                normalized_data["id"] = payment_details[alt_id_field]
                break
    
    # Récupérer les informations du fournisseur si présentes
    if "third" in payment_details and isinstance(payment_details["third"], dict):
        third = payment_details["third"]
        normalized_data["third_name"] = third.get("name", "")
        normalized_data["third_ident"] = third.get("ident", "")
    
    # Récupérer les factures liées à ce paiement
    if "linkedDocs" in payment_details and isinstance(payment_details["linkedDocs"], dict):
        linked_docs = []
        for k, v in payment_details["linkedDocs"].items():
            if k != '_xml_childtag' and isinstance(v, dict):
                linked_doc = {
                    "id": v.get("id", ""),
                    "amount": v.get("amount", ""),
                    "doctype": v.get("doctype", ""),
                    "ident": v.get("ident", ""),
                    "date": v.get("date", "")
                }
                linked_docs.append(linked_doc)
        
        normalized_data["linked_documents"] = linked_docs
        normalized_data["linked_documents_count"] = len(linked_docs)
    
    return normalized_data

def batch_download_invoices(self, invoice_ids: List[str], max_retries: int = 3) -> Dict[str, str]:
    """
    Télécharge par lots les PDFs de plusieurs factures fournisseurs.
    
    Args:
        invoice_ids: Liste des IDs de factures à télécharger
        max_retries: Nombre maximum de tentatives par facture en cas d'échec
        
    Returns:
        Dictionnaire avec les IDs des factures en clé et les chemins des PDFs en valeur
    """
    logger.info(f"Téléchargement par lots de {len(invoice_ids)} factures")
    
    results = {}
    
    for invoice_id in invoice_ids:
        success = False
        
        for attempt in range(max_retries):
            try:
                pdf_path = self.download_supplier_invoice_pdf(invoice_id)
                
                if pdf_path:
                    results[invoice_id] = pdf_path
                    success = True
                    logger.info(f"✅ Facture {invoice_id} téléchargée avec succès")
                    break
                
            except Exception as e:
                logger.error(f"❌ Erreur lors du téléchargement de la facture {invoice_id}: {e}")
            
            # Si ce n'est pas la dernière tentative, attendre avant de réessayer
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5  # Temps d'attente exponentiel: 5s, 10s, 15s...
                logger.info(f"Nouvelle tentative dans {wait_time}s pour la facture {invoice_id}")
                time.sleep(wait_time)
        
        if not success:
            logger.warning(f"⚠️ Échec du téléchargement de la facture {invoice_id} après {max_retries} tentatives")
    
    logger.info(f"Téléchargement terminé: {len(results)}/{len(invoice_ids)} factures téléchargées avec succès")
    return results

def run_complete_sync(self, start_date: str = None, end_date: str = None, limit: int = 1000, download_pdfs: bool = True) -> Dict:
    """
    Effectue une synchronisation complète des factures fournisseurs et télécharge optionnellement les PDFs.
    
    Args:
        start_date: Date de début au format YYYY-MM-DD (optionnel)
        end_date: Date de fin au format YYYY-MM-DD (optionnel)
        limit: Nombre maximum de factures à récupérer
        download_pdfs: Si True, télécharge les PDFs des factures
        
    Returns:
        Résultats de la synchronisation
    """
    start_time = time.time()
    logger.info(f"🚀 Démarrage de la synchronisation complète des factures fournisseurs")
    
    results = {
        "invoices": [],
        "suppliers": [],
        "total_invoices": 0,
        "total_suppliers": 0,
        "downloaded_pdfs": 0,
        "failed_pdfs": 0
    }
    
    # 1. Récupérer toutes les factures fournisseurs
    if start_date and end_date:
        logger.info(f"Récupération des factures du {start_date} au {end_date}")
        invoices = self.get_supplier_invoices_by_date_range(start_date, end_date, limit)
    else:
        logger.info("Récupération de toutes les factures fournisseurs")
        invoices = self.get_all_supplier_invoices(limit)
    
    results["total_invoices"] = len(invoices)
    results["invoices"] = invoices
    
    # 2. Récupérer tous les fournisseurs
    suppliers = self.get_suppliers(limit)
    results["total_suppliers"] = len(suppliers)
    results["suppliers"] = suppliers
    
    # 3. Télécharger les PDFs si demandé
    if download_pdfs and invoices:
        logger.info(f"Téléchargement des PDFs pour {len(invoices)} factures")
        
        invoice_ids = [invoice.get("id") for invoice in invoices if invoice.get("id")]
        pdf_results = self.batch_download_invoices(invoice_ids)
        
        results["downloaded_pdfs"] = len(pdf_results)
        results["failed_pdfs"] = len(invoice_ids) - len(pdf_results)
        results["pdf_paths"] = pdf_results
    
    # Calculer le temps d'exécution
    execution_time = time.time() - start_time
    results["execution_time"] = execution_time
    
    logger.info(f"✅ Synchronisation terminée en {execution_time:.2f} secondes")
    logger.info(f"📊 Résultats: {results['total_invoices']} factures, {results['total_suppliers']} fournisseurs")
    
    if download_pdfs:
        logger.info(f"📄 PDFs: {results['downloaded_pdfs']} téléchargés, {results['failed_pdfs']} échecs")
    
    return results

def __repr__(self):
    """Représentation de la classe pour le debugging"""
    return f"SellsySupplierAPI(url={self.api_url})"

def __str__(self):
    """Représentation sous forme de chaîne"""
    return f"API Sellsy pour les factures fournisseurs"


# Exemple d'utilisation si ce fichier est exécuté directement
if __name__ == "__main__":
    try:
        # Créer l'instance de l'API
        api = SellsySupplierAPI()
        
        # Tester la connexion
        if api.test_connection():
            print("Connexion à l'API Sellsy établie avec succès!")
            
            # Exemple: explorer les méthodes API disponibles
            # api.explore_api_methods()
            
            # Exemple: récupérer toutes les factures fournisseurs
            invoices = api.get_all_supplier_invoices(limit=10)
            print(f"Nombre de factures récupérées: {len(invoices)}")
            
            if invoices:
                # Afficher les détails de la première facture
                first_invoice = invoices[0]
                print(f"Détails de la facture {first_invoice.get('id', 'N/A')}:")
                print(json.dumps(first_invoice, indent=2, ensure_ascii=False))
                
                # Télécharger le PDF de la première facture
                invoice_id = first_invoice.get('id')
                if invoice_id:
                    pdf_path = api.download_supplier_invoice_pdf(invoice_id)
                    if pdf_path:
                        print(f"PDF téléchargé: {pdf_path}")
        else:
            print("Échec de la connexion à l'API Sellsy")
    
    except Exception as e:
        print(f"Erreur: {e}")
