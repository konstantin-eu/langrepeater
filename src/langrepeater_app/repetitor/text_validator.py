# german_repetitor/repetitor/text_validator.py

import re
import logging
from dataclasses import dataclass
from typing import Set, Optional, Callable, List

# Assuming constants are defined here or imported
from src.langrepeater_app.repetitor.constants import (
    COMMENT_PREFIX,
    DESCRIPTION_PREFIX,
    HEADER_PREFIX,
    MAX_TTS_TEXT_LENGTH, # Assuming this maps to maxTextLengthValPowerUser
    # Define other limits if needed, Java code had multiple limits
)
# Assuming SubtitleInterval is defined here or imported
from src.langrepeater_app.repetitor.phrasereader.models import SubtitleInterval, SUBTITLE_MARKER

logger = logging.getLogger(__name__)

# --- Character Sets (based on Java static block [cite: 373-392]) ---

# Basic Latin letters and digits
_BASE_LATIN_DIGITS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
# Common punctuation and symbols allowed
_SPEC_SYMBOLS = set(" |.,?!;:'\"\\-()/“”’‘+%$&") # Added common quotes
# German specific characters allowed german set
_DE_UMLAUTS_SZ = set("äöüßÄÖÜ")
# Cyrillic characters
_CYRILLIC = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")

# Combined sets
ENG_LETTERS: Set[str] = _BASE_LATIN_DIGITS | _SPEC_SYMBOLS
DE_LETTERS: Set[str] = _BASE_LATIN_DIGITS | _SPEC_SYMBOLS | _DE_UMLAUTS_SZ
# Used for descriptions or translations that might mix German, Russian, English
DE_EN_RU_LETTERS: Set[str] = DE_LETTERS | _CYRILLIC | ENG_LETTERS

# Add '>' if superuser allows it (conditionally added in get_... methods)
# SUPERUSER_EXTRA_CHARS = {'>'}


# --- Data Classes ---

@dataclass
class UserConfig:
    """Configuration for the validator, e.g., user privileges."""
    superuser: bool = True
    # Add other config options if needed

@dataclass
class ValidationResult:
    """Result of the validation process."""
    is_valid: bool
    error_message: Optional[str] = None
    # Add more fields if needed, e.g., line number of error

# --- Validator Class ---

