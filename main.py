import argparse
import time
import logging
import uvicorn
import os

from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableSupplierAPI, sync_supplier_invoices_to_airtable
from webhook_handler import app
from config import CONFIG_VALID

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

def sync_supplier_invoices(days=30, batch_size=50, cooldown=2):
    """
    Synchronise les factures fournisseur des X derniers jours depuis Sellsy vers Airtable.
    """
    if not CONFIG_VALID:
        logger.error("Configuration invalide. Vérifiez vos variables d'environnement.")
        return

    sellsy = SellsySupplierAPI()
    airtable = AirtableSupplierAPI()

    logger.info(f"🔄 Récupération des factures des {days} derniers jours...")
    invoices = sellsy.get_supplier_invoices(days)

    if not invoices:
        logger.info("Aucune facture fournisseur trouvée.")
        return

    logger.info(f"{len(invoices)} factures trouvées. Début de la synchronisation...")

    success, errors = 0, 0

    for idx, invoice in enumerate(invoices):
        invoice_id = str(invoice.get("id", ""))
        if not invoice_id:
            logger.warning(f"Facture sans ID détectée à l'index {idx}, ignorée.")
            errors += 1
            continue

        logger.info(f"📦 Traitement facture {invoice_id} ({idx + 1}/{len(invoices)})")

        try:
            details = sellsy.get_supplier_invoice_details(invoice_id)
            source_data = details if details else invoice
            formatted = airtable.format_supplier_invoice_for_airtable(source_data)

            pdf_path = None
            try:
                pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)
            except Exception as e:
                logger.warning(f"Erreur téléchargement PDF: {e}")

            if formatted:
                result = airtable.insert_or_update_supplier_invoice(formatted, pdf_path)
                if result:
                    logger.info(f"✅ Facture {invoice_id} synchronisée (Airtable ID: {result})")
                    success += 1
                else:
                    logger.warning(f"⚠️ Insertion échouée pour {invoice_id}")
                    errors += 1
            else:
                logger.warning(f"⚠️ Formatage échoué pour {invoice_id}")
                errors += 1

            if (idx + 1) % batch_size == 0 and idx < len(invoices) - 1:
                logger.info(f"⏸️ Pause de {cooldown}s...")
                time.sleep(cooldown)

        except Exception as e:
            logger.error(f"❌ Erreur traitement facture {invoice_id}: {e}")
            errors += 1
            time.sleep(1)

    logger.info(f"🎉 Synchronisation terminée: {success} réussies, {errors} échouées.")

def start_webhook_server(host="0.0.0.0", port=8000):
    """
    Démarre le serveur webhook pour écouter les événements Sellsy.
    """
    if not CONFIG_VALID:
        logger.error("Configuration invalide. Vérifiez vos variables d'environnement.")
        return

    logger.info(f"🚀 Lancement du serveur webhook sur {host}:{port}")
    
    pdf_dir = os.environ.get("PDF_STORAGE_DIR", "pdf_invoices_suppliers")
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)
        logger.info(f"Répertoire PDF créé: {pdf_dir}")

    try:
        uvicorn.run(app, host=host, port=port)
    except Exception as e:
        logger.error(f"Erreur lancement serveur webhook: {e}")

def run_full_sync():
    """
    Exécute une synchronisation complète via la méthode optimisée.
    """
    if not CONFIG_VALID:
        logger.error("Configuration invalide.")
        return

    logger.info("🔁 Synchronisation complète avec client Sellsy...")
    try:
        sellsy = SellsySupplierAPI()
        sync_supplier_invoices_to_airtable(sellsy)
    except Exception as e:
        logger.error(f"Erreur pendant la synchronisation complète: {e}")

def sync_missing_supplier_invoices(limit=1000):
    """
    Synchronise les factures fournisseur manquantes dans Airtable.
    """
    if not CONFIG_VALID:
        logger.error("Configuration invalide.")
        return

    sellsy = SellsySupplierAPI()
    airtable = AirtableSupplierAPI()

    logger.info(f"🔍 Recherche des factures manquantes (limite: {limit})...")
    invoices = sellsy.get_all_supplier_invoices(limit)

    if not invoices:
        logger.warning("Aucune facture trouvée.")
        return

    missing, synced = 0, 0

    for idx, invoice in enumerate(invoices):
        invoice_id = str(invoice.get("id", ""))
        if not invoice_id:
            continue

        existing = airtable.find_supplier_invoice_by_id(invoice_id)

        if not existing:
            missing += 1
            logger.info(f"📝 Facture manquante: {invoice_id}")

            details = sellsy.get_supplier_invoice_details(invoice_id)
            source_data = details if details else invoice
            formatted = airtable.format_supplier_invoice_for_airtable(source_data)

            if formatted:
                pdf_path = None
                try:
                    pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)
                except Exception as e:
                    logger.warning(f"Erreur PDF: {e}")

                result = airtable.insert_or_update_supplier_invoice(formatted, pdf_path)

                if result:
                    synced += 1
                    logger.info(f"✅ Facture ajoutée: {invoice_id}")
                else:
                    logger.warning(f"⚠️ Échec insertion: {invoice_id}")

            if missing % 10 == 0:
                logger.info("⏸️ Pause de 2s pour éviter saturation...")
                time.sleep(2)

        if (idx + 1) % 50 == 0:
            logger.info(f"Progression: {idx + 1}/{len(invoices)}")

    logger.info(f"🔚 Vérification terminée. {missing} manquantes, {synced} synchronisées.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Sellsy vers Airtable")
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("sync", help="Synchroniser les factures récentes")
    sync_parser.add_argument("--days", type=int, default=30, help="Jours à synchroniser")
    sync_parser.add_argument("--batch", type=int, default=50, help="Taille du lot")
    sync_parser.add_argument("--cooldown", type=int, default=2, help="Pause entre lots (s)")

    subparsers.add_parser("fullsync", help="Synchronisation complète optimisée")

    webhook_parser = subparsers.add_parser("webhook", help="Lancer serveur webhook")
    webhook_parser.add_argument("--host", type=str, default="0.0.0.0")
    webhook_parser.add_argument("--port", type=int, default=8000)

    missing_parser = subparsers.add_parser("sync-missing-supplier", help="Sync factures manquantes")
    missing_parser.add_argument("--limit", type=int, default=1000, help="Limite de factures à analyser")

    args = parser.parse_args()

    if not CONFIG_VALID:
        print("⚠️ Configuration invalide. Vérifiez vos variables d'environnement.")
        exit(1)

    if args.command == "sync":
        sync_supplier_invoices(args.days, args.batch, args.cooldown)
    elif args.command == "fullsync":
        run_full_sync()
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    elif args.command == "sync-missing-supplier":
        sync_missing_supplier_invoices(args.limit)
    else:
        parser.print_help()
