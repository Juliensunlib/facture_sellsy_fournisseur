import argparse
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableAPI
import uvicorn
from webhook_handler import app
import time

def sync_invoices(days=365):
    """Synchronise les factures des X derniers jours"""
    sellsy = SellsySupplierAPI()
    airtable = AirtableAPI()

    print(f"Récupération des factures d'achat des {days} derniers jours...")
    # Note: la méthode get_purchase_invoices ne filtre pas par date dans l'implémentation actuelle
    # Vous pourriez vouloir ajouter ce filtre dans SellsySupplierAPI
    invoices = sellsy.get_purchase_invoices(limit=1000)

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
                
                # Récupération de l'URL du PDF
                pdf_url = None
                pdf_fields = ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf"]
                for field in pdf_fields:
                    if field in invoice_details and invoice_details[field]:
                        pdf_url = invoice_details[field]
                        break
                
                pdf_path = None
                if pdf_url:
                    pdf_path = sellsy.download_invoice_pdf(pdf_url, invoice_id)

                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture {invoice_id} n'a pas pu être formatée correctement")
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture {invoice_id} - utilisation des données de base")
                formatted_invoice = airtable.format_invoice_for_airtable(invoice)
                
                # Recherche de l'URL PDF dans les données de base
                pdf_url = None
                pdf_fields = ["pdf_url", "pdfUrl", "downloadUrl", "public_link", "pdf"]
                for field in pdf_fields:
                    if field in invoice and invoice[field]:
                        pdf_url = invoice[field]
                        break
                        
                pdf_path = None
                if pdf_url:
                    pdf_path = sellsy.download_invoice_pdf(pdf_url, invoice_id)

                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture {invoice_id} traitée avec données de base ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture {invoice_id} n'a pas pu être formatée correctement, même avec les données de base")
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture {invoice.get('id')}: {e}")

    print("Synchronisation terminée.")

def sync_supplier_invoices(limit=1000):
    """
    Synchronise les factures fournisseur dans Airtable
    Note: Cette fonction nécessite des méthodes qui ne semblent pas être implémentées dans la version actuelle
    de SellsySupplierAPI. Considérez soit de l'implémenter, soit de fusionner cette fonctionnalité avec sync_invoices.
    """
    print("⚠️ Cette fonction doit être mise à jour pour utiliser l'API Sellsy v2.")
    print("Les méthodes get_all_supplier_invoices et get_supplier_invoice_details ne sont pas disponibles.")
    print("Utilisez plutôt la fonction sync_invoices qui utilise get_purchase_invoices et get_invoice_details.")
    
    # Implémentation alternative basée sur les méthodes disponibles
    # Cette fonction est maintenant équivalente à sync_invoices
    sync_invoices(limit=limit)

def start_webhook_server(host="0.0.0.0", port=8000):
    """Démarre le serveur webhook"""
    print(f"Démarrage du serveur webhook sur {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Outil de synchronisation Sellsy v2 - Airtable")

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
