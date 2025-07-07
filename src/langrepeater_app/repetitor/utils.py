# german_repetitor/repetitor/utils.py

import logging
from pathlib import Path
from typing import Optional

# Project Imports (assuming exceptions are defined)
from src.langrepeater_app.repetitor.exceptions import InputError

logger = logging.getLogger(__name__)

def read_local_file(file_path_str: str, encoding: str = 'utf-8') -> str:
    """
    Reads the entire content of a local text file.
    Equivalent to Java's GermanRepetitorMain.readFile.

    Args:
        file_path_str: The path to the file as a string.
        encoding: The text encoding to use (default: 'utf-8').

    Returns:
        The content of the file as a single string.

    Raises:
        InputError: If the file cannot be found or read.
    """
    file_path = Path(file_path_str)
    logger.debug(f"Attempting to read local file: {file_path.resolve()}")

    if not file_path.is_file():
        logger.error(f"Input file not found or is not a regular file: {file_path.resolve()}")
        raise InputError(f"File not found or is not a file: {file_path_str}")

    try:
        content = file_path.read_text(encoding=encoding)
        logger.info(f"Successfully read {len(content)} characters from {file_path.resolve()}")
        return content
    except FileNotFoundError: # Should be caught by is_file, but good practice
        logger.error(f"Input file not found during read attempt: {file_path.resolve()}")
        raise InputError(f"File not found: {file_path_str}")
    except IOError as e:
        logger.error(f"IOError reading file {file_path.resolve()}: {e}", exc_info=True)
        raise InputError(f"Could not read file: {file_path_str} ({e})") from e
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error reading file {file_path.resolve()} with encoding '{encoding}': {e}", exc_info=True)
        raise InputError(f"Encoding error reading file {file_path_str} with '{encoding}'") from e
    except Exception as e:
        logger.error(f"Unexpected error reading file {file_path.resolve()}: {e}", exc_info=True)
        raise InputError(f"Unexpected error reading file {file_path_str}: {e}") from e

# --- Add other utility functions as needed ---
# For example, functions for path manipulation, safe filename creation, etc.

# def create_safe_filename(input_string: str) -> str:
#     """Creates a filesystem-safe filename from an input string."""
#     # Remove or replace invalid characters
#     safe_name = "".join(c if c.isalnum() else "_" for c in input_string)
#     # Optional: Truncate length
#     max_len = 100
#     return safe_name[:max_len]

