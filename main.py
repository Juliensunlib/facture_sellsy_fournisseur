import argparse
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableAPI
import uvicorn
from webhook_handler import app
import time

def sync_invoices(limit=1000, days=365):
    """Synchronise les factures des X derniers jours (limitées à N factures max)"""
    sellsy = SellsySupplierAPI()
    airtable = AirtableAPI()

    print(f"Récupération des factures d'achat (limite {limit}) sur les {days} derniers jours...")

    invoices = sellsy.search_purchase_invoices(limit=limit)

    if not invoices:
        print("Aucune facture trouvée.")
        return

    print(f"{len(invoices)} factures trouvées.")

    for idx, invoice in enumerate(invoices):
        try:
            invoice_id = str(invoice["id"])
            print(f"Traitement de la facture {invoice_id} ({idx+1}/{len(invoices)})...")

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
                    print(f"✅ Facture {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture {invoice_id} n'a pas pu être formatée correctement")
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture {invoice_id} - utilisation des données de base")
                formatted_invoice = airtable.format_invoice_for_airtable(invoice)

                pdf_url = next((invoice.get(field) for field in ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf"] if invoice.get(field)), None)
                pdf_path = sellsy.download_invoice_pdf(pdf_url, invoice_id) if pdf_url else None

                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture {invoice_id} traitée avec données de base ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture {invoice_id} n'a pas pu être formatée correctement, même avec les données de base")
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture {invoice.get('id')}: {e}")

    print("Synchronisation terminée.")

def sync_supplier_invoices(limit=1000):
    print("Utilisation de la fonction sync_invoices avec limit.")
    sync_invoices(limit=limit)

def start_webhook_server(host="0.0.0.0", port=8000):
    print(f"Démarrage du serveur webhook sur {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Outil de synchronisation Sellsy v2 - Airtable")

    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    sync_parser = subparsers.add_parser("sync", help="Synchroniser les factures des derniers jours")
    sync_parser.add_argument("--limit", type=int, default=1000, help="Nombre maximum de factures à synchroniser")
    sync_parser.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")

    supplier_parser = subparsers.add_parser("sync-supplier", help="Synchroniser les factures fournisseur")
    supplier_parser.add_argument("--limit", type=int, default=1000, help="Nombre maximum de factures fournisseur à vérifier")

    webhook_parser = subparsers.add_parser("webhook", help="Démarrer le serveur webhook")
    webhook_parser.add_argument("--host", type=str, default="0.0.0.0", help="Hôte du serveur")
    webhook_parser.add_argument("--port", type=int, default=8000, help="Port du serveur")

    args = parser.parse_args()

    if args.command == "sync":
        sync_invoices(limit=args.limit, days=args.days)
    elif args.command == "sync-supplier":
        sync_supplier_invoices(limit=args.limit)
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    else:
        parser.print_help()
