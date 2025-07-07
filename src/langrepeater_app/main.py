import os
import sys
import time
import logging
# import argparse
from enum import Enum, auto
from pathlib import Path
from dotenv import load_dotenv

from src.langrepeater_app.repetitor.audio.models import RenderJob

# Load environment variables from .env file for local dev
load_dotenv()

# Project imports (adjust paths based on your final structure)
try:
    from src.langrepeater_app.repetitor.config import (
        LanguageRepetitorConfig,
        create_config,
        ConfigError,
    )
    from src.langrepeater_app.repetitor.constants import Language, HEADER_PREFIX
    from src.langrepeater_app.repetitor.phrasereader.reader import PhrasesReader
    from src.langrepeater_app.repetitor.exceptions import PhraseParsingError
    from src.langrepeater_app.repetitor.text_validator import TextValidator, UserConfig
    from src.langrepeater_app.repetitor.exceptions import RepetitorError
    from src.langrepeater_app.repetitor.repetitor import LanguageRepetitor
    # from repetitor.google.storage import read_gcs_file # Needs implementation
    from src.langrepeater_app.repetitor.utils import read_local_file # Needs implementation
except ImportError as e:
    print(f"Error importing project modules: {e}. Ensure PYTHONPATH is set correctly or run from the project root.")
    sys.exit(1)


# --- Logging Setup ---
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)], # Add FileHandler if needed
    force=True
)
logger = logging.getLogger(__name__)

# --- Main Application Logic ---
def run_track_processing(cfg: LanguageRepetitorConfig, track_identifier: str):
    """Reads, validates, and processes a single track."""
    # global logger

    logger.info(f"--- Processing track: {track_identifier} ---")

    # --- Read Input ---
    file_content = ""
    try:
        file_content = read_local_file(track_identifier)
        logger.info(f"Successfully read input ({len(file_content)} chars).")
    except Exception as e:
        logger.error(f"Failed to read input for track {track_identifier}: {e}", exc_info=True)
        raise RepetitorError(f"Input read error for {track_identifier}") from e

    # --- Text Validation ---
    logger.info("Validating text format...")
    user_config = UserConfig(superuser=True) # Or determine based on config/user
    processed_headers = {}
    def header_processor(lines):
        if lines and lines[0].startswith(HEADER_PREFIX):
            # Make sure cfg object is accessible or pass it if needed
            cfg.german_audio_source_filename = lines[0][len(HEADER_PREFIX):].strip()
            processed_headers['german_audio_source_filename'] = cfg.german_audio_source_filename
            logger.info(f"Detected audio source header: {cfg.german_audio_source_filename}")

    try:
        # Ensure validator is created correctly based on config (e.g., languages)
        validator = TextValidator.get_de_en_ru_validator(user_config)
        validation_result = validator.validate_and_fixup_text_format(
            file_content, user_config, header_processor)
        if not validation_result.is_valid:
            logger.error(f"Text validation failed: {validation_result.error_message}")
            raise RepetitorError(f"Text validation failed: {validation_result.error_message}")
        logger.info("Text validation successful.")
    except Exception as e:
        logger.error(f"Error during text validation: {e}", exc_info=True)
        raise RepetitorError("Text validation error") from e

    # Update config based on processed headers if necessary
    # Example: if processed_headers.get('german_audio_source_filename'): ...

    # --- Phrase Parsing ---
    logger.info("Parsing phrases...")
    try:
        phrases_supplier = PhrasesReader(file_content=file_content)
        # Potentially set translator if needed: phrases_supplier.set_translator(...)
        phrases = phrases_supplier.get_phrases()
        logger.info(f"Parsed {len(phrases)} phrases.")
        if not phrases:
            logger.warning("Phrases list is empty. Nothing to process for this track.")
            return # Or raise error depending on desired behavior
    except PhraseParsingError as e:
        logger.error(f"Failed to parse phrases: {e}", exc_info=True)
        raise RepetitorError("Phrase parsing error") from e
    except Exception as e:
        logger.error(f"Unexpected error during phrase parsing: {e}", exc_info=True)
        raise RepetitorError("Unexpected phrase parsing error") from e


    # --- Core Repetitor Logic ---
    logger.info("Initializing language repetitor...")
    try:
        render_job = RenderJob(cfg, phrases) # Assumes RenderJob class exists
        language_repetitor = LanguageRepetitor(render_job) # Assumes LanguageRepetitor class exists
        logger.info("Starting media track creation...")
        language_repetitor.create_media_track()
        logger.info("Media track creation completed.")
    except Exception as e:
        logger.error(f"Error during media track creation: {e}", exc_info=True)
        raise RepetitorError("Media track creation failed") from e

    logger.info(f"--- Successfully finished processing track: {track_identifier} ---")


def langrepeater_main(track_in, create_video = False):
    print(f"track_in:{track_in} create_video:{create_video}")

    # global logger
    """Main application entry point."""
    start_ts = time.time()
    logger.info("="*20 + " GermanRepetitor Started " + "="*20)
    # --- Argument Parsing (Optional) ---
    # parser = argparse.ArgumentParser(description="German Language Repetitor")
    # # parser.add_argument('--config', type=str, help='Path to config file', default='config.yaml')
    # parser.add_argument('--track', type=str, help='Specify a single track file to process (overrides default tracks)')
    # args = parser.parse_args()
    # args.track = track_in

    # --- Determine Mode ---
    try:
        config_helper = LanguageRepetitorConfig(track_in) # Temp config to get mode
        # logger.debug(f"Environment variables: {os.environ}") # Use debug level
    except Exception as e:
        logger.critical(f"Failed to determine application mode: {e}", exc_info=True)
        sys.exit(1)

    # --- Determine Tracks ---
    tracks_to_process = []
    if track_in:
        tracks_to_process = [track_in]
        logger.info(f"Processing specified track: {track_in}")
    else:
        raise ValueError("track not specified!")

    if not tracks_to_process:
       logger.error("No input tracks specified or found.")
       sys.exit(1)


    # --- Process Each Track ---
    errors_occurred = False
    for track_id in tracks_to_process:
        try:
            # Create a specific config for this track run
            cfg = create_config(track_identifier=track_id, create_video=create_video)
            run_track_processing(cfg, track_id)
        except ConfigError as e:
             logger.error(f"Configuration error for track {track_id}: {e}", exc_info=True)
             errors_occurred = True
             exit(1)
        except RepetitorError as e:
             logger.error(f"Processing error for track {track_id}: {e}", exc_info=True)
             errors_occurred = True
             exit(1)
        except Exception as e:
             logger.critical(f"Unhandled critical error processing track {track_id}: {e}", exc_info=True)
             errors_occurred = True
             exit(1)
             # Decide whether to continue with other tracks or exit
             # break

    # --- Final Summary ---
    duration_sec = time.time() - start_ts
    completion_status = "with errors" if errors_occurred else "successfully"
    logger.info(f"Finished all tasks {completion_status}.")
    logger.info(f"Total Duration: {duration_sec:.2f} seconds ({duration_sec / 60:.2f} minutes).")
    logger.info("="*20 + " GermanRepetitor Finished " + "="*20)

    sys.exit(1 if errors_occurred else 0)


