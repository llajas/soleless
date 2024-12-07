# Soleless Standalone

Soleless Standalone is a Python-based script designed for migrating documents from Shoeboxed to Paperless. It connects to the Shoeboxed API to retrieve documents and uploads them to Paperless while also handling document metadata, including custom fields, tags, and correspondents. This script is meant for one-time use as it does not maintain any form of state between runs. An OCI compliant 'Containerfile' is included for building a container image for use in a Docker or Kubernetes environment. An example of how this can deployed via Helm chart in a clustered environment can be found at [this link](https://github.com/llajas/homelab/tree/8ea2660d52f09c9b2ba33708b6e9e85718b91c7d/apps/soleless).

## Features
- Fetches documents from Shoeboxed accounts.
- Uploads documents to Paperless with associated metadata.
- Handles custom fields, tags, document types, and correspondents in Paperless.
- Includes retry logic for failed operations.
- Concurrency support using Python threads for efficient document processing.

## Prerequisites
- Python 3.6+
- Access to Shoeboxed and Paperless API credentials.
  - Note that in order to obtain an API key for your Shoeboxed account, you'll need to create a new application in the Shoeboxed Developer Portal. Once you have created an application, you will receive a `client_id`, `client_secret` and `redirect_uri` that you can use to authenticate with the Shoeboxed API. The `redirect_uri` is the URL that the user will be redirected to after they have authorized the application.

## Setup

### Environment Variables
To configure Soleless Standalone, set the following environment variables:

- **Shoeboxed**
  - `SHOEBOXED_CLIENT_ID`: Your Shoeboxed Client ID.
  - `SHOEBOXED_CLIENT_SECRET`: Your Shoeboxed Client Secret.
  - `SHOEBOXED_REDIRECT_URI`: Redirect URI used for OAuth.
  - `AUTHORIZATION_CODE`: Shoeboxed authorization code obtained through OAuth. This is done as described in the Shoeboxed API documentation:

  - **Begin Authorization**: Direct the user to the OAuth 2.0 authorization endpoint:

    ```
    https://id.shoeboxed.com/oauth/authorize?client_id=<your client id>&response_type=code&scope=all&redirect_uri=<your site>
    ```
  
  Once the app is authorized, you will receive a 'code' in the URL (e.g., `https://api.shoeboxed.com/v2/explorer/o2c.html?code=<VALUE>`). This code should be used as the `AUTHORIZATION_CODE` environment variable. Note that the code expires quickly, so it must be used promptly. After the initial authorization, the app can run perpetually by using the refresh token.

- The app has two modes of ignition with regards to the `AUTHORIZATION_CODE`
  - If the `AUTHORIZATION_CODE` environment variable is set at start-time, the app will use it to obtain an access token and refresh token.
  - If the `AUTHORIZATION_CODE` environment variable is not set at start-time, the app will direct the user to the Shoeboxed OAuth 2.0 authorization endpoint URI to obtain the authorization code.

This allows the app to run either in an 'interactive' mode so that there is no need to immediately set the `AUTHORIZATION_CODE` environment variable, or in a 'non-interactive' or 'Kubernetes' mode where the `AUTHORIZATION_CODE` environment variable is pre-set at start time, requiring no user interaction to run, but requires fast action once the code is obtained.


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