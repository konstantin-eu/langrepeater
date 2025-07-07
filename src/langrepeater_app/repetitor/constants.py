# german_repetitor/repetitor/constants.py

from enum import Enum, auto

# --- Language Definitions ---

# Google Cloud Language Codes (from Language.java and LanguageHelper.java)
DE_LANG_CODE = "de-DE"
RU_LANG_CODE = "ru-RU"
EN_LANG_CODE = "en-US"

class Language(Enum):
    """Represents supported languages."""
    DE = DE_LANG_CODE
    RU = RU_LANG_CODE
    EN = EN_LANG_CODE
    # Add other languages if needed

# --- Google Cloud Voice Names (from Voice.java) ---
# Consider making these configurable instead of hardcoding if they change often
VOICE_RU_STANDARD_A = "ru-RU-Standard-A"
VOICE_DE_STANDARD_A = "de-DE-Standard-A" # Basic in Java enum name
VOICE_DE_WAVENET_A = "de-DE-Wavenet-A"
VOICE_DE_POLYGLOT_1 = "de-DE-Polyglot-1"
VOICE_DE_STUDIO_B = "de-DE-Studio-B"
VOICE_EN_STANDARD_B = "en-US-Standard-B"

# Dictionary mapping Language enum to a default voice (can be expanded)
DEFAULT_VOICES = {
    Language.DE: VOICE_DE_STANDARD_A,
    Language.RU: VOICE_RU_STANDARD_A,
    Language.EN: VOICE_EN_STANDARD_B,
}

# Specific high-quality voices (map as needed in config or logic)
PREMIUM_VOICES = {
    Language.DE: {
        "WaveNet": VOICE_DE_WAVENET_A,
        "Polyglot": VOICE_DE_POLYGLOT_1,
        "Studio": VOICE_DE_STUDIO_B,
    }
    # Add premium voices for other languages if used
}


# --- Segment and SubGroup Types (from SegmentType.java and LanguageRepetitorConfig.java) ---

# class SegmentType(Enum):
#     """Defines the source or type of an audio segment."""
#     GENERATED_CLOUD_BATCH = auto() # Requires silence detection for splitting
#     GENERATED_CLOUD = auto()       # Generated individually, potentially cached
#     FILE_SEGMENT = auto()          # Segment cut from an existing audio file

# class SubGroupType(Enum):
#     """Defines the logical role of a subgroup within a phrase card."""
#     DESCRIPTION = auto()
#     ORIGINAL_PHRASE = auto()
#     TRANSLATION = auto()

# --- Text Prefixes (from PhrasesReader2.java) ---
RUS_PREFIX = "rus:"
DE_PREFIX = "de:"
EN_PREFIX = "en:"
COMMENT_PREFIX = "--"
HEADER_PREFIX = "-- header:" # Specific comment type
DESCRIPTION_PREFIX = "*"

# --- Audio Processing Constants (from LanguageRepetitorConfig.java and others) ---
WAV_HEADER_SIZE = 44
# Threshold for detecting voice frames in PCM data (absolute value sum or similar metric)
# Value from Java: 70 (needs careful tuning in Python based on implementation)
VOICE_AMPLITUDE_THRESHOLD = 70
# Pause inserted between generated phrases in batch TTS SSML
PAUSE_BREAK_SEC_INT = 2
# Minimum duration of silence to be considered a significant pause (in seconds)
SILENCE_MIN_DURATION_SEC = 1.8 # Java: 1.8
# Offset from the middle of detected silence to adjust segment boundaries (in seconds)
STEP_FROM_SILENCE_MIDDLE_SEC = 0.7 # Java: 0.7
# Default fixed delay after original phrase if dynamic delay is not used (in seconds)
ORIG_SEGMENT_DELAY_OVERRIDE_SEC = 3 # Java: 3
# Default fixed delay after translation phrase (in seconds)
TRANSLATION_SEGMENT_DELAY_OVERRIDE_SEC = 1 # Java: 1
# Default fixed delay after description phrase (in seconds)
DESCRIPTION_SEGMENT_DELAY_OVERRIDE_SEC = 0 # Java: 0
# Default TTS speed for original language segments
ORIG_SEGMENT_SPEED = "100%" # Java: 90%
# Default TTS speed for translation/description segments
TRANSLATION_SEGMENT_SPEED = "100%" # Java: 100%
# Extra silence added at the very end of the track (in seconds)
SILENCE_AT_THE_END_SEC = 5 # Java: 5
# Max text length for Google Cloud TTS API (check current limits)
MAX_TTS_TEXT_LENGTH = 4800 # Java: 5000

# --- File System ---
DEFAULT_TEMP_DIR_NAME = "temp"
DEFAULT_OUTPUT_DIR_NAME = "out"
DEFAULT_IMAGE_DIR_NAME = "img"
DEFAULT_PHRASES_DIR_NAME = "phrases"

# --- Other ---
# Default image filename (make configurable if needed)
DEFAULT_IMAGE_FILENAME = "img_germ_flag_960_720.jpg" # Example from Java

