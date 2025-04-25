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
        logger.info(f"Traitement facture: {invoice.get('id', invoice.get('docid', 'ID inconnu'))}")
        try:
            # Afficher les clés principales pour debug
            logger.debug(f"Structure complète reçue: {json.dumps(invoice, indent=2)}")
        except:
            logger.debug("Impossible de sérialiser la structure complète en JSON")
            
        # Vérifications de sécurité
        if not invoice:
            logger.warning("Données de facture invalides ou vides")
            return None
            
        logger.info(f"Structure de la facture - Clés principales: {list(invoice.keys())}")
        
        # Détection du format (V1 ou OCR)
        format_v1 = "docid" in invoice or "ident" in invoice
        
        # --- Récupération de l'ID de facture ---
        invoice_id = None
        if format_v1:
            invoice_id = str(invoice.get("id", ""))
        else:
            invoice_id = str(invoice.get("id", ""))
            
        logger.info(f"ID Facture: {invoice_id} (format détecté: {'V1' if format_v1 else 'OCR/V2'})")
        
        # --- Récupération des informations fournisseur ---
        supplier_id = None
        supplier_name = ""
        
        if format_v1:
            # Format V1 - Amélioration de la recherche du fournisseur
            if "thirdname" in invoice and invoice["thirdname"]:
                supplier_name = invoice.get("thirdname", "")
                supplier_id = str(invoice.get("thirdid", ""))
                logger.info(f"Fournisseur trouvé via thirdname: {supplier_name} (ID: {supplier_id})")
            elif "corp_name" in invoice and invoice["corp_name"]:
                supplier_name = invoice.get("corp_name", "")
                supplier_id = str(invoice.get("thirdid", ""))
                logger.info(f"Fournisseur trouvé via corp_name: {supplier_name} (ID: {supplier_id})")
            elif "thirdid" in invoice and invoice["thirdid"]:
                # Recherche plus poussée via thirdid si disponible
                supplier_id = str(invoice.get("thirdid", ""))
                # Chercher le nom dans d'autres champs possibles
                for field in ["thirdident", "subject", "third", "thirddisplayedname"]:
                    if field in invoice and invoice[field]:
                        supplier_name = str(invoice[field])
                        logger.info(f"Fournisseur trouvé via {field}: {supplier_name} (ID: {supplier_id})")
                        break
                if not supplier_name and supplier_id:
                    supplier_name = f"Fournisseur #{supplier_id}"
                    logger.info(f"Utilisation de l'ID comme nom: {supplier_name}")
            # Recherche de données dans les structures imbriquées
            elif "third" in invoice and isinstance(invoice["third"], dict):
                if "name" in invoice["third"]:
                    supplier_name = invoice["third"]["name"]
                    supplier_id = str(invoice["third"].get("id", ""))
                    logger.info(f"Fournisseur trouvé via third.name: {supplier_name} (ID: {supplier_id})")
        else:
            # Format OCR/V2
            if "related" in invoice and isinstance(invoice["related"], list):
                for related in invoice["related"]:
                    if related.get("type") in ["individual", "corporation", "supplier", "third"]:
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
        
        # Recherche étendue du fournisseur si toujours vide
        if not supplier_name:
            logger.info("Recherche étendue du fournisseur...")
            for field in ["thirdname", "corporation", "corp_name", "corpname", "supplier_name", "supplierName"]:
                if field in invoice and invoice[field]:
                    supplier_name = str(invoice[field])
                    logger.info(f"Fournisseur trouvé via recherche étendue ({field}): {supplier_name}")
                    break
            
            # Recherche dans les sous-objets
            if not supplier_name:
                for obj_name in ["supplier", "third", "corporation", "contact"]:
                    if obj_name in invoice and isinstance(invoice[obj_name], dict):
                        for name_field in ["name", "fullname", "displayName", "title"]:
                            if name_field in invoice[obj_name] and invoice[obj_name][name_field]:
                                supplier_name = str(invoice[obj_name][name_field])
                                if "id" in invoice[obj_name] and not supplier_id:
                                    supplier_id = str(invoice[obj_name]["id"])
                                logger.info(f"Fournisseur trouvé dans {obj_name}.{name_field}: {supplier_name}")
                                break
        
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
            if isinstance(created_date, str):
                # Si c'est une date avec heure (format datetime)
                if " " in created_date:
                    created_date = created_date.split(" ")[0]
                # Si format ISO avec T
                elif "T" in created_date:
                    created_date = created_date.split("T")[0]
                # Format timestamp avec /
                elif "/" in created_date:
                    parts = created_date.split("/")
                    if len(parts) == 3:
                        # Format français JJ/MM/AAAA
                        if len(parts[2]) == 4:  # année en 4 chiffres
                            created_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                        # Format MM/JJ/AAAA
                        else:
                            created_date = f"{parts[2]}-{parts[0]}-{parts[1]}"
                
                # Vérifier et nettoyer le format de date
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', created_date):
                    try:
                        # Tentative de conversion - pour le format "YYYY-MM-DD HH:MM:SS"
                        if " " in original_date:
                            date_obj = datetime.datetime.strptime(original_date, "%Y-%m-%d %H:%M:%S")
                            created_date = date_obj.strftime("%Y-%m-%d")
                        else:
                            # Autres formats de date possibles
                            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]:
                                try:
                                    date_obj = datetime.datetime.strptime(original_date, fmt)
                                    created_date = date_obj.strftime("%Y-%m-%d")
                                    break
                                except ValueError:
                                    continue
                    except ValueError:
                        # En cas d'échec, utiliser la date actuelle
                        logger.warning(f"Format de date invalide '{created_date}', utilisation de la date actuelle")
                        created_date = datetime.datetime.now().strftime("%Y-%m-%d")
            logger.info(f"Date formatée: {created_date} (origine: {original_date} via {date_field_used})")
        else:
            # Date par défaut
            created_date = datetime.datetime.now().strftime("%Y-%m-%d")
            logger.warning(f"Date non trouvée pour la facture {invoice_id}, utilisation de la date actuelle")
        
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
        
        # --- FORMAT V1: Récupération améliorée des montants HT et TTC ---
        if format_v1:
            # Vérification des champs directs simples
            direct_ht_fields = ["totalAmountTaxesFree", "rowsAmountAllInc", "rowsAmount", "totalHT", "amount_base"]
            direct_ttc_fields = ["totalAmount", "total", "totalTTC", "amount_total"]
            
            # Recherche HT
            for field in direct_ht_fields:
                if field in invoice and invoice[field] is not None:
                    montant_ht = self._safe_float_conversion(invoice[field])
                    ht_source = field
                    logger.info(f"Montant HT trouvé via {field}: {montant_ht}")
                    break
                    
            # Recherche TTC
            for field in direct_ttc_fields:
                if field in invoice and invoice[field] is not None:
                    montant_ttc = self._safe_float_conversion(invoice[field])
                    ttc_source = field
                    logger.info(f"Montant TTC trouvé via {field}: {montant_ttc}")
                    break
        else:
            # --- FORMAT OCR/V2: Récupération améliorée des montants ---
            # Méthode 1 - Recherche dans la structure "amounts"
            if "amounts" in invoice and isinstance(invoice["amounts"], dict):
                amounts = invoice["amounts"]
                logger.info(f"Structure amounts trouvée")
                
                # Montant HT - recherche étendue dans les clés possibles
                ht_keys = ["totalAmountWithoutVat", "total_excluding_tax", "baseHT", "totalHT", "preTax", 
                          "amount_excl_tax", "amount_ht", "net_amount"]
                for key in ht_keys:
                    if key in amounts and amounts[key] is not None:
                        montant_ht = self._safe_float_conversion(amounts[key])
                        ht_source = f"amounts.{key}"
                        logger.info(f"Montant HT trouvé via amounts.{key}: {montant_ht}")
                        break
                
                # Montant TTC - recherche étendue
                ttc_keys = ["total_including_tax", "totalAmountWithTaxes", "totalTTC", "total",
                           "amount_incl_tax", "amount_ttc", "gross_amount"]
                for key in ttc_keys:
                    if key in amounts and amounts[key] is not None:
                        montant_ttc = self._safe_float_conversion(amounts[key])
                        ttc_source = f"amounts.{key}"
                        logger.info(f"Montant TTC trouvé via amounts.{key}: {montant_ttc}")
                        break
            
            # Format OCR/V2: Méthode 2 - Champs directs en racine
            direct_ht_fields = ["total_amount_without_taxes", "totalHT", "preTaxAmount", "baseHT", 
                               "amount_excl_tax", "net_amount", "totalAmountTaxesFree"]
            direct_ttc_fields = ["total_amount_with_taxes", "totalTTC", "totalAmount", "finalAmount", 
                                "amount_incl_tax", "gross_amount", "total"]
            
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
                    logger.debug(f"Analyse ligne {i+1}")
                    
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
                    # Structure 5: prix * quantité
                    elif "price" in row and "quantity" in row:
                        row_amount = self._safe_float_conversion(row["price"]) * self._safe_float_conversion(row["quantity"])
                    
                    ht_total += row_amount
                    logger.debug(f"  Montant ligne: {row_amount}")
            
            if montant_ht == 0.0 and ht_total > 0:
                montant_ht = ht_total
                ht_source = "somme des lignes"
                logger.info(f"Montant HT calculé à partir des lignes: {montant_ht}")
        
        # Si on a uniquement le HT, calculer le TTC avec le taux standard
        if montant_ht > 0 and montant_ttc == 0.0:
            default_tax_rate = 20.0  # Taux de TVA standard
            
            # Chercher un taux de TVA explicite
            for field in ["tax_rate", "taxRate", "vatRate", "vat_rate", "tva", "vat", "taxPercent"]:
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
            
            for field in ["tax_rate", "taxRate", "vatRate", "vat_rate", "tva", "vat", "taxPercent"]:
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
        
        # --- Récupération du statut et mapping amélioré ---
        status = ""
        status_field_used = None
        
        if format_v1:
            # Format V1
            status_fields = ["step_hex", "doc_status", "status"]
        else:
            # Format OCR/V2
            status_fields = ["status", "doc_status", "state", "documentStatus"]
        
        for field in status_fields:
            if field in invoice and invoice[field]:
                status = str(invoice[field]).lower()  # Normalisation en minuscules
                status_field_used = field
                logger.info(f"Statut trouvé via {field}: {status}")
                break
        
        # Mapper les codes statut vers des libellés explicites
        status_mapping = {
            "paid": "Payée",
            "unpaid": "Non payée",
            "draft": "Brouillon",
            "created": "Créée",
            "validated": "Validée",
            "canceled": "Annulée",
            "pending": "En attente",
            "accepted": "Acceptée",
            "sent": "Envoyée",
            "partpaid": "Partiellement payée",
            "cancelled": "Annulée",
            "ongoing": "En cours",
            "ok": "Payée",  # Mapping spécifique pour le statut "ok"
            "nok": "Non payée",
            "done": "Terminée"
        }
        
        # Appliquer le mapping si disponible
        original_status = status
        status = status_mapping.get(status.lower(), status.capitalize())
        
        # Si statut toujours vide, définir un statut par défaut
        if not status:
            status = "Non spécifié"
            logger.warning(f"Statut non trouvé, utilisation par défaut: {status}")
        else:
            logger.info(f"Statut final: {status} (origine: {original_status} via {status_field_used})")
        
        # --- Récupération du lien PDF ---
        pdf_url = ""
        pdf_url_field = None
        pdf_fields = ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf", "file_url", "fileUrl"]
        
        for field in pdf_fields:
            if field in invoice and invoice[field]:
                pdf_url = invoice[field]
                pdf_url_field = field
                logger.info(f"URL PDF trouvée via {field}: {pdf_url}")
                break
            
        # Construction de l'URL web Sellsy avec l'ID
        web_url = ""
        if invoice_id:
            # Format différent selon API V1 ou V2
            if format_v1:
                web_url = f"https://go.sellsy.com/purchase/{invoice_id}"
            else:
                web_url = f"https://go.sellsy.com/purchase/{invoice_id}"
            logger.info(f"URL Sellsy construite: {web_url}")
        
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
        
        logger.info(f"Facture {invoice_id} formatée avec succès")
        logger.info(f"Résultat formaté: {json.dumps(result, indent=2)}")
        return result

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
        
        # Traitement du PDF si disponible
        if pdf_path and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            logger.info(f"Ajout du PDF pour la facture {sellsy_id}")
            pdf_base64 = self.encode_file_to_base64(pdf_path)
            if pdf_base64:
                # Format pour les attachements Airtable
                filename = os.path.basename(pdf_path)
                airtable_data["Fichier_PDF"] = [
                    {
                        "url": f"data:application/pdf;base64,{pdf_base64}",
                        "filename": filename
                    }
                ]
        
        # Vérifier si la facture existe déjà
        existing_record = self.find_supplier_invoice_by_id(sellsy_id)
        
        if existing_record:
            # Mise à jour
            record_id = existing_record["id"]
            logger.info(f"Mise à jour de la facture existante {sellsy_id} (record {record_id})")
            self.table.update(record_id, airtable_data)
            return record_id
        else:
            # Création
            logger.info(f"Création d'une nouvelle facture {sellsy_id}")
            response = self.table.create(airtable_data)
            record_id = response.get("id")
            logger.info(f"Facture créée avec ID Airtable: {record_id}")
            return record_id
    
    except Exception as e:
        logger.error(f"Erreur lors de l'insertion/mise à jour de la facture {sellsy_id}: {e}")
        return None
