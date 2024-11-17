import os
import requests
from getpass import getpass

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

# Test the function
if __name__ == "__main__":
    paperless_url = os.getenv('PAPERLESS_URL')
    if not paperless_url:
        paperless_url = input("Enter Paperless URL (e.g., https://paperless.example.com): ").rstrip('/')
    
    token = get_paperless_auth_token(paperless_url)
    if token:
        print(f"Obtained token: {token[:10]}...") # Print first 10 characters for security
    else:
        print("Failed to obtain token.")