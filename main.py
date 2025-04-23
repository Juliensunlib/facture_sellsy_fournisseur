import argparse
from sellsy_api import SellsyAPI
from airtable_api import AirtableSupplierAPI
import uvicorn
from webhook_handler import app
import time

def sync_supplier_invoices(days=365):
    """Synchronise les factures fournisseur des X derniers jours"""
    sellsy = SellsyAPI()
    airtable = AirtableSupplierAPI()
    
    print(f"Récupération des factures fournisseur des {days} derniers jours...")
    invoices = sellsy.get_supplier_invoices(days)
    
    if not invoices:
        print("Aucune facture fournisseur trouvée.")
        return
    
    print(f"{len(invoices)} factures fournisseur trouvées.")
    
    for idx, invoice in enumerate(invoices):
        try:
            # Récupérer les détails complets si nécessaire
            invoice_id = str(invoice["id"])
            print(f"Traitement de la facture fournisseur {invoice_id} ({idx+1}/{len(invoices)})...")
            
            # Ajouter un délai entre les requêtes pour éviter les limitations d'API
            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)
                
            invoice_details = sellsy.get_supplier_invoice_details(invoice_id)
            
            if invoice_details:
                # Formater pour Airtable
                formatted_invoice = airtable.format_supplier_invoice_for_airtable(invoice_details)
                
                # Télécharger le PDF
                pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)
                
                # Insérer ou mettre à jour dans Airtable avec le PDF
                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture fournisseur {invoice_id} traitée ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture fournisseur {invoice_id} n'a pas pu être formatée correctement")
            else:
                print(f"⚠️ Impossible de récupérer les détails de la facture fournisseur {invoice_id} - utilisation des données de base")
                # Utilisez les données de base si les détails ne sont pas disponibles
                formatted_invoice = airtable.format_supplier_invoice_for_airtable(invoice)
                
                # Télécharger le PDF même avec les données de base
                pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)
                
                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    print(f"✅ Facture fournisseur {invoice_id} traitée avec données de base ({idx+1}/{len(invoices)}).")
                else:
                    print(f"⚠️ La facture fournisseur {invoice_id} n'a pas pu être formatée correctement, même avec les données de base")
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la facture fournisseur {invoice.get('id')}: {e}")
    
    print("Synchronisation terminée.")

def sync_missing_supplier_invoices(limit=1000):
    """Synchronise les factures fournisseur manquantes dans Airtable"""
    sellsy = SellsyAPI()
    airtable = AirtableSupplierAPI()
    
    print(f"Récupération de toutes les factures fournisseur de Sellsy (max {limit})...")
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
            
            # Ajouter un délai entre les requêtes pour éviter les limitations d'API
            if idx > 0 and idx % 10 == 0:
                print("Pause de 2 secondes pour éviter les limitations d'API...")
                time.sleep(2)
            
            # Vérifier d'abord si la facture existe déjà dans Airtable
            existing_record = airtable.find_supplier_invoice_by_id(invoice_id)
            
            if existing_record:
                # Si la facture existe déjà, on peut quand même mettre à jour le PDF
                print(f"🔄 Facture fournisseur {invoice_id} déjà présente dans Airtable, mise à jour du PDF.")
                pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)
                
                # Récupérer les détails pour la mise à jour
                invoice_details = sellsy.get_supplier_invoice_details(invoice_id)
                source_data = invoice_details if invoice_details else invoice
                formatted_invoice = airtable.format_supplier_invoice_for_airtable(source_data)
                
                if formatted_invoice:
                    airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                    updated_count += 1
                    print(f"✅ Facture fournisseur {invoice_id} mise à jour avec PDF ({idx+1}/{len(all_invoices)}).")
                continue
                
            # Récupérer les détails complets de la facture
            invoice_details = sellsy.get_supplier_invoice_details(invoice_id)
            
            # Source de données à utiliser (détails ou basique)
            source_data = invoice_details if invoice_details else invoice
            
            if not invoice_details:
                print(f"⚠️ Impossible de récupérer les détails de la facture fournisseur {invoice_id} - utilisation des données de base")
            
            # Télécharger le PDF pour cette facture
            pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)
            
            # Formater pour Airtable
            formatted_invoice = airtable.format_supplier_invoice_for_airtable(source_data)
            
            # Ajouter à Airtable
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
    parser = argparse.ArgumentParser(description="Outil de synchronisation Sellsy - Airtable pour factures fournisseur")
    
    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")
    
    # Commande sync
    sync_parser = subparsers.add_parser("sync", help="Synchroniser les factures fournisseur des derniers jours")
    sync_parser.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")
    
    # Commande sync-missing
    missing_parser = subparsers.add_parser("sync-missing", help="Synchroniser les factures fournisseur manquantes")
    missing_parser.add_argument("--limit", type=int, default=1000, help="Nombre maximum de factures à vérifier")
    
    # Commande webhook
    webhook_parser = subparsers.add_parser("webhook", help="Démarrer le serveur webhook")
    webhook_parser.add_argument("--host", type=str, default="0.0.0.0", help="Hôte du serveur")
    webhook_parser.add_argument("--port", type=int, default=8000, help="Port du serveur")
    
    args = parser.parse_args()
    
    if args.command == "sync":
        sync_supplier_invoices(args.days)
    elif args.command == "sync-missing":
        sync_missing_supplier_invoices(args.limit)
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    else:
        parser.print_help()