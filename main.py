from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableSupplierAPI
import argparse
import time
import uvicorn
from webhook_handler import app  # si tu veux le support webhook

def sync_all_supplier_invoices(days=365):
    sellsy = SellsySupplierAPI()
    airtable = AirtableSupplierAPI()

    print(f"🔄 Synchronisation des factures fournisseur des {days} derniers jours...")
    invoices = sellsy.get_supplier_invoices(days=days)

    if not invoices:
        print("❌ Aucune facture trouvée.")
        return

    for idx, invoice in enumerate(invoices):
        try:
            invoice_id = str(invoice["id"])
            print(f"📄 Traitement de la facture {invoice_id} ({idx+1}/{len(invoices)})...")

            details = sellsy.get_supplier_invoice_details(invoice_id)
            source = details if details else invoice

            formatted = airtable.format_supplier_invoice_for_airtable(source)
            pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)

            if formatted:
                airtable.insert_or_update_supplier_invoice(formatted, pdf_path)
                print(f"✅ Facture {invoice_id} synchronisée.")
            else:
                print(f"⚠️ Formatage échoué pour la facture {invoice_id}")
        except Exception as e:
            print(f"❌ Erreur sur {invoice.get('id')}: {e}")

        if idx % 10 == 0 and idx != 0:
            print("⏱️ Pause API de 2s...")
            time.sleep(2)

    print("🎉 Synchronisation terminée.")

def start_webhook_server(host="0.0.0.0", port=8000):
    print(f"🚀 Démarrage du serveur webhook sur {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Sellsy → Airtable")
    sub = parser.add_subparsers(dest="command")

    sync = sub.add_parser("sync", help="Sync des factures fournisseurs")
    sync.add_argument("--days", type=int, default=30)

    webhook = sub.add_parser("webhook", help="Démarrer serveur webhook")
    webhook.add_argument("--host", default="0.0.0.0")
    webhook.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.command == "sync":
        sync_all_supplier_invoices(days=args.days)
    elif args.command == "webhook":
        start_webhook_server(host=args.host, port=args.port)
    else:
        parser.print_help()