class TextValidator:
    """
    Validates the format and content of the input phrase text.
    Equivalent to Java's TextValidator.java
    """
    # --- Constants from Java ---
    PER_DAY_USER_LIMIT_VAL = 10000 # Not used in validation logic itself, maybe for API limits?
    MAX_LINE_LENGTH_VAL = 550 # Java: 400
    MAX_TEXT_LENGTH_VAL = 6000 # Java: 6000
    MAX_TEXT_LENGTH_VAL_POWER_USER = 100000 # Java: 40000 (using TTS limit)

    def __init__(self, allowed_chars_translation: Set[str], allowed_chars_german: Set[str]):
        """
        Initializes the validator with specific character sets.

        Args:
            allowed_chars_translation: Set of allowed characters for translation/description lines.
            allowed_chars_german: Set of allowed characters for German lines.
        """
        self.allowed_chars_translation = allowed_chars_translation
        self.allowed_chars_german = allowed_chars_german
        logger.debug(f"Validator initialized. German chars: {len(self.allowed_chars_german)}, Translation chars: {len(self.allowed_chars_translation)}")

    @classmethod
    def get_de_en_validator(cls, user_config: UserConfig) -> 'TextValidator':
        """Creates a validator for German and English/general text."""
        german_chars = DE_LETTERS.copy()
        trans_chars = DE_LETTERS.copy() # Assuming EN uses DE subset + basic latin
        # if user_config.superuser:
        #     german_chars.update(SUPERUSER_EXTRA_CHARS)
        #     trans_chars.update(SUPERUSER_EXTRA_CHARS)
        return cls(trans_chars, german_chars)

    @classmethod
    def get_de_en_ru_validator(cls, user_config: UserConfig) -> 'TextValidator':
        """Creates a validator allowing German, English, and Russian characters."""
        german_chars = DE_LETTERS.copy()
        trans_chars = DE_EN_RU_LETTERS.copy()
        # if user_config.superuser:
        #     german_chars.update(SUPERUSER_EXTRA_CHARS)
        #     trans_chars.update(SUPERUSER_EXTRA_CHARS)
        return cls(trans_chars, german_chars)

    def _check_line(self, line: str, allowed_chars: Set[str], user_config: UserConfig) -> Optional[str]:
        """
        Checks if all characters in a line are within the allowed set.

        Args:
            line: The string line to check.
            allowed_chars: The set of permissible characters.
            user_config: The user configuration.

        Returns:
            The first invalid character found, or None if the line is valid.
        """
        # Potential change to match Java's superuser logic exactly:
        for char in line:
            if user_config.superuser:
                # If superuser, only return if NOT allowed AND ALSO NOT letter/digit
                if char not in allowed_chars and not char.isalnum():  # isalnum is Python's letter/digit check
                    # Maybe also check for space? Java didn't explicitly check space here.
                    # if char not in allowed_chars and not (char.isalnum() or char.isspace()):
                    return char
            elif char not in allowed_chars:  # Non-superuser check
                return char
        return None

    def validate_and_fixup_text_format(
        self,
        text: str,
        user_config: UserConfig,
        header_processor: Optional[Callable[[List[str]], None]] = None
    ) -> ValidationResult:
        """
        Validates the structure and character content of the input text.

        Args:
            text: The raw input text content.
            user_config: User configuration settings.
            header_processor: An optional callback function to process header lines.

        Returns:
            A ValidationResult object.
        """
        logger.info("Starting text validation...")
        max_len = self.MAX_TEXT_LENGTH_VAL_POWER_USER if user_config.superuser else self.MAX_TEXT_LENGTH_VAL
        text_trimmed = text.strip()

        if not text_trimmed:
             return ValidationResult(is_valid=False, error_message="Input text cannot be empty.")

        if len(text_trimmed) > max_len:
            return ValidationResult(
                is_valid=False,
                error_message=f"Overall text size ({len(text_trimmed)}) exceeds limit ({max_len})."
            )

        lines = [line for line in text_trimmed.splitlines() if line.strip()] # Split and remove empty lines

        if not lines:
             return ValidationResult(is_valid=False, error_message="Input text contains no non-empty lines after stripping.")

        # --- Process Header ---
        if header_processor:
            try:
                # Pass only lines potentially containing headers
                header_lines = [line for line in lines if line.startswith(HEADER_PREFIX)]
                header_processor(header_lines)
            except Exception as e:
                 logger.error(f"Error in header processor callback: {e}", exc_info=True)
                 exit(1)
                 # Decide if this is a fatal error
                 # return ValidationResult(is_valid=False, error_message="Header processing failed.")

        # --- State Machine for Validation ---
        expecting_german = True
        expecting_description = True
        last_german_line = ""

        for i, line_raw in enumerate(lines):
            line_num = i + 1 # 1-based index for messages
            line = line_raw.strip()

            # Skip comments
            if line.startswith(COMMENT_PREFIX):
                continue

            # Handle potential subtitle interval lines (if superuser)
            current_interval: Optional[SubtitleInterval] = None
            line_content_for_validation = line # Start with the full line
            if SUBTITLE_MARKER in line:
                if user_config.superuser:
                    current_interval = SubtitleInterval.from_line(line)
                    if current_interval.is_valid():
                         # If interval is valid, assume the *next* line is the actual phrase
                         # This might need adjustment based on exact format rules
                         logger.debug(f"Line {line_num}: Parsed subtitle interval. Expecting phrase on next line.")
                         # We might skip validation on the timestamp line itself,
                         # or validate the audio filename if present.
                         # For now, let's assume the next line holds the content.
                         continue # Skip to next line
                    else:
                         # If interval marker present but invalid, treat as normal text? Or error?
                         logger.warning(f"Line {line_num}: Found '-->' but failed to parse valid interval.")
                         # Fall through to treat as normal text for now
                else:
                    # Non-superusers cannot have subtitle markers
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Line {line_num}: Subtitle marker ('-->') found, but not allowed for this user."
                    )


            # Check line length limit
            if len(line_content_for_validation) > self.MAX_LINE_LENGTH_VAL:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Line {line_num}: Length ({len(line_content_for_validation)}) exceeds limit ({self.MAX_LINE_LENGTH_VAL}). Content: '{line_content_for_validation[:50]}...'"
                )

            is_description_line = line_content_for_validation.startswith(DESCRIPTION_PREFIX)

            # --- State Logic ---
            if expecting_description and is_description_line:
                expecting_german = True # Reset for next pair/description
                desc_content = line_content_for_validation[len(DESCRIPTION_PREFIX):].strip()
                if not desc_content:
                    continue
                    # return ValidationResult(is_valid=False, error_message=f"Line {line_num}: Description marker '*' found, but content is empty.")
                invalid_char = self._check_line(desc_content, self.allowed_chars_translation, user_config)
                if invalid_char:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Line {line_num} (Description): Invalid character '{invalid_char}'. Allowed: Translation/Description set. Content: '{desc_content[:50]}...'"
                    )
                # Description line is valid, continue to next line
                last_german_line = "" # Reset last German line tracker

            elif is_description_line: # Description not expected here
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Line {line_num}: Unexpected description line found after German phrase '{last_german_line[:50]}...'. Expected translation."
                )

            elif expecting_german:
                invalid_char = self._check_line(line_content_for_validation, self.allowed_chars_german, user_config)
                if invalid_char:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Line {line_num} (Expected German): Invalid character '{invalid_char}'. Allowed: German set. Content: '{line_content_for_validation[:50]}...'"
                    )
                # German line is valid
                last_german_line = line_content_for_validation
                expecting_german = False
                expecting_description = False # Can't be description immediately after German

            else: # Expecting translation
                invalid_char = self._check_line(line_content_for_validation, self.allowed_chars_translation, user_config)
                if invalid_char:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Line {line_num} (Expected Translation): Invalid character '{invalid_char}'. Allowed: Translation/Description set. Content: '{line_content_for_validation[:50]}...'"
                    )
                # Translation line is valid
                expecting_german = True # Reset for next pair/description
                expecting_description = True
                last_german_line = "" # Reset

        # --- Final Check ---
        if not expecting_german: # Ended expecting a translation
             return ValidationResult(
                is_valid=False,
                error_message=f"Validation Error: The last German phrase ('{last_german_line[:50]}...') is missing its corresponding translation line."
            )

        logger.info("Text validation completed successfully.")
        return ValidationResult(is_valid=True, error_message="The text format is valid.")

