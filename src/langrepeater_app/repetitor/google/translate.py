# german_repetitor/repetitor/google/translate.py

import logging
import os
from typing import Optional, List, Sequence

# Attempt to import Google Cloud Translate library
try:
    from google.cloud import translate_v3 as translate
    from google.api_core import exceptions as google_exceptions
    from google.api_core import operations_v1 # For batch operations if needed
    from google.longrunning import operations_pb2 # For batch operations if needed
    GCT_AVAILABLE = True
except ImportError:
    translate = None # Define as None if library not installed
    google_exceptions = None
    operations_v1 = None
    operations_pb2 = None
    GCT_AVAILABLE = False
    print("GCT not available")
    exit(1)

# Project Imports
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig
from src.langrepeater_app.repetitor.exceptions import GoogleCloudError, ConfigError

logger = logging.getLogger(__name__)

# --- Google Translate Client ---
# Singleton pattern for the client is good practice
_translate_client: Optional['translate.TranslationServiceClient'] = None

def _get_translate_client() -> 'translate.TranslationServiceClient':
    """Initializes and returns a singleton Google Translation API client instance."""
    global _translate_client
    if not GCT_AVAILABLE:
        raise GoogleCloudError("Google Cloud Translate library ('google-cloud-translate') is not installed.")

    if _translate_client is None:
        try:
            logger.info("Initializing Google Cloud Translation client...")
            # Uses Application Default Credentials (ADC) by default.
            _translate_client = translate.TranslationServiceClient()
            logger.info("Google Cloud Translation client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Translation client: {e}", exc_info=True)
            raise GoogleCloudError(f"Google Translate client initialization failed: {e}") from e
    return _translate_client

