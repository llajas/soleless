import os
import requests
from urllib.parse import quote_plus
from getpass import getpass

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
    print(f"Access Token: {access_token[:10]}...") # Print first 10 characters for security
    print(f"Refresh Token: {refresh_token[:10]}...") # Print first 10 characters for security
    return access_token, refresh_token

# Test the functions
if __name__ == "__main__":
    # Get Shoeboxed credentials from environment variables or user input
    client_id = os.getenv('SHOEBOXED_CLIENT_ID')
    if not client_id:
        client_id = input("Enter Shoeboxed Client ID: ")
    
    client_secret = os.getenv('SHOEBOXED_CLIENT_SECRET')
    if not client_secret:
        client_secret = getpass("Enter Shoeboxed Client Secret: ")
    
    redirect_uri = os.getenv('SHOEBOXED_REDIRECT_URI')
    if not redirect_uri:
        redirect_uri = input("Enter Shoeboxed Redirect URI: ")

    # Generate and display the authorization URL
    auth_url = generate_auth_url(client_id, redirect_uri)
    print("Please visit this URL to authorize:", auth_url)

    # Get the authorization code from the user
    authorization_code = input("Please enter the authorization code: ")

    # Exchange the authorization code for access token
    token_response = exchange_code_for_access_token(client_id, client_secret, authorization_code, redirect_uri)

    if token_response:
        access_token, refresh_token = handle_token_response(token_response)
        print("Authentication successful.")
    else:
        print("Failed to obtain tokens from Shoeboxed.")