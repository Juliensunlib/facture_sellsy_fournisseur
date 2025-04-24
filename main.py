import argparse
from sellsy_api import SellsyAPI
from airtable_api import AirtableAPI
import uvicorn
from webhook_handler import app
import time

def sync_invoices(days=365):
    """Synchronise les factures des X derniers jours"""
    sellsy = SellsyAPI()
    airtable = AirtableAPI()

    print(f"Récupération des factures des {days} derniers jours...")
    invoices = sellsy.get_invoices(days)

    if not invoices:
        print("Aucune facture trouvée.")
        return

    print(f"{len(invoices)} factures trouvées.")

    for idx, invoice in enumerate(invoices):
        try:
            invoice_id = str(invoice["id"])
            print(f"Traitement de la facture {invoice_id} ({idx+1}/{len(invoices)})...")

            # Pause pour éviter les limitations d'API
            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)

            invoice_details = sellsy.get_invoice_details(invoice_id)

            if invoice_details:
                # Formatage pour Airtable
                formatted_invoice = airtable.format_invoice_for_airtable(invoice_details)
                pdf_path = sellsy.download_invoice_pdf(invoice_id)

                if formatted_invoice:
                    airtable.insert_or_update_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture {invoice_id} n'a pas pu être formatée correctement")
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture {invoice_id} - utilisation des données de base")
                formatted_invoice = airtable.format_invoice_for_airtable(invoice)
                pdf_path = sellsy.download_invoice_pdf(invoice_id)

                if formatted_invoice:
                    airtable.insert_or_update_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture {invoice_id} traitée avec données de base ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture {invoice_id} n'a pas pu être formatée correctement, même avec les données de base")
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture {invoice.get('id')}: {e}")

    print("Synchronisation terminée.")

def sync_supplier_invoices(limit=1000):
    """Synchronise les factures fournisseur dans Airtable"""
    sellsy = SellsyAPI()
    airtable = AirtableAPI()

    print(f"Récupération des factures fournisseur de Sellsy (max {limit})...")
    all_invoices = sellsy.get_all_supplier_invoices(limit)

    if not all_invoices:
        print("Aucune facture fournisseur trouvée.")
        return

    print(f"{len(all_invoices)} factures fournisseur trouvées dans Sellsy.")

    added_count = 0
    updated_count = 0
    error_count = 0

    for idx, invoice in enumerate(all_invoices):
        try:
            invoice_id = str(invoice["id"])
            print(f"Traitement de la facture fournisseur {invoice_id} ({idx+1}/{len(all_invoices)})...")

            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)

            existing_record = airtable.find_supplier_invoice_by_id(invoice_id)

            if existing_record:
                print(f"🔄 Facture fournisseur {invoice_id} déjà présente dans Airtable, mise à jour du PDF.")
                pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)

                invoice_details = sellsy.get_supplier_invoice_details(invoice_id)
                source_data = invoice_details if invoice_details else invoice
                formatted_invoice = airtable.format_supplier_invoice_for_airtable(source_data)

                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    updated_count += 1
                    print(f"✅ Facture fournisseur {invoice_id} mise à jour avec PDF ({idx+1}/{len(all_invoices)}).")
                continue

            invoice_details = sellsy.get_supplier_invoice_details(invoice_id)
            source_data = invoice_details if invoice_details else invoice

            if not invoice_details:
                print(f"⚠️ Impossible de récupérer les détails de la facture fournisseur {invoice_id} - utilisation des données de base")

            pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)

            formatted_invoice = airtable.format_supplier_invoice_for_airtable(source_data)

            if formatted_invoice:
                try:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    added_count += 1
                    print(f"➕ Facture fournisseur {invoice_id} ajoutée avec PDF ({idx+1}/{len(all_invoices)}).")
                except Exception as e:
                    print(f"❌ Erreur lors de l'ajout de la facture fournisseur {invoice_id} à Airtable: {e}")
                    error_count += 1
            else:
                print(f"⚠️ La facture fournisseur {invoice_id} n'a pas pu être formatée correctement")
                error_count += 1

        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture fournisseur {invoice.get('id')}: {e}")
            error_count += 1

    print(f"Synchronisation terminée. {added_count} nouvelles factures fournisseur ajoutées, {updated_count} factures déjà présentes, {error_count} erreurs.")

def start_webhook_server(host="0.0.0.0", port=8000):
    """Démarre le serveur webhook"""
    print(f"Démarrage du serveur webhook sur {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Outil de synchronisation Sellsy - Airtable")

    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # Commande sync
    sync_parser = subparsers.add_parser("sync", help="Synchroniser les factures des derniers jours")
    sync_parser.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")

    # Commande sync-supplier
    supplier_parser = subparsers.add_parser("sync-supplier", help="Synchroniser les factures fournisseur")
    supplier_parser.add_argument("--limit", type=int, default=1000, help="Nombre maximum de factures fournisseur à vérifier")

    # Commande webhook
    webhook_parser = subparsers.add_parser("webhook", help="Démarrer le serveur webhook")
    webhook_parser.add_argument("--host", type=str, default="0.0.0.0", help="Hôte du serveur")
    webhook_parser.add_argument("--port", type=int, default=8000, help="Port du serveur")

    args = parser.parse_args()

    if args.command == "sync":
        sync_invoices(args.days)
    elif args.command == "sync-supplier":
        sync_supplier_invoices(args.limit)
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    else:
        parser.print_help()
