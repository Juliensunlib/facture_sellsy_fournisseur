import argparse
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableAPI
import uvicorn
from webhook_handler import app
import time
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

    print(f"Récupération des factures fournisseur (limite {limit})...")

    invoices = sellsy.get_supplier_invoices(limit=limit)

    if not invoices:
        print("Aucune facture fournisseur trouvée.")
        return

    print(f"{len(invoices)} factures fournisseur trouvées.")

    for idx, invoice in enumerate(invoices):
        try:
            invoice_id = str(invoice.get("docid", ""))
            if not invoice_id:
                print(f"⚠️ ID de facture manquant pour l'index {idx}")
                continue
                
            print(f"Traitement de la facture fournisseur {invoice_id} ({idx+1}/{len(invoices)})...")

            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)

            # Récupérer les détails complets de la facture
            invoice_details = sellsy.get_supplier_invoice_details(invoice_id)
            
            if invoice_details and invoice_details.get("status") == "success" and "response" in invoice_details:
                invoice_data = invoice_details["response"]
                formatted_invoice = airtable.format_invoice_for_airtable(invoice_data)
                
                # Récupérer le PDF
                pdf_path = sellsy.get_supplier_invoice_pdf(invoice_id)

                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture fournisseur {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture fournisseur {invoice_id} n'a pas pu être formatée correctement")
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture fournisseur {invoice_id} - utilisation des données de base")
                formatted_invoice = airtable.format_invoice_for_airtable(invoice)
                
                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice)
                    print(f"✅ Facture fournisseur {invoice_id} traitée avec données de base ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture fournisseur {invoice_id} n'a pas pu être formatée correctement, même avec les données de base")
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture fournisseur {invoice.get('docid', 'ID inconnu')}: {e}")

    print("Synchronisation des factures fournisseur terminée.")

def sync_ocr_invoices(limit=1000, days=365):
    """Synchronise les factures OCR des X derniers jours (limitées à N factures max)"""
    sellsy = SellsySupplierAPI()
    airtable = AirtableAPI()

    print(f"Récupération des factures d'achat OCR (limite {limit})...")

    invoices = sellsy.search_purchase_invoices(limit=limit)

    if not invoices:
        print("Aucune facture OCR trouvée.")
        return

    print(f"{len(invoices)} factures OCR trouvées.")

    for idx, invoice in enumerate(invoices):
        try:
            invoice_id = str(invoice["id"])
            print(f"Traitement de la facture OCR {invoice_id} ({idx+1}/{len(invoices)})...")

            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)

            invoice_details = sellsy.get_invoice_details(invoice_id)

            if invoice_details:
                formatted_invoice = airtable.format_invoice_for_airtable(invoice_details)

                pdf_url = next((invoice_details.get(field) for field in ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf"] if invoice_details.get(field)), None)
                pdf_path = sellsy.download_invoice_pdf(pdf_url, invoice_id) if pdf_url else None

                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture OCR {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture OCR {invoice_id} n'a pas pu être formatée correctement")
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture OCR {invoice_id} - utilisation des données de base")
                formatted_invoice = airtable.format_invoice_for_airtable(invoice)

                pdf_url = next((invoice.get(field) for field in ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf"] if invoice.get(field)), None)
                pdf_path = sellsy.download_invoice_pdf(pdf_url, invoice_id) if pdf_url else None

                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture OCR {invoice_id} traitée avec données de base ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture OCR {invoice_id} n'a pas pu être formatée correctement, même avec les données de base")
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture OCR {invoice.get('id')}: {e}")

    print("Synchronisation des factures OCR terminée.")

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
