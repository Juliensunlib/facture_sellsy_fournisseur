import argparse
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableAPI
import uvicorn
from webhook_handler import app
import time
import datetime
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")

def sync_supplier_invoices(limit=1000, days=365):
    """Synchronise les factures fournisseur (limitées à N factures max)"""
    sellsy = SellsySupplierAPI()
    airtable = AirtableAPI()

    print(f"Récupération des factures fournisseur (limite {limit}, jours {days})...")

    invoices = sellsy.get_supplier_invoices(limit=limit, days=days)

    if not invoices:
        print("Aucune facture fournisseur trouvée.")
        return

    print(f"{len(invoices)} factures fournisseur trouvées.")
    success_count = 0
    error_count = 0

    for idx, invoice in enumerate(invoices):
        try:
            # Vérification de la présence d'un ID valide
            invoice_id = None
            for id_field in ["docid", "id", "doc_id"]:
                if id_field in invoice and invoice[id_field]:
                    invoice_id = str(invoice[id_field])
                    break
                    
            if not invoice_id:
                print(f"⚠️ ID de facture manquant pour l'index {idx}")
                error_count += 1
                continue
                
            print(f"Traitement de la facture fournisseur {invoice_id} ({idx+1}/{len(invoices)})...")

            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)

            # Récupérer les détails complets de la facture
            invoice_details = sellsy.get_supplier_invoice_details(invoice_id)
            
            # Variable pour stocker les données de facture à utiliser
            invoice_data = None
            
            if invoice_details and invoice_details.get("status") == "success" and "response" in invoice_details:
                invoice_data = invoice_details["response"]
                # Vérifier que les données contiennent bien un ID
                if not invoice_data.get("id") and not invoice_data.get("docid"):
                    invoice_data["id"] = invoice_id
                    invoice_data["docid"] = invoice_id
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture {invoice_id} - utilisation des données de base")
                invoice_data = invoice
                # Vérifier et compléter les données de base
                if not invoice_data.get("id"):
                    invoice_data["id"] = invoice_id
                if not invoice_data.get("docid"):
                    invoice_data["docid"] = invoice_id
            
            # Formatage et traitement de la facture
            if invoice_data:
                # Afficher les clés principales pour débogage
                keys = list(invoice_data.keys())
                print(f"Structure de la facture - Clés principales: {keys[:10]}...")
                
                formatted_invoice = airtable.format_invoice_for_airtable(invoice_data)
                
                # Récupérer le PDF
                pdf_path = sellsy.get_supplier_invoice_pdf(invoice_id)

                if formatted_invoice:
                    result = airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    if result:
                        print(f"✅ Facture fournisseur {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                        success_count += 1
                    else:
                        print(f"⚠️ Échec de l'insertion dans Airtable pour la facture {invoice_id}")
                        error_count += 1
                else:
                    print(f"⚠️ La facture fournisseur {invoice_id} n'a pas pu être formatée correctement")
                    error_count += 1
            else:
                print(f"⚠️ Données insuffisantes pour la facture {invoice_id}")
                error_count += 1
                
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture fournisseur {invoice.get('docid', invoice.get('id', 'ID inconnu'))}: {e}")
            error_count += 1

    print(f"Synchronisation des factures fournisseur terminée. Succès: {success_count}, Erreurs: {error_count}")

def sync_ocr_invoices(limit=1000, days=365):
    """Synchronise les factures OCR des X derniers jours (limitées à N factures max)"""
    sellsy = SellsySupplierAPI()
    airtable = AirtableAPI()

    print(f"Récupération des factures d'achat OCR (limite {limit}, jours {days})...")

    invoices = sellsy.search_purchase_invoices(limit=limit, days=days)

    if not invoices:
        print("Aucune facture OCR trouvée.")
        return

    print(f"{len(invoices)} factures OCR trouvées.")
    success_count = 0
    error_count = 0

    for idx, invoice in enumerate(invoices):
        try:
            # Vérification de la présence d'un ID valide
            if not invoice.get("id"):
                print(f"⚠️ ID de facture OCR manquant pour l'index {idx}")
                error_count += 1
                continue
                
            invoice_id = str(invoice["id"])
            print(f"Traitement de la facture OCR {invoice_id} ({idx+1}/{len(invoices)})...")

            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)

            # Récupérer les détails complets
            invoice_details = sellsy.get_invoice_details(invoice_id)
            
            # Variable pour stocker les données à utiliser
            invoice_data = None
            
            if invoice_details:
                invoice_data = invoice_details
                # Vérifier que l'ID est présent
                if not invoice_data.get("id"):
                    invoice_data["id"] = invoice_id
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture OCR {invoice_id} - utilisation des données de base")
                invoice_data = invoice
                # S'assurer que l'ID est présent
                if not invoice_data.get("id"):
                    invoice_data["id"] = invoice_id
            
            # Formatage et traitement de la facture
            if invoice_data:
                # Afficher les clés principales pour débogage
                keys = list(invoice_data.keys())
                print(f"Structure de la facture OCR - Clés principales: {keys[:10]}...")
                
                formatted_invoice = airtable.format_invoice_for_airtable(invoice_data)

                # Récupérer l'URL du PDF
                pdf_url = None
                for field in ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf"]:
                    if field in invoice_data and invoice_data[field]:
                        pdf_url = invoice_data[field]
                        break
                        
                pdf_path = None
                if pdf_url:
                    pdf_path = sellsy.download_invoice_pdf(pdf_url, invoice_id)

                if formatted_invoice:
                    result = airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    if result:
                        print(f"✅ Facture OCR {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                        success_count += 1
                    else:
                        print(f"⚠️ Échec de l'insertion dans Airtable pour la facture OCR {invoice_id}")
                        error_count += 1
                else:
                    print(f"⚠️ La facture OCR {invoice_id} n'a pas pu être formatée correctement")
                    error_count += 1
            else:
                print(f"⚠️ Données insuffisantes pour la facture OCR {invoice_id}")
                error_count += 1
                
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture OCR {invoice.get('id', 'ID inconnu')}: {e}")
            error_count += 1

    print(f"Synchronisation des factures OCR terminée. Succès: {success_count}, Erreurs: {error_count}")

def start_webhook_server(host="0.0.0.0", port=8000):
    """Démarre le serveur webhook FastAPI"""
    print(f"Démarrage du serveur webhook sur {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Outil de synchronisation Sellsy - Airtable")

    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # Commande pour les factures OCR via API V2
    ocr_parser = subparsers.add_parser("sync-ocr", help="Synchroniser les factures OCR (API V2)")
    ocr_parser.add_argument("--limit", type=int, default=1000, help="Nombre maximum de factures à synchroniser")
    ocr_parser.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")

    # Commande pour les factures fournisseur via API V1
    supplier_parser = subparsers.add_parser("sync-supplier", help="Synchroniser les factures fournisseur (API V1)")
    supplier_parser.add_argument("--limit", type=int, default=1000, help="Nombre maximum de factures fournisseur à synchroniser")
    supplier_parser.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")

    # Commande pour le serveur webhook
    webhook_parser = subparsers.add_parser("webhook", help="Démarrer le serveur webhook")
    webhook_parser.add_argument("--host", type=str, default="0.0.0.0", help="Hôte du serveur")
    webhook_parser.add_argument("--port", type=int, default=8000, help="Port du serveur")

    args = parser.parse_args()

    if args.command == "sync-ocr":
        sync_ocr_invoices(limit=args.limit, days=args.days)
    elif args.command == "sync-supplier":
        sync_supplier_invoices(limit=args.limit, days=args.days)
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    else:
        parser.print_help()
