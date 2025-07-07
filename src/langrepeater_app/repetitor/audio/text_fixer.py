# german_repetitor/repetitor/audio/text_fixer.py

import logging
import re
from typing import Optional

# Project Imports (assuming Language enum exists)
from src.langrepeater_app.repetitor.constants import Language, MAX_TTS_TEXT_LENGTH

logger = logging.getLogger(__name__)

class SsmlSrtFixer:
    """
    Provides methods to clean and format text for SSML and SRT usage.
    Based on Java's SsmlAndSrtFixer, DeDateReplacer, DeNumberDateReplacer.
    """

    # --- German Date/Number Patterns (from Java examples) ---
    # Regex for DD. Month YYYY (e.g., 3. Juni 2024) - requires month name lookup
    # Using a simpler regex for DD. Month first, then handle year if needed
    # Matches day number (optional dot), space, German month name
    _de_date_pattern = re.compile(
        r"(\b\d{1,2})\.?(?=\s+(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Jan\.?|Feb\.?|Mrz\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Okt\.?|Nov\.?|Dez\.?)\b)",
        re.IGNORECASE
    )
    # Regex for DD.MM.YYYY
    _de_numeric_date_pattern = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
    # Regex for numbers with dots as thousands separators (e.g., 1.000.000)
    _de_number_pattern = re.compile(r"(\d{1,3}(?:\.\d{3})+)") # Matches 1.000, 10.000, 1.000.000 etc.
    # Regex for numbers with comma as decimal separator (e.g., 1,5)
    _de_decimal_pattern = re.compile(r"(\b\d+),(\d+\b)") # Matches 1,5 100,23 etc.

    # German Ordinal Numbers (up to 31 for dates)
    _de_ordinal_map = {
        1: "erste", 2: "zweite", 3: "dritte", 4: "vierte", 5: "fünfte",
        6: "sechste", 7: "siebte", 8: "achte", 9: "neunte", 10: "zehnte",
        11: "elfte", 12: "zwölfte", 13: "dreizehnte", 14: "vierzehnte", 15: "fünfzehnte",
        16: "sechzehnte", 17: "siebzehnte", 18: "achtzehnte", 19: "neunzehnte", 20: "zwanzigste",
        21: "einundzwanzigste", 22: "zweiundzwanzigste", 23: "dreiundzwanzigste", 24: "vierundzwanzigste",
        25: "fünfundzwanzigste", 26: "sechsundzwanzigste", 27: "siebenundzwanzigste", 28: "achtundzwanzigste",
        29: "neunundzwanzigste", 30: "dreißigste", 31: "einunddreißigste"
    }
    # German Month Names (mapping abbreviations to full names)
    _de_month_map = {
        'jan': 'Januar', 'feb': 'Februar', 'mär': 'März', 'mrz': 'März', 'apr': 'April',
        'mai': 'Mai', 'jun': 'Juni', 'jul': 'Juli', 'aug': 'August', 'sep': 'September',
        'okt': 'Oktober', 'nov': 'November', 'dez': 'Dezember'
    }


    def _fix_german_dates(self, text: str) -> str:
        """Replaces German date numbers with ordinal words (e.g., 3. -> dritte)."""
        def replace_date(match):
            day_num = int(match.group(1))
            ordinal = self._de_ordinal_map.get(day_num)
            if ordinal:
                logger.debug(f"Replacing German date: {match.group(0)} -> {ordinal}")
                return ordinal # Return only the word, space is handled by regex lookahead
            else:
                logger.warning(f"Could not find ordinal for day number: {day_num}")
                return match.group(0) # Return original if not found

        try:
            text = self._de_date_pattern.sub(replace_date, text)
            # TODO: Add replacement logic for DD.MM.YYYY if needed, converting to text
            # This is more complex as it involves month names and potentially year pronunciation.
            # Example (very basic, needs improvement):
            # text = self._de_numeric_date_pattern.sub(lambda m: f"{self._de_ordinal_map.get(int(m.group(1)), m.group(1))} {self._de_month_map.get(int(m.group(2)), m.group(2))} {m.group(3)}", text)

        except Exception as e:
            logger.error(f"Error during German date fixing: {e}", exc_info=True)
            # Return original text on error
            exit(1)
        return text

    def _fix_german_numbers(self, text: str) -> str:
        """Removes thousands separators (dots) and replaces decimal commas with dots for TTS."""
        def replace_number(match):
            num_str = match.group(1)
            # Remove dots used as thousands separators
            cleaned_num = num_str.replace('.', '')
            logger.debug(f"Replacing German number format: {num_str} -> {cleaned_num}")
            return cleaned_num

        def replace_decimal(match):
            # Replace comma decimal separator with dot
            fixed_decimal = f"{match.group(1)} Punkt {match.group(2)}" # Say "Punkt"
            # Alternative: replace with actual dot if TTS handles it well:
            # fixed_decimal = f"{match.group(1)}.{match.group(2)}"
            logger.debug(f"Replacing German decimal format: {match.group(0)} -> {fixed_decimal}")
            return fixed_decimal

        try:
            text = self._de_number_pattern.sub(replace_number, text)
            text = self._de_decimal_pattern.sub(replace_decimal, text)
        except Exception as e:
            logger.error(f"Error during German number fixing: {e}", exc_info=True)
            # Return original text on error
            exit(1)
        return text

    def fix_tss_text_segment(self, text: str, language: Optional[Language] = None) -> str:
        """
        Applies general cleanup and language-specific fixes to text before TTS.
        Equivalent to Java's SsmlAndSrtFixer.fixTssTextSegment.

        Args:
            text: The input text segment.
            language: The language of the text (used for specific fixes).

        Returns:
            The cleaned and fixed text.
        """
        if not text:
            return ""

        # Strip leading/trailing whitespace
        text = text.strip()
        if not text:
            return ""

        # Add trailing punctuation if missing (basic check)
        # More sophisticated sentence ending detection might be needed
        if not re.search(r'[.?!;,:\-]$', text):
            text += "."

        # Apply language-specific fixes
        if language == Language.DE:
            text = self._fix_german_dates(text)
            text = self._fix_german_numbers(text)
        # Add elif blocks for other languages if specific fixes are needed

        # TODO: Add more general fixes if required (e.g., common abbreviations)
        # text = text.replace("...", " dot dot dot ") # Example

        return text

    def _fix_text_for_ssml(self, text: str) -> str:
        """Escapes characters problematic for SSML."""
        if not text:
            return ""
        # Basic XML escaping - most crucial are &, <, >
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        # Quotes are less critical inside SSML text nodes but good practice to escape
        text = text.replace("\"", "&quot;")
        text = text.replace("'", "&apos;")
        return text

    def ssml_wrap_text(self, text: str, lang_code: str, speed_percent: Optional[str] = None) -> str:
        """
        Wraps cleaned text in basic SSML tags (<speak>, <prosody>).

        Args:
            text: The text content (should already be cleaned by fix_tss_text_segment).
            lang_code: The language code (e.g., "en-US", "de-DE").
            speed_percent: Optional speaking rate (e.g., "90%").

        Returns:
            The SSML string.
        """
        fixed_content = self._fix_text_for_ssml(text)

        # Build SSML structure
        ssml = "<speak>"
        if speed_percent:
            # Validate speed format? Remove '%' for attribute value?
            # Google Cloud expects rate as percentage string like "100%" or number like 1.0
            # Let's assume the input 'speed_percent' is already in the correct format string.
            # Basic check:
            rate_value = speed_percent.strip()
            # if not rate_value.endswith('%'): rate_value += "%" # Ensure % if missing? Depends on API.
            ssml += f'<prosody rate="{rate_value}">'

        ssml += fixed_content

        if speed_percent:
            ssml += "</prosody>"
        ssml += "</speak>"

        # Final length check (optional, but good practice)
        if len(ssml) >= MAX_TTS_TEXT_LENGTH:
            logger.warning(f"Generated SSML is very long ({len(ssml)} chars). May exceed API limits.")
            # Truncation logic could be added here if needed, but might break SSML structure

        return ssml


    def fix_text_for_srt(self, text: str) -> str:
        """
        Applies basic fixes/escaping for text to be included in SRT files.
        Equivalent to Java's SsmlAndSrtFixer.fixTextForSrt.
        """
        if not text:
            return ""
        # Basic SRT doesn't require much escaping like XML/HTML.
        # Main issues are usually HTML-like tags if the player interprets them.
        # Let's escape '<' and '>' to prevent accidental tag interpretation.
        # Ampersand '&' is usually fine in SRT.
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        # Newlines within a caption block are usually handled correctly by SRT parsers.
        return text

