import argparse
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableSupplierAPI
import time
import uvicorn
from webhook_handler import app  # Si tu utilises un serveur webhook

def sync_supplier_invoices(days=365):
    """Synchronise les factures fournisseur des X derniers jours depuis Sellsy vers Airtable"""
    sellsy = SellsySupplierAPI()
    airtable = AirtableSupplierAPI()
    
    print(f"🔄 Récupération des factures fournisseur des {days} derniers jours...")
    invoices = sellsy.get_supplier_invoices(days)
    
    if not invoices:
        print("Aucune facture fournisseur trouvée.")
        return
    
    print(f"{len(invoices)} factures trouvées.")
    
    for idx, invoice in enumerate(invoices):
        invoice_id = str(invoice["id"])
        print(f"📦 Traitement de la facture {invoice_id} ({idx+1}/{len(invoices)})")

        # Essai de récupération de tous les détails
        details = sellsy.get_supplier_invoice_details(invoice_id)
        source_data = details if details else invoice

        formatted_invoice = airtable.format_supplier_invoice_for_airtable(source_data)
        pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)

        if formatted_invoice:
            airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
            print(f"✅ Facture {invoice_id} synchronisée avec Airtable")
        else:
            print(f"⚠️ Formatage échoué pour {invoice_id}")

        if idx % 10 == 0 and idx != 0:
            print("⏸️ Pause de 2s pour éviter la saturation de l'API...")
            time.sleep(2)

    print("🎉 Synchronisation terminée.")

def start_webhook_server(host="0.0.0.0", port=8000):
    print(f"🚀 Serveur webhook en écoute sur {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronisation Sellsy -> Airtable")
    subparsers = parser.add_subparsers(dest="command")

    sync = subparsers.add_parser("sync", help="Synchroniser les factures fournisseur")
    sync.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")

    webhook = subparsers.add_parser("webhook", help="Démarrer le serveur webhook")
    webhook.add_argument("--host", type=str, default="0.0.0.0")
    webhook.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.command == "sync":
        sync_supplier_invoices(args.days)
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    else:
        parser.print_help()
import argparse
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableSupplierAPI
import time
import uvicorn
from webhook_handler import app  # Si tu utilises un serveur webhook

def sync_supplier_invoices(days=365):
    """Synchronise les factures fournisseur des X derniers jours depuis Sellsy vers Airtable"""
    sellsy = SellsySupplierAPI()
    airtable = AirtableSupplierAPI()
    
    print(f"🔄 Récupération des factures fournisseur des {days} derniers jours...")
    invoices = sellsy.get_supplier_invoices(days)
    
    if not invoices:
        print("Aucune facture fournisseur trouvée.")
        return
    
    print(f"{len(invoices)} factures trouvées.")
    
    for idx, invoice in enumerate(invoices):
        invoice_id = str(invoice["id"])
        print(f"📦 Traitement de la facture {invoice_id} ({idx+1}/{len(invoices)})")

        # Essai de récupération de tous les détails
        details = sellsy.get_supplier_invoice_details(invoice_id)
        source_data = details if details else invoice

        formatted_invoice = airtable.format_supplier_invoice_for_airtable(source_data)
        pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)

        if formatted_invoice:
            airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
            print(f"✅ Facture {invoice_id} synchronisée avec Airtable")
        else:
            print(f"⚠️ Formatage échoué pour {invoice_id}")

        if idx % 10 == 0 and idx != 0:
            print("⏸️ Pause de 2s pour éviter la saturation de l'API...")
            time.sleep(2)

    print("🎉 Synchronisation terminée.")

def start_webhook_server(host="0.0.0.0", port=8000):
    print(f"🚀 Serveur webhook en écoute sur {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronisation Sellsy -> Airtable")
    subparsers = parser.add_subparsers(dest="command")

    sync = subparsers.add_parser("sync", help="Synchroniser les factures fournisseur")
    sync.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")

    webhook = subparsers.add_parser("webhook", help="Démarrer le serveur webhook")
    webhook.add_argument("--host", type=str, default="0.0.0.0")
    webhook.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.command == "sync":
        sync_supplier_invoices(args.days)
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    else:
        parser.print_help()
