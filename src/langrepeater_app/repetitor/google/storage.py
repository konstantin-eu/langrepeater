# german_repetitor/repetitor/google/storage.py

import logging
from typing import Optional

# Attempt to import Google Cloud Storage library
try:
    from google.cloud import storage
    from google.api_core import exceptions as google_exceptions
    GCS_AVAILABLE = True
except ImportError:
    storage = None # Define as None if library not installed
    google_exceptions = None
    GCS_AVAILABLE = False
    print("GCS not available")
    exit(1)

# Project Imports
from src.langrepeater_app.repetitor.exceptions import GoogleCloudError, InputError

logger = logging.getLogger(__name__)

# --- GCS Client Initialization (Singleton Pattern Recommended) ---
# Avoid initializing the client repeatedly for every call.
_gcs_client: Optional['storage.Client'] = None

def _get_gcs_client() -> 'storage.Client':
    """Initializes and returns a singleton GCS client instance."""
    global _gcs_client
    if not GCS_AVAILABLE:
        raise GoogleCloudError("Google Cloud Storage library ('google-cloud-storage') is not installed.")

    if _gcs_client is None:
        try:
            logger.info("Initializing Google Cloud Storage client...")
            # The client uses Application Default Credentials (ADC) by default.
            # Ensure ADC are configured in the environment (e.g., service account key file path
            # set in GOOGLE_APPLICATION_CREDENTIALS env var, or running on GCP infra).
            _gcs_client = storage.Client()
            logger.info("Google Cloud Storage client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Storage client: {e}", exc_info=True)
            raise GoogleCloudError(f"GCS client initialization failed: {e}") from e
    return _gcs_client

# --- GCS File Reading Function ---

def read_gcs_file(bucket_name: str, blob_name: str, encoding: str = 'utf-8') -> str:
    """
    Reads the content of a text file (blob) from Google Cloud Storage.

    Args:
        bucket_name: The name of the GCS bucket.
        blob_name: The name/path of the blob (file) within the bucket.
        encoding: The text encoding to use (default: 'utf-8').

    Returns:
        The content of the file as a string.

    Raises:
        ConfigError: If bucket_name or blob_name is missing.
        InputError: If the bucket or blob is not found, or access is denied.
        GoogleCloudError: For other GCS API errors or if the library is missing.
    """
    if not bucket_name or not blob_name:
        raise ConfigError("Missing bucket name or blob name for GCS access.")

    logger.info(f"Attempting to read from GCS: gs://{bucket_name}/{blob_name}")

    try:
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        logger.debug(f"Downloading blob: {blob.name}")
        # Download the blob's content as bytes first
        content_bytes = blob.download_as_bytes()

        # Decode the bytes using the specified encoding
        content_string = content_bytes.decode(encoding)
        logger.info(f"Successfully read {len(content_bytes)} bytes from gs://{bucket_name}/{blob_name}")
        return content_string

    except google_exceptions.NotFound:
        logger.error(f"GCS resource not found: gs://{bucket_name}/{blob_name}")
        raise InputError(f"GCS resource not found: gs://{bucket_name}/{blob_name}")
    except google_exceptions.Forbidden as e:
        logger.error(f"Permission denied accessing GCS resource: gs://{bucket_name}/{blob_name}. Check credentials/IAM roles. Error: {e}")
        raise InputError(f"Permission denied for GCS resource: gs://{bucket_name}/{blob_name}")
    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode GCS blob gs://{bucket_name}/{blob_name} using encoding '{encoding}': {e}")
        raise InputError(f"Encoding error reading GCS file with '{encoding}'") from e
    except Exception as e:
        # Catch other potential google-cloud-storage or general exceptions
        logger.error(f"Failed to read from GCS gs://{bucket_name}/{blob_name}: {e}", exc_info=True)
        # Wrap in a custom exception for consistency
        raise GoogleCloudError(f"Failed to read GCS file: {e}", service="Storage") from e

