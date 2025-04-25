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

    # ... toutes les autres méthodes ici, inchangées jusqu'à ...

    def insert_or_update_supplier_invoice(self, invoice_data: Dict, pdf_path: Optional[str] = None) -> Optional[str]:
        """
        Insère ou met à jour une facture fournisseur dans Airtable avec son PDF si disponible
        """
        if not invoice_data:
            logger.error("Données de facture fournisseur invalides, impossible d'insérer/mettre à jour")
            return None

        sellsy_id = str(invoice_data.get("ID_Facture_Fournisseur", ""))
        if not sellsy_id:
            logger.error("ID Sellsy manquant dans les données, impossible d'insérer/mettre à jour")
            return None

        try:
            airtable_data = invoice_data.copy()

            if pdf_path and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                logger.info(f"Ajout du PDF pour la facture {sellsy_id}")
                pdf_content = self.encode_file_to_base64(pdf_path)
                if pdf_content:
                    filename = os.path.basename(pdf_path)
                    airtable_data["Pièce_jointe"] = [
                        {
                            "url": f"data:application/pdf;base64,{pdf_content}",
                            "filename": filename
                        }
                    ]
                else:
                    logger.warning(f"Impossible d'encoder le PDF {pdf_path}, pièce jointe ignorée")

            existing_record = self.find_supplier_invoice_by_id(sellsy_id)

            if existing_record:
                record_id = existing_record["id"]
                logger.info(f"Mise à jour de la facture existante {sellsy_id} (record Airtable: {record_id})")
                for key, value in existing_record["fields"].items():
                    if key not in airtable_data and key not in ["ID_Facture_Fournisseur"]:
                        airtable_data[key] = value
                updated_record = self.table.update(record_id, airtable_data)
                return record_id
            else:
                created_record = self.table.create(airtable_data)
                return created_record["id"]

        except Exception as e:
            logger.error(f"Erreur lors de l'insertion/mise à jour de la facture {sellsy_id}: {e}")
            return None

    def bulk_insert_supplier_invoices(self, invoices: List[Dict], pdf_dir: Optional[str] = None) -> Dict[str, str]:
        """
        Insère ou met à jour plusieurs factures fournisseurs en lot
        """
        results = {}
        processed = 0
        failed = 0

        if not invoices:
            logger.warning("Aucune facture à traiter")
            return results

        logger.info(f"Traitement en lot de {len(invoices)} factures")

        for invoice in invoices:
            try:
                invoice_id = str(invoice.get("id", invoice.get("docid", "")))
                if not invoice_id:
                    logger.warning("Facture sans ID, ignorée")
                    failed += 1
                    continue

                formatted_invoice = self.format_invoice_for_airtable(invoice)
                if not formatted_invoice:
                    logger.warning(f"Impossible de formater la facture {invoice_id}, ignorée")
                    failed += 1
                    continue

                pdf_path = None
                if pdf_dir:
                    pdf_patterns = [
                        f"{invoice_id}.pdf",
                        f"facture_{invoice_id}.pdf",
                        f"invoice_{invoice_id}.pdf"
                    ]
                    for pattern in pdf_patterns:
                        potential_path = os.path.join(pdf_dir, pattern)
                        if os.path.exists(potential_path):
                            pdf_path = potential_path
                            break

                airtable_id = self.insert_or_update_supplier_invoice(formatted_invoice, pdf_path)
                if airtable_id:
                    results[invoice_id] = airtable_id
                    processed += 1
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                logger.error(f"Erreur lors du traitement d'une facture: {e}")

        logger.info(f"Traitement en lot terminé: {processed} réussi(es), {failed} échec(s)")
        return results

    def delete_supplier_invoice(self, sellsy_id: str) -> bool:
        """
        Supprime une facture fournisseur d'Airtable par son ID Sellsy
        """
        if not sellsy_id:
            logger.warning("ID Sellsy vide, impossible de supprimer")
            return False

        try:
            existing_record = self.find_supplier_invoice_by_id(sellsy_id)
            if not existing_record:
                logger.warning(f"Facture {sellsy_id} non trouvée, impossible de supprimer")
                return False

            record_id = existing_record["id"]
            self.table.delete(record_id)
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la suppression de la facture {sellsy_id}: {e}")
            return False

    def get_all_supplier_invoices(self, max_records: int = 100) -> List[Dict]:
        """
        Récupère toutes les factures fournisseurs d'Airtable
        """
        try:
            records = self.table.all(max_records=max_records)
            return records
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des factures fournisseurs: {e}")
            return []

    def search_supplier_invoices(self, search_criteria: Dict) -> List[Dict]:
        """
        Recherche des factures fournisseurs selon des critères
        """
        if not search_criteria:
            logger.warning("Aucun critère de recherche spécifié")
            return []

        formulas = []
        try:
            for field, value in search_criteria.items():
                if isinstance(value, str):
                    safe_value = value.replace("'", "''")
                    formulas.append(f"{{{field}}}='{safe_value}'")
                elif isinstance(value, (int, float)):
                    formulas.append(f"{{{field}}}={value}")
                elif isinstance(value, bool):
                    formulas.append(f"{{{field}}}={str(value).lower()}")
                elif isinstance(value, dict) and "min" in value and "max" in value:
                    formulas.append(f"AND({{{field}}}>={value['min']}, {{{field}}}<={value['max']})")
                elif isinstance(value, dict) and "contains" in value:
                    safe_contains = str(value["contains"]).replace("'", "''")
                    formulas.append(f"FIND('{safe_contains}', {{{field}}})")

            final_formula = f"AND({','.join(formulas)})" if len(formulas) > 1 else formulas[0]

            records = self.table.all(formula=final_formula)
            return records

        except Exception as e:
            logger.error(f"Erreur lors de la recherche de factures: {e}")
            return []

    def get_supplier_invoice_stats(self) -> Dict[str, Any]:
        """
        Calcule des statistiques sur les factures fournisseurs
        """
        try:
            records = self.table.all()
            if not records:
                return {
                    "total_count": 0,
                    "total_amount_ht": 0,
                    "total_amount_ttc": 0,
                    "status_distribution": {},
                    "supplier_distribution": {}
                }

            total_ht = 0
            total_ttc = 0
            status_count = {}
            supplier_count = {}

            for record in records:
                fields = record["fields"]
                if "Montant_HT" in fields:
                    total_ht += self._safe_float_conversion(fields["Montant_HT"])
                if "Montant_TTC" in fields:
                    total_ttc += self._safe_float_conversion(fields["Montant_TTC"])

                status = fields.get("Statut", "Non spécifié")
                status_count[status] = status_count.get(status, 0) + 1

                supplier = fields.get("Fournisseur", "Non spécifié")
                supplier_count[supplier] = supplier_count.get(supplier, 0) + 1

            return {
                "total_count": len(records),
                "total_amount_ht": round(total_ht, 2),
                "total_amount_ttc": round(total_ttc, 2),
                "status_distribution": status_count,
                "supplier_distribution": supplier_count
            }

        except Exception as e:
            logger.error(f"Erreur lors du calcul des statistiques: {e}")
            return {
                "error": str(e),
                "total_count": 0
            }
