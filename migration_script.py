import os
import requests
import logging
from urllib.parse import quote_plus
from getpass import getpass
import json

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
    print(f"Access Token: {access_token[:10]}...")  # Print first 10 characters for security
    print(f"Refresh Token: {refresh_token[:10]}...")  # Print first 10 characters for security
    return access_token, refresh_token

# Paperless Authentication Function
def get_paperless_auth_token():
    """
    Retrieve the Paperless authentication token from environment variables.
    """
    token = os.getenv('PAPERLESS_AUTH_TOKEN')

    if not token:
        token = input("Enter Paperless Authentication Token: ")
    
    if token:
        print("Authentication token retrieved successfully.")
        return token
    else:
        print("Authentication token is missing.")
        return None

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
    
# Main function
if __name__ == "__main__":
    # Shoeboxed setup
    client_id = os.getenv('SHOEBOXED_CLIENT_ID')
    if not client_id:
        client_id = input("Enter Shoeboxed Client ID: ")

    client_secret = os.getenv('SHOEBOXED_CLIENT_SECRET')
    if not client_secret:
        client_secret = getpass("Enter Shoeboxed Client Secret: ")

    redirect_uri = os.getenv('SHOEBOXED_REDIRECT_URI')
    if not redirect_uri:
        redirect_uri = input("Enter Shoeboxed Redirect URI: ")

    # Step 1: Generate the Shoeboxed auth URL and obtain access token
    auth_url = generate_auth_url(client_id, redirect_uri)
    print("Please visit this URL to authorize:", auth_url)

    authorization_code = input("Please enter the Shoeboxed authorization code: ")
    access_token_info = exchange_code_for_access_token(client_id, client_secret, authorization_code, redirect_uri)

    if access_token_info:
        shoeboxed_access_token, shoeboxed_refresh_token = handle_token_response(access_token_info)
        print("Shoeboxed authentication successful.")
    else:
        print("Failed to obtain tokens from Shoeboxed.")
        exit(1)

    # Step 2: Paperless setup and authentication with the token
    paperless_token = get_paperless_auth_token()
    if not paperless_token:
        print("Failed to retrieve the Paperless token.")
        exit(1)

    # Step 3: Verify the Paperless token with a GET request to `/api/documents/`
    headers = {
        'Authorization': f'Token {paperless_token}'
    }
    verification_url = f"{PAPERLESS_URL}/api/documents/"
    response = requests.get(verification_url, headers=headers)

    if response.status_code == 200:
        print("Paperless authentication successful.")
    else:
        print(f"Failed to authenticate with Paperless. Status Code: {response.status_code}, Response: {response.text}")
        exit(1)

    # Step 4: Fetch user info and documents from Shoeboxed
    account_ids = fetch_user_info(shoeboxed_access_token)
    if account_ids:
        print(f"Found {len(account_ids)} account(s).")

        # If multiple accounts, let user choose one
        if len(account_ids) > 1:
            for i, account_id in enumerate(account_ids):
                print(f"{i + 1}. {account_id}")
            choice = int(input("Enter the number of the account to use: ")) - 1
            selected_account_id = account_ids[choice]
        else:
            selected_account_id = account_ids[0]

        print(f"Using account ID: {selected_account_id}")

        # Fetch documents for the selected account
        documents = fetch_documents(selected_account_id, shoeboxed_access_token)
        if documents:
            print(f"Fetched {len(documents)} documents from Shoeboxed.")
        else:
            print("Failed to fetch documents from Shoeboxed.")
            exit(1)
    else:
        print("No accounts found or failed to fetch user information.")
        exit(1)

    print("\nAuthentication completed for both Shoeboxed and Paperless.")
    print("Document fetching from Shoeboxed completed.")
    print("You can now proceed with document migration.")