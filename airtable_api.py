from pyairtable import Table
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_SUPPLIER_TABLE_NAME
import datetime
import os
import base64
import logging
import re
import json
from typing import Dict, Optional, Any, List, Union

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airtable_api")

class AirtableAPI:
    def __init__(self):
        """Initialisation de la connexion à Airtable"""
        try:
            self.table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_SUPPLIER_TABLE_NAME)
            logger.info(f"Connexion établie à la table Airtable: {AIRTABLE_SUPPLIER_TABLE_NAME}")
            
            # Dictionnaire de traduction des statuts (étapes) de l'anglais vers le français
            self.status_translations = {
                "draft": "Brouillon",
                "sent": "Envoyé",
                "accepted": "Accepté",
                "refused": "Refusé",
                "expired": "Expiré",
                "pending": "En attente",
                "completed": "Terminé",
                "canceled": "Annulé",
                "paid": "Payé",
                "partially_paid": "Partiellement payé",
                "validated": "Validé",
                "in_progress": "En cours",
                "processing": "En traitement",
                "delivered": "Livré",
                "archived": "Archivé",
                "new": "Nouveau",
                "received": "Reçu",
                "ordered": "Commandé",
                "due": "A régler",
                "payinprogress": "Paiement partiel",
                "late": "Retard",
                "cancelled": "Annulée"
            }
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de la connexion Airtable: {e}")
            raise

    def format_invoice_for_airtable(self, invoice: Dict) -> Optional[Dict]:
        """
        Convertit une facture d'achat Sellsy au format Airtable
        Gère à la fois le format V1 et le format OCR
        
        Args:
            invoice: Dictionnaire contenant les données de la facture d'achat
            
        Returns:
            Dictionnaire formaté pour Airtable ou None en cas d'erreur
        """
        # Log pour debug
        invoice_id = invoice.get('id', invoice.get('docid', 'ID inconnu'))
        logger.info(f"Traitement facture: {invoice_id}")
        
        # Vérifications de sécurité
        if not invoice:
            logger.warning("Données de facture invalides ou vides")
            return None
            
        logger.info(f"Structure de la facture - Clés principales: {list(invoice.keys())}")
        
        # Détection du format (V1 ou OCR)
        format_v1 = "docid" in invoice or "ident" in invoice
        
        # --- Récupération de l'ID de facture ---
        invoice_id = str(invoice.get("id", ""))
        logger.info(f"ID Facture: {invoice_id} (format détecté: {'V1' if format_v1 else 'OCR/V2'})")
        
        # --- Récupération des informations fournisseur ---
        supplier_id = None
        supplier_name = ""
        
        if format_v1:
            # Format V1
            if "thirdName" in invoice:
                supplier_name = invoice.get("thirdName", "")
                supplier_id = str(invoice.get("thirdid", ""))
                logger.info(f"Fournisseur trouvé via thirdName: {supplier_name} (ID: {supplier_id})")
            elif "thirdname" in invoice:
                supplier_name = invoice.get("thirdname", "")
                supplier_id = str(invoice.get("thirdid", ""))
                logger.info(f"Fournisseur trouvé via thirdname: {supplier_name} (ID: {supplier_id})")
            elif "corp_name" in invoice:
                supplier_name = invoice.get("corp_name", "")
                supplier_id = str(invoice.get("thirdid", ""))
                logger.info(f"Fournisseur trouvé via corp_name: {supplier_name} (ID: {supplier_id})")
        else:
            # Format OCR/V2
            if "related" in invoice and isinstance(invoice["related"], list):
                for related in invoice["related"]:
                    if related.get("type") in ["individual", "corporation"]:
                        supplier_id = str(related.get("id", ""))
                        supplier_name = related.get("name", "")
                        logger.info(f"Fournisseur trouvé via related: {supplier_name} (ID: {supplier_id})")
                        break
            elif "third" in invoice and isinstance(invoice["third"], dict):
                supplier_id = str(invoice["third"].get("id", ""))
                supplier_name = invoice["third"].get("name", "")
                logger.info(f"Fournisseur trouvé via third: {supplier_name} (ID: {supplier_id})")
            elif "supplier" in invoice and isinstance(invoice["supplier"], dict):
                supplier_id = str(invoice["supplier"].get("id", ""))
                supplier_name = invoice["supplier"].get("name", "")
                logger.info(f"Fournisseur trouvé via supplier: {supplier_name} (ID: {supplier_id})")
        
        # Fallback pour le nom du fournisseur
        if not supplier_name and supplier_id:
            supplier_name = f"Fournisseur #{supplier_id}"
            logger.info(f"Utilisation du nom par défaut: {supplier_name}")
        
        # --- Gestion de la date ---
        created_date = None
        date_field_used = None
        
        if format_v1:
            # Format V1
            date_fields = ["doc_date", "created", "displayedDate", "date"]
        else:
            # Format OCR/V2
            date_fields = ["created_at", "date", "issueDate", "documentdate", "displayedDate"]
        
        for field in date_fields:
            if field in invoice and invoice[field]:
                created_date = invoice[field]
                date_field_used = field
                logger.info(f"Date trouvée via {field}: {created_date}")
                break
        
        # Formatage de la date pour Airtable
        if created_date:
            original_date = created_date
            # Conversion en format standard YYYY-MM-DD
            formatted_date = self._format_date(created_date)
            
            if formatted_date:
                created_date = formatted_date
                logger.info(f"Date formatée: {created_date} (origine: {original_date} via {date_field_used})")
            else:
                # Date par défaut en cas d'échec de formatage
                created_date = datetime.datetime.now().strftime("%Y-%m-%d")
                logger.warning(f"Format de date invalide '{original_date}', utilisation de la date actuelle: {created_date}")
        else:
            # Date par défaut
            created_date = datetime.datetime.now().strftime("%Y-%m-%d")
            logger.warning(f"Date non trouvée pour la facture {invoice_id}, utilisation de la date actuelle: {created_date}")
        
        # --- Récupération du numéro de facture ---
        reference = ""
        ref_field_used = None
        
        if format_v1:
            # Format V1
            ref_fields = ["ident", "docnum", "reference", "displayedIdent"]
        else:
            # Format OCR/V2
            ref_fields = ["reference", "number", "ident", "docnum", "document_number", "displayedIdent"] 
        
        # Essayer les champs pour le numéro de facture
        for field in ref_fields:
            if field in invoice and invoice[field]:
                reference = str(invoice[field])
                ref_field_used = field
                logger.info(f"Numéro de facture trouvé via {field}: {reference}")
                break
        
        # Si toujours vide, utiliser l'ID comme fallback
        if not reference and invoice_id:
            reference = f"REF-{invoice_id}"
            ref_field_used = "ID fallback"
            logger.info(f"Utilisation de l'ID comme référence par défaut: {reference}")
        
        logger.info(f"Numéro final retenu: {reference} (source: {ref_field_used})")
        
        # --- Récupération des montants ---
        montant_ht = 0.0
        montant_ttc = 0.0
        ht_source = None
        ttc_source = None
        
        if format_v1:
            # Format V1
            if "totalAmountTaxesFree" in invoice:
                montant_ht = self._safe_float_conversion(invoice["totalAmountTaxesFree"])
                ht_source = "totalAmountTaxesFree"
                logger.info(f"Montant HT trouvé via totalAmountTaxesFree: {montant_ht}")
            elif "totalHT" in invoice:
                montant_ht = self._safe_float_conversion(invoice["totalHT"])
                ht_source = "totalHT"
                logger.info(f"Montant HT trouvé via totalHT: {montant_ht}")
                
            if "totalAmount" in invoice:
                montant_ttc = self._safe_float_conversion(invoice["totalAmount"])
                ttc_source = "totalAmount"
                logger.info(f"Montant TTC trouvé via totalAmount: {montant_ttc}")
            elif "totalTTC" in invoice:
                montant_ttc = self._safe_float_conversion(invoice["totalTTC"])
                ttc_source = "totalTTC"
                logger.info(f"Montant TTC trouvé via totalTTC: {montant_ttc}")
                
            # Alternative: amounts
            if montant_ht == 0.0 and "amount_base" in invoice:
                montant_ht = self._safe_float_conversion(invoice["amount_base"])
                ht_source = "amount_base"
                logger.info(f"Montant HT trouvé via amount_base: {montant_ht}")
                
            if montant_ttc == 0.0 and "amount_total" in invoice:
                montant_ttc = self._safe_float_conversion(invoice["amount_total"])
                ttc_source = "amount_total"
                logger.info(f"Montant TTC trouvé via amount_total: {montant_ttc}")
        else:
            # Format OCR/V2: Méthode 1 - Extraction structurée des montants depuis "amounts"
            if "amounts" in invoice and isinstance(invoice["amounts"], dict):
                amounts = invoice["amounts"]
                
                # Montant HT
                ht_keys = ["totalAmountWithoutVat", "total_excluding_tax", "baseHT", "totalHT", "preTax"]
                for key in ht_keys:
                    if key in amounts and amounts[key] is not None:
                        montant_ht = self._safe_float_conversion(amounts[key])
                        ht_source = f"amounts.{key}"
                        logger.info(f"Montant HT trouvé via amounts.{key}: {montant_ht}")
                        break
                
                # Montant TTC
                ttc_keys = ["total_including_tax", "totalAmountWithTaxes", "totalTTC", "total"]
                for key in ttc_keys:
                    if key in amounts and amounts[key] is not None:
                        montant_ttc = self._safe_float_conversion(amounts[key])
                        ttc_source = f"amounts.{key}"
                        logger.info(f"Montant TTC trouvé via amounts.{key}: {montant_ttc}")
                        break
            
            # Format OCR/V2: Méthode 2 - Champs directs en racine
            direct_ht_fields = ["total_amount_without_taxes", "totalHT", "preTaxAmount", "baseHT"]
            direct_ttc_fields = ["total_amount_with_taxes", "totalTTC", "totalAmount", "finalAmount"]
            
            if montant_ht == 0.0:
                for field in direct_ht_fields:
                    if field in invoice and invoice[field] is not None:
                        montant_ht = self._safe_float_conversion(invoice[field])
                        ht_source = field
                        logger.info(f"Montant HT trouvé via champ direct {field}: {montant_ht}")
                        break
                        
            if montant_ttc == 0.0:
                for field in direct_ttc_fields:
                    if field in invoice and invoice[field] is not None:
                        montant_ttc = self._safe_float_conversion(invoice[field])
                        ttc_source = field
                        logger.info(f"Montant TTC trouvé via champ direct {field}: {montant_ttc}")
                        break
        
        # Méthode commune: Calcul à partir des lignes d'achat
        if (montant_ht == 0.0 or montant_ttc == 0.0) and "rows" in invoice and isinstance(invoice["rows"], list):
            logger.info(f"Calcul des montants à partir des lignes ({len(invoice['rows'])} lignes)")
            ht_total = 0.0
            for i, row in enumerate(invoice["rows"]):
                if isinstance(row, dict):
                    row_amount = 0.0
                    # Structure 1: montant unitaire * quantité
                    if "unit_amount" in row and "qty" in row:
                        row_amount = self._safe_float_conversion(row["unit_amount"]) * self._safe_float_conversion(row["qty"])
                    # Structure 2: total direct
                    elif "total" in row:
                        row_amount = self._safe_float_conversion(row["total"])
                    # Structure 3: autre format
                    elif "unitAmount" in row and "quantity" in row:
                        row_amount = self._safe_float_conversion(row["unitAmount"]) * self._safe_float_conversion(row["quantity"])
                    # Structure 4: totalAmount
                    elif "totalAmount" in row:
                        row_amount = self._safe_float_conversion(row["totalAmount"])
                    
                    ht_total += row_amount
            
            if montant_ht == 0.0 and ht_total > 0:
                montant_ht = ht_total
                ht_source = "somme des lignes"
                logger.info(f"Montant HT calculé à partir des lignes: {montant_ht}")
        
        # Si on a uniquement le HT, calculer le TTC avec le taux standard
        if montant_ht > 0 and montant_ttc == 0.0:
            default_tax_rate = 20.0  # Taux de TVA standard
            
            # Chercher un taux de TVA explicite
            for field in ["tax_rate", "taxRate", "vatRate", "vat_rate"]:
                if field in invoice and invoice[field] is not None:
                    default_tax_rate = self._safe_float_conversion(invoice[field])
                    logger.info(f"Taux TVA trouvé via {field}: {default_tax_rate}%")
                    break
            
            montant_ttc = montant_ht * (1 + (default_tax_rate / 100))
            ttc_source = f"calculé avec TVA {default_tax_rate}%"
            logger.info(f"Montant TTC calculé à partir du HT avec TVA {default_tax_rate}%: {montant_ttc}")
        
        # Si on a uniquement le TTC, déduire le HT
        if montant_ttc > 0 and montant_ht == 0.0:
            default_tax_rate = 20.0  # Taux de TVA standard
            
            for field in ["tax_rate", "taxRate", "vatRate", "vat_rate"]:
                if field in invoice and invoice[field] is not None:
                    default_tax_rate = self._safe_float_conversion(invoice[field])
                    logger.info(f"Taux TVA trouvé via {field}: {default_tax_rate}%")
                    break
            
            montant_ht = montant_ttc / (1 + (default_tax_rate / 100))
            ht_source = f"déduit du TTC avec TVA {default_tax_rate}%"
            logger.info(f"Montant HT déduit du TTC avec TVA {default_tax_rate}%: {montant_ht}")
        
        # Arrondir les montants à 2 décimales
        montant_ht = round(montant_ht, 2)
        montant_ttc = round(montant_ttc, 2)
        
        logger.info(f"Montants finaux: HT={montant_ht} ({ht_source}), TTC={montant_ttc} ({ttc_source})")
        
        # --- Récupération du statut ---
        status = ""
        status_field_used = None
        
        # Priorité au champ "step" de Sellsy
        if "step" in invoice and invoice["step"]:
            status = str(invoice["step"])
            status_field_used = "step"
            logger.info(f"Statut trouvé via step: {status}")
            
            # Traduction du statut en français si disponible
            if status.lower() in self.status_translations:
                original_status = status
                status = self.status_translations[status.lower()]
                logger.info(f"Statut traduit: '{original_status}' -> '{status}'")
        else:
            # Fallback sur les autres champs si "step" n'existe pas
            if format_v1:
                # Format V1
                status_fields = ["step_hex", "doc_status", "status"]
            else:
                # Format OCR/V2
                status_fields = ["status", "doc_status", "state", "documentStatus"]
            
            for field in status_fields:
                if field in invoice and invoice[field]:
                    status = str(invoice[field])
                    status_field_used = field
                    logger.info(f"Statut trouvé via {field}: {status}")
                    
                    # Vérifier si le statut doit être traduit
                    if status.lower() in self.status_translations:
                        original_status = status
                        status = self.status_translations[status.lower()]
                        logger.info(f"Statut traduit: '{original_status}' -> '{status}'")
                    
                    break
        
        # Si statut toujours vide, définir un statut par défaut
        if not status:
            status = "Non spécifié"
            logger.warning(f"Statut non trouvé, utilisation par défaut: {status}")
        else:
            logger.info(f"Statut final: {status} (origine: {status_field_used})")
        
        # --- Récupération du lien PDF ---
        pdf_url = ""
        pdf_url_field = None
        pdf_fields = ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf"]
        
        for field in pdf_fields:
            if field in invoice and invoice[field]:
                pdf_url = invoice[field]
                pdf_url_field = field
                logger.info(f"URL PDF trouvée via {field}: {pdf_url}")
                break
            
        # Construction de l'URL web Sellsy avec l'ID
        web_url = ""
        if invoice_id:
            web_url = f"https://go.sellsy.com/purchase/{invoice_id}"
            logger.info(f"URL Sellsy construite: {web_url}")
        
        # --- NOUVEAU: Récupération des champs personnalisés ---
        numero_de_facture_custom = ""
        client_abonne_id = ""
        client_abonne_name = ""

        # Ajouter ce code pour mieux comprendre la structure des champs personnalisés
        if "customfields" in invoice:
    logger.info(f"Structure des champs personnalisés (customfields): {json.dumps(invoice['customfields'], indent=2)}")
        elif "custom_fields" in invoice:
    logger.info(f"Structure des champs personnalisés (custom_fields): {json.dumps(invoice['custom_fields'], indent=2)}")
        else:
    logger.info("Aucun champ personnalisé trouvé dans la facture")
        # Extraction des champs personnalisés
        if "customfields" in invoice and isinstance(invoice["customfields"], dict):
            logger.info("Traitement des champs personnalisés")
            
            # Parcourir les champs personnalisés
            for custom_field_id, custom_field_data in invoice["customfields"].items():
                # Recherche du champ "numero-de-facture"
                if isinstance(custom_field_data, dict):
                    if custom_field_data.get("code") == "numero-de-facture" and "value" in custom_field_data:
                        numero_de_facture_custom = str(custom_field_data["value"])
                        logger.info(f"Champ personnalisé 'numero-de-facture' trouvé: {numero_de_facture_custom}")
                    
                    # Recherche du champ "client-abonne"
                    elif custom_field_data.get("code") == "client-abonne" and "value" in custom_field_data:
                        # La valeur peut être une chaîne ou un dictionnaire selon le format
                        if isinstance(custom_field_data["value"], dict):
                            client_abonne_id = str(custom_field_data["value"].get("id", ""))
                            client_abonne_name = custom_field_data["value"].get("name", "")
                        elif isinstance(custom_field_data["value"], str) and custom_field_data["value"].isdigit():
                            client_abonne_id = custom_field_data["value"]
                        logger.info(f"Champ personnalisé 'client-abonne' trouvé: ID={client_abonne_id}, Nom={client_abonne_name}")
        
        # Format alternatif pour les champs personnalisés (format OCR/V2)
        if not numero_de_facture_custom or not client_abonne_id:
            if "custom_fields" in invoice and isinstance(invoice["custom_fields"], list):
                for custom_field in invoice["custom_fields"]:
                    if isinstance(custom_field, dict):
                        # Recherche du champ "numero-de-facture"
                        if custom_field.get("code") == "numero-de-facture" and "value" in custom_field:
                            numero_de_facture_custom = str(custom_field["value"])
                            logger.info(f"Champ personnalisé 'numero-de-facture' trouvé (format alternatif): {numero_de_facture_custom}")
                        
                        # Recherche du champ "client-abonne"
                        elif custom_field.get("code") == "client-abonne" and "value" in custom_field:
                            if isinstance(custom_field["value"], dict):
                                client_abonne_id = str(custom_field["value"].get("id", ""))
                                client_abonne_name = custom_field["value"].get("name", "")
                            elif isinstance(custom_field["value"], str) and custom_field["value"].isdigit():
                                client_abonne_id = custom_field["value"]
                            logger.info(f"Champ personnalisé 'client-abonne' trouvé (format alternatif): ID={client_abonne_id}, Nom={client_abonne_name}")

        # Essayer de trouver le client abonné dans d'autres structures pour le format V1
        if not client_abonne_id and format_v1:
            if "related" in invoice and isinstance(invoice["related"], dict):
                for rel_type, rel_data in invoice["related"].items():
                    if rel_type.lower() in ["client", "customer", "consumer"] and isinstance(rel_data, dict):
                        client_abonne_id = str(rel_data.get("id", ""))
                        client_abonne_name = rel_data.get("name", rel_data.get("displayName", ""))
                        logger.info(f"Client abonné trouvé via related.{rel_type}: ID={client_abonne_id}, Nom={client_abonne_name}")
                        break
        
        # Construction du résultat final
        result = {
            "ID_Facture_Fournisseur": invoice_id,
            "Numéro": reference,
            "Date": created_date,
            "Fournisseur": supplier_name,
            "ID_Fournisseur_Sellsy": supplier_id,
            "Montant_HT": montant_ht,
            "Montant_TTC": montant_ttc,
            "Statut": status,
            "URL": web_url
        }
        
        # Ajouter le lien direct vers le PDF si disponible
        if pdf_url:
            result["PDF_URL"] = pdf_url
            logger.info(f"PDF_URL ajouté: {pdf_url} (source: {pdf_url_field})")
        
        # Ajouter le numéro de facture personnalisé s'il est disponible
        if numero_de_facture_custom:
            result["Numéro_Facture_Personnalisé"] = numero_de_facture_custom
            logger.info(f"Numéro de facture personnalisé ajouté: {numero_de_facture_custom}")
        
        # Ajouter l'ID du client abonné s'il est disponible
        if client_abonne_id:
            result["ID_Client_Abonne"] = client_abonne_id
            logger.info(f"ID client abonné ajouté: {client_abonne_id}")
            
            # Ajouter le nom du client abonné s'il est disponible
            if client_abonne_name:
                result["Nom_Client_Abonne"] = client_abonne_name
                logger.info(f"Nom client abonné ajouté: {client_abonne_name}")
        
        logger.info(f"Facture {invoice_id} formatée avec succès")
        logger.info(f"Résultat formaté: {json.dumps(result, indent=2)}")
        return result

    def _format_date(self, date_str: str) -> Optional[str]:
        """
        Formate une chaîne de date en format YYYY-MM-DD
        
        Args:
            date_str: La chaîne de date à formater
            
        Returns:
            Chaîne au format YYYY-MM-DD ou None en cas d'échec
        """
        if not date_str:
            return None
            
        # Si déjà au bon format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
            
        # Liste des formats à essayer
        date_formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%m/%d/%Y",
            "%m/%d/%Y %H:%M:%S",
            "%d-%m-%Y",
            "%d-%m-%Y %H:%M:%S",
            "%m-%d-%Y",
            "%m-%d-%Y %H:%M:%S"
        ]
        
        # Tentative de conversion avec chaque format
        for fmt in date_formats:
            try:
                date_obj = datetime.datetime.strptime(date_str, fmt)
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                continue
                
        # Si on arrive ici, aucun format n'a fonctionné
        return None

    def _safe_float_conversion(self, value: Any) -> float:
        """Conversion sécurisée en float avec gestion d'erreurs"""
        try:
            if value is None:
                return 0.0
            if isinstance(value, str):
                clean_value = re.sub(r'[^\d.,]', '', value)
                # Gestion des séparateurs décimaux français et internationaux
                clean_value = clean_value.replace(',', '.')
                # S'il y a plusieurs points, ne garder que le dernier
                if clean_value.count('.') > 1:
                    parts = clean_value.split('.')
                    clean_value = ''.join(parts[:-1]) + '.' + parts[-1]
                if not clean_value:
                    logger.warning(f"Conversion en float - chaîne nettoyée vide: '{value}' -> ''")
                    return 0.0
                return float(clean_value)
            return float(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Impossible de convertir '{value}' en float: {e}")
            return 0.0

    def find_supplier_invoice_by_id(self, sellsy_id: str) -> Optional[Dict]:
        """
        Recherche une facture fournisseur dans Airtable par son ID Sellsy
        
        Args:
            sellsy_id: ID de la facture fournisseur dans Sellsy
            
        Returns:
            Record Airtable ou None si non trouvé
        """
        if not sellsy_id:
            logger.warning("ID Sellsy vide, impossible de rechercher la facture fournisseur")
            return None
            
        # Sécurité : conversion en chaîne et échappement des apostrophes
        sellsy_id = str(sellsy_id).replace("'", "''")
        formula = f"{{ID_Facture_Fournisseur}}='{sellsy_id}'"
        logger.info(f"Recherche dans Airtable avec formule : {formula}")
        
        try:
            records = self.table.all(formula=formula)
            logger.info(f"Résultat de recherche : {len(records)} enregistrement(s) trouvé(s).")
            return records[0] if records else None
        except Exception as e:
            logger.error(f"Erreur lors de la recherche de la facture {sellsy_id} : {e}")
            return None

    def encode_file_to_base64(self, file_path: str) -> Optional[str]:
        """
        Encode un fichier en base64 pour Airtable
        
        Args:
            file_path: Chemin du fichier à encoder
            
        Returns:
            Chaîne base64 ou None en cas d'erreur
        """
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"Fichier introuvable: {file_path}")
            return None
        
        # Vérifier que le fichier n'est pas vide
        if os.path.getsize(file_path) == 0:
            logger.warning(f"Fichier vide: {file_path}")
            return None
        
        try:
            with open(file_path, 'rb') as file:
                # Vérification du contenu du fichier (premiers octets d'un PDF: %PDF)
                first_bytes = file.read(4)
                file.seek(0)  # Revenir au début du fichier
                
                if first_bytes != b'%PDF':
                    logger.warning(f"Le fichier {file_path} ne semble pas être un PDF valide")
                
                encoded_string = base64.b64encode(file.read()).decode('utf-8')
                logger.debug(f"Fichier {file_path} encodé avec succès ({len(encoded_string)} caractères)")
                return encoded_string
        except Exception as e:
            logger.error(f"Erreur lors de l'encodage du fichier {file_path}: {e}")
            return None

    def insert_or_update_supplier_invoice(self, invoice_data: Dict, pdf_path: Optional[str] = None) -> Optional[str]:
        """
        Insère ou met à jour une facture fournisseur dans Airtable avec son PDF si disponible
        
        Args:
            invoice_data: Données de la facture formatées pour Airtable
            pdf_path: Chemin vers le fichier PDF (optionnel)
            
        Returns:
            ID de l'enregistrement Airtable ou None en cas d'erreur
        """
        if not invoice_data:
            logger.error("Données de facture fournisseur invalides, impossible d'insérer/mettre à jour")
            return None
            
        sellsy_id = str(invoice_data.get("ID_Facture_Fournisseur", ""))
        if not sellsy_id:
            logger.error("ID Sellsy manquant dans les données, impossible d'insérer/mettre à jour")
            return None
        
        try:
            # Préparation des données
            airtable_data = invoice_data.copy()
            
            # Traitement du PDF via chemin local si disponible
            if pdf_path and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                logger.info(f"Ajout du PDF pour la facture {sellsy_id}: {pdf_path}")

                pdf_base64 = self.encode_file_to_base64(pdf_path)
                if pdf_base64:
                    airtable_data["PDF"] = [
                        {
                            "url": f"data:application/pdf;base64,{pdf_base64}",
                            "filename": os.path.basename(pdf_path)
                        }
                    ]
                else:
                    logger.warning(f"Impossible d'encoder le PDF pour la facture {sellsy_id}")
            
            # Téléchargement et intégration du PDF depuis l'URL si disponible
            elif "PDF_URL" in airtable_data and airtable_data["PDF_URL"]:
                pdf_url = airtable_data["PDF_URL"]
                logger.info(f"URL du PDF disponible pour la facture {sellsy_id}: {pdf_url}")
                
                # Si nous avons seulement l'URL du PDF, la conserver pour affichage
                # Airtable utilisera cette URL pour afficher un lien vers le PDF
                airtable_data["Lien_PDF"] = pdf_url
                logger.info(f"Lien PDF ajouté pour la facture {sellsy_id}")

            # Recherche d'un enregistrement existant
            existing_record = self.find_supplier_invoice_by_id(sellsy_id)

            if existing_record:
                record_id = existing_record["id"]
                logger.info(f"Facture fournisseur {sellsy_id} déjà présente, mise à jour en cours...")
                self.table.update(record_id, airtable_data)
                logger.info(f"Facture fournisseur {sellsy_id} mise à jour avec succès.")
                return record_id
            else:
                logger.info(f"Facture fournisseur {sellsy_id} non trouvée, insertion en cours...")
                record = self.table.create(airtable_data)
                logger.info(f"Facture fournisseur {sellsy_id} ajoutée avec succès (ID: {record['id']}).")
                return record['id']
        except Exception as e:
            logger.error(f"Erreur lors de l'insertion/mise à jour de la facture {sellsy_id}: {e}")
            logger.debug(f"Clés dans les données: {list(invoice_data.keys()) if invoice_data else 'N/A'}")
            return None

    def format_supplier_invoice_for_airtable(self, invoice: Dict) -> Optional[Dict]:
        """
        Alias pour maintenir la compatibilité avec l'ancien code
        """
        return self.format_invoice_for_airtable(invoice)
    
    def download_pdf_from_url(self, url: str, output_path: str) -> bool:
        """
        Télécharge un PDF depuis une URL
        
        Args:
            url: URL du PDF à télécharger
            output_path: Chemin où sauvegarder le PDF
            
        Returns:
            True si le téléchargement a réussi, False sinon
        """
        try:
            import requests
            
            # Vérification de l'URL
            if not url or not url.startswith(('http://', 'https://')):
                logger.warning(f"URL invalide pour le téléchargement du PDF: {url}")
                return False
            
            # Création du répertoire parent si besoin
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Téléchargement avec timeout
            logger.info(f"Téléchargement du PDF depuis {url}")
            response = requests.get(url, timeout=30, stream=True)
            
            # Vérification de la réponse HTTP
            if response.status_code != 200:
                logger.warning(f"Échec du téléchargement du PDF: statut HTTP {response.status_code}")
                return False
            
            # Vérification du type de contenu
            content_type = response.headers.get('Content-Type', '')
            if 'application/pdf' not in content_type and not url.lower().endswith('.pdf'):
                logger.warning(f"Le contenu téléchargé n'est pas un PDF: {content_type}")
                # On continue quand même, car parfois le type MIME peut être incorrect
            
            # Sauvegarde du fichier
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Vérification du fichier téléchargé
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"PDF téléchargé avec succès: {output_path} ({os.path.getsize(output_path)} octets)")
                return True
            else:
                logger.warning(f"Le PDF téléchargé est vide ou n'existe pas: {output_path}")
                return False
            
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement du PDF depuis {url}: {e}")
            return False
    
    def process_invoice_with_pdf(self, invoice: Dict, pdf_url: Optional[str] = None, pdf_path: Optional[str] = None) -> Optional[str]:
        """
        Traite une facture et son PDF, que ce soit par URL ou par chemin local
        
        Args:
            invoice: Données de la facture Sellsy
            pdf_url: URL du PDF de la facture (optionnel)
            pdf_path: Chemin local vers le PDF de la facture (optionnel)
            
        Returns:
            ID de l'enregistrement Airtable ou None en cas d'échec
        """
        # Formatage de la facture pour Airtable
        formatted_invoice = self.format_invoice_for_airtable(invoice)
        if not formatted_invoice:
            logger.error("Échec du formatage de la facture pour Airtable")
            return None
        
        # Récupération de l'ID de la facture
        invoice_id = formatted_invoice.get("ID_Facture_Fournisseur", "")
        
        # Si un PDF_URL est spécifié dans l'appel de fonction, l'utiliser en priorité
        if pdf_url:
            formatted_invoice["PDF_URL"] = pdf_url
            logger.info(f"URL PDF externe fournie pour la facture {invoice_id}: {pdf_url}")
        
        # Si on a une URL PDF dans la facture et pas de chemin local, essayer de télécharger le PDF
        if "PDF_URL" in formatted_invoice and formatted_invoice["PDF_URL"] and not pdf_path:
            # Création d'un répertoire temporaire pour les PDFs si besoin
            temp_pdf_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp_pdfs")
            os.makedirs(temp_pdf_dir, exist_ok=True)
            
            # Téléchargement du PDF
            temp_pdf_path = os.path.join(temp_pdf_dir, f"facture_{invoice_id}.pdf")
            download_success = self.download_pdf_from_url(formatted_invoice["PDF_URL"], temp_pdf_path)
            
            if download_success:
                pdf_path = temp_pdf_path
                logger.info(f"PDF téléchargé avec succès pour la facture {invoice_id}: {pdf_path}")
        
        # Insertion ou mise à jour dans Airtable
        return self.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
