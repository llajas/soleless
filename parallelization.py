import os
import requests
import json
import logging
import time
from datetime import datetime, timedelta
import concurrent.futures
from requests.exceptions import RequestException

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_WORKERS = 5
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
TOKEN_REFRESH_INTERVAL = timedelta(minutes=25)  # Refresh 5 minutes before expiration
PROGRESS_FILE = "progress.json"

# ===========================
# Utility Functions
# ===========================

def retry_operation(operation, *args, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY, **kwargs):
    """
    Generic retry wrapper for operations that may fail intermittently.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return operation(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            logger.error(f"Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Operation failed after {max_retries} attempts.")
                raise

def load_progress():
    """Load processing progress from file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as file:
            return json.load(file)
    return {}

def save_progress(progress):
    """Save current processing progress to a file."""
    with open(PROGRESS_FILE, "w") as file:
        json.dump(progress, file)

# ===========================
# Shoeboxed Client Class
# ===========================

class ShoeboxedClient:
    def __init__(self):
        self.client_id, self.client_secret, self.redirect_uri, self.authorization_code = self.check_env_vars()
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None  # datetime object

    def check_env_vars(self):
        """Check if Shoeboxed environment variables are set"""
        missing_env_vars = []
        client_id = os.getenv('SHOEBOXED_CLIENT_ID')
        client_secret = os.getenv('SHOEBOXED_CLIENT_SECRET')
        redirect_uri = os.getenv('SHOEBOXED_REDIRECT_URI')
        authorization_code = os.getenv('AUTHORIZATION_CODE')

        if not client_id:
            missing_env_vars.append('SHOEBOXED_CLIENT_ID')
        if not client_secret:
            missing_env_vars.append('SHOEBOXED_CLIENT_SECRET')
        if not redirect_uri:
            missing_env_vars.append('SHOEBOXED_REDIRECT_URI')
        if not authorization_code:
            missing_env_vars.append('AUTHORIZATION_CODE')

        if missing_env_vars:
            raise EnvironmentError(f"Missing environment variables: {', '.join(missing_env_vars)}")
        else:
            return client_id, client_secret, redirect_uri, authorization_code

    def authenticate(self):
        """Authenticate with Shoeboxed and obtain tokens"""
        self.access_token, self.refresh_token = self.exchange_code_for_access_token()
        self.token_expiry = datetime.now() + timedelta(minutes=30)

        if not self.access_token or not self.refresh_token:
            raise ValueError("Failed to obtain tokens from Shoeboxed.")

    def exchange_code_for_access_token(self):
        """Exchange authorization code for access and refresh tokens"""
        token_url = "https://id.shoeboxed.com/oauth/token"
        payload = {
            'code': self.authorization_code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
        }
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            response = requests.post(token_url, headers=headers, auth=(self.client_id, self.client_secret), data=payload)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            logger.info("Successfully obtained access and refresh tokens.")
            return access_token, refresh_token
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error while exchanging code: {e}")
            logger.error(f"Response status code: {response.status_code}")
            logger.error(f"Response body: {response.text}")
            return None, None

    def refresh_access_token(self):
        """Refresh the access token using the refresh token"""
        token_url = "https://id.shoeboxed.com/oauth/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json'
        }
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }

        try:
            response = requests.post(token_url, data=payload, headers=headers)
            response.raise_for_status()
            response_data = response.json()
            self.access_token = response_data.get('access_token')
            self.refresh_token = response_data.get('refresh_token')
            self.token_expiry = datetime.now() + timedelta(minutes=30)
            logger.info("Access token refreshed successfully.")
        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}")
            raise

    def ensure_token_validity(self):
        """Ensure the access token is still valid, refresh if necessary"""
        if datetime.now() >= self.token_expiry - timedelta(minutes=5):
            logger.info("Refreshing Shoeboxed access token...")
            self.refresh_access_token()

    def fetch_user_info(self):
        """Fetch user information from Shoeboxed API"""
        self.ensure_token_validity()
        url = "https://api.shoeboxed.com/v2/user"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': 'Your Application Name'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        user_info = response.json()
        account_ids = [account['id'] for account in user_info.get('accounts', [])]
        return account_ids

    def fetch_documents(self, account_id):
        """Fetch all documents for a given account"""
        self.ensure_token_validity()
        all_documents = []
        base_url = f"https://api.shoeboxed.com/v2/accounts/{account_id}/documents"
        offset = 0
        limit = 100

        while True:
            url = f"{base_url}?offset={offset}&limit={limit}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'User-Agent': 'Your Application Name'
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            documents = data.get('documents', [])
            if not documents:
                break
            all_documents.extend(documents)
            offset += limit
            logger.info(f"Fetched {len(all_documents)} documents so far.")

        return all_documents

# ===========================
# Paperless Client Class
# ===========================

class PaperlessClient:
    def __init__(self):
        self.token, self.url = self.check_env_vars()
        self.headers = {
            'Authorization': f'Token {self.token}',
            'User-Agent': 'Your Application Name'
        }
        self.custom_field_mapping = {}
        self.document_type_mapping = {}
        self.correspondent_mapping = {}
        self.tag_mapping = {}

    def check_env_vars(self):
        """Check if Paperless environment variables are set"""
        paperless_url = os.getenv('PAPERLESS_URL')
        paperless_token = os.getenv('PAPERLESS_AUTH_TOKEN')

        if not paperless_url or not paperless_token:
            raise EnvironmentError("Missing Paperless credentials in environment variables.")

        return paperless_token, paperless_url

    def ensure_resources(self):
        """Ensure custom fields and document types exist"""
        self.ensure_custom_fields()
        self.ensure_document_types()

    def ensure_custom_fields(self):
        """Ensure custom fields exist in Paperless and create mappings"""
        # Use your existing ensure_custom_fields function logic here
        # Then populate self.custom_field_mapping with field name to ID mapping

        # For brevity, assuming ensure_custom_fields function is implemented
        custom_fields_list = self._ensure_custom_fields()
        self.custom_field_mapping = {field['name']: field for field in custom_fields_list}

    def _ensure_custom_fields(self):
        """Implement the logic to ensure custom fields exist"""
        # Fetch existing custom fields
        response = requests.get(
            f"{self.url}/api/custom_fields/",
            headers=self.headers
        )
        if response.status_code == 200:
            existing_fields = response.json().get('results', [])
        else:
            logger.error(f"Failed to fetch custom fields. Status Code: {response.status_code}, Response: {response.text}")
            return []

        existing_field_names = {field['name']: field for field in existing_fields}

        # List of required custom fields (Same as your existing required_fields)
        required_fields = [
            {"name": "Source Type", "data_type": "select", "extra_data": '{"select_options": ["mail", "integration", "email", "web", "unknown"]}'},
            {"name": "Account ID", "data_type": "string", "extra_data": "null"},
            {"name": "Issued Date", "data_type": "date", "extra_data": "null"},
            {"name": "Uploaded Date", "data_type": "date", "extra_data": "null"},
            {"name": "Notes", "data_type": "string", "extra_data": "null"},
            {"name": "Attachment Name", "data_type": "string", "extra_data": "null"},
            {"name": "Attachment URL", "data_type": "url", "extra_data": "null"},
            {"name": "Shoeboxed Document ID", "data_type": "string", "extra_data": "null"},
            # Receipt fields
            {"name": "Invoice Number", "data_type": "string", "extra_data": "null"},
            {"name": "Tax", "data_type": "monetary", "extra_data": '{"default_currency": "USD"}'},
            {"name": "Total", "data_type": "monetary", "extra_data": '{"default_currency": "USD"}'},
            {"name": "Currency", "data_type": "string", "extra_data": "null"},
            {"name": "Payment Type", "data_type": "select", "extra_data": '{"select_options": ["credit-card", "cash", "paypal", "other", "check"]}'},
            {"name": "Card Last Four Digits", "data_type": "string", "extra_data": "null"},
            {"name": "Vendor", "data_type": "string", "extra_data": "null"},
            # Business Card fields
            {"name": "Website", "data_type": "url", "extra_data": "null"},
            {"name": "City", "data_type": "string", "extra_data": "null"},
            {"name": "State", "data_type": "string", "extra_data": "null"},
            {"name": "Zip", "data_type": "string", "extra_data": "null"},
            {"name": "Email", "data_type": "string", "extra_data": "null"},
            {"name": "Phone", "data_type": "string", "extra_data": "null"},
            {"name": "Company", "data_type": "string", "extra_data": "null"},
            {"name": "Surname", "data_type": "string", "extra_data": "null"},
            {"name": "First Name", "data_type": "string", "extra_data": "null"}
        ]

        # Create missing fields
        for field in required_fields:
            existing_field = existing_field_names.get(field['name'])
            if not existing_field:
                payload = {
                    "name": field['name'],
                    "data_type": field['data_type'],
                    "extra_data": json.loads(field['extra_data']) if field['extra_data'] != "null" else None
                }
                create_response = requests.post(
                    f"{self.url}/api/custom_fields/",
                    headers=self.headers,
                    json=payload
                )
                if create_response.status_code == 201:
                    logger.info(f"Successfully created custom field '{field['name']}'.")
                else:
                    logger.error(f"Failed to create custom field '{field['name']}'. Status Code: {create_response.status_code}, Response: {create_response.text}")

        # Fetch the updated list of custom fields
        response = requests.get(
            f"{self.url}/api/custom_fields/",
            headers=self.headers
        )
        if response.status_code == 200:
            updated_fields = response.json().get('results', [])
            logger.info("Fetched updated custom fields after creation.")
            return updated_fields
        else:
            logger.error(f"Failed to fetch updated custom fields. Status Code: {response.status_code}, Response: {response.text}")
            return []

    def ensure_document_types(self):
        """Ensure document types exist in Paperless and create mappings"""
        # Similar to your existing ensure_document_types function
        # Populate self.document_type_mapping with type name to ID mapping

        # Fetch existing document types
        response = requests.get(f"{self.url}/api/document_types/", headers=self.headers)
        if response.status_code == 200:
            existing_types = response.json().get('results', [])
        else:
            logger.error(f"Failed to fetch document types. Status Code: {response.status_code}, Response: {response.text}")
            return

        existing_type_names = {doc_type['name']: doc_type for doc_type in existing_types}

        # List of required document types
        required_types = [
            {"name": "Business Cards", "matching_algorithm": 0, "is_insensitive": True},
            {"name": "Documents", "matching_algorithm": 0, "is_insensitive": True},
            {"name": "Receipts", "matching_algorithm": 0, "is_insensitive": True}
        ]

        # Create missing document types
        for doc_type in required_types:
            existing_type = existing_type_names.get(doc_type['name'])
            if not existing_type:
                create_response = requests.post(
                    f"{self.url}/api/document_types/",
                    headers=self.headers,
                    json=doc_type
                )
                if create_response.status_code == 201:
                    logger.info(f"Successfully created document type '{doc_type['name']}'.")
                else:
                    logger.error(f"Failed to create document type '{doc_type['name']}'. Status Code: {create_response.status_code}, Response: {create_response.text}")

        # Fetch the updated list of document types
        response = requests.get(f"{self.url}/api/document_types/", headers=self.headers)
        if response.status_code == 200:
            updated_types = response.json().get('results', [])
            self.document_type_mapping = {doc_type['name']: doc_type['id'] for doc_type in updated_types}
            logger.info("Fetched updated document types after creation.")
        else:
            logger.error(f"Failed to fetch updated document types. Status Code: {response.status_code}, Response: {response.text}")

    def ensure_correspondents(self, correspondents_list):
        """Ensure all correspondents exist in Paperless and create mapping"""
        # Fetch existing correspondents
        response = requests.get(f"{self.url}/api/correspondents/", headers=self.headers)
        if response.status_code == 200:
            existing_correspondents = response.json().get('results', [])
        else:
            logger.error(f"Failed to fetch correspondents. Status Code: {response.status_code}, Response: {response.text}")
            existing_correspondents = []

        existing_correspondent_names = {correspondent['name']: correspondent['id'] for correspondent in existing_correspondents}

        # Create missing correspondents
        for name in correspondents_list:
            if name and name not in existing_correspondent_names:
                payload = {"name": name}
                create_response = requests.post(f"{self.url}/api/correspondents/", headers=self.headers, json=payload)
                if create_response.status_code == 201:
                    new_correspondent = create_response.json()
                    existing_correspondent_names[name] = new_correspondent['id']
                    logger.info(f"Correspondent '{name}' created successfully.")
                else:
                    logger.error(f"Failed to create correspondent '{name}'. Status Code: {create_response.status_code}, Response: {create_response.text}")

        self.correspondent_mapping = existing_correspondent_names

    def ensure_tags(self, tags_list):
        """Ensure all tags exist in Paperless and create mapping"""
        # Fetch existing tags
        response = requests.get(f"{self.url}/api/tags/", headers=self.headers)
        if response.status_code == 200:
            existing_tags = response.json().get('results', [])
        else:
            logger.error(f"Failed to fetch tags. Status Code: {response.status_code}, Response: {response.text}")
            existing_tags = []

        existing_tag_names = {tag['name']: tag['id'] for tag in existing_tags}

        # Create missing tags
        for name in tags_list:
            if name and name not in existing_tag_names:
                payload = {"name": name}
                create_response = requests.post(f"{self.url}/api/tags/", headers=self.headers, json=payload)
                if create_response.status_code == 201:
                    new_tag = create_response.json()
                    existing_tag_names[name] = new_tag['id']
                    logger.info(f"Tag '{name}' created successfully.")
                else:
                    logger.error(f"Failed to create tag '{name}'. Status Code: {create_response.status_code}, Response: {create_response.text}")

        self.tag_mapping = existing_tag_names

    def upload_document(self, document, custom_field_ids, correspondent_id, document_type_id, tag_ids):
        """Upload a document to Paperless"""
        # Implement logic similar to your existing upload_document_to_paperless function
        # Use the mappings and IDs provided
        pass  # Implement logic here

    def poll_task_completion(self, task_id):
        """Poll for task completion and get document ID"""
        # Implement logic similar to your existing poll_for_task_completion function
        pass  # Implement logic here

    def update_custom_fields(self, document_id, custom_field_values):
        """Update custom fields for a document"""
        # Implement logic similar to your existing update_document_custom_fields function
        pass  # Implement logic here

    def fetch_failed_tasks(self):
        """Fetch failed tasks from Paperless"""
        # Implement logic similar to your existing fetch_failed_tasks function
        pass  # Implement logic here

# ===========================
# Document Processor Class
# ===========================

class DocumentProcessor:
    def __init__(self, shoeboxed_client, paperless_client):
        self.shoeboxed_client = shoeboxed_client
        self.paperless_client = paperless_client

    def pre_process_metadata(self, all_documents):
        """Pre-process all documents to extract correspondents and tags"""
        correspondents_set = set()
        tags_set = set()

        for document in all_documents:
            # Extract correspondent based on document type
            correspondent_name = self.get_correspondent_name(document)
            if correspondent_name:
                correspondents_set.add(correspondent_name)

            # Extract tags
            tags = self.get_tags(document)
            tags_set.update(tags)

        # Ensure correspondents and tags exist in Paperless
        self.paperless_client.ensure_correspondents(list(correspondents_set))
        self.paperless_client.ensure_tags(list(tags_set))

    def process_document(self, document):
        """Process a single document"""
        try:
            # Map custom fields
            custom_field_values = self.map_custom_fields(document)
            custom_field_ids = list(custom_field_values.keys())

            # Determine document type
            document_type_name = self.get_document_type_name(document)
            document_type_id = self.paperless_client.document_type_mapping.get(document_type_name)

            # Get correspondent ID
            correspondent_name = self.get_correspondent_name(document)
            correspondent_id = self.paperless_client.correspondent_mapping.get(correspondent_name)

            # Get tag IDs
            tags = self.get_tags(document)
            tag_ids = [self.paperless_client.tag_mapping.get(tag) for tag in tags if tag in self.paperless_client.tag_mapping]

            # Upload document
            task_id = self.paperless_client.upload_document(
                document,
                custom_field_ids,
                correspondent_id,
                document_type_id,
                tag_ids
            )
            if not task_id:
                logger.error(f"Failed to upload document {document['id']}.")
                return False

            # Poll for task completion
            document_id = self.paperless_client.poll_task_completion(task_id)
            if not document_id:
                logger.error(f"Failed to process document {document['id']}.")
                return False

            # Update custom fields
            self.paperless_client.update_custom_fields(document_id, custom_field_values)

            logger.info(f"Document {document['id']} processed successfully.")
            return True
        except Exception as e:
            logger.error(f"Error processing document {document['id']}: {e}")
            return False

    def map_custom_fields(self, document):
        """Map Shoeboxed document metadata to Paperless custom fields"""
        # Implement logic similar to your existing map_custom_fields function
        # Use self.paperless_client.custom_field_mapping
        pass  # Implement logic here

    def get_document_type_name(self, document):
        """Determine the document type name based on Shoeboxed document type"""
        shoeboxed_doc_type = document.get("type")
        document_type_name_map = {
            "business-card": "Business Cards",
            "other": "Documents",
            "receipt": "Receipts"
        }
        return document_type_name_map.get(shoeboxed_doc_type, "Documents")

    def get_correspondent_name(self, document):
        """Extract correspondent name based on document type"""
        document_type = document.get("type", "other")

        if document_type == "receipt":
            correspondent_name = document.get("vendor")
        elif document_type == "business-card":
            correspondent_name = document.get("company")
        elif document_type == "other":
            correspondent_name = document.get("name")
        else:
            correspondent_name = None

        return correspondent_name

    def get_tags(self, document):
        """Get tags from the document"""
        tags = set()

        if document.get('type') == 'receipt' and document.get('categories'):
            categories = document.get('categories', [])
            tags.update(categories)

        # Check for envelope ID tag for documents sourced via mail
        if document.get('source', {}).get('type') == 'mail':
            envelope_id = document.get('source', {}).get('envelope')
            if envelope_id:
                tags.add(envelope_id.upper())

        return tags

# ===========================
# Main Function
# ===========================

def main():
    # Step 1: Initialize clients
    try:
        shoeboxed_client = ShoeboxedClient()
        shoeboxed_client.authenticate()
        logger.info("Shoeboxed authentication successful.")
    except Exception as e:
        logger.error(f"Shoeboxed authentication failed: {e}")
        exit(1)

    try:
        paperless_client = PaperlessClient()
        paperless_client.ensure_resources()
        logger.info("Paperless resources ensured.")
    except Exception as e:
        logger.error(f"Paperless initialization failed: {e}")
        exit(1)

    # Step 2: Fetch user info from Shoeboxed
    try:
        account_ids = shoeboxed_client.fetch_user_info()
    except Exception as e:
        logger.error(f"Failed to fetch Shoeboxed user info: {e}")
        exit(1)

    # Step 3: Process documents
    progress = load_progress()
    current_batch = progress.get('current_batch', 0)
    document_processor = DocumentProcessor(shoeboxed_client, paperless_client)

    all_documents = []

    for account_id in account_ids:
        try:
            documents = shoeboxed_client.fetch_documents(account_id)
            all_documents.extend(documents)
        except Exception as e:
            logger.error(f"Failed to fetch documents for account {account_id}: {e}")
            continue

    # Pre-process metadata to avoid race conditions
    document_processor.pre_process_metadata(all_documents)

    # Process documents concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_document = {
            executor.submit(document_processor.process_document, document): document for document in all_documents
        }

        for future in concurrent.futures.as_completed(future_to_document):
            document = future_to_document[future]
            try:
                result = future.result()
                if result:
                    logger.info(f"Document {document['id']} processed successfully.")
                    current_batch += 1
                    progress['current_batch'] = current_batch
                    save_progress(progress)
            except Exception as exc:
                logger.error(f"Document {document['id']} generated an exception: {exc}")

    # Step 4: Retry failed tasks
    failed_tasks = paperless_client.fetch_failed_tasks()
    if failed_tasks:
        logger.info(f"Retrying {len(failed_tasks)} failed document uploads...")
        # Implement retry logic similar to your existing code

    logger.info("Document migration completed successfully.")

if __name__ == "__main__":
    main()
