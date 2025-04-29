import os
import time
import logging
import requests
import base64
import json
import datetime
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
        self.api_v1_url = "https://apifeed.sellsy.com"
        self.token_url = "https://login.sellsy.com/oauth2/access-tokens"
        self.access_token = self.get_access_token()

        if not self.access_token:
            raise ValueError("Impossible d'obtenir un token OAuth2 depuis Sellsy.")

        os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

    def get_access_token(self) -> Optional[str]:
        logger.info("🔐 Récupération du token OAuth2 Sellsy")
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
                return response.json().get("access_token")
            else:
                logger.error(f"Erreur OAuth2 : {response.status_code} {response.text}")
        except requests.RequestException as e:
            logger.error(f"Erreur de requête OAuth2 : {e}")
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
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        payload = {
            "method": method,
            "io_mode": "json",
            "do_in": json.dumps({
                "method": method,
                "params": params
            })
        }

        logger.info(f"Requête API v1 vers {self.api_v1_url} - Méthode: {method}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(self.api_v1_url, headers=headers, data=payload)
            logger.info(f"Code de statut de la réponse: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                logger.debug(f"Réponse réussie: {json.dumps(result, indent=2)[:500]}...")
                return result

            logger.error(f"Erreur API v1 {method}: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Exception API v1: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de décodage JSON: {e}")
            logger.error(f"Contenu de la réponse: {response.text[:500]}...")
        return None

    def get_supplier_invoices(self, limit: int = 100, days: int = 365) -> List[Dict]:
        """
        Récupère les factures fournisseur et assure que chacune contient un ID valide
        """
        logger.info(f"📅 Récupération des factures fournisseur (limite: {limit}, jours: {days}) via API v1...")

        # Étape 1: Récupérer les IDs des factures avec Purchase.getList
        params = {
            "pagination": {
                "nbperpage": min(limit, 100),
                "pagenum": 1
            },
            "order": {
                "direction": "DESC",
                "field": "doc_date"
            },
            "doctype": "invoice"
        }

        # Ajout du filtre de date si spécifié
        if days > 0:
            date_from = int(time.time()) - (days * 86400)
            params["search"] = {
                "doc_date": {
                    "from": date_from
                }
            }

        detailed_invoices = []
        total_pages = 1
        current_page = 1

        while current_page <= total_pages and len(detailed_invoices) < limit:
            params["pagination"]["pagenum"] = current_page
            logger.info(f"Récupération de la page {current_page} de la liste des factures")

            response = self._make_v1_request("Purchase.getList", params)

            if not response or response.get("status") != "success" or "response" not in response:
                logger.error("Erreur lors de la récupération des factures fournisseur")
                break

            data = response["response"]

            if current_page == 1 and "infos" in data and "nbpages" in data["infos"]:
                total_pages = data["infos"]["nbpages"]
                logger.info(f"Total des pages: {total_pages}")

            if "result" in data and isinstance(data["result"], dict):
                logger.info(f"Nombre de factures sur la page {current_page}: {len(data['result'])}")
                
                # Pour chaque ID de facture, récupérer les détails complets immédiatement
                for invoice_id, invoice_summary in data["result"].items():
                    if not invoice_id:
                        logger.warning(f"ID de facture manquant dans les résultats")
                        continue
                    
                    # Vérifions que l'ID est une chaîne valide
                    try:
                        invoice_id_str = str(invoice_id).strip()
                        if not invoice_id_str:
                            logger.warning(f"ID de facture vide après conversion")
                            continue
                            
                        # Complétons les informations de base depuis le résumé
                        if isinstance(invoice_summary, dict):
                            # Assurons-nous que ces champs essentiels sont présents
                            invoice_summary["id"] = invoice_id_str
                            invoice_summary["docid"] = invoice_id_str
                            
                            # Si docnum manque, essayons d'utiliser le champ ident
                            if "docnum" not in invoice_summary and "ident" in invoice_summary:
                                invoice_summary["docnum"] = invoice_summary["ident"]
                                
                            detailed_invoices.append(invoice_summary)
                            logger.info(f"Ajout de la facture {invoice_id_str} aux résultats")
                    except Exception as e:
                        logger.error(f"Erreur lors du traitement de l'ID {invoice_id}: {e}")

            current_page += 1

            if len(detailed_invoices) >= limit:
                detailed_invoices = detailed_invoices[:limit]
                break

        logger.info(f"📋 {len(detailed_invoices)} factures fournisseur récupérées")
        return detailed_invoices

    def get_supplier_invoice_details(self, invoice_id: str, include_custom_fields: bool = True) -> Optional[Dict]:
        """
        Récupère les détails d'une facture fournisseur via Purchase.getOne,
        avec option d'inclusion des champs personnalisés
        
        Args:
            invoice_id: ID de la facture fournisseur
            include_custom_fields: Si True, inclut les champs personnalisés associés à la facture
            
        Returns:
            Dictionnaire contenant les détails de la facture ou None en cas d'erreur
        """
        if not invoice_id:
            logger.error("ID de facture vide, impossible de récupérer les détails")
            return None
            
        logger.info(f"🔍 Récupération des détails de la facture fournisseur {invoice_id}")

        params = {
            "id": invoice_id,
            "includeTags": "N"  # Ne pas inclure les smart-tags pour simplifier
        }

        response = self._make_v1_request("Purchase.getOne", params)
        
        if response and response.get("status") == "success" and "response" in response:
            logger.info(f"Détails récupérés pour la facture {invoice_id}")
            invoice_data = response["response"]
            
            # Ajouter l'ID explicitement pour assurer la cohérence
            if isinstance(invoice_data, dict):
                invoice_data["id"] = invoice_id
                invoice_data["docid"] = invoice_id
                
                # S'assurer que nous avons un numéro de facture
                if "docnum" not in invoice_data and "ident" in invoice_data:
                    invoice_data["docnum"] = invoice_data["ident"]
                
                # Récupérer et intégrer les champs personnalisés si demandé
                if include_custom_fields:
                    custom_fields = self.get_invoice_custom_fields(invoice_id)
                    
                    if custom_fields:
                        invoice_data["customFields"] = custom_fields
                        logger.info(f"Ajout de {len(custom_fields)} champs personnalisés à la facture {invoice_id}")
                    else:
                        invoice_data["customFields"] = {}
                        logger.info(f"Aucun champ personnalisé trouvé pour la facture {invoice_id}")
            
            return invoice_data
        else:
            logger.error(f"Impossible de récupérer les détails de la facture {invoice_id}")
            return None

    def get_invoice_custom_fields(self, invoice_id: str) -> Dict[str, Any]:
        """
        Récupère les champs personnalisés associés à une facture fournisseur
        
        Args:
            invoice_id: ID de la facture
            
        Returns:
            Dictionnaire avec les valeurs des champs personnalisés (clé = ID du champ)
        """
        if not invoice_id:
            logger.error("ID de facture vide, impossible de récupérer les champs personnalisés")
            return {}
            
        logger.info(f"🔍 Récupération des champs personnalisés pour la facture {invoice_id}")
        
        params = {
            "linkedtype": "purchase",  # Type d'entité pour les factures fournisseur
            "linkedid": invoice_id
        }
        
        response = self._make_v1_request("CustomFields.getValues", params)
        
        if response and response.get("status") == "success" and "response" in response:
            custom_fields = response["response"]
            if isinstance(custom_fields, dict) and custom_fields:
                logger.info(f"Champs personnalisés récupérés pour la facture {invoice_id}: {list(custom_fields.keys())}")
                return custom_fields
            else:
                logger.info(f"Aucun champ personnalisé trouvé pour la facture {invoice_id}")
        else:
            logger.error(f"Erreur lors de la récupération des champs personnalisés pour la facture {invoice_id}")
        
        return {}

    def get_custom_field_definitions(self, entity_type: str = "purchase") -> Dict[str, Dict]:
        """
        Récupère les définitions des champs personnalisés pour un type d'entité
        
        Args:
            entity_type: Type d'entité (ex: 'purchase', 'client', 'supplier', etc.)
            
        Returns:
            Dictionnaire des définitions de champs personnalisés (clé = ID du champ)
        """
        logger.info(f"📋 Récupération des définitions de champs personnalisés pour {entity_type}")
        
        # Paramètres pour filtrer les champs selon le type d'entité
        params = {}
        if entity_type:
            field_param = f"useOn_{entity_type}"
            params["search"] = {
                field_param: "Y"
            }
        
        response = self._make_v1_request("CustomFields.getList", params)
        
        if response and response.get("status") == "success" and "response" in response:
            result = response["response"]
            if "result" in result and isinstance(result["result"], dict):
                definitions = {}
                for field_id, field_data in result["result"].items():
                    if isinstance(field_data, dict):
                        # Ajouter l'ID au dictionnaire du champ
                        field_data["id"] = field_id
                        definitions[field_id] = field_data
                
                logger.info(f"📋 {len(definitions)} définitions de champs personnalisés récupérées pour {entity_type}")
                return definitions
        
        logger.error(f"Impossible de récupérer les définitions de champs personnalisés pour {entity_type}")
        return {}

    def get_custom_field_value(self, entity_type: str, entity_id: str, field_id: str) -> Optional[Any]:
        """
        Récupère la valeur d'un champ personnalisé pour une entité spécifique
        
        Args:
            entity_type: Type d'entité (ex: 'purchase', 'client', 'supplier', etc.)
            entity_id: ID de l'entité
            field_id: ID du champ personnalisé
            
        Returns:
            Valeur du champ personnalisé ou None en cas d'erreur
        """
        if not entity_type or not entity_id or not field_id:
            logger.error("Paramètres invalides pour la récupération de la valeur du champ personnalisé")
            return None
            
        logger.info(f"🔍 Récupération de la valeur du champ personnalisé {field_id} pour {entity_type} {entity_id}")
        
        params = {
            "linkedtype": entity_type,
            "linkedid": entity_id,
            "cfid": field_id
        }
        
        response = self._make_v1_request("CustomFields.getValues", params)
        
        if response and response.get("status") == "success" and "response" in response:
            # La structure de la réponse peut varier selon le type de champ
            values = response["response"]
            if values and field_id in values:
                logger.info(f"Valeur récupérée pour le champ {field_id}")
                return values[field_id]
        
        logger.warning(f"Aucune valeur trouvée pour le champ {field_id}")
        return None

    def format_invoice_with_custom_fields(self, invoice: Dict) -> Dict:
        """
        Formate les données d'une facture en incluant les champs personnalisés
        avec leurs noms lisibles
        
        Args:
            invoice: Dictionnaire contenant les données de la facture
            
        Returns:
            Dictionnaire formaté avec les champs personnalisés
        """
        # Vérifier si nous avons déjà les champs personnalisés dans l'objet facture
        if "customFields" not in invoice:
            logger.info(f"Récupération des champs personnalisés pour la facture {invoice.get('id', 'N/A')}")
            invoice["customFields"] = self.get_invoice_custom_fields(invoice.get("id", ""))
        
        # Récupérer les définitions des champs personnalisés pour obtenir les noms
        cf_definitions = self.get_custom_field_definitions("purchase")
        
        formatted_invoice = {
            "ID_Facture_Fournisseur": invoice.get("id", ""),
            "Numéro": invoice.get("docnum", invoice.get("ident", "")),
            "Date": invoice.get("displayedDate", ""),
            "Fournisseur": invoice.get("thirdname", ""),
            "ID_Fournisseur_Sellsy": invoice.get("thirdid", ""),
            "Montant_HT": invoice.get("totalAmountTaxesFree", 0),
            "Montant_TTC": invoice.get("totalAmount", 0),
            "Statut": invoice.get("step", ""),
            "URL": f"https://go.sellsy.com/purchase/{invoice.get('id', '')}"
        }
        
        # Ajouter les champs personnalisés avec leurs noms lisibles
        if invoice.get("customFields"):
            for field_id, field_value in invoice["customFields"].items():
                field_name = field_id
                # Utiliser le nom du champ s'il est disponible dans les définitions
                if field_id in cf_definitions:
                    field_name = cf_definitions[field_id].get("name", field_id)
                    
                formatted_invoice[f"CF_{field_name}"] = field_value
        
        return formatted_invoice

    def search_purchase_invoices(self, limit: int = 100, days: int = 365) -> List[Dict]:
        """
        Méthode pour l'API V2 OCR, avec filtrage par date si nécessaire
        """
        logger.info(f"📅 Recherche des factures d'achat OCR (limite: {limit}, jours: {days})...")
        offset = 0
        invoices = []

        # Créer le filtre de date si nécessaire
        filters = {}
        if days > 0:
            date_from = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            filters["created_at"] = {"$gte": date_from}

        while len(invoices) < limit:
            payload = {
                "filters": filters,
                "limit": min(limit - len(invoices), 100),
                "offset": offset,
                "order": "created_at",
                "direction": "desc"
            }

            data = self._make_post("/ocr/pur-invoice/search", json_data=payload)
            if not data or "data" not in data:
                break

            batch = data["data"]
            
            # Filtrer pour ne garder que les entrées avec ID valide
            valid_batch = [invoice for invoice in batch if invoice.get("id")]
            
            invoices.extend(valid_batch)
            logger.info(f"Lot récupéré: {len(valid_batch)} factures valides sur {len(batch)}")
            
            if len(batch) < 100:
                break
            offset += len(batch)

        logger.info(f"Total des factures OCR récupérées: {len(invoices)}")
        return invoices[:limit]

    def get_invoice_details(self, invoice_id: str) -> Optional[Dict]:
        """
        Méthode pour l'API V2 OCR
        """
        if not invoice_id:
            logger.error("ID de facture OCR vide, impossible de récupérer les détails")
            return None
            
        logger.info(f"🔍 Détails de la facture OCR {invoice_id}")
        details = self._make_get(f"/ocr/pur-invoice/{invoice_id}")
        
        # S'assurer que l'ID est présent dans les détails
        if details:
            details["id"] = invoice_id
        
        return details

    def download_invoice_pdf(self, pdf_url: str, invoice_id: str) -> Optional[str]:
        if not pdf_url:
            logger.warning(f"URL PDF vide pour la facture {invoice_id}")
            return None
            
        if not invoice_id:
            logger.warning("ID de facture manquant pour le téléchargement PDF")
            return None
            
        logger.info(f"⬇️ Téléchargement du PDF pour la facture {invoice_id}")
        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            response = requests.get(pdf_url, headers=headers)
            if response.status_code == 200:
                file_path = os.path.join(PDF_STORAGE_DIR, f"invoice_{invoice_id}.pdf")
                with open(file_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"📄 PDF enregistré: {file_path}")
                return file_path
            else:
                logger.error(f"Erreur téléchargement PDF: {response.status_code}")
        except requests.RequestException as e:
            logger.error(f"Erreur lors du téléchargement du PDF: {e}")
        return None

    def get_supplier_invoice_pdf(self, invoice_id: str) -> Optional[str]:
        if not invoice_id:
            logger.warning("ID de facture manquant pour la récupération du PDF")
            return None
            
        logger.info(f"📄 Récupération du PDF pour la facture fournisseur {invoice_id}")

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
        
    def get_custom_field(self, field_id: str) -> Optional[Dict]:
        """
        Récupère les détails d'un champ personnalisé via CustomFields.getOne
        
        Args:
            field_id: ID du champ personnalisé à récupérer
            
        Returns:
            Dictionnaire contenant les détails du champ personnalisé ou None en cas d'erreur
        """
        if not field_id:
            logger.error("ID de champ personnalisé vide, impossible de récupérer les détails")
            return None
            
        logger.info(f"🔍 Récupération des détails du champ personnalisé {field_id}")

        params = {
            "id": field_id
        }

        response = self._make_v1_request("CustomFields.getOne", params)
        
        if response and response.get("status") == "success" and "response" in response:
            logger.info(f"Détails récupérés pour le champ personnalisé {field_id}")
            return response["response"]  # On retourne directement la partie response pour faciliter l'accès aux données
        else:
            logger.error(f"Impossible de récupérer les détails du champ personnalisé {field_id}")
            return None
            
    def get_all_custom_fields(self, type_filter: str = None) -> List[Dict]:
        """
        Récupère tous les champs personnalisés
        
        Args:
            type_filter: Optionnel - Type de champ personnalisé à filtrer (ex: 'unit', 'text', etc.)
            
        Returns:
            Liste de dictionnaires contenant les détails des champs personnalisés
        """
        logger.info(f"📋 Récupération de tous les champs personnalisés" + 
                   (f" de type {type_filter}" if type_filter else ""))
        
        params = {}
        if type_filter:
            params["search"] = {
                "type": type_filter
            }
            
        response = self._make_v1_request("CustomFields.getList", params)
        
        if response and response.get("status") == "success" and "response" in response:
            result = response["response"]
            if "result" in result and isinstance(result["result"], dict):
                fields_list = []
                for field_id, field_data in result["result"].items():
                    # S'assurer que l'ID est inclus dans les données du champ
                    if isinstance(field_data, dict):
                        field_data["id"] = field_id
                        fields_list.append(field_data)
                    
                logger.info(f"📋 {len(fields_list)} champs personnalisés récupérés")
                return fields_list
                
        logger.error("Impossible de récupérer la liste des champs personnalisés")
        return []

# Exemple d'utilisation:
"""
api = SellsySupplierAPI()

# Récupérer les détails d'une facture avec les champs personnalisés
invoice_details = api.get_supplier_invoice_details("413", include_custom_fields=True)

# Formatter la facture pour un affichage lisible
formatted_invoice = api.format_invoice_with_custom_fields(invoice_details)

print(json.dumps(formatted_invoice, indent=2))
"""
