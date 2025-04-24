from pyairtable import Table
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_SUPPLIER_TABLE_NAME
import datetime
import os
import base64
import logging
import re
from typing import Dict, Optional, Any, List, Union

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airtable_api")

class AirtableSupplierAPI:
    def __init__(self):
        """Initialisation de la connexion à Airtable"""
        try:
            self.table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_SUPPLIER_TABLE_NAME)
            logger.info(f"Connexion établie à la table Airtable: {AIRTABLE_SUPPLIER_TABLE_NAME}")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de la connexion Airtable: {e}")
            raise

    def format_supplier_invoice_for_airtable(self, invoice: Dict) -> Optional[Dict]:
        """
        Convertit une facture fournisseur Sellsy au format Airtable
        
        Args:
            invoice: Dictionnaire contenant les données de la facture fournisseur
            
        Returns:
            Dictionnaire formaté pour Airtable ou None en cas d'erreur
        """
        # Vérifications de sécurité
        if not invoice:
            logger.warning("Données de facture fournisseur invalides ou vides")
            return None
            
        logger.debug(f"Structure de la facture fournisseur - Clés principales: {list(invoice.keys())}")
        
        # --- Récupération des informations fournisseur ---
        supplier_id = None
        supplier_name = ""
        
        # Extraction structurée des informations fournisseur
        if "relation" in invoice and isinstance(invoice["relation"], dict):
            relation = invoice["relation"]
            supplier_id = str(relation.get("id", ""))
            supplier_name = relation.get("name", "")
        elif "related" in invoice and isinstance(invoice["related"], list):
            for related in invoice["related"]:
                if related.get("type") in ["individual", "corporation"]:
                    supplier_id = str(related.get("id", ""))
                    supplier_name = related.get("name", "")
                    break
        
        # Fallback pour le nom du fournisseur
        if not supplier_name:
            supplier_name = invoice.get("company_name", invoice.get("supplier_name", ""))
            if not supplier_name and supplier_id:
                supplier_name = f"Fournisseur #{supplier_id}"
        
        # --- Gestion de la date ---
        created_date = None
        date_fields = ["created_at", "date", "created", "issueDate"]
        
        for field in date_fields:
            if field in invoice and invoice[field]:
                created_date = invoice[field]
                break
        
        # Formatage de la date pour Airtable
        if created_date:
            # Conversion en format standard YYYY-MM-DD
            if isinstance(created_date, str):
                # Si format ISO avec T
                if "T" in created_date:
                    created_date = created_date.split("T")[0]
                # Vérifier et nettoyer le format de date
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', created_date):
                    try:
                        # Tentative de conversion si format non standard
                        date_obj = datetime.datetime.strptime(created_date, "%Y-%m-%d")
                        created_date = date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        # Si échec, utiliser la date actuelle
                        logger.warning(f"Format de date invalide '{created_date}', utilisation de la date actuelle")
                        created_date = datetime.datetime.now().strftime("%Y-%m-%d")
        else:
            # Date par défaut
            created_date = datetime.datetime.now().strftime("%Y-%m-%d")
            logger.warning(f"Date non trouvée pour la facture {invoice.get('id', 'inconnue')}, utilisation de la date actuelle")
        
        # --- Récupération des montants ---
        montant_ht = 0.0
        montant_ttc = 0.0
        
        # Extraction structurée des montants
        if "amounts" in invoice and isinstance(invoice["amounts"], dict):
            amounts = invoice["amounts"]
            # Montant HT
            ht_keys = ["total_excluding_tax", "total_excl_tax", "tax_excl", "total_raw_excl_tax", "totalAmountWithoutTaxes"]
            for key in ht_keys:
                if key in amounts and amounts[key] is not None:
                    montant_ht = self._safe_float_conversion(amounts[key])
                    break
            
            # Montant TTC
            ttc_keys = ["total_including_tax", "total_incl_tax", "tax_incl", "total_incl_tax", "totalAmountWithTaxes"]
            for key in ttc_keys:
                if key in amounts and amounts[key] is not None:
                    montant_ttc = self._safe_float_conversion(amounts[key])
                    break
        
        # Vérification des structures alternatives
        if montant_ht == 0.0:
            # Vérifier d'autres chemins possibles
            if "amount" in invoice and isinstance(invoice["amount"], dict):
                montant_ht = self._safe_float_conversion(invoice["amount"].get("tax_excl", 0))
            elif "total_amount_without_taxes" in invoice:
                montant_ht = self._safe_float_conversion(invoice["total_amount_without_taxes"])
            
        if montant_ttc == 0.0:
            # Vérifier d'autres chemins possibles
            if "amount" in invoice and isinstance(invoice["amount"], dict):
                montant_ttc = self._safe_float_conversion(invoice["amount"].get("tax_incl", 0))
            elif "total_amount_with_taxes" in invoice:
                montant_ttc = self._safe_float_conversion(invoice["total_amount_with_taxes"])
        
        # --- Récupération du numéro de facture ---
        reference = ""
        ref_fields = ["reference", "number", "decimal_number", "invoiceNumber"]
        
        for field in ref_fields:
            if field in invoice and invoice[field]:
                reference = str(invoice[field])
                break
            
        # --- Récupération du statut et autres informations ---
        status = str(invoice.get("status", ""))
        pdf_link = invoice.get("pdf_link", "")
        invoice_id = str(invoice.get("id", ""))
        
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
            "URL": f"https://go.sellsy.com/purchase/{invoice_id}" if invoice_id else ""
        }
        
        # Ajouter le lien direct vers le PDF si disponible
        if pdf_link:
            result["PDF_URL"] = pdf_link
        
        logger.debug(f"Facture {invoice_id} formatée avec succès: HT={montant_ht}, TTC={montant_ttc}")
        return result

    def _safe_float_conversion(self, value: Any) -> float:
        """Conversion sécurisée en float avec gestion d'erreurs"""
        try:
            if value is None:
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Impossible de convertir '{value}' en float, utilisation de 0.0")
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
            
            # Traitement du PDF si disponible
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

