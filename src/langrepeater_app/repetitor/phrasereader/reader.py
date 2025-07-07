# german_repetitor/repetitor/phrasereader/reader.py

import logging
from typing import List, Optional

# Project Imports
from src.langrepeater_app.repetitor.constants import COMMENT_PREFIX, DESCRIPTION_PREFIX, HEADER_PREFIX
from src.langrepeater_app.repetitor.exceptions import PhraseParsingError
# Import models from the current package
from src.langrepeater_app.repetitor.phrasereader.models import Phrase, SubtitleInterval

logger = logging.getLogger(__name__)

import re



class PhrasesReader:
    """
    Parses input text content into a list of Phrase objects.
    Handles descriptions, comments, and original/translation pairs,
    including optional subtitle timestamps.
    Equivalent logic to Java's PhrasesReader2.java
    """

    def __init__(self, file_content: str, has_translation: bool = True):
        """
        Initializes the PhrasesReader.

        Args:
            file_content: The raw text content to parse.
            has_translation: Flag indicating if translation lines are expected
                             in the input format (defaults to True).
        """
        self.file_content = file_content
        self.has_translation = has_translation # Determines if we expect pairs
        logger.debug(f"PhrasesReader initialized (has_translation={has_translation})")

    def get_phrases(self) -> List[Phrase]:
        """
        Parses the file_content into a list of Phrase objects.

        Returns:
            A list of Phrase objects.

        Raises:
            PhraseParsingError: If the input format is invalid or parsing fails.
        """
        if not self.file_content:
            logger.warning("Input file content is empty. Returning empty phrase list.")
            return []

        # Split into lines and filter out comments and empty lines
        all_lines = self.file_content.splitlines()
        # Keep original line numbers for error reporting
        lines_with_numbers = [
            (i + 1, line.strip()) for i, line in enumerate(all_lines)
            if line.strip() and not line.strip().startswith(COMMENT_PREFIX)
            # Keep header lines initially, might be filtered later if needed
            # or line.strip().startswith(HEADER_PREFIX)
        ]

        if not lines_with_numbers:
            logger.warning("No valid content lines found after filtering comments/empty lines.")
            return []

        phrases: List[Phrase] = []
        i = 0
        while i < len(lines_with_numbers):
            line_num, current_line = lines_with_numbers[i]

            try:
                if current_line.startswith(DESCRIPTION_PREFIX):
                    # Description line
                    desc_content = current_line[len(DESCRIPTION_PREFIX):].strip()
                    if not desc_content:
                         logger.warning(f"Line {line_num}: Description marker '*' found but content is empty.")
                         # Skip empty descriptions or raise error? Skipping for now.
                         i += 1
                         continue
                    phrases.append(Phrase.make_description(desc_content))
                    i += 1
                else:
                    # Could be a timestamp line or an original phrase line
                    original_ts_line = ""
                    original_line_content = current_line
                    interval = SubtitleInterval.from_line(current_line)

                    if interval.is_valid():
                        # This line is a timestamp line
                        original_ts_line = current_line
                        # The *next* line should be the original phrase content
                        i += 1
                        if i >= len(lines_with_numbers):
                            raise PhraseParsingError(f"Timestamp line {line_num} ('{current_line}') is not followed by a phrase line.", line_number=line_num)
                        original_line_num, original_line_content = lines_with_numbers[i]
                        logger.debug(f"Line {original_line_num}: Identified as original phrase following timestamp {line_num}.")
                    else:
                         # Not a valid timestamp line, treat as original phrase directly
                         original_line_num = line_num # Use current line number

                    # We now have the original phrase content (either current line or next line)
                    if not original_line_content or original_line_content.startswith(DESCRIPTION_PREFIX):
                         # Should not happen if timestamp logic is correct, but check anyway
                         raise PhraseParsingError(f"Expected an original phrase at line {original_line_num}, but found invalid content: '{original_line_content}'", line_number=original_line_num)

                    # Check for translation line
                    translation_line_content = ""
                    if self.has_translation:
                        i += 1 # Move index past the original phrase line
                        if i >= len(lines_with_numbers):
                            raise PhraseParsingError(f"Expected a translation line after original phrase line {original_line_num} ('{original_line_content[:50]}...'), but reached end of input.", line_number=original_line_num)

                        translation_line_num, translation_line_content = lines_with_numbers[i]

                        # Basic check: translation shouldn't look like a description or timestamp
                        if translation_line_content.startswith(DESCRIPTION_PREFIX) or SubtitleInterval.from_line(translation_line_content).is_valid():
                             raise PhraseParsingError(f"Expected a translation at line {translation_line_num}, but found description or timestamp line: '{translation_line_content}'", line_number=translation_line_num)

                        # Optional: Add more checks for translation validity if needed

                    # Create the phrase object
                    phrases.append(Phrase.make_phrase(
                        orig_text=original_line_content,
                        trans_text=translation_line_content,
                        ts_line=original_ts_line
                    ))
                    i += 1 # Move index past the translation line (or the original if no translation expected)

            except Exception as e:
                # Catch potential errors during processing a block and wrap them
                logger.error(f"Error processing line {line_num} ('{current_line[:50]}...'): {e}", exc_info=True)
                exit(1)

                if isinstance(e, PhraseParsingError):
                    raise # Re-raise specific parsing errors
                else:
                    # Wrap unexpected errors
                    raise PhraseParsingError(f"Unexpected error processing line {line_num}: {e}", line_number=line_num) from e

        logger.info(f"Successfully parsed {len(phrases)} phrases.")
        return phrases

