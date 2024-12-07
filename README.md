# Soleless Standalone

Soleless Standalone is a Python-based script designed for migrating documents from Shoeboxed to Paperless. It connects to the Shoeboxed API to retrieve documents and uploads them to Paperless while also handling document metadata, including custom fields, tags, and correspondents. This script is meant for one-time use but could be containerized and automated for repeated migrations.

## Features
- Fetches documents from Shoeboxed accounts.
- Uploads documents to Paperless with associated metadata.
- Handles custom fields, tags, document types, and correspondents in Paperless.
- Includes retry logic for failed operations.
- Concurrency support using Python threads for efficient document processing.

## Prerequisites
- Python 3.6+
- Access to Shoeboxed and Paperless API credentials.

## Setup

### Environment Variables
To configure Soleless Standalone, set the following environment variables:

- **Shoeboxed**
  - `SHOEBOXED_CLIENT_ID`: Your Shoeboxed Client ID.
  - `SHOEBOXED_CLIENT_SECRET`: Your Shoeboxed Client Secret.
  - `SHOEBOXED_REDIRECT_URI`: Redirect URI used for OAuth.
  - `AUTHORIZATION_CODE`: Shoeboxed authorization code obtained through OAuth. This is done as described in the Shoeboxed API documentation:

  - **Step 1: Begin Authorization**: Direct the user to the OAuth 2.0 authorization endpoint:
    
    ```
    https://id.shoeboxed.com/oauth/authorize?client_id=<your client id>&response_type=code&scope=all&redirect_uri=<your site>
    ```
  
  Once the app is authorized, you will receive a 'code' in the URL (e.g., `https://api.shoeboxed.com/v2/explorer/o2c.html?code=<VALUE>`). This code should be used as the `AUTHORIZATION_CODE` environment variable. Note that the code expires quickly, so it must be used promptly. After the initial authorization, the app can run perpetually by using the refresh token.

- **Paperless**
  - `PAPERLESS_URL`: URL to your Paperless instance.
  - `PAPERLESS_AUTH_TOKEN`: Paperless API token for authentication.

### Running the Script
Make sure that you have set all the necessary environment variables. Then run the script using:

```sh
python soleless_standalone.py
```

## Configuration
The script has some configurable parameters you can adjust based on your needs:

- **Concurrency**
  - `MAX_WORKERS`: Number of worker threads to use for concurrent processing. This can be set via an environment variable and defaults to 5 if not specified.

- **Retries**
  - `MAX_RETRIES`: Number of times to retry an operation in case of failure. This can be set via an environment variable and defaults to 3 if not specified.
  - `RETRY_DELAY`: Number of seconds to wait between retries. This can be set via an environment variable and defaults to 5 if not specified.

## Usage
The script follows these main steps:

1. **Authentication**: Authenticates with Shoeboxed to get an access token.
2. **Resource Setup**: Ensures that all required custom fields, document types, and tags are present in Paperless.
3. **Document Fetching**: Retrieves documents from Shoeboxed for all linked accounts.
4. **Document Uploading**: Uploads documents to Paperless and assigns metadata accordingly.

Documents are processed concurrently, and any failed uploads are retried based on the configuration.

## Error Handling
- Each document processing step includes retry logic to handle intermittent failures.
- If an error occurs during authentication or API requests, it will be logged and retried based on the configuration.

## Logging
All operations are logged to provide insights during the migration process. Logs are written to the console and include information about each document, the authentication steps, and any errors encountered.

## Contributions
Contributions are welcome. Please submit a pull request with a detailed description of your changes.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments
- [Shoeboxed](https://www.shoeboxed.com) for providing API access to document data.
  - [Shoeboxed API GitHub Repository](https://github.com/Shoeboxed/api)
  - [Shoeboxed API Explorer](https://api.shoeboxed.com/v2/explorer/index.html)
- [Paperless NGX](https://github.com/paperless-ngx/paperless-ngx) for creating an open-source document management solution.
  - [Paperless NGX Documentation](https://docs.paperless-ngx.com/)

## Disclaimer
This tool is intended for personal use only. By using it, you agree to comply with the terms of service of the API provider. The author assumes no liability for any misuse of this tool.