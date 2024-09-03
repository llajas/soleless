import os
import requests
import logging
from urllib.parse import quote_plus
from getpass import getpass

# Setup logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

# Try to use PAPERLESS_URL from environment variable, prompt if not set
PAPERLESS_URL = os.getenv('PAPERLESS_URL')
if not PAPERLESS_URL:
    PAPERLESS_URL = input("Enter Paperless URL (e.g., https://paperless.example.com): ").rstrip('/')
    
# Shoeboxed Authentication Functions

def generate_auth_url(client_id, redirect_uri):
    base_url = "https://id.shoeboxed.com/oauth/authorize"
    response_type = "code"
    scope = "all"
    auth_url = f"{base_url}?client_id={client_id}&response_type={response_type}&scope={scope}&redirect_uri={quote_plus(redirect_uri)}"
    return auth_url

def exchange_code_for_access_token(client_id, client_secret, authorization_code, redirect_uri):
    token_url = "https://id.shoeboxed.com/oauth/token"
    payload = {
        'code': authorization_code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    }
    auth = (client_id, client_secret)
    headers = {

        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    response = requests.post(token_url, auth=auth, data=payload, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error obtaining access token: {response.status_code}, {response.text}")
        return None

def handle_token_response(token_response):
    access_token = token_response.get('access_token')
    refresh_token = token_response.get('refresh_token')
    # Commenting out prints for sensitive information
    # print(f"Access Token: {access_token}")
    # print(f"Refresh Token: {refresh_token}")
    return access_token, refresh_token

# Shoeboxed API Functions

def fetch_user_info(access_token):
    """
    Fetches user information from the Shoeboxed API, including account IDs.

    Parameters:
    - access_token (str): The OAuth access token.

    Returns:
    - list: A list of account IDs associated with the user.
    """
    url = "https://api.shoeboxed.com/v2/user"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Your Application Name'
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        user_info = response.json()
        # Extracting account IDs
        account_ids = [account['id'] for account in user_info.get('accounts', [])]
        return account_ids
    else:
        print(f"Error fetching user info: {response.status_code}, {response.text}")
        return None

def fetch_documents(account_id, access_token):
    """
    Fetches documents for a given account from the Shoeboxed API.

    Parameters:
    - account_id (str): The account ID.
    - access_token (str): The OAuth access token.
    """
    url = f"https://api.shoeboxed.com/v2/accounts/{account_id}/documents"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Your Application Name'
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        documents = response.json()
        print("Documents:", documents)
        return documents
    else:
        print(f"Error fetching documents: {response.status_code}, {response.text}")
        return None

def download_and_save_attachment(document):
    url = document['attachment']['url']
    filename = f"{document['id']}.pdf"
    
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(response.content)
        return filename
    else:
        print(f"Failed to download attachment: {response.status_code}")
        return None

# Paperless Authentication Functions

def get_paperless_auth_token(paperless_url):
    """
    Authenticate with Paperless and capture the auth token for the session.
    """
    # Ensure the base URL does not end with a slash
    if paperless_url.endswith('/'):
        paperless_url = paperless_url[:-1]
    
    auth_url = f"{paperless_url}/api/token/"
    username = input("Enter Paperless username: ")
    password = getpass("Enter Paperless password: ")
    response = requests.post(auth_url, json={"username": username, "password": password})
    if response.status_code == 200:
        token = response.json().get('token')
        print("Authentication successful.")
        return token
    else:
        print(f"Authentication failed: {response.status_code}, {response.text}")
        return None

# Paperless API Functions

def fetch_document_type_ids(paperless_url, paperless_token):
    """
    Fetches document type IDs from Paperless.
    
    Parameters:
    - paperless_url (str): The base URL of the Paperless instance.
    - paperless_token (str): The auth token for Paperless.
    
    Returns:
    - dict: A dictionary mapping document type names to their IDs.
    """
    # Ensure the base URL does not end with a slash
    if paperless_url.endswith('/'):
        paperless_url = paperless_url[:-1]

    url = f"{paperless_url}/api/document_types/"
    headers = {
        'Authorization': f'Token {paperless_token}',
        'User-Agent': 'Your Application Name'
    }
    
    response = requests.get(url, headers=headers)
    
    try:
        document_types_response = response.json()
        document_types = {}
        for doc_type in document_types_response.get('results', []):
            document_types[doc_type['name']] = doc_type['id']
        return document_types
    except requests.exceptions.JSONDecodeError:
        print(f"Failed to fetch document type IDs: {response.text}")
        return {}

def fetch_tags(paperless_url, paperless_token):
    url = f"{paperless_url.rstrip('/')}/api/tags/"
    headers = {'Authorization': f'Token {paperless_token}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        tags = response.json().get('results', [])
        return {tag['name']: tag['id'] for tag in tags}
    else:
        print(f"Failed to fetch tags: {response.status_code}, {response.text}")
        return {}

def create_tag(paperless_url, paperless_token, tag_name):
    url = f"{paperless_url.rstrip('/')}/api/tags/"
    headers = {
        'Authorization': f'Token {paperless_token}',
        'Content-Type': 'application/json'
    }
    data = {'name': tag_name}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code in [200, 201]:
        return response.json()['id']
    else:
        print(f"Failed to create tag '{tag_name}': {response.status_code}, {response.text}")
        return None

def ensure_tags_exist(paperless_url, paperless_token, tags_needed):
    existing_tags = fetch_tags(paperless_url, paperless_token)  # Fetch existing tags
    tags_ids = []

    for tag in tags_needed:
        if tag in existing_tags:
            tags_ids.append(existing_tags[tag])  # Use existing tag ID
        else:
            # Create new tag and add its ID to the list
            new_tag_id = create_tag(paperless_url, paperless_token, tag)
            if new_tag_id:
                tags_ids.append(new_tag_id)

    return tags_ids

def upload_document_to_paperless(filename, metadata, document_type_ids, tag_ids_needed, paperless_url, paperless_token):
    url = f"{paperless_url.rstrip('/')}/api/documents/post_document/"
    headers = {'Authorization': f'Token {paperless_token}', 'User-Agent': 'Your Application Name'}

    # Prepare document type ID
    doc_type_name = metadata.get('type')
    document_type_id = document_type_ids.get(doc_type_name)

    # Ensure tag_ids_needed is already a list of integer IDs
    # If not, this part needs to ensure the conversion from tag names to IDs

    files = {'document': (filename, open(filename, 'rb'), 'application/pdf')}
    data = {
        'title': filename.split('.')[0],
        'created': metadata.get('issued'),
        'document_type': document_type_id,
        'tags': tag_ids_needed  # Ensure this is a list of integer IDs
    }

    response = requests.post(url, headers=headers, files=files, data=data)
    if response.status_code in [200, 201]:
        print(f"Document {filename} uploaded successfully.")
        return response.json()
    else:
        print(f"Failed to upload document {filename}: {response.status_code}, {response.text}")
        return None

# Main function

if __name__ == "__main__":
    # Shoeboxed setup
    client_id = os.getenv('SHOEBOXED_CLIENT_ID')
    client_secret = os.getenv('SHOEBOXED_CLIENT_SECRET')
    redirect_uri = os.getenv('SHOEBOXED_REDIRECT_URI')

    auth_url = generate_auth_url(client_id, redirect_uri)
    print("Please visit this URL to authorize:", auth_url)

    authorization_code = getpass("Please enter the authorization code: ")
    access_token_info = exchange_code_for_access_token(client_id, client_secret, authorization_code, redirect_uri)

    if not access_token_info:
        print("Failed to obtain tokens from Shoeboxed.")
        exit(1)

    access_token, _ = handle_token_response(access_token_info)
    account_ids = fetch_user_info(access_token)
    if not account_ids:
        print("Failed to obtain account IDs from Shoeboxed.")
        exit(1)

    # Assuming you're using the first account ID to fetch documents
    documents = fetch_documents(account_ids[0], access_token)
    if not documents or 'documents' not in documents:
        print("Failed to fetch documents from Shoeboxed.")
        exit(1)

    # Paperless setup and authentication
    paperless_url = PAPERLESS_URL  # Ensure this variable is correctly set earlier in your script
    paperless_token = get_paperless_auth_token(paperless_url)
    if not paperless_token:
        print("Failed to authenticate with Paperless.")
        exit(1)

    # Fetch document types and existing tags from Paperless
    document_type_ids = fetch_document_type_ids(paperless_url, paperless_token)
    tag_ids = fetch_tags(paperless_url, paperless_token)

    # Process each document
    for document in documents['documents']:
        filename = download_and_save_attachment(document)
        if filename:
            metadata = {
                'issued': document.get('issued'),
                'type': document.get('type'),
                'categories': document.get('categories', []),
                'source': document.get('source', {})
            }

            # Ensure necessary tags exist in Paperless and get their IDs
            envelope_list = [metadata['source'].get('envelope')] if metadata['source'].get('envelope') else []
            categories_list = metadata.get('categories', [])
            tags_needed = envelope_list + categories_list
            tag_ids_needed = ensure_tags_exist(paperless_url, paperless_token, tags_needed)

            # Upload document to Paperless
            upload_document_to_paperless(filename, metadata, document_type_ids, tag_ids_needed, paperless_url, paperless_token)

            os.remove(filename)  # Clean up the downloaded document
        else:
            print(f"Failed to download document: {document.get('id')}")

# Pending implementation

def make_authenticated_request(access_token):
    url = "https://api.shoeboxed.com/v2/some/endpoint"  # Change this to the actual endpoint
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Your Application Name'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print(response.json())
    else:
        print(f"Error making authenticated request: {response.status_code}, {response.text}")

def add_note_to_paperless_document(doc_id, note):
    url = f"{PAPERLESS_URL}/documents/{doc_id}/notes/"
    data = {'note': note}
    response = requests.post(url, json=data)
    if response.status_code == 201:
        print(f"Note added to document {doc_id} successfully.")
    else:
        print(f"Failed to add note to document {doc_id}: {response.status_code}")

def ensure_custom_fields_exist(paperless_url, paperless_token, custom_fields_needed):
    existing_fields = fetch_custom_fields(paperless_url, paperless_token)
    field_ids = {}
    for field_name, data_type in custom_fields_needed.items():
        if field_name not in existing_fields:
            field_id = create_custom_field(paperless_url, paperless_token, field_name, data_type)
            field_ids[field_name] = field_id
        else:
            field_ids[field_name] = existing_fields[field_name]
    return field_ids

def fetch_custom_fields(paperless_url, paperless_token):
    url = f"{paperless_url.rstrip('/')}/api/custom_fields/"
    headers = {'Authorization': f'Token {paperless_token}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        fields = {field['name']: field['id'] for field in response.json().get('results', [])}
        return fields
    else:
        print(f"Failed to fetch custom fields: {response.status_code}, {response.text}")
        return {}

def create_custom_field(paperless_url, paperless_token, name, data_type):
    url = f"{paperless_url.rstrip('/')}/api/custom_fields/"
    headers = {'Authorization': f'Token {paperless_token}', 'Content-Type': 'application/json'}
    data = {'name': name, 'data_type': data_type}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code in [200, 201]:
        return response.json()['id']
    else:
        print(f"Failed to create custom field '{name}': {response.status_code}, {response.text}")
        return None

def update_document_with_custom_fields(paperless_url, paperless_token, document_id, custom_field_values):
    url = f"{paperless_url.rstrip('/')}/api/documents/{document_id}/"
    headers = {'Authorization': f'Token {paperless_token}', 'Content-Type': 'application/json'}
    data = {'custom_fields': custom_field_values}  # Format as needed
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code in [200, 201]:
        print(f"Document {document_id} updated with custom fields successfully.")
    else:
        print(f"Failed to update document {document_id} with custom fields: {response.status_code}, {response.text}")