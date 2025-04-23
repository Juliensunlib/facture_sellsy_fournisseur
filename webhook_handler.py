from pyairtable import Table
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME
import datetime
import json
import base64
import os
import requests

class AirtableAPI:
    def __init__(self):
        """Initialisation de la connexion à Airtable"""
        self.table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)

    def format_invoice_for_airtable(self, invoice):
        """Convertit une facture Sellsy au format Airtable"""
        # Vérifications de sécurité pour éviter les erreurs si des champs sont manquants
        if not invoice:
            print("⚠️ Données de facture invalides ou vides")
            return None
            
        # Affichage des clés principales pour débogage
        print(f"Structure de la facture - Clés principales: {list(invoice.keys())}")
        
        # Récupérer l'ID client de Sellsy avec gestion des cas où les champs sont manquants
        client_id = None
        client_name = ""
        
        # Vérifier les différentes structures possibles de l'API Sellsy pour les informations client
        if "relation" in invoice:
            if "id" in invoice["relation"]:
                client_id = str(invoice["relation"]["id"])
            if "name" in invoice["relation"]:
                client_name = invoice["relation"]["name"]
        elif "related" in invoice:
            for related in invoice.get("related", []):
                if related.get("type") == "individual" or related.get("type") == "corporation":
                    client_id = str(related.get("id", ""))
                    client_name = related.get("name", "")
                    break
            # Si le nom n'est pas disponible directement
            if not client_name:
                client_name = invoice.get("company_name", invoice.get("client_name", "Client #" + str(client_id) if client_id else ""))
        
        # Gestion de la date - vérifier plusieurs chemins possibles dans la structure JSON
        created_date = ""
        for date_field in ["created_at", "date", "created"]:
            if date_field in invoice and invoice[date_field]:
                created_date = invoice[date_field]
                break
        
        # S'assurer que la date est au format YYYY-MM-DD pour Airtable
        if created_date:
            # Si la date contient un T (format ISO), prendre juste la partie date
            if "T" in created_date:
                created_date = created_date.split("T")[0]
        else:
            # Fournir une date par défaut si aucune n'est disponible
            created_date = datetime.datetime.now().strftime("%Y-%m-%d")
            print(f"⚠️ Date non trouvée pour la facture {invoice.get('id', 'inconnue')}, utilisation de la date actuelle")
        
        # Récupération des montants avec gestion des différentes structures possibles
        montant_ht = 0
        montant_ttc = 0
        
        # Extraction des montants - simplification et amélioration de la robustesse
        if "amounts" in invoice:
            print(f"Structure amounts: {list(invoice['amounts'].keys())}")
            amounts = invoice["amounts"]
            # Essayer différentes clés possibles pour montant HT
            for key in ["total_excluding_tax", "total_excl_tax", "tax_excl", "total_raw_excl_tax"]:
                if key in amounts and amounts[key] is not None:
                    montant_ht = amounts[key]
                    break
            
            # Essayer différentes clés possibles pour montant TTC
            for key in ["total_including_tax", "total_incl_tax", "tax_incl", "total_incl_tax"]:
                if key in amounts and amounts[key] is not None:
                    montant_ttc = amounts[key]
                    break
        
        # Fallback sur d'autres structures possibles si les montants sont toujours à 0
        if montant_ht == 0 and "amount" in invoice:
            amount = invoice["amount"]
            if "tax_excl" in amount:
                montant_ht = amount["tax_excl"]
            
        if montant_ttc == 0 and "amount" in invoice:
            amount = invoice["amount"]
            if "tax_incl" in amount:
                montant_ttc = amount["tax_incl"]
        
        # Fallback sur les champs directs
        if montant_ht == 0 and "total_amount_without_taxes" in invoice:
            montant_ht = invoice["total_amount_without_taxes"]
            
        if montant_ttc == 0 and "total_amount_with_taxes" in invoice:
            montant_ttc = invoice["total_amount_with_taxes"]
        
        # Récupération du numéro de facture
        reference = ""
        for ref_field in ["reference", "number", "decimal_number"]:
            if ref_field in invoice and invoice[ref_field]:
                reference = invoice[ref_field]
                break
            
        # Récupération du statut
        status = invoice.get("status", "")
        
        # Récupération du lien PDF direct de Sellsy
        pdf_link = invoice.get("pdf_link", "")
        
        # Conversion explicite des montants en float pour éviter les problèmes avec Airtable
        try:
            montant_ht = float(montant_ht) if montant_ht else 0.0
            montant_ttc = float(montant_ttc) if montant_ttc else 0.0
        except (ValueError, TypeError) as e:
            print(f"⚠️ Erreur lors de la conversion des montants: {e}")
            print(f"Valeurs avant conversion: HT={montant_ht}, TTC={montant_ttc}")
            # Assigner des valeurs par défaut en cas d'erreur
            montant_ht = 0.0
            montant_ttc = 0.0
        
        # Créer un dictionnaire avec des valeurs par défaut pour éviter les erreurs
        result = {
            "ID_Facture": str(invoice.get("id", "")),  # Conversion explicite en str
            "Numéro": reference,
            "Date": created_date,  # Date formatée correctement
            "Client": client_name,
            "ID_Client_Sellsy": client_id,  # Ajout de l'ID client Sellsy
            "Montant_HT": montant_ht,  # Maintenant c'est un float
            "Montant_TTC": montant_ttc,  # Maintenant c'est un float
            "Statut": status,
            "URL": f"https://go.sellsy.com/document/{invoice.get('id', '')}"
        }
        
        # Ajouter le lien direct vers le PDF si disponible
        if pdf_link:
            result["PDF_URL"] = pdf_link
        
        print(f"Montants finaux (après conversion): HT={montant_ht} (type: {type(montant_ht)}), TTC={montant_ttc} (type: {type(montant_ttc)})")
        return result

    def find_invoice_by_id(self, sellsy_id):
        """Recherche une facture dans Airtable par son ID Sellsy"""
        if not sellsy_id:
            print("⚠️ ID Sellsy vide, impossible de rechercher la facture")
            return None
            
        sellsy_id = str(sellsy_id)  # Sécurité : conversion en chaîne
        formula = f"{{ID_Facture}}='{sellsy_id}'"
        print(f"🔍 Recherche dans Airtable avec formule : {formula}")
        try:
            records = self.table.all(formula=formula)
            print(f"Résultat de recherche : {len(records)} enregistrement(s) trouvé(s).")
            return records[0] if records else None
        except Exception as e:
            print(f"❌ Erreur lors de la recherche de la facture {sellsy_id} : {e}")
            return None

    def insert_or_update_invoice(self, invoice_data, pdf_path=None):
        """Insère ou met à jour une facture dans Airtable avec PDF"""
        if not invoice_data:
            print("❌ Données de facture invalides, impossible d'insérer/mettre à jour")
            return None
            
        sellsy_id = str(invoice_data.get("ID_Facture", ""))
        if not sellsy_id:
            print("❌ ID Sellsy manquant dans les données, impossible d'insérer/mettre à jour")
            return None
        
        # Créer une copie des données pour ne pas modifier l'original
        invoice_data_copy = invoice_data.copy()
        
        # Ajouter la pièce jointe PDF si elle existe
        if pdf_path and os.path.exists(pdf_path):
            try:
                # Vérifier la taille du fichier PDF
                file_size = os.path.getsize(pdf_path)
                print(f"Taille du fichier PDF: {file_size} octets")
                
                # Si le fichier est trop grand (plus de 2MB), utiliser un lien au lieu d'une pièce jointe
                if file_size > 2000000:  # 2MB limite Airtable pour les attachements
                    print(f"⚠️ Le fichier PDF est trop volumineux ({file_size/1000000:.2f} MB), utilisation du lien direct à la place")
                    # S'assurer que le lien PDF est dans les données
                    if "PDF_URL" in invoice_data_copy:
                        print(f"✅ Utilisation du lien direct au lieu de la pièce jointe: {invoice_data_copy['PDF_URL']}")
                    else:
                        print("⚠️ Pas de lien PDF disponible, impossible d'ajouter la référence au PDF")
                elif file_size > 0:
                    # La méthode avec base64 cause des problèmes, utilisons l'URL du fichier
                    if "PDF_URL" in invoice_data_copy:
                        print(f"✅ Utilisation du lien direct au lieu de la pièce jointe: {invoice_data_copy['PDF_URL']}")
                    else:
                        print("⚠️ Pas de lien PDF disponible, impossible d'ajouter la référence au PDF")
                else:
                    print(f"⚠️ Fichier PDF vide pour la facture {sellsy_id}, impossible d'ajouter la pièce jointe")
            except Exception as e:
                print(f"❌ Erreur lors de la préparation du PDF pour Airtable: {e}")
        
        try:
            existing_record = self.find_invoice_by_id(sellsy_id)

            if existing_record:
                record_id = existing_record["id"]
                print(f"🔁 Facture {sellsy_id} déjà présente, mise à jour en cours...")
                self.table.update(record_id, invoice_data_copy)
                print(f"✅ Facture {sellsy_id} mise à jour avec succès.")
                return record_id
            else:
                print(f"➕ Facture {sellsy_id} non trouvée, insertion en cours...")
                record = self.table.create(invoice_data_copy)
                print(f"✅ Facture {sellsy_id} ajoutée avec succès à Airtable (ID: {record['id']}).")
                return record['id']
        except Exception as e:
            print(f"❌ Erreur lors de l'insertion/mise à jour de la facture {sellsy_id}: {e}")
            # Afficher les clés pour le débogage
            print(f"Clés dans les données: {list(invoice_data_copy.keys()) if invoice_data_copy else 'N/A'}")
            print(f"Valeur du champ Date: '{invoice_data_copy.get('Date', 'N/A')}'" if invoice_data_copy else "N/A")
            raise e

# Code principal pour synchroniser les factures Sellsy avec Airtable
def sync_invoices_to_airtable(sellsy_api_client):
    print("🚀 Début de la synchronisation des factures Sellsy vers Airtable...")

    # Récupère toutes les factures depuis Sellsy
    invoices = sellsy_api_client.get_all_invoices()

    if invoices:
        print(f"📦 {len(invoices)} factures récupérées depuis Sellsy.")
        airtable_api = AirtableAPI()

        # Parcours des factures récupérées et insertion ou mise à jour dans Airtable
        for invoice in invoices:
            formatted_invoice = airtable_api.format_invoice_for_airtable(invoice)
            if formatted_invoice:
                # Télécharger le PDF pour cette facture
                pdf_path = sellsy_api_client.download_invoice_pdf(invoice["id"])
                # Insérer ou mettre à jour avec le PDF
                airtable_api.insert_or_update_invoice(formatted_invoice, pdf_path)

        print("✅ Synchronisation terminée.")
