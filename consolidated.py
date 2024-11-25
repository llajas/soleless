import os
import requests
import json
import logging
from urllib.parse import quote_plus
import time  # For polling
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paperless Environment Variables
PAPERLESS_URL = os.getenv('PAPERLESS_URL')
PAPERLESS_TOKEN = os.getenv('PAPERLESS_AUTH_TOKEN')

# Shoeboxed Environment Variables
SHOEBOXED_CLIENT_ID = os.getenv('SHOEBOXED_CLIENT_ID')
SHOEBOXED_CLIENT_SECRET = os.getenv('SHOEBOXED_CLIENT_SECRET')
SHOEBOXED_REDIRECT_URI = os.getenv('SHOEBOXED_REDIRECT_URI')

# Access Token and Refresh Token variables for Shoeboxed
ACCESS_TOKEN_EXPIRATION = timedelta(minutes=30)  # Assuming 30 minutes validity
TOKEN_REFRESH_INTERVAL = ACCESS_TOKEN_EXPIRATION - timedelta(minutes=5)  # Refresh 5 minutes before expiration

# Progress File for resuming from last run
PROGRESS_FILE = "progress.json"

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
# Paperless Functions
# ===========================

def check_paperless_env_vars():
    """Check if Paperless environment variables are set"""
    paperless_url = os.getenv('PAPERLESS_URL')
    paperless_token = os.getenv('PAPERLESS_AUTH_TOKEN')

    if not paperless_url or not paperless_token:
        raise EnvironmentError("Missing Paperless credentials in environment variables.")

    return paperless_token, paperless_url