def sync_supplier_invoices_to_airtable(sellsy_api_client):
    """
    Synchronise toutes les factures fournisseur depuis Sellsy vers Airtable
    
    Args:
        sellsy_api_client: Instance de l'API Sellsy
    """
    logger.info("Début de la synchronisation des factures fournisseur Sellsy vers Airtable...")

    # Récupération des factures
    invoices = sellsy_api_client.get_all_supplier_invoices()

    if invoices:
        logger.info(f"{len(invoices)} factures fournisseur récupérées depuis Sellsy.")
        airtable_api = AirtableSupplierAPI()

        # Traitement des factures
        for idx, invoice in enumerate(invoices):
            logger.info(f"Traitement de la facture {idx+1}/{len(invoices)}")
            
            # Formatage pour Airtable
            formatted_invoice = airtable_api.format_supplier_invoice_for_airtable(invoice)
            
            if formatted_invoice:
                # Téléchargement du PDF
                pdf_path = None
                if 'id' in invoice:
                    try:
                        pdf_path = sellsy_api_client.download_supplier_invoice_pdf(invoice['id'])
                    except Exception as e:
                        logger.warning(f"Impossible de télécharger le PDF pour la facture {invoice['id']}: {e}")
                
                # Insertion ou mise à jour
                airtable_id = airtable_api.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                if airtable_id:
                    logger.info(f"Facture {invoice['id']} synchronisée avec succès (Airtable ID: {airtable_id})")
                else:
                    logger.warning(f"Problème lors de la synchronisation de la facture {invoice['id']}")
            else:
                logger.warning(f"Formatage échoué pour la facture {invoice.get('id', 'inconnue')}")

        logger.info("Synchronisation terminée.")
    else:
        logger.warning("Aucune facture fournisseur récupérée depuis Sellsy.")