class GoogleTranslateClient:
    """
    Provides methods to interact with the Google Cloud Translation API (v3).
    Wraps functionality similar to Java's TranslateText and BatchTranslateText.
    """

    def __init__(self, config: LanguageRepetitorConfig):
        """
        Initializes the GoogleTranslateClient.

        Args:
            config: The application configuration object.

        Raises:
            ConfigError: If the Google Cloud Project ID is not found.
        """
        self.client = _get_translate_client() # Get the singleton client
        # Attempt to get project ID from environment first, then config (if added)
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        # if not self.project_id and hasattr(config, 'google_cloud_project_id'):
        #     self.project_id = config.google_cloud_project_id

        # Fallback based on Java TranslateText.java [cite: 449]
        if not self.project_id:
             self.project_id = "langrepeater" # Default project ID used in Java
             logger.warning(f"GOOGLE_CLOUD_PROJECT environment variable not set. Using default project ID: {self.project_id}")
             # raise ConfigError("Google Cloud Project ID not found in environment variables (GOOGLE_CLOUD_PROJECT).")

        self.location = "global" # Typically 'global' for translateText
        self.batch_location = "us-central1" # Batch operations often restricted (Java used us-central1) [cite: 69]
        self.parent = f"projects/{self.project_id}/locations/{self.location}"
        self.batch_parent = f"projects/{self.project_id}/locations/{self.batch_location}"
        logger.info(f"GoogleTranslateClient initialized for project '{self.project_id}' (location: {self.location}, batch location: {self.batch_location})")


    def translate_text(
        self,
        contents: List[str],
        target_language_code: str,
        source_language_code: Optional[str] = None,
        mime_type: str = "text/plain"
    ) -> List[translate.Translation]:
        """
        Translates a list of texts to the target language.
        Equivalent to Java's TranslateText.translateText [cite: 459-465].

        Args:
            contents: A list of strings to translate.
            target_language_code: The ISO 639-1 code of the target language (e.g., "en", "de").
            source_language_code: Optional ISO 639-1 code of the source language.
                                  If None, the API attempts auto-detection.
            mime_type: The format of the input text ("text/plain" or "text/html").

        Returns:
            A list of google.cloud.translate_v3.types.Translation objects.

        Raises:
            GoogleCloudError: If the translation API call fails.
            ValueError: If input arguments are invalid.
        """
        if not contents:
            return []
        if not target_language_code:
            raise ValueError("Target language code cannot be empty.")

        request_dict = {
            "parent": self.parent,
            "contents": contents,
            "mime_type": mime_type,
            "target_language_code": target_language_code,
        }
        if source_language_code:
            request_dict["source_language_code"] = source_language_code

        logger.debug(f"Sending translation request: target={target_language_code}, source={source_language_code}, num_items={len(contents)}")

        try:
            response = self.client.translate_text(request=request_dict)
            logger.info(f"Successfully received translation for {len(response.translations)} items.")
            return response.translations
        except google_exceptions.GoogleAPICallError as e:
            logger.error(f"Translation API call failed: {e}", exc_info=True)
            raise GoogleCloudError(f"Translation API call failed: {e}", service="Translate") from e
        except Exception as e:
            logger.error(f"Unexpected error during translation: {e}", exc_info=True)
            raise GoogleCloudError(f"Unexpected translation error: {e}", service="Translate") from e

    def translate_single_text(
        self,
        text: str,
        target_language_code: str,
        source_language_code: Optional[str] = None,
        mime_type: str = "text/plain"
    ) -> Optional[str]:
        """
        Helper method to translate a single string.

        Args:
            text: The string to translate.
            target_language_code: The target language code.
            source_language_code: Optional source language code.
            mime_type: The mime type.

        Returns:
            The translated text string, or None if translation fails or input is empty.
        """
        if not text:
            return None
        try:
            results = self.translate_text(
                contents=[text],
                target_language_code=target_language_code,
                source_language_code=source_language_code,
                mime_type=mime_type
            )
            if results:
                return results[0].translated_text
            else:
                logger.warning(f"Translation returned no results for text: '{text[:50]}...'")
                return None
        except GoogleCloudError:
            # Error already logged in translate_text
            return None # Return None on failure for single text

    def batch_translate_text_gcs(
        self,
        input_uri: str,
        output_uri_prefix: str,
        source_language_code: str,
        target_language_codes: List[str],
        mime_type: str = "text/plain",
        timeout_seconds: int = 600 # Default timeout slightly longer than Java's random max
    ) -> Tuple[bool, Optional[translate.BatchTranslateResponse]]:
        """
        Performs batch translation using GCS input and output.
        Equivalent to Java's BatchTranslateText.batchTranslateText [cite: 61-91].

        Args:
            input_uri: GCS URI of the input file or prefix (e.g., "gs://bucket/input.txt").
            output_uri_prefix: GCS URI prefix for output results (e.g., "gs://bucket/output/").
            source_language_code: Source language code.
            target_language_codes: List of target language codes.
            mime_type: Mime type of the input files.
            timeout_seconds: Maximum time to wait for the operation to complete.

        Returns:
            A tuple: (success_boolean, BatchTranslateResponse object or None on failure/timeout).

        Raises:
            GoogleCloudError: If the batch translation request fails or times out.
            ValueError: If input arguments are invalid.
        """
        if not input_uri.startswith("gs://") or not output_uri_prefix.startswith("gs://"):
            raise ValueError("Input URI and Output URI prefix must be GCS paths (gs://...).")
        if not source_language_code or not target_language_codes:
            raise ValueError("Source and target language codes must be provided.")

        input_config = translate.InputConfig(
            gcs_source=translate.GcsSource(input_uri=input_uri),
            mime_type=mime_type,
        )
        output_config = translate.OutputConfig(
            gcs_destination=translate.GcsDestination(output_uri_prefix=output_uri_prefix)
        )

        logger.info(f"Starting batch translation: {input_uri} -> {output_uri_prefix} ({source_language_code} -> {target_language_codes})")

        try:
            operation = self.client.batch_translate_text(
                request={
                    "parent": self.batch_parent,
                    "source_language_code": source_language_code,
                    "target_language_codes": target_language_codes,
                    "input_configs": [input_config],
                    "output_config": output_config,
                }
            )

            logger.info(f"Batch translation operation started: {operation.operation.name}. Waiting for completion (timeout={timeout_seconds}s)...")

            # Wait for the operation to complete
            response = operation.result(timeout=timeout_seconds)

            logger.info("Batch translation operation completed successfully.")
            logger.info(f"  Total Characters: {response.total_characters}")
            logger.info(f"  Translated Characters: {response.translated_characters}")
            logger.info(f"  Failed Documents: {response.failed_documents}")
            logger.info(f"  Total Documents: {response.total_documents}")
            logger.info(f"  Submit Time: {response.submit_time}")
            logger.info(f"  End Time: {response.end_time}")
            return True, response

        except google_exceptions.TimeoutError:
            logger.error(f"Batch translation operation timed out after {timeout_seconds} seconds ({operation.operation.name}).")
            raise GoogleCloudError(f"Batch translation timed out ({operation.operation.name})", service="Translate")
        except google_exceptions.GoogleAPICallError as e:
            logger.error(f"Batch translation API call failed: {e}", exc_info=True)
            raise GoogleCloudError(f"Batch translation API call failed: {e}", service="Translate") from e
        except Exception as e:
            logger.error(f"Unexpected error during batch translation: {e}", exc_info=True)
            raise GoogleCloudError(f"Unexpected batch translation error: {e}", service="Translate") from e


# Example Usage (within your application logic):
# try:
#     config = LanguageRepetitorConfig(...) # Get config
#     translator = GoogleTranslateClient(config)
#
#     # Single text translation
#     translated = translator.translate_single_text("Hallo Welt", "en", "de")
#     if translated:
#         print(f"Translation: {translated}")
#
#     # Batch translation
#     # success, response = translator.batch_translate_text_gcs(
#     #     input_uri="gs://your-input-bucket/input_folder/",
#     #     output_uri_prefix="gs://your-output-bucket/results/",
#     #     source_language_code="de",
#     #     target_language_codes=["en", "fr"]
#     # )
#     # if success:
#     #     print("Batch translation finished.")
#
# except (ConfigError, GoogleCloudError, ValueError) as e:
#     logger.critical(f"Translation failed: {e}")
#     # Handle error appropriately