def ensure_custom_fields(paperless_url, paperless_token):
    """Ensure all required custom fields are created if they do not exist"""
    # Fetch existing custom fields
    response = requests.get(
        f"{paperless_url}/api/custom_fields/",
        headers={"Authorization": f"Token {paperless_token}"}
    )
    if response.status_code == 200:
        existing_fields = response.json().get('results', [])
    else:
        logger.error(f"Failed to fetch custom fields. Status Code: {response.status_code}, Response: {response.text}")
        return []

    existing_field_names = {field['name']: field for field in existing_fields}

    # List of required custom fields
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
        {"name": "Tax", "data_type": "monetary", "extra_data": '{"default_currency": "usd"}'},
        {"name": "Total", "data_type": "monetary", "extra_data": '{"default_currency": "usd"}'},
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

    missing_fields = []
    for field in required_fields:
        existing_field = existing_field_names.get(field['name'])
        if not existing_field:
            payload = {
                "name": field['name'],
                "data_type": field['data_type'],
                "extra_data": json.loads(field['extra_data']) if field['extra_data'] != "null" else None
            }
            create_response = requests.post(
                f"{paperless_url}/api/custom_fields/",
                headers={
                    "Authorization": f"Token {paperless_token}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            if create_response.status_code == 201:
                logger.info(f"Successfully created custom field '{field['name']}'.")
                missing_fields.append(field['name'])
            else:
                logger.error(f"Failed to create custom field '{field['name']}'. Status Code: {create_response.status_code}, Response: {create_response.text}")

    if not missing_fields:
        logger.info("All required custom fields already exist.")
    else:
        logger.info(f"Created missing fields: {missing_fields}.")

    # Fetch the updated list of custom fields
    response = requests.get(
        f"{paperless_url}/api/custom_fields/",
        headers={"Authorization": f"Token {paperless_token}"}
    )

    if response.status_code == 200:
        updated_fields = response.json().get('results', [])
        logger.info("Fetched updated custom fields after creation.")
        return updated_fields
    else:
        logger.error(f"Failed to fetch updated custom fields. Status Code: {response.status_code}, Response: {response.text}")
        return []
    
def ensure_document_types(paperless_url, headers):
    """
    Ensure all required document types are created if they do not exist.
    Returns a list of all document types (existing and newly created).
    """
    # Fetch existing document types
    response = requests.get(f"{paperless_url}/api/document_types/", headers=headers)
    if response.status_code == 200:
        existing_types = response.json().get('results', [])
    else:
        logger.error(f"Failed to fetch document types. Status Code: {response.status_code}, Response: {response.text}")
        return []

    existing_type_names = {doc_type['name']: doc_type for doc_type in existing_types}

    # List of required document types
    required_types = [
        {"name": "Business Cards", "matching_algorithm": 0, "is_insensitive": True},
        {"name": "Documents", "matching_algorithm": 0, "is_insensitive": True},
        {"name": "Receipts", "matching_algorithm": 0, "is_insensitive": True}
    ]

    missing_types = []
    for doc_type in required_types:
        existing_type = existing_type_names.get(doc_type['name'])
        if not existing_type:
            # Create the document type if it does not exist
            create_response = requests.post(
                f"{paperless_url}/api/document_types/",
                headers=headers,
                json=doc_type
            )
            if create_response.status_code == 201:
                logger.info(f"Successfully created document type '{doc_type['name']}'.")
                missing_types.append(create_response.json())
            else:
                logger.error(f"Failed to create document type '{doc_type['name']}'. Status Code: {create_response.status_code}, Response: {create_response.text}")
        else:
            logger.info(f"Document type '{doc_type['name']}' already exists.")
            missing_types.append(existing_type)

    # Fetch the updated list of document types
    response = requests.get(f"{paperless_url}/api/document_types/", headers=headers)
    if response.status_code == 200:
        updated_types = response.json().get('results', [])
        logger.info("Fetched updated document types after creation.")
        return updated_types
    else:
        logger.error(f"Failed to fetch updated document types. Status Code: {response.status_code}, Response: {response.text}")
        return []


def create_custom_field_mapping(custom_fields_list):
    """
    Creates a mapping from custom field names to their details.
    """
    mapping = {}
    for field in custom_fields_list:
        field_name = field['name']
        mapping[field_name] = field
    return mapping

def create_document_type_mapping(document_types_list):
    """
    Creates a mapping from document type names to their details.
    """
    mapping = {}
    for doc_type in document_types_list:
        doc_type_name = doc_type['name']
        mapping[doc_type_name] = doc_type
    return mapping

def assign_document_type(paperless_url, headers, document_id, document_type_name, document_type_mapping):
    """
    Assigns a document type to a document, if it exists in the provided mapping.
    """
    document_type = document_type_mapping.get(document_type_name)
    if document_type:
        response = requests.patch(
            f"{paperless_url}/api/documents/{document_id}/",
            headers=headers,
            json={"document_type": document_type['id']}
        )
        if response.status_code != 200:
            logger.error(f"Failed to assign document type '{document_type_name}' to document {document_id}. Status Code: {response.status_code}, Response: {response.text}")
        else:
            logger.info(f"Document type '{document_type_name}' assigned to document {document_id}.")
    else:
        logger.error(f"Document type '{document_type_name}' not found in the mapping. Failed to assign to document {document_id}.")

# ===========================
# Upload Document Function
# ===========================

def upload_document_to_paperless(document, custom_field_ids, paperless_url, paperless_token, correspondent_mapping, document_type_name, document_types, tags):
    """
    Uploads a document to Paperless and associates custom fields, document types, correspondents, and tags.
    """
    # Extract the necessary data
    file_url = document.get('attachment', {}).get('url')
    file_name = document.get('attachment', {}).get('name')
    document_type = document.get('type', 'other')  # Default to 'other' if type is not provided

    # Determine correspondent based on document type
    if document_type == 'receipt':
        correspondent_name = document.get('vendor')
    elif document_type == 'business-card':
        correspondent_name = document.get('company')
    elif document_type == 'other':
        correspondent_name = document.get('name')
    else:
        correspondent_name = None

    # Log if no correspondent found
    if not correspondent_name:
        logger.warning(f"No correspondent found for document {document.get('id')} of type '{document_type}'. Proceeding without correspondent.")

    # Ensure the correspondent is created or fetched from Paperless
    correspondent_id = None
    if correspondent_name:
        correspondent_id = correspondent_mapping.get(correspondent_name)
        if not correspondent_id:
            # Create the correspondent if it doesn't exist
            correspondent_id = create_correspondent(correspondent_name, paperless_url, paperless_token)
            if correspondent_id:
                correspondent_mapping[correspondent_name] = correspondent_id

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
        files.append(('correspondent', (None, correspondent_id)))

    # Include custom field IDs (without values)
    for field_id in custom_field_ids:
        files.append(('custom_fields', (None, str(field_id))))

    # Include document type ID
    document_type_id = document_types.get(document_type_name)
    if document_type_id:
        files.append(('document_type', (None, str(document_type_id))))
    else:
        logger.warning(f"Document type '{document_type_name}' not found. Skipping document type association.")

    # Include tags
    for tag in tags:
        files.append(('tags', (None, str(tag))))

    # Upload the document to Paperless
    upload_url = f"{paperless_url}/api/documents/post_document/"
    headers = {
        'Authorization': f'Token {paperless_token}',
        'User-Agent': 'Your Application Name'
    }
    response = requests.post(upload_url, headers=headers, files=files)
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

def poll_for_task_completion(task_id, paperless_url, paperless_token, timeout=600, interval=10):
    """
    Polls the Paperless API for task completion and returns the document ID.
    Args:
        task_id (str): Task UUID returned after uploading the document.
        paperless_url (str): Paperless API base URL.
        paperless_token (str): Authorization token for the Paperless API.
        timeout (int, optional): The maximum time (in seconds) to wait for the task to complete. Defaults to 600.
        interval (int, optional): Time interval (in seconds) between polling attempts. Defaults to 10.
    Returns:
        str: The document ID if the task completed successfully, None otherwise.
    """
    task_url = f"{paperless_url}/api/tasks/?task_id={task_id}"
    headers = {
        "Authorization": f"Token {paperless_token}",
        "Accept": "application/json"
    }
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(task_url, headers=headers)
        if response.status_code == 200:
            task_data = response.json()
            if task_data and isinstance(task_data, list) and 'related_document' in task_data[0]:
                document_id = task_data[0]['related_document']
                if document_id:
                    logging.info(f"Document ID obtained: {document_id}")
                    return document_id
        elif response.status_code == 404:
            logging.warning(f"Task not found (404). Retrying after {interval} seconds...")
        else:
            logging.error(f"Failed to get task status. Status Code: {response.status_code}, Response: {response.text}")
            return None
        
        # Sleep for the specified interval before polling again
        time.sleep(interval)

    logging.error(f"Timeout exceeded while waiting for task {task_id} to complete.")
    return None

# Updated function to send only non-null fields
def update_document_custom_fields(document_id, custom_field_values, paperless_url, paperless_token):
    """
    Update the custom fields for a given document in Paperless.
    Args:
        document_id (str): The ID of the document to update.
        custom_field_values (dict): The custom fields to be updated.
        paperless_url (str): URL for the Paperless API.
        paperless_token (str): Token for Paperless authentication.
    Returns:
        bool: True if the update was successful, False otherwise.
    """
    # Filter out fields with `null` values
    filtered_custom_field_values = {field_id: value for field_id, value in custom_field_values.items() if value is not None}

    if not filtered_custom_field_values:
        logging.info(f"No valid custom fields to update for document {document_id}.")
        return True

    update_url = f"{paperless_url}/api/documents/{document_id}/"
    headers = {
        "Authorization": f"Token {paperless_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "custom_fields": [{"field": field_id, "value": value} for field_id, value in filtered_custom_field_values.items()]
    }

    response = requests.patch(update_url, headers=headers, json=payload)
    if response.status_code in [200, 204]:
        logging.info(f"Custom fields for document {document_id} updated successfully.")
        return True
    else:
        logging.error(f"Failed to update custom fields for document {document_id}. Status Code: {response.status_code}, Response: {response.text}")
        return False

def create_or_fetch_tag(paperless_url, paperless_token, tag_name):
    """
    Ensures a tag with the given name exists in Paperless and returns the tag ID.
    """
    # Fetch existing tags
    response = requests.get(
        f"{paperless_url}/api/tags/",
        headers={"Authorization": f"Token {paperless_token}"}
    )
    if response.status_code == 200:
        tags = response.json().get('results', [])
        for tag in tags:
            if tag['name'] == tag_name:
                return tag['id']
    else:
        logger.error(f"Failed to fetch tags. Status Code: {response.status_code}, Response: {response.text}")
        return None

    # Create a new tag if it does not exist
    payload = {"name": tag_name}
    create_response = requests.post(
        f"{paperless_url}/api/tags/",
        headers={
            "Authorization": f"Token {paperless_token}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    if create_response.status_code == 201:
        logger.info(f"Tag '{tag_name}' created successfully.")
        return create_response.json().get('id')
    else:
        logger.error(f"Failed to create tag '{tag_name}'. Status Code: {create_response.status_code}, Response: {create_response.text}")
        return None

# ===========================
# Ensure Correspondents Function
# ===========================

def ensure_correspondents(paperless_url, paperless_token, document_correspondents):
    """
    Ensure all correspondents are fetched or created in Paperless.
    Returns a dictionary mapping correspondent names to their IDs.
    """
    # Fetch existing correspondents
    response = requests.get(
        f"{paperless_url}/api/correspondents/",
        headers={"Authorization": f"Token {paperless_token}"}
    )
    # Log the response details for better debugging
    logger.info(f"Fetching correspondents from Paperless URL: {paperless_url}/api/correspondents/")
    logger.info(f"Response Status Code: {response.status_code}")
    logger.info(f"Response Text: {response.text}")
    # Check the status code and return appropriately
    if response.status_code == 200:
        existing_correspondents = response.json().get('results', [])
    elif response.status_code == 401:
        logger.error("Unauthorized access. Check your Paperless token.")
        return {}
    elif response.status_code == 404:
        logger.error("Endpoint not found. Check your Paperless URL.")
        return {}
    else:
        logger.error(f"Failed to fetch correspondents. Status Code: {response.status_code}, Response: {response.text}")
        return {}

    correspondent_mapping = {correspondent['name']: correspondent['id'] for correspondent in existing_correspondents}

    # Create correspondents if they do not exist
    for correspondent_name in document_correspondents:
        if correspondent_name and correspondent_name not in correspondent_mapping:
            correspondent_id = create_correspondent(correspondent_name, paperless_url, paperless_token)
            if correspondent_id:
                correspondent_mapping[correspondent_name] = correspondent_id
            else:
                logger.warning(f"Unable to create correspondent '{correspondent_name}'. Skipping.")

    return correspondent_mapping

# ===========================
# Create Correspondents Function
# ===========================

def create_correspondent(name, paperless_url, paperless_token):
    """
    Create a new correspondent in Paperless.
    Returns the correspondent ID if creation is successful, otherwise returns None.
    """
    payload = {
        "name": name
    }
    response = requests.post(
        f"{paperless_url}/api/correspondents/",
        headers={
            "Authorization": f"Token {paperless_token}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    if response.status_code == 201:
        correspondent_id = response.json().get('id')
        logger.info(f"Successfully created correspondent '{name}' with ID: {correspondent_id}")
        return correspondent_id
    else:
        logger.error(f"Failed to create correspondent '{name}'. Status Code: {response.status_code}, Response: {response.text}")
        return None

# ===========================
# Shoeboxed Functions
# ===========================

def check_shoeboxed_env_vars():
    """Check if Shoeboxed environment variables are set"""
    missing_env_vars = []
    client_id = os.getenv('SHOEBOXED_CLIENT_ID')
    client_secret = os.getenv('SHOEBOXED_CLIENT_SECRET')
    redirect_uri = os.getenv('SHOEBOXED_REDIRECT_URI')

    if not client_id:
        missing_env_vars.append('SHOEBOXED_CLIENT_ID')
    if not client_secret:
        missing_env_vars.append('SHOEBOXED_CLIENT_SECRET')
    if not redirect_uri:
        missing_env_vars.append('SHOEBOXED_REDIRECT_URI')

    if missing_env_vars:
        raise EnvironmentError(f"Error: Missing environment variables: {', '.join(missing_env_vars)}")
    else:
        return client_id, client_secret, redirect_uri

def generate_auth_url(client_id, redirect_uri):
    base_url = "https://id.shoeboxed.com/oauth/authorize"
    response_type = "code"
    scope = "all"
    auth_url = f"{base_url}?client_id={client_id}&response_type={response_type}&scope={scope}&redirect_uri={quote_plus(redirect_uri)}"
    return auth_url

def exchange_code_for_access_token(client_id, client_secret, authorization_code, redirect_uri):
    """Exchange authorization code for access and refresh tokens"""
    token_url = "https://id.shoeboxed.com/oauth/token"
    payload = {
        'code': authorization_code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    }
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        response = requests.post(token_url, headers=headers, auth=(client_id, client_secret), data=payload)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')

        if not access_token or not refresh_token:
            logger.error("Failed to obtain valid tokens from Shoeboxed response.")
            return None, None

        logger.info("Successfully obtained access and refresh tokens.")
        return access_token, refresh_token

    except requests.exceptions.HTTPError as e:
        logger.error(f"Error while exchanging code: {e}")
        logger.error(f"Response status code: {response.status_code}")
        logger.error(f"Response body: {response.text}")
        return None, None

def handle_token_response(token_response):
    access_token = token_response.get('access_token')
    refresh_token = token_response.get('refresh_token')
    logger.info(f"Access Token obtained.")
    return access_token, refresh_token

def refresh_access_token(client_id, client_secret, refresh_token):
    """
    Refreshes the access token using the provided refresh token.
    Args:
        client_id (str): The client ID of your application.
        client_secret (str): The client secret of your application.
        refresh_token (str): The refresh token to exchange for a new access token.
    Returns:
        Tuple: (new_access_token, new_refresh_token)
    """
    token_url = "https://id.shoeboxed.com/oauth/token"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',  # Required for OAuth
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json'
    }
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }

    try:
        response = requests.post(token_url, data=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        new_access_token = response_data.get('access_token')
        new_refresh_token = response_data.get('refresh_token')

        if not new_access_token or not new_refresh_token:
            raise ValueError("Invalid response received from Shoeboxed API.")

        logging.info(f"Access Token refreshed successfully.")
        return new_access_token, new_refresh_token

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to refresh access token. RequestException: {e}")
        raise
    except ValueError as e:
        logging.error(f"Failed to refresh access token. ValueError: {e}")
        raise

def authenticate_shoeboxed():
    """Authenticate with Shoeboxed and obtain tokens"""
    client_id = os.getenv('SHOEBOXED_CLIENT_ID')
    client_secret = os.getenv('SHOEBOXED_CLIENT_SECRET')
    redirect_uri = os.getenv('SHOEBOXED_REDIRECT_URI')
    shoeboxed_auth_code = os.getenv('AUTHORIZATION_CODE')

    # Check for missing environment variables
    if not client_id or not client_secret or not redirect_uri:
        raise EnvironmentError("Missing Shoeboxed credentials in environment variables.")

    # Check if AUTHORIZATION_CODE is provided in the environment
    if shoeboxed_auth_code:
        logger.info("Using authorization code from environment variable.")
    else:
        # Generate authentication URL and prompt for manual input
        auth_url = generate_auth_url(client_id, redirect_uri)
        print("Please visit this URL to authorize:", auth_url)
        shoeboxed_auth_code = input("Please enter the Shoeboxed authorization code: ")

    # Exchange code for access and refresh tokens
    access_token, refresh_token = exchange_code_for_access_token(client_id, client_secret, shoeboxed_auth_code, redirect_uri)

    if access_token and refresh_token:
        return access_token, refresh_token
    else:
        raise ValueError("Failed to obtain tokens from Shoeboxed.")


def fetch_user_info(access_token):
    """
    Fetches user information from the Shoeboxed API, including account IDs.
    """
    url = "https://api.shoeboxed.com/v2/user"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Your Application Name'
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # This will automatically raise an error for non-2xx responses
    user_info = response.json()
    account_ids = [account['id'] for account in user_info.get('accounts', [])]
    return account_ids

def get_shoeboxed_tokens(client_id, client_secret, refresh_token):
    """
    Fetch or refresh Shoeboxed access tokens using the refresh token.
    Args:
        client_id (str): Client ID for Shoeboxed.
        client_secret (str): Client Secret for Shoeboxed.
        refresh_token (str): Refresh token to get new access token.
    Returns:
        tuple: access_token and new refresh_token
    """
    try:
        # Refresh access token using the refresh token
        new_tokens = refresh_access_token(client_id, client_secret, refresh_token)
        logger.info("Access token successfully refreshed.")
        return new_tokens
    except Exception as e:
        logger.error(f"Failed to refresh access token: {e}")
        exit(1)  # Exit if unable to refresh, or consider handling retry logic

def fetch_all_documents(account_id, access_token):
    """
    Fetches all documents for a given account from the Shoeboxed API, handling pagination based on .totalCount.
    """
    all_documents = []
    base_url = f"https://api.shoeboxed.com/v2/accounts/{account_id}/documents"
    offset = 0
    limit = 100  # Assuming 100 documents per request is the maximum allowed by the API

    # Function to perform a single request and get documents
    def fetch_documents_chunk(offset, limit):
        url = f"{base_url}?offset={offset}&limit={limit}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'Your Application Name'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Automatically raise an error for non-2xx responses
        return response.json()

    # Initial request to get the total count of documents
    data = fetch_documents_chunk(offset, limit)
    total_count = data.get('totalCount', 0)
    all_documents.extend(data.get('documents', []))

    logger.info(f"Total documents to fetch: {total_count}")
    logger.info(f"Fetched {len(all_documents)} documents out of {total_count} so far.")

    # Fetch remaining documents in chunks until all are retrieved
    while len(all_documents) < total_count:
        offset += limit
        data = fetch_documents_chunk(offset, limit)
        all_documents.extend(data.get('documents', []))
        logger.info(f"Fetched {len(all_documents)} documents out of {total_count} so far.")

    return all_documents

def fetch_and_process_documents(account_id, access_token):
    """
    Fetches all documents for a given account.
    """
    all_documents = fetch_all_documents(account_id, access_token)
    if all_documents is None:
        logger.error("Failed to fetch documents.")
        return []
    return all_documents

# ===========================
# Field Mapper Functions
# ===========================

from datetime import datetime

def map_custom_fields(document, custom_field_mapping):
    """
    Maps Shoeboxed document metadata to appropriate custom fields for Paperless.
    Args:
        document (dict): The Shoeboxed document metadata.
        custom_field_mapping (dict): Mapping of custom field names to their details.
    Returns:
        dict: A dictionary mapping custom field IDs to their corresponding values.
    """
    field_mapping = {}

    # Iterate through available custom fields and set values accordingly
    for field_name, field_info in custom_field_mapping.items():
        field_id = field_info['id']
        data_type = field_info['data_type']
        extra_data = field_info.get('extra_data', {})

        # Mapping based on custom fields defined in Paperless
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

# ===========================
# Tag Mapper Functions
# ===========================

def ensure_tags(paperless_url, headers, categories=None, envelope_id=None):
    """
    Ensure tags exist in Paperless for the given categories and optionally an envelope ID.
    Args:
        paperless_url (str): URL for the Paperless API.
        headers (dict): Headers with authorization for Paperless API.
        categories (list, optional): Categories from Shoeboxed document to be added as tags.
        envelope_id (str, optional): Envelope ID to add as a tag.
    Returns:
        list: List of tag IDs that correspond to the categories and the envelope ID.
    """
    categories = categories or []
    tag_ids = []

    # Combine envelope_id with categories for unified processing
    tags_to_ensure = []

    # Handle envelope ID separately with uppercase transformation
    if envelope_id:
        tags_to_ensure.append(envelope_id.upper())

    # Add categories without uppercase transformation
    tags_to_ensure += categories

    # Fetch existing tags from Paperless
    response = requests.get(f"{paperless_url}/api/tags/", headers=headers)
    if response.status_code != 200:
        logging.error(f"Failed to fetch tags. Status Code: {response.status_code}, Response: {response.text}")
        return []

    existing_tags = {tag['name']: tag for tag in response.json().get('results', [])}

    # Ensure each tag is present in Paperless
    for tag_name in tags_to_ensure:
        if tag_name in existing_tags:
            tag_ids.append(existing_tags[tag_name]['id'])
        else:
            # Create the tag since it doesn't exist
            payload = {"name": tag_name}
            create_response = requests.post(f"{paperless_url}/api/tags/", headers=headers, json=payload)
            if create_response.status_code == 201:
                new_tag = create_response.json()
                tag_ids.append(new_tag['id'])
                logging.info(f"Tag '{tag_name}' created successfully with ID {new_tag['id']}.")
            else:
                logging.error(f"Failed to create tag '{tag_name}'. Status Code: {create_response.status_code}, Response: {create_response.text}")

    return tag_ids

# ===========================
# Main Function
# ===========================

if __name__ == "__main__":
    # Step 1: Check Paperless Environment Variables
    try:
        paperless_token, paperless_url = check_paperless_env_vars()
        logger.info("All Paperless environment variables are set.")
    except EnvironmentError as e:
        logger.error(e)
        exit(1)

    # Step 2: Check Shoeboxed Environment Variables
    try:
        client_id, client_secret, redirect_uri = check_shoeboxed_env_vars()
        logger.info("All Shoeboxed environment variables are set.")
    except EnvironmentError as e:
        logger.error(e)
        exit(1)

    # Step 3: Authenticate with Shoeboxed
    try:
        shoeboxed_access_token, shoeboxed_refresh_token = authenticate_shoeboxed()

        if shoeboxed_access_token and shoeboxed_refresh_token:
            logger.info("Shoeboxed authentication successful.")
        else:
            logger.error("Shoeboxed authentication failed. Exiting.")
            exit(1)
    except (EnvironmentError, ValueError) as e:
        logger.error(e)
        exit(1)

    # Set up initial token refresh timing
    start_time = datetime.now()
    next_refresh_time = start_time + TOKEN_REFRESH_INTERVAL

    # Step 4: Ensure Custom Fields Exist in Paperless and fetch them
    custom_fields_list = ensure_custom_fields(paperless_url, paperless_token)
    if not custom_fields_list:
        logger.error("Failed to retrieve custom fields from Paperless.")
        exit(1)

    # Create mapping from custom field names to their details
    custom_field_mapping = create_custom_field_mapping(custom_fields_list)
    logger.info("Custom field mapping created.")

    # Step 5: Ensure Document Types Exist in Paperless and fetch them
    document_types_list = ensure_document_types(paperless_url, {"Authorization": f"Token {paperless_token}"})
    if not document_types_list:
        logger.error("Failed to retrieve document types from Paperless.")
        exit(1)

    # Create mapping from document type names to their details
    document_type_mapping = {doc_type['name']: doc_type['id'] for doc_type in document_types_list}
    logger.info("Document type mapping created.")

    # Step 6: Fetch and display user info from Shoeboxed
    try:
        user_info = fetch_user_info(shoeboxed_access_token)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            # Refresh access token if the access token is expired
            logger.info("Access token expired. Refreshing token...")
            shoeboxed_access_token, shoeboxed_refresh_token = refresh_access_token(client_id, client_secret, shoeboxed_refresh_token)
            # Retry fetching user info
            user_info = fetch_user_info(shoeboxed_access_token)
        else:
            logger.error(f"Failed to fetch user information: {e}")
            exit(1)

    # Load existing progress if available
    progress = load_progress()
    current_batch = progress.get('current_batch', 0)

    # Step 7: Process Accounts and Documents with Batching
    BATCH_SIZE = 10

    # Step 8: Process Accounts and Documents
    if user_info is not None:
        logger.info(f"Account IDs: {user_info}")
        for account_id in user_info:
            logger.info(f"Processing Account ID: {account_id}")

            # Fetch documents for the current account
            documents = fetch_and_process_documents(account_id, shoeboxed_access_token)

            # Process documents in batches
            for i in range(0, len(documents), BATCH_SIZE):
                batch_documents = documents[i:i + BATCH_SIZE]

                # Refresh token if needed before starting a new batch
                current_time = datetime.now()
                if current_time >= next_refresh_time:
                    logger.info("Refreshing access token before continuing...")
                    shoeboxed_access_token, shoeboxed_refresh_token = refresh_access_token(client_id, client_secret, shoeboxed_refresh_token)
                    next_refresh_time = current_time + TOKEN_REFRESH_INTERVAL

                # Process each document in the current batch
                for document in batch_documents:
                    try:
                        # Extract correspondent based on document type
                        correspondent_name = None
                        document_type = document.get("type", "other")

                        if document_type == "receipt":
                            correspondent_name = document.get("vendor")
                        elif document_type == "business-card":
                            correspondent_name = document.get("company")
                        elif document_type == "other":
                            correspondent_name = document.get("name")

                        # Ensure Correspondents exist in Paperless
                        correspondent_mapping = ensure_correspondents(paperless_url, paperless_token, [correspondent_name] if correspondent_name else [])
                        if not correspondent_mapping:
                            logger.error(f"Failed to retrieve or create correspondents for document {document['id']}.")
                            continue

                        # Map custom fields to get values
                        custom_field_values = map_custom_fields(document, custom_field_mapping)
                        logger.info(f"Custom field mapping for document {document['id']} complete.")

                        # Get custom field IDs (without values) to associate during upload
                        custom_field_ids = list(custom_field_values.keys())

                        # Determine document type - direct mapping for consistency
                        shoeboxed_doc_type = document.get("type")
                        document_type_name_map = {
                            "business-card": "Business Cards",
                            "other": "Documents",
                            "receipt": "Receipts"
                        }
                        document_type_name = document_type_name_map.get(shoeboxed_doc_type, "Documents")

                        # Handle tags for categories and envelope ID
                        tags = []
                        if document_type == 'receipt' and document.get('categories'):
                            categories = document.get('categories', [])
                            tags += categories

                        # Check for envelope ID tag for documents sourced via mail
                        if document.get('source', {}).get('type') == 'mail':
                            envelope_id = document.get('source', {}).get('envelope')
                            if envelope_id:
                                tags.append(envelope_id)

                        # Ensure tags are created or fetched from Paperless
                        tags = ensure_tags(paperless_url, {"Authorization": f"Token {paperless_token}"}, categories=document.get('categories', []), envelope_id=document.get('source', {}).get('envelope'))

                        # Upload document and associate custom fields
                        task_id = upload_document_to_paperless(
                            document,
                            custom_field_ids,
                            paperless_url,
                            paperless_token,
                            correspondent_mapping,
                            document_type_name,
                            document_type_mapping,
                            tags
                        )
                        if not task_id:
                            logger.error(f"Failed to upload document {document['id']}.")
                            continue

                        # Poll for task completion to get document ID
                        document_id = poll_for_task_completion(task_id, paperless_url, paperless_token, timeout=600, interval=10)
                        if not document_id:
                            logger.error(f"Failed to process document {document['id']}.")
                            continue

                        # Update document custom fields with values
                        if custom_field_values:
                            update_result = update_document_custom_fields(document_id, custom_field_values, paperless_url, paperless_token)
                            if update_result:
                                logger.info(f"Document {document['id']} uploaded and metadata updated successfully.")
                            else:
                                logger.error(f"Failed to update custom fields for document {document['id']}.")

                    except Exception as e:
                        logger.error(f"Error processing document {document['id']}: {e}")

                # Pause briefly after each batch to avoid overwhelming the system
                time.sleep(5)
    else:
        logger.error("Failed to fetch user information.")
        exit(1)

    logger.info("Document migration completed successfully.")
