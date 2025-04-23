import requests
import json
import time
import base64
import os
from datetime import datetime, timedelta
from config import SELLSY_CLIENT_ID, SELLSY_CLIENT_SECRET, SELLSY_API_URL, PDF_STORAGE_DIR

class SellsySupplierAPI:
    def __init__(self):
        self.access_token = None
        self.token_expires_at = 0
        self.api_url = SELLSY_API_URL
        print(f"API URL configurée: {self.api_url}")
        
        # Vérifier que les identifiants sont bien définis (sans les afficher)
        if not SELLSY_CLIENT_ID or not SELLSY_CLIENT_SECRET:
            print("ERREUR: Identifiants Sellsy manquants dans les variables d'environnement")
        
        # Créer le répertoire de stockage des PDF s'il n'existe pas
        if not os.path.exists(PDF_STORAGE_DIR):
            os.makedirs(PDF_STORAGE_DIR)
            print(f"Répertoire de stockage des PDF créé: {PDF_STORAGE_DIR}")

    def get_access_token(self):
        """Obtient ou renouvelle le token d'accès Sellsy selon la documentation v2"""
        current_time = time.time()
        
        # Vérifier si le token est encore valide
        if self.access_token and current_time < self.token_expires_at - 60:
            return self.access_token
        
        # Si non, demander un nouveau token
        url = "https://login.sellsy.com/oauth2/access-tokens"
        
        # Authentification avec les identifiants client en Base64
        auth_string = f"{SELLSY_CLIENT_ID}:{SELLSY_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        data = "grant_type=client_credentials"
        
        print(f"Tentative d'authentification à l'API Sellsy: {url}")
        
        try:
            response = requests.post(url, headers=headers, data=data)
            print(f"Statut de la réponse: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    token_data = response.json()
                    self.access_token = token_data["access_token"]
                    self.token_expires_at = current_time + token_data["expires_in"]
                    print("✅ Token d'accès obtenu avec succès")
                    return self.access_token
                except json.JSONDecodeError as e:
                    print(f"❌ Erreur de décodage JSON: {e}")
                    print(f"Contenu de la réponse (100 premiers caractères): {response.text[:100]}")
                    raise Exception("Réponse de l'API Sellsy invalide")
            else:
                print(f"❌ Erreur d'authentification Sellsy: Code {response.status_code}")
                print(f"Réponse complète: {response.text}")
                raise Exception(f"Échec de l'authentification Sellsy (code {response.status_code})")
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur de connexion à l'API Sellsy: {e}")
            raise Exception(f"Impossible de se connecter à l'API Sellsy: {e}")

    def get_supplier_invoices(self, days=365):
        """Récupère les factures fournisseur des derniers jours spécifiés (défaut: 365 jours = 1 an)"""
        # Calcul de la date à partir d'il y a un an
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"🔍 Récupération des factures fournisseur du {start_date} au {end_date} (période de {days} jours)")
        
        # Utiliser la méthode générique pour récupérer toutes les factures fournisseur avec filtre de date
        return self.get_all_supplier_invoices(
            limit=10000,  # Limite très élevée pour garantir qu'on récupère tout
            created_after=f"{start_date}T00:00:00Z",
            created_before=f"{end_date}T23:59:59Z"
        )

    def get_all_supplier_invoices(self, limit=10000, **filters):
        """
        Récupère toutes les factures fournisseur avec pagination robuste et gestion d'erreurs améliorée
        
        Args:
            limit: Nombre maximum de factures à récupérer (défaut: 10000)
            **filters: Filtres additionnels à passer à l'API Sellsy
                    - created_after: Date de début (format ISO)
                    - created_before: Date de fin (format ISO)
                    - status: Statut des factures
        """
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        all_invoices = []
        current_page = 1
        page_size = 100  # La taille de page maximale généralement acceptée par Sellsy
        
        # Paramètres de pagination
        max_retries = 5        # Nombre maximum de tentatives par page
        retry_delay = 5        # Délai entre les tentatives en secondes
        page_delay = 1         # Délai entre les pages en secondes
        
        print(f"🚀 Récupération de toutes les factures fournisseur (limite: {limit})...")
        if filters:
            print(f"📋 Filtres appliqués: {filters}")
        
        # Boucle de pagination
        while len(all_invoices) < limit:
            # Construction des paramètres de la requête
            params = {
                "limit": page_size,
                "offset": (current_page - 1) * page_size,  # Utiliser offset au lieu de page
                "order": "created",           # Tri par date de création
                "direction": "desc"          # Ordre décroissant (plus récent d'abord)
            }
            
            # Ajout des filtres additionnels
            params.update(filters)
            
            # URL pour les factures fournisseur (différent des factures client)
            url = f"{self.api_url}/purchases/invoices"
            print(f"📄 Récupération de la page {current_page} (offset {params['offset']}): {url}")
            
            # Gestion des tentatives pour cette page
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    response = requests.get(url, headers=headers, params=params)
                    status_code = response.status_code
                    print(f"📊 Statut de la réponse: {status_code}")
                    
                    if status_code == 200:
                        # Traitement des données en cas de succès
                        response_data = response.json()
                        page_invoices = response_data.get("data", [])
                        
                        # Si la page est vide, on a fini
                        if not page_invoices:
                            print("🏁 Page vide reçue, fin de la pagination")
                            return all_invoices[:limit]
                            
                        # Nombre de factures restantes à récupérer
                        remaining = limit - len(all_invoices)
                        
                        # Ajouter seulement les factures nécessaires
                        invoices_to_add = page_invoices[:remaining]
                        all_invoices.extend(invoices_to_add)
                        
                        print(f"✅ Page {current_page}: {len(invoices_to_add)} factures fournisseur récupérées (total: {len(all_invoices)}/{limit})")
                        
                        # Vérifier si on doit continuer la pagination
                        if len(all_invoices) >= limit:
                            print("🏁 Limite atteinte, fin de la récupération")
                            return all_invoices[:limit]
                        
                        if len(page_invoices) < page_size:
                            print("🏁 Dernière page atteinte (moins de résultats que la taille de page)")
                            return all_invoices[:limit]
                        
                        # Passer à la page suivante
                        current_page += 1
                        success = True
                        
                        # Pause entre les pages pour éviter de surcharger l'API
                        print(f"⏱️ Pause de {page_delay} seconde(s) entre les pages...")
                        time.sleep(page_delay)
                        
                    elif status_code == 401:
                        # Token expiré, renouvellement
                        print("🔄 Token expiré, renouvellement...")
                        self.token_expires_at = 0
                        token = self.get_access_token()
                        headers["Authorization"] = f"Bearer {token}"
                        retry_count += 1
                        print(f"🔄 Nouveau token obtenu, tentative {retry_count}/{max_retries} pour la page {current_page}")
                    
                    elif status_code == 429:
                        # Rate limiting - attendre plus longtemps
                        wait_time = 30  # 30 secondes par défaut
                        if 'Retry-After' in response.headers:
                            try:
                                wait_time = int(response.headers['Retry-After'])
                            except ValueError:
                                pass
                        
                        print(f"⚠️ Limitation de débit (429), attente de {wait_time} secondes...")
                        time.sleep(wait_time)
                        retry_count += 1
                    
                    else:
                        # Autres erreurs
                        print(f"❌ Erreur lors de la récupération (page {current_page}): {status_code} - {response.text}")
                        retry_count += 1
                        
                        if retry_count >= max_retries:
                            print(f"❌ Nombre maximum de tentatives atteint pour la page {current_page}")
                        else:
                            print(f"⏱️ Tentative {retry_count}/{max_retries} après {retry_delay} secondes...")
                            time.sleep(retry_delay)
                
                except Exception as e:
                    # Gestion des exceptions (problèmes réseau, etc.)
                    print(f"❌ Exception lors de la récupération de la page {current_page}: {e}")
                    retry_count += 1
                    
                    if retry_count >= max_retries:
                        print(f"❌ Nombre maximum de tentatives atteint pour la page {current_page}")
                    else:
                        print(f"⏱️ Tentative {retry_count}/{max_retries} après {retry_delay} secondes...")
                        time.sleep(retry_delay)
            
            # Si toutes les tentatives ont échoué pour cette page
            if not success:
                print(f"⚠️ Impossible de récupérer la page {current_page} après {max_retries} tentatives")
                print(f"⚠️ Retour des {len(all_invoices)} factures fournisseur déjà récupérées")
                return all_invoices[:limit]
    
        print(f"🎉 Total des factures fournisseur récupérées: {len(all_invoices)}")
        return all_invoices[:limit]

    def get_supplier_invoice_details(self, invoice_id):
        """Récupère les détails d'une facture fournisseur spécifique"""
        if not invoice_id:
            print("❌ ID de facture fournisseur invalide")
            return None
            
        invoice_id = str(invoice_id)  # Conversion en chaîne
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        # URL pour les détails d'une facture fournisseur
        url = f"{self.api_url}/purchases/invoices/{invoice_id}"
        print(f"🔍 Récupération des détails de la facture fournisseur {invoice_id}: {url}")
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = requests.get(url, headers=headers)
                status_code = response.status_code
                print(f"📊 Statut: {status_code}")
                
                if status_code == 200:
                    data = response.json()
                    # Vérifier le format de la réponse
                    if "data" in data:
                        print(f"✅ Détails de la facture fournisseur {invoice_id} récupérés (format avec data)")
                        return data.get("data", {})
                    else:
                        print(f"✅ Détails de la facture fournisseur {invoice_id} récupérés (format direct)")
                        return data
                
                elif status_code == 401:
                    # Renouveler le token et réessayer
                    print("🔄 Token expiré, renouvellement...")
                    self.token_expires_at = 0
                    token = self.get_access_token()
                    headers["Authorization"] = f"Bearer {token}"
                    retry_count += 1
                
                elif status_code == 404:
                    print(f"❌ Facture fournisseur {invoice_id} non trouvée (404)")
                    return None
                
                else:
                    print(f"❌ Erreur {status_code}: {response.text}")
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 5  # 5 secondes entre les tentatives
                        print(f"⏱️ Tentative {retry_count}/{max_retries} dans {wait_time} secondes...")
                        time.sleep(wait_time)
            
            except Exception as e:
                print(f"❌ Exception lors de la récupération des détails: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 5
                    print(f"⏱️ Tentative {retry_count}/{max_retries} dans {wait_time} secondes...")
                    time.sleep(wait_time)
        
        print(f"❌ Échec après {max_retries} tentatives pour la facture fournisseur {invoice_id}")
        return None
    
    def download_supplier_invoice_pdf(self, invoice_id):
        """Télécharge le PDF d'une facture fournisseur et retourne le chemin du fichier"""
        if not invoice_id:
            print("❌ ID de facture fournisseur invalide pour le téléchargement du PDF")
            return None
        
        # Conversion explicite en string
        invoice_id = str(invoice_id)
        
        # Définir le chemin du fichier PDF
        pdf_filename = f"facture_fournisseur_{invoice_id}.pdf"
        pdf_path = os.path.join(PDF_STORAGE_DIR, pdf_filename)
        
        # Vérifier si le fichier existe déjà
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            if file_size > 0:
                print(f"📄 PDF déjà existant pour la facture fournisseur {invoice_id}: {pdf_path} ({file_size} octets)")
                return pdf_path
            else:
                print(f"⚠️ Fichier PDF existant mais vide, retéléchargement...")
        
        # Si non, d'abord récupérer les détails de la facture pour obtenir le lien PDF direct
        invoice_details = self.get_supplier_invoice_details(invoice_id)
        if not invoice_details:
            print(f"❌ Impossible de récupérer les détails pour télécharger le PDF")
            return None
        
        # Vérifier si le lien PDF est disponible directement dans les détails de la facture
        pdf_link = invoice_details.get("pdf_link")
        if not pdf_link:
            print(f"⚠️ Lien PDF non trouvé dans les détails de la facture fournisseur {invoice_id}")
            # Essayer l'URL standard quand même
        else:
            print(f"🔗 Lien PDF trouvé: {pdf_link}")
        
        # Méthodes de téléchargement à essayer
        methods = [
            {
                "name": "Lien direct",
                "url": pdf_link,
                "headers": {
                    "Authorization": f"Bearer {self.get_access_token()}",
                    "Accept": "application/pdf"
                },
                "skip_if_none": True  # Ignorer si pdf_link est None
            },
            {
                "name": "API standard",
                "url": f"{self.api_url}/purchases/invoices/{invoice_id}/document",
                "headers": {
                    "Authorization": f"Bearer {self.get_access_token()}",
                    "Accept": "application/pdf"
                },
                "skip_if_none": False
            }
        ]
        
        # Essayer chaque méthode jusqu'à ce qu'une fonctionne
        for method in methods:
            # Vérifier si on doit sauter cette méthode
            if method["skip_if_none"] and not method["url"]:
                continue
                
            url = method["url"]
            name = method["name"]
            print(f"📥 Téléchargement par {name}: {url}")
            
            try:
                response = requests.get(url, headers=method["headers"])
                status_code = response.status_code
                print(f"📊 Statut: {status_code}")
                
                if status_code == 200:
                    # Vérifier que c'est bien un PDF
                    content_type = response.headers.get('Content-Type', '')
                    content_length = len(response.content)
                    
                    if ('pdf' not in content_type.lower() and 
                        content_length < 1000 and 
                        not response.content.startswith(b'%PDF')):
                        print(f"⚠️ Contenu non PDF reçu: {content_type}, taille: {content_length}")
                        continue
                    
                    # Sauvegarder le PDF
                    with open(pdf_path, 'wb') as f:
                        f.write(response.content)
                    
                    file_size = os.path.getsize(pdf_path)
                    print(f"✅ PDF téléchargé avec succès: {pdf_path} ({file_size} octets)")
                    return pdf_path
                
                elif status_code == 401:
                    # Renouveler le token et réessayer une fois
                    print("🔄 Token expiré, renouvellement...")
                    self.token_expires_at = 0
                    new_token = self.get_access_token()
                    method["headers"]["Authorization"] = f"Bearer {new_token}"
                    
                    # Nouvel essai avec le token renouvelé
                    response = requests.get(url, headers=method["headers"])
                    if response.status_code == 200:
                        with open(pdf_path, 'wb') as f:
                            f.write(response.content)
                        file_size = os.path.getsize(pdf_path)
                        print(f"✅ PDF téléchargé après renouvellement: {pdf_path} ({file_size} octets)")
                        return pdf_path
                
                print(f"❌ Échec du téléchargement par {name}: {status_code}")
                
            except Exception as e:
                print(f"❌ Exception lors du téléchargement par {name}: {e}")
        
        # Si toutes les méthodes ont échoué, créer un fichier vide
        print("❌ Toutes les méthodes de téléchargement ont échoué")
        with open(pdf_path, 'w') as f:
            f.write("")
        print(f"⚠️ Fichier vide créé: {pdf_path}")
        return pdf_path