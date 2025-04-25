from pyairtable import Table
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_SUPPLIER_TABLE_NAME
import datetime
import os
import base64
import logging
import re
import json
from typing import Dict, Optional, Any, List, Union

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airtable_api")

class AirtableAPI:
    def __init__(self):
        """Initialisation de la connexion à Airtable"""
        try:
            self.table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_SUPPLIER_TABLE_NAME)
            logger.info(f"Connexion établie à la table Airtable: {AIRTABLE_SUPPLIER_TABLE_NAME}")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de la connexion Airtable: {e}")
            raise

    # ... [aucun changement dans toutes les fonctions précédentes]

    def encode_file_to_base64(self, file_path: str) -> Optional[str]:
        """
        Encode un fichier en base64 pour Airtable

        Args:
            file_path: Chemin du fichier à encoder

        Returns:
            Chaîne base64 ou None en cas d'erreur
        """
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"Fichier introuvable: {file_path}")
            return None

        # Vérifier que le fichier n'est pas vide
        if os.path.getsize(file_path) == 0:
            logger.warning(f"Fichier vide: {file_path}")
            return None

        try:
            with open(file_path, 'rb') as file:
                # Vérification du contenu du fichier (premiers octets d'un PDF: %PDF)
                first_bytes = file.read(4)
                file.seek(0)  # Revenir au début du fichier

                if first_bytes != b'%PDF':
                    logger.warning(f"Le fichier {file_path} ne semble pas être un PDF valide")

                encoded_string = base64.b64encode(file.read()).decode('utf-8')
                logger.debug(f"Fichier {file_path} encodé avec succès ({len(encoded_string)} caractères)")
                return encoded_string
        except Exception as e:
            logger.error(f"Erreur lors de l'encodage du fichier {file_path}: {e}")
            return None

    def insert_or_update_supplier_invoice(self, invoice_data: Dict, pdf_path: Optional[str] = None) -> Optional[str]:
        """
        Insère ou met à jour une facture fournisseur dans Airtable avec son PDF si disponible

        Args:
            invoice_data: Données de la facture formatées pour Airtable
            pdf_path: Chemin vers le fichier PDF (optionnel)

        Returns:
            ID de l'enregistrement Airtable ou None en cas d'erreur
        """
        if not invoice_data:
            logger.error("Données de facture fournisseur invalides, impossible d'insérer/mettre à jour")
            return None

        sellsy_id = str(invoice_data.get("ID_Facture_Fournisseur", ""))
        if not sellsy_id:
            logger.error("ID Sellsy manquant dans les données, impossible d'insérer/mettre à jour")
            return None

        try:
            # Préparation des données
            airtable_data = invoice_data.copy()

            # Traitement du PDF si disponible
            if pdf_path and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                logger.info(f"Ajout du PDF pour la facture {sellsy_id}")
                pdf_base64 = self.encode_file_to_base64(pdf_path)
                if pdf_base64:
                    # Format pour les attachements Airtable
                    filename = os.path.basename(pdf_path)
                    airtable_data["Fichier_PDF"] = [
                        {
                            "url": f"data:application/pdf;base64,{pdf_base64}",
                            "filename": filename
                        }
                    ]

            # Vérifier si la facture existe déjà
            existing_record = self.find_supplier_invoice_by_id(sellsy_id)

            if existing_record:
                # Mise à jour
                record_id = existing_record["id"]
                logger.info(f"Mise à jour de la facture existante {sellsy_id} (record {record_id})")
                self.table.update(record_id, airtable_data)
                return record_id
            else:
                # Création
                logger.info(f"Création d'une nouvelle facture {sellsy_id}")
                response = self.table.create(airtable_data)
                record_id = response.get("id")
                logger.info(f"Facture créée avec ID Airtable: {record_id}")
                return record_id

        except Exception as e:
            logger.error(f"Erreur lors de l'insertion/mise à jour de la facture {sellsy_id}: {e}")
            return None
