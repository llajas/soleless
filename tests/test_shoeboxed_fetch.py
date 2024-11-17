import os
import requests

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
    
    if response.status_code == 200:
        user_info = response.json()
        account_ids = [account['id'] for account in user_info.get('accounts', [])]
        return account_ids
    else:
        print(f"Error fetching user info: {response.status_code}, {response.text}")
        return None

def fetch_documents(account_id, access_token):
    """
    Fetches documents for a given account from the Shoeboxed API.
    """
    url = f"https://api.shoeboxed.com/v2/accounts/{account_id}/documents"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Your Application Name'
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        documents = response.json()
        return documents
    else:
        print(f"Error fetching documents: {response.status_code}, {response.text}")
        return None

# Test the functions
if __name__ == "__main__":
    access_token = input("Enter the Shoeboxed access token: ")

    # Fetch user info and account IDs
    account_ids = fetch_user_info(access_token)
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
        documents = fetch_documents(selected_account_id, access_token)
        if documents:
            print(f"Successfully fetched documents.")
            print(f"Total documents: {documents.get('totalCount', 'Unknown')}")
            print(f"Documents in this batch: {len(documents.get('documents', []))}")
            
            # Print some info about the first document (if any)
            if documents.get('documents'):
                first_doc = documents['documents'][0]
                print("\nFirst document info:")
                print(f"ID: {first_doc.get('id')}")
                print(f"Type: {first_doc.get('type')}")
                print(f"Issued: {first_doc.get('issued')}")
        else:
            print("Failed to fetch documents.")
    else:
        print("Failed to fetch user info and account IDs.")