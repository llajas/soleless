import os
import requests
import json
import logging
import time
from datetime import datetime, timedelta
import concurrent.futures
from requests.exceptions import RequestException
from urllib.parse import quote_plus
import shelve

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_WORKERS = 5
MAX_RETRIES = 5
MAX_RETRY_ATTEMPTS = 5
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
                    headers={**self.headers, "Content-Type": "application/json"},
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
            self.custom_field_mapping = {field['name']: field for field in updated_fields}
            logger.info("Custom field mapping created.")
        else:
            logger.error(f"Failed to fetch updated custom fields. Status Code: {response.status_code}, Response: {response.text}")

    def ensure_document_types(self):
        """Ensure document types exist in Paperless and create mappings"""
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
                    headers={**self.headers, "Content-Type": "application/json"},
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
            logger.info("Document type mapping created.")
        else:
            logger.error(f"Failed to fetch updated document types. Status Code: {response.status_code}, Response: {response.text}")

    def ensure_correspondents(self, correspondents_list):
        """Ensure all correspondents exist in Paperless and create mapping"""
        # Fetch existing correspondents
        existing_correspondent_names = self.get_existing_correspondents()

        # Create missing correspondents
        for name in correspondents_list:
            if name and name not in existing_correspondent_names:
                correspondent_id = self.create_correspondent(name)
                if correspondent_id:
                    existing_correspondent_names[name] = correspondent_id

        self.correspondent_mapping = existing_correspondent_names

    def get_existing_correspondents(self):
        """Fetch existing correspondents and return a name-to-ID mapping"""
        existing_correspondent_names = {}
        page = 1
        while True:
            response = requests.get(f"{self.url}/api/correspondents/?page={page}", headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if not results:
                    break
                for correspondent in results:
                    existing_correspondent_names[correspondent['name']] = correspondent['id']
                if not data.get('next'):
                    break
                page += 1
            else:
                logger.error(f"Failed to fetch correspondents. Status Code: {response.status_code}, Response: {response.text}")
                break
        return existing_correspondent_names
    
    def create_correspondent(self, name):
        """Create a new correspondent and return its ID"""
        payload = {"name": name}
        create_response = requests.post(
            f"{self.url}/api/correspondents/",
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload
        )
        if create_response.status_code == 201:
            new_correspondent = create_response.json()
            logger.info(f"Correspondent '{name}' created successfully.")
            return new_correspondent['id']
        elif create_response.status_code == 400 and "unique constraint" in create_response.text:
            # Correspondent already exists, fetch its ID
            existing_correspondents = self.get_existing_correspondents()
            return existing_correspondents.get(name)
        else:
            logger.error(f"Failed to create correspondent '{name}'. Status Code: {create_response.status_code}, Response: {create_response.text}")
            return None

    def ensure_tags(self, tags_list):
        """Ensure all tags exist in Paperless and create mapping"""
        # Fetch existing tags
        existing_tag_names = self.get_existing_tags()

        # Create missing tags
        for name in tags_list:
            if name and name not in existing_tag_names:
                tag_id = self.create_tag(name)
                if tag_id:
                    existing_tag_names[name] = tag_id

        self.tag_mapping = existing_tag_names

    def get_existing_tags(self):
        """Fetch existing tags and return a name-to-ID mapping"""
        existing_tag_names = {}
        page = 1
        while True:
            response = requests.get(f"{self.url}/api/tags/?page={page}", headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if not results:
                    break
                for tag in results:
                    existing_tag_names[tag['name']] = tag['id']
                if not data.get('next'):
                    break
                page += 1
            else:
                logger.error(f"Failed to fetch tags. Status Code: {response.status_code}, Response: {response.text}")
                break
        return existing_tag_names

    def create_tag(self, name):
        """Create a new tag and return its ID"""
        payload = {"name": name}
        create_response = requests.post(
            f"{self.url}/api/tags/",
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload
        )
        if create_response.status_code == 201:
            new_tag = create_response.json()
            logger.info(f"Tag '{name}' created successfully.")
            return new_tag['id']
        elif create_response.status_code == 400 and "unique constraint" in create_response.text:
            # Tag already exists, fetch its ID
            existing_tags = self.get_existing_tags()
            return existing_tags.get(name)
        else:
            logger.error(f"Failed to create tag '{name}'. Status Code: {create_response.status_code}, Response: {create_response.text}")
            return None

    def upload_document(self, document, custom_field_ids, correspondent_id, document_type_id, tag_ids):
        """Upload a document to Paperless"""
        # Extract the necessary data
        file_url = document.get('attachment', {}).get('url')
        file_name = document.get('id')
        document_type = document.get('type', 'other')  # Default to 'other' if type is not provided

        # Download the file from Shoeboxed
        if not file_url or not file_name:
            logger.error(f"Document {document.get('id')} is missing attachment information.")
            return None

        file_response = requests.get(file_url, headers={'User-Agent': 'Your Application Name'})
        if file_response.status_code != 200:
            logger.error(f"Failed to download file for document {document.get('id')}. Status Code: {file_response.status_code}")
            return None
        file_content = file_response.content

        # Prepare the upload payload
        # Determine the appropriate 'created' date based on document type
        if document.get('type') == 'business-card':
            created_date = document.get('uploaded')
        else:
            created_date = document.get('issued')

        files = [
            ('document', (file_name, file_content)),
            ('title', (None, document.get('title', file_name))),
            ('created', (None, created_date)),
        ]

        # Include the correspondent if available
        if correspondent_id:
            files.append(('correspondent', (None, str(correspondent_id))))

        # Include custom field IDs (without values)
        for field_id in custom_field_ids:
            files.append(('custom_fields', (None, str(field_id))))

        # Include document type ID
        if document_type_id:
            files.append(('document_type', (None, str(document_type_id))))
        else:
            logger.warning(f"Document type ID not found. Skipping document type association.")

        # Include tags
        for tag_id in tag_ids:
            files.append(('tags', (None, str(tag_id))))

        # Upload the document to Paperless
        upload_url = f"{self.url}/api/documents/post_document/"
        response = requests.post(upload_url, headers=self.headers, files=files)
        if response.status_code in [200, 202]:
            # Handle response based on status code
            if response.status_code == 202:
                # If response is JSON with task_id
                task_id = response.json().get('task_id')
            elif response.status_code == 200:
                # If response is a plain UUID string
                task_id = response.text.strip('"')
            logger.info(f"Document {document.get('id')} uploaded successfully. Task ID: {task_id}")
            return task_id
        else:
            logger.error(f"Failed to upload document {document.get('id')}. Status Code: {response.status_code}, Response: {response.text}")
            return None

    def poll_task_completion(self, task_id, timeout=600, interval=10):
        """Poll for task completion and get document ID"""
        task_url = f"{self.url}/api/tasks/?task_id={task_id}"
        start_time = time.time()

        while time.time() - start_time < timeout:
            response = requests.get(task_url, headers=self.headers)
            if response.status_code == 200:
                tasks = response.json()
                if tasks and isinstance(tasks, list) and 'related_document' in tasks[0]:
                    document_id = tasks[0]['related_document']
                    if document_id:
                        logger.info(f"Document ID obtained: {document_id}")
                        # Adding a sleep to give the database some time to finalize the transaction
                        time.sleep(2)
                        return document_id
            elif response.status_code == 404:
                logger.warning(f"Task not found (404). Retrying after {interval} seconds...")
            else:
                logger.error(f"Failed to get task status. Status Code: {response.status_code}, Response: {response.text}")
                return None
            time.sleep(interval)

        logger.error(f"Timeout exceeded while waiting for task {task_id} to complete.")
        return None

    def update_custom_fields(self, document_id, custom_field_values):
        """Update custom fields for a document"""
        # Filter out fields with null values
        filtered_custom_field_values = {field_id: value for field_id, value in custom_field_values.items() if value is not None}

        if not filtered_custom_field_values:
            logger.info(f"No valid custom fields to update for document {document_id}.")
            return True

        def operation():
            update_url = f"{self.url}/api/documents/{document_id}/"
            payload = {
                "custom_fields": [{"field": field_id, "value": value} for field_id, value in filtered_custom_field_values.items()]
            }
            response = requests.patch(update_url, headers={**self.headers, 'Content-Type': 'application/json'}, json=payload)
            if response.status_code in [200, 204]:
                logger.info(f"Custom fields for document {document_id} updated successfully.")
                return True
            else:
                raise requests.exceptions.RequestException(f"Failed to update custom fields for document {document_id}. Status Code: {response.status_code}, Response: {response.text}")

        try:
            return retry_operation(operation)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update document custom fields for {document_id} after retries: {e}")
            return False

    def fetch_failed_tasks(self):
        """Fetches all tasks with a FAILURE status from the Paperless API."""
        failed_tasks = []
        page = 1
        while True:
            task_url = f"{self.url}/api/tasks/?status=FAILURE&page={page}"
            response = requests.get(task_url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                tasks = data.get('results', [])
                if not tasks:
                    break
                failed_tasks.extend(tasks)
                if not data.get('next'):
                    break
                page += 1
            else:
                logger.error(f"Failed to fetch tasks. Status Code: {response.status_code}, Response: {response.text}")
                break
        return failed_tasks

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
        field_mapping = {}

        # Use the custom_field_mapping from the PaperlessClient
        custom_field_mapping = self.paperless_client.custom_field_mapping

        # Iterate through available custom fields and set values accordingly
        for field_name, field_info in custom_field_mapping.items():
            field_id = field_info['id']
            data_type = field_info['data_type']
            extra_data = field_info.get('extra_data', {})

            # Implement your field mapping logic here
            # For example:
            if field_name == 'Source Type' and data_type == 'select':
                value = document.get('source', {}).get('type')
                field_options = extra_data.get('select_options', [])
                if value and value.lower() in field_options:
                    index = field_options.index(value.lower())
                    field_mapping[field_id] = index
            elif field_name == 'Issued Date' and data_type == 'date':
                # Convert datetime to date format (YYYY-MM-DD)
                issued_date = document.get('issued')
                if issued_date:
                    try:
                        date_value = datetime.fromisoformat(issued_date.replace("Z", "+00:00")).date().isoformat()
                        field_mapping[field_id] = date_value
                    except ValueError:
                        logging.error(f"Invalid date format for 'issued': {issued_date}")
            elif field_name == 'Uploaded Date' and data_type == 'date':
                # Convert datetime to date format (YYYY-MM-DD)
                uploaded_date = document.get('uploaded')
                if uploaded_date:
                    try:
                        date_value = datetime.fromisoformat(uploaded_date.replace("Z", "+00:00")).date().isoformat()
                        field_mapping[field_id] = date_value
                    except ValueError:
                        logging.error(f"Invalid date format for 'uploaded': {uploaded_date}")
            elif field_name == 'Notes' and data_type == 'string':
                field_mapping[field_id] = document.get('notes')
            elif field_name == 'Attachment Name' and data_type == 'string':
                field_mapping[field_id] = document.get('attachment', {}).get('name')
            elif field_name == 'Attachment URL' and data_type == 'url':
                field_mapping[field_id] = document.get('attachment', {}).get('url')
            elif field_name == 'Shoeboxed Document ID' and data_type == 'string':
                field_mapping[field_id] = document.get('id')
            # Receipt specific fields
            elif field_name == 'Vendor' and data_type == 'string':
                field_mapping[field_id] = document.get('vendor')
            elif field_name == 'Invoice Number' and data_type == 'string':
                field_mapping[field_id] = document.get('invoiceNumber')
            elif field_name == 'Tax' and data_type == 'monetary':
                field_mapping[field_id] = document.get('tax')
            elif field_name == 'Total' and data_type == 'monetary':
                field_mapping[field_id] = document.get('total')
            elif field_name == 'Currency' and data_type == 'string':
                field_mapping[field_id] = document.get('currency')
            elif field_name == 'Payment Type' and data_type == 'select':
                value = document.get('paymentType', {}).get('type')
                field_options = extra_data.get('select_options', [])
                if value and value.lower() in field_options:
                    index = field_options.index(value.lower())
                    field_mapping[field_id] = index
            elif field_name == 'Card Last Four Digits' and data_type == 'string':
                field_mapping[field_id] = document.get('paymentType.cardLastFourDigits')
            # Business Card specific fields
            elif field_name == 'First Name' and data_type == 'string':
                field_mapping[field_id] = document.get('firstName')
            elif field_name == 'Surname' and data_type == 'string':
                field_mapping[field_id] = document.get('surname')
            elif field_name == 'Company' and data_type == 'string':
                field_mapping[field_id] = document.get('company')
            elif field_name == 'Email' and data_type == 'string':
                field_mapping[field_id] = document.get('email')
            elif field_name == 'Phone' and data_type == 'string':
                field_mapping[field_id] = document.get('phone')
            elif field_name == 'City' and data_type == 'string':
                field_mapping[field_id] = document.get('city')
            elif field_name == 'State' and data_type == 'string':
                field_mapping[field_id] = document.get('state')
            elif field_name == 'Zip' and data_type == 'string':
                field_mapping[field_id] = document.get('zip')
            elif field_name == 'Website' and data_type == 'url':
                field_mapping[field_id] = document.get('website')

        return field_mapping

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

        if correspondent_name:
            correspondent_name = correspondent_name.strip()
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
    
    def retry_failed_documents(self, failed_tasks):
        """Retry failed documents based on the tasks endpoint."""
        retry_counts = self.load_retry_counts()

        for task in failed_tasks:
            document_id = task.get('task_file_name')
            if not document_id:
                continue

            # Check if we've already retried this document too many times
            retry_count = retry_counts.get(document_id, 0)
            if retry_count >= MAX_RETRY_ATTEMPTS:
                logger.warning(f"Maximum retry attempts reached for document {document_id}. Skipping.")
                continue

            # Find the original document data
            original_document = next((doc for doc in self.all_documents if doc['id'] == document_id), None)
            if not original_document:
                logger.error(f"Original document data not found for document ID {document_id}.")
                continue

            logger.info(f"Retrying document {document_id} (Attempt {retry_count + 1})")

            # Retry processing the document
            result = self.process_document(original_document)

            if result:
                logger.info(f"Document {document_id} retried successfully.")
                # Optionally, remove the task from the failed tasks list
            else:
                logger.error(f"Document {document_id} retry failed.")
                # Increment the retry count
                retry_counts[document_id] = retry_count + 1

        # Save the updated retry counts
        self.save_retry_counts(retry_counts)

    def load_retry_counts(self):
        """Load retry counts from a persistent storage."""
        try:
            with shelve.open('retry_counts.db') as db:
                return dict(db)
        except Exception as e:
            logger.error(f"Failed to load retry counts: {e}")
            return {}

    def save_retry_counts(self, retry_counts):
        """Save retry counts to a persistent storage."""
        try:
            with shelve.open('retry_counts.db') as db:
                for key, value in retry_counts.items():
                    db[key] = value
        except Exception as e:
            logger.error(f"Failed to save retry counts: {e}")

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

    # Assign all_documents to the document_processor for access during retries
    document_processor.all_documents = all_documents

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
                else:
                    logger.error(f"Document {document['id']} failed to process.")
            except Exception as exc:
                logger.error(f"Document {document['id']} generated an exception: {exc}")

    # Step 4: Retry failed tasks
    failed_tasks = paperless_client.fetch_failed_tasks()
    if failed_tasks:
        logger.info(f"Retrying {len(failed_tasks)} failed document uploads...")
        document_processor.retry_failed_documents(failed_tasks)

    logger.info("Document migration completed successfully.")

if __name__ == "__main__":
    main()