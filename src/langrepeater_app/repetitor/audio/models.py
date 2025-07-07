import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, TYPE_CHECKING
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig, SubGroupType, SegmentType

# Avoid circular imports for type hinting
# These imports assume the structure previously defined
if TYPE_CHECKING:
    from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig, SubGroupType
    from src.langrepeater_app.repetitor.constants import Language
    # Import Phrase from phrasereader models if needed for RenderJob typing
    from src.langrepeater_app.repetitor.phrasereader.models import Phrase, SubtitleInterval

logger = logging.getLogger(__name__)

@dataclass
class Caption:
    """
    Represents a single subtitle caption entry.
    Equivalent to Java's Caption.java
    """
    start_ts_ms: int
    end_ts_ms: int
    text: str
    index: Optional[int] = None # Optional index for SRT generation

    def _to_subtitle_timestamp(self, total_milliseconds: int) -> str:
        """Converts milliseconds to HH:MM:SS,ms format."""
        if total_milliseconds < 0:
            total_milliseconds = 0
        hours = total_milliseconds // (3600 * 1000)
        milliseconds_remaining = total_milliseconds % (3600 * 1000)
        minutes = milliseconds_remaining // (60 * 1000)
        milliseconds_remaining %= (60 * 1000)
        seconds = milliseconds_remaining // 1000
        milliseconds = milliseconds_remaining % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def to_srt_segment(self, idx: int) -> str:
        """Formats the caption as an SRT block."""
        start_str = self._to_subtitle_timestamp(self.start_ts_ms)
        end_str = self._to_subtitle_timestamp(self.end_ts_ms)
        # Basic text fixing for SRT (more might be needed)
        # Needs SsmlSrtFixer equivalent logic here or passed in
        # from .text_fixer import SsmlSrtFixer # Example import
        # fixed_text = SsmlSrtFixer().fix_text_for_srt(self.text)
        fixed_text = self.text # Placeholder - actual fixing needed
        return f"{idx}\n{start_str} --> {end_str}\n{fixed_text}\n\n"

    def scale_caption(self, scale_factor: float):
        """Scales the start and end timestamps."""
        if scale_factor <= 0:
            logger.warning("Attempted to scale caption by non-positive factor.")
            return
        self.start_ts_ms = int(self.start_ts_ms * scale_factor)
        self.end_ts_ms = int(self.end_ts_ms * scale_factor)

@dataclass
class WAVHeader:
    """
    Stores WAV file header information.
    Equivalent to Java's WAVHeaderReader.WAVHeader
    """
    sample_rate: int
    bit_depth: int
    channels: int

    # Default values based on Java code
    DEFAULT_SAMPLE_RATE = 22050 # Java: 22050
    DEFAULT_BIT_DEPTH = 16
    DEFAULT_CHANNELS = 1

    @classmethod
    def get_default(cls) -> 'WAVHeader':
        return cls(
            sample_rate=cls.DEFAULT_SAMPLE_RATE,
            bit_depth=cls.DEFAULT_BIT_DEPTH,
            channels=cls.DEFAULT_CHANNELS
        )

@dataclass
class AudioContent:
    """
    Holds loaded PCM audio data and its header.
    Equivalent to Java's AudioContent.java
    """
    header: WAVHeader
    pcm_bytes: bytes # Raw PCM data (without WAV header)

@dataclass
class SegmentVariant:
    """
    Represents one specific audio realization (e.g., cloud, file) for a Segment.
    Replaces the nested Variant class in Java's Segment.
    """
    # Defined in phrasereader.models
    from src.langrepeater_app.repetitor.phrasereader.models import SubtitleInterval

    subtitle_interval: Optional[SubtitleInterval] = None # Relevant for FILE_SEGMENT
    audio_file_key: Optional[str] = None # Path or key to the source audio (e.g., PCM file path, cache key)
    speed_percent: str = "100%" # Speed for TTS generation (e.g., "90%")
    start_time_sec: float = -1.0 # Start time within the audio_file (if applicable)
    end_time_sec: float = -1.0   # End time within the audio_file (if applicable)

    # Runtime calculated duration (can be memoized)
    _duration_ms: Optional[int] = None

    def get_duration_ms(self, config: 'LanguageRepetitorConfig', segment_type: 'SegmentType') -> int:
        """Calculates or retrieves the duration in milliseconds."""
        # This needs proper calculation based on start/end times or loading the audio segment
        # For now, a placeholder calculation based on timestamps if available
        if self._duration_ms is not None:
            return self._duration_ms

        if self.start_time_sec >= 0 and self.end_time_sec >= self.start_time_sec:
             duration_sec = self.end_time_sec - self.start_time_sec
             self._duration_ms = int(duration_sec * 1000)
             if self._duration_ms <= 0 and duration_sec > 0: # Handle very short durations rounding to 0ms
                 self._duration_ms = 1
             elif self._duration_ms < 0:
                 logger.warning(f"Calculated negative duration for variant {self}")
                 self._duration_ms = 0 # Or handle as error

             return self._duration_ms
        else:
             # Duration needs to be determined by loading/generating the audio segment
             # This is a significant gap compared to Java's Mp3Helper approach
             logger.warning(f"Cannot determine duration for variant {self} without loading audio.")
             # Placeholder: return 0 or raise error
             # Returning 0 might cause issues with pause calculations.
             # Consider raising NotImplementedError if duration is essential here.
             return 0 # Or raise NotImplementedError("Duration calculation requires audio loading")

@dataclass
class Segment:
    """
    Represents a piece of text within a SubGroup, potentially with multiple audio variants.
    Equivalent to Java's Segment.java
    """
    text: str # Should be the final, fixed text ready for TTS/display
    language: 'Language'
    is_silent: bool = False # Determined based on text content
    subgroup_config: dict = field(default_factory=dict) # Config specific to the subgroup it belongs to
    # Dictionary mapping SegmentType to its audio realization details
    variants: Dict['SegmentType', SegmentVariant] = field(default_factory=dict)

    def __post_init__(self):
        # Basic silence check (can be made more sophisticated)
        # Needs equivalent of Java's Group.containsNoEnglishOrGermanOrRussianLetters
        # This regex checks for *any* letter from the specified alphabets.
        if not re.search(r'[A-Za-zÄäÖöÜüßА-Яа-я]', self.text, re.IGNORECASE):
             self.is_silent = True

    def select_type(self, subgroup_type: 'SubGroupType', iteration_num: int) -> Optional['SegmentType']:
        """Selects the appropriate SegmentType based on iteration (simple version)."""
        # Java version had complex logic based on iteration count and available types.
        # This needs to be replicated based on the desired behavior.
        # Simple version: return the first available type found in a preferred order.
        preferred_order = [SegmentType.FILE_SEGMENT, SegmentType.GENERATED_CLOUD, SegmentType.GENERATED_CLOUD_BATCH]
        for seg_type in preferred_order:
            if seg_type in self.variants:
                return seg_type
        # Fallback if none of the preferred types are present
        available_types = list(self.variants.keys())
        return available_types[0] if available_types else None


@dataclass
class SubGroup:
    """
    Represents a logical part of a phrase card (description, original, translation).
    Equivalent to the nested SubGroup in Java's Group.java
    """
    subgroup_type: 'SubGroupType'
    delay_override: bool = False # Whether to use a fixed delay after this subgroup
    delay_override_sec: int = 0 # The fixed delay value in seconds
    segments: List[Segment] = field(default_factory=list)
    # Runtime calculated properties
    subtitle_track_caption_text: str = "" # Combined text for subtitles

@dataclass
class Group:
    """
    Represents a full phrase card (either a description or an original/translation pair).
    Equivalent to Java's Group.java
    """
    # Maps SubGroupType to the actual SubGroup object
    subgroups: Dict['SubGroupType', SubGroup] = field(default_factory=dict)
    config: Optional['LanguageRepetitorConfig'] = None # Reference to main config

    def is_description(self) -> bool:
        """Checks if this group represents only a description."""
        from src.langrepeater_app.repetitor.config import SubGroupType
        return len(self.subgroups) == 1 and SubGroupType.DESCRIPTION in self.subgroups

    def get_subgroup_list(self) -> List[SubGroup]:
         """Returns subgroups in a standard order (Original, Translation or just Description)."""
         from src.langrepeater_app.repetitor.config import SubGroupType
         ordered_list = []
         if self.is_description():
             if SubGroupType.DESCRIPTION in self.subgroups:
                 ordered_list.append(self.subgroups[SubGroupType.DESCRIPTION])
         else:
             # Standard order: Original first, then Translation
             if SubGroupType.ORIGINAL_PHRASE in self.subgroups:
                 ordered_list.append(self.subgroups[SubGroupType.ORIGINAL_PHRASE])
             if SubGroupType.TRANSLATION in self.subgroups:
                 ordered_list.append(self.subgroups[SubGroupType.TRANSLATION])
         return ordered_list


@dataclass
class RenderJob:
    """
    Bundles configuration and phrases for processing.
    Equivalent to Java's RenderJob.java
    """
    config: 'LanguageRepetitorConfig'
    phrases: List['Phrase'] # Assumes Phrase is imported or defined elsewhere


@dataclass
class CloudTimepoint:
    """
    Simple data class for start/end times derived from silence detection or TTS API.
    Equivalent to Java's CloudTimepoint.java
    """
    start_time_sec: float
    end_time_sec: float

@dataclass
class PcmPause:
    """
    Represents a detected silence interval in PCM data.
    Equivalent to Java's PcmPause.java
    """
    start_sec: float
    end_sec: float

    def get_middle(self) -> float:
        """Calculates the midpoint of the pause interval."""
        return self.start_sec + (self.end_sec - self.start_sec) / 2.0

    def get_duration(self) -> float:
        """Calculates the duration of the pause interval."""
        return self.end_sec - self.start_sec

