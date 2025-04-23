import argparse
import time
import logging
import uvicorn
import os
from sellsy_api import SellsySupplierAPI
from airtable_api import AirtableSupplierAPI, sync_supplier_invoices_to_airtable
from webhook_handler import app  # Importation du serveur webhook
from config import CONFIG_VALID

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")

def sync_supplier_invoices(days=30, batch_size=50, cooldown=2):
    """
    Synchronise les factures fournisseur des X derniers jours depuis Sellsy vers Airtable
    
    Args:
        days: Nombre de jours à synchroniser (défaut: 30)
        batch_size: Nombre de factures par lot avant pause (défaut: 50)
        cooldown: Temps de pause en secondes entre les lots (défaut: 2)
    """
    if not CONFIG_VALID:
        logger.error("Configuration invalide, vérifiez vos variables d'environnement")
        return
        
    sellsy = SellsySupplierAPI()
    airtable = AirtableSupplierAPI()
    
    logger.info(f"🔄 Récupération des factures fournisseur des {days} derniers jours...")
    invoices = sellsy.get_supplier_invoices(days)
    
    if not invoices:
        logger.info("Aucune facture fournisseur trouvée.")
        return
    
    logger.info(f"{len(invoices)} factures trouvées. Démarrage de la synchronisation...")
    
    success_count = 0
    error_count = 0
    
    for idx, invoice in enumerate(invoices):
        invoice_id = str(invoice.get("id", ""))
        if not invoice_id:
            logger.warning(f"Facture sans ID à l'index {idx}, ignorée")
            error_count += 1
            continue
            
        logger.info(f"📦 Traitement de la facture {invoice_id} ({idx+1}/{len(invoices)})")

        try:
            # Essai de récupération de tous les détails
            details = sellsy.get_supplier_invoice_details(invoice_id)
            source_data = details if details else invoice

            formatted_invoice = airtable.format_supplier_invoice_for_airtable(source_data)
            
            # Téléchargement du PDF
            pdf_path = None
            try:
                pdf_path = sellsy.download_supplier_invoice_pdf(invoice_id)
            except Exception as e:
                logger.warning(f"Erreur lors du téléchargement du PDF: {e}")

            if formatted_invoice:
                result = airtable.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                if result:
                    logger.info(f"✅ Facture {invoice_id} synchronisée avec Airtable (ID: {result})")
                    success_count += 1
                else:
                    logger.warning(f"⚠️ Échec de l'insertion/mise à jour pour {invoice_id}")
                    error_count += 1
            else:
                logger.warning(f"⚠️ Formatage échoué pour {invoice_id}")
                error_count += 1

            # Pause après chaque lot pour éviter de surcharger les APIs
            if (idx + 1) % batch_size == 0 and idx < len(invoices) - 1:
                logger.info(f"⏸️ Pause de {cooldown}s pour éviter la saturation des APIs...")
                time.sleep(cooldown)
                
        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement de la facture {invoice_id}: {e}")
            error_count += 1
            
            # En cas d'erreur, faire une petite pause pour laisser les APIs respirer
            time.sleep(1)

    logger.info(f"🎉 Synchronisation terminée. Résultats: {success_count} réussies, {error_count} échouées")

def start_webhook_server(host="0.0.0.0", port=8000):
    """
    Démarre le serveur webhook pour écouter les événements Sellsy
    
    Args:
        host: Adresse IP d'écoute (défaut: 0.0.0.0)
        port: Port d'écoute (défaut: 8000)
    """
    if not CONFIG_VALID:
        logger.error("Configuration invalide, vérifiez vos variables d'environnement")
        return
        
    logger.info(f"🚀 Démarrage du serveur webhook sur {host}:{port}")
    
    # Vérification du répertoire de stockage des PDFs
    pdf_dir = os.environ.get("PDF_STORAGE_DIR", "pdf_invoices_suppliers")
    if not os.path.exists(pdf_dir):
        logger.info(f"Création du répertoire pour les PDFs: {pdf_dir}")
        os.makedirs(pdf_dir)
    
    # Démarrage du serveur
    try:
        uvicorn.run(app, host=host, port=port)
    except Exception as e:
        logger.error(f"Erreur lors du démarrage du serveur webhook: {e}")

def run_full_sync():
    """
    Exécute une synchronisation complète en utilisant la fonction optimisée
    """
    if not CONFIG_VALID:
        logger.error("Configuration invalide, vérifiez vos variables d'environnement")
        return
        
    logger.info("🔄 Démarrage de la synchronisation complète avec sellsy_api_client...")
    try:
        sellsy_client = SellsySupplierAPI()
        sync_supplier_invoices_to_airtable(sellsy_client)
    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation complète: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronisation Sellsy -> Airtable")
    subparsers = parser.add_subparsers(dest="command")

    # Commande sync
    sync_parser = subparsers.add_parser("sync", help="Synchroniser les factures fournisseur")
    sync_parser.add_argument("--days", type=int, default=30, help="Nombre de jours à synchroniser")
    sync_parser.add_argument("--batch", type=int, default=50, help="Taille des lots de traitement")
    sync_parser.add_argument("--cooldown", type=int, default=2, help="Temps de pause entre les lots (secondes)")

    # Commande fullsync (utilise la fonction optimisée)
    subparsers.add_parser("fullsync", help="Exécute une synchronisation complète optimisée")

    # Commande webhook
    webhook_parser = subparsers.add_parser("webhook", help="Démarrer le serveur webhook")
    webhook_parser.add_argument("--host", type=str, default="0.0.0.0", help="Adresse IP d'écoute")
    webhook_parser.add_argument("--port", type=int, default=8000, help="Port d'écoute")

    # Analyse des arguments
    args = parser.parse_args()
    
    # Vérification des variables d'environnement
    if not CONFIG_VALID:
        print("⚠️  Configuration incomplète. Vérifiez votre fichier .env ou les variables d'environnement.")
        exit(1)
    
    # Exécution de la commande appropriée
    if args.command == "sync":
        sync_supplier_invoices(args.days, args.batch, args.cooldown)
    elif args.command == "fullsync":
        run_full_sync()
    elif args.command == "webhook":
        start_webhook_server(args.host, args.port)
    else:
        parser.print_help()
