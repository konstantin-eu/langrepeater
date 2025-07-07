# german_repetitor/repetitor/phrasereader/models.py

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

SUBTITLE_MARKER = " --> " # Marker used in subtitle timestamp lines

@dataclass
class SubtitleInterval:
    """
    Represents a subtitle timestamp interval and potentially an associated audio file.
    Equivalent to Java's SubtitleInterval.java
    """
    start_ts_sec: float = -1.0 # Start time in seconds, -1.0 if invalid/not present
    end_ts_sec: float = -1.0   # End time in seconds, -1.0 if invalid/not present
    audio_file: Optional[str] = None # Optional audio filename associated with the interval
    original_line: str = "" # Store the original line for reference or debugging

    @staticmethod
    def _parse_timestamp_to_seconds(timestamp: str) -> float:
        """Parses HH:MM:SS,ms or HH:MM:SS.ms timestamp to seconds."""
        try:
            # Support both comma and dot for milliseconds separator
            parts = re.split('[:,.]', timestamp)
            if len(parts) != 4:
                raise ValueError("Timestamp format is not HH:MM:SS,ms or HH:MM:SS.ms")
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            milliseconds = int(parts[3])
            # Ensure milliseconds are padded correctly if needed (e.g., "1" -> 100ms)
            if len(parts[3]) == 1:
                 milliseconds *= 100
            elif len(parts[3]) == 2:
                 milliseconds *= 10

            total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
            return total_ms / 1000.0
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse timestamp '{timestamp}': {e}")
            raise ValueError(f"Invalid timestamp format: {timestamp}") from e

    @classmethod
    def from_line(cls, line: str) -> 'SubtitleInterval':
        """
        Creates a SubtitleInterval object by parsing a line.
        Expects format like: "HH:MM:SS,ms --> HH:MM:SS,ms [audio_file.wav]"
        The audio file part is optional.
        """
        line = line.strip()
        start_ts = -1.0
        end_ts = -1.0
        audio_file = None

        if SUBTITLE_MARKER in line:
            try:
                parts = line.split(SUBTITLE_MARKER, 1)
                start_time_str = parts[0].strip()
                end_part = parts[1].strip()

                # Check if audio file is present after end timestamp
                # Split only once to handle filenames with spaces
                time_audio_split = end_part.split(maxsplit=1)
                end_time_str = time_audio_split[0].strip()
                if len(time_audio_split) > 1:
                    audio_file = time_audio_split[1].strip()

                start_ts = cls._parse_timestamp_to_seconds(start_time_str)
                end_ts = cls._parse_timestamp_to_seconds(end_time_str)

                # Basic validation
                if start_ts < 0 or end_ts < 0 or end_ts < start_ts:
                     logger.warning(f"Invalid timestamp values parsed from line '{line}': start={start_ts}, end={end_ts}")
                     # Reset to invalid state if parsing looks wrong
                     start_ts = -1.0
                     end_ts = -1.0
                     audio_file = None # Also invalidate audio file if times are bad

            except Exception as e:
                logger.warning(f"Could not parse subtitle interval from line '{line}': {e}")
                start_ts = -1.0
                end_ts = -1.0
                audio_file = None
                exit(1)

        return cls(start_ts_sec=start_ts, end_ts_sec=end_ts, audio_file=audio_file, original_line=line)

    def is_valid(self) -> bool:
        """Checks if the interval has valid (non-negative) timestamps."""
        return self.start_ts_sec >= 0 and self.end_ts_sec >= 0

    def __str__(self) -> str:
        if self.is_valid():
            return f"Interval[{self.start_ts_sec:.3f}s -> {self.end_ts_sec:.3f}s" + (f", file='{self.audio_file}'" if self.audio_file else "") + "]"
        else:
            return "Interval[Invalid]"


@dataclass
class Phrase:
    """
    Represents either a description line or an original/translation phrase pair.
    Equivalent to Java's Phrase.java
    """
    original: str = ""          # The original language phrase (e.g., German)
    translation: str = ""       # The translated phrase (e.g., English, Russian)
    description: str = ""       # A description/comment line (starts with '*')
    original_ts_line: str = "" # Stores the full timestamp line if the original came from a timed source

    # Field to indicate if this instance represents a description
    # Initialized automatically after the object is created
    is_description: bool = field(init=False, default=False)

    def __post_init__(self):
        """Called after the dataclass is initialized."""
        # Determine if this is a description based on whether description field has content
        self.is_description = bool(self.description)
        # Basic cleanup (optional, could be done during parsing)
        self.original = self.original.strip()
        self.translation = self.translation.strip()
        self.description = self.description.strip()

    @classmethod
    def make_description(cls, desc_text: str) -> 'Phrase':
        """Factory method to create a description-type Phrase."""
        return cls(description=desc_text)

    @classmethod
    def make_phrase(cls, orig_text: str, trans_text: str, ts_line: str = "") -> 'Phrase':
        """Factory method to create an original/translation-type Phrase."""
        return cls(original=orig_text, translation=trans_text, original_ts_line=ts_line)

    def __str__(self) -> str:
        if self.is_description:
            return f"Description: '{self.description}'"
        else:
            ts_info = f" (TS: '{self.original_ts_line}')" if self.original_ts_line else ""
            return f"Phrase[Orig: '{self.original}'{ts_info}, Trans: '{self.translation}']"

