import os
from pathlib import Path
from enum import Enum, auto
import logging
import tempfile

from src.langrepeater_app.repetitor.constants import Language  # Assumes constants.py exists
from src.lib_clean.lib_common import get_app_dir

logger = logging.getLogger(__name__)



class ConfigError(Exception):
    pass


class SubGroupType(Enum):  # From LanguageRepetitorConfig [cite: 224]
    DESCRIPTION = auto()
    ORIGINAL_PHRASE = auto()
    TRANSLATION = auto()


class SegmentType(Enum):
    """Defines the source or type of an audio segment."""
    GENERATED_CLOUD_BATCH = auto()  # Requires silence detection for splitting
    GENERATED_CLOUD = auto()  # Generated individually, potentially cached
    FILE_SEGMENT = auto()  # Segment cut from an existing audio file


# Example structure - adapt heavily based on Java logic
class LanguageRepetitorConfig:
    # --- Constants ---
    WAV_HEADER_SIZE = 44
    VOICE_ACCUMULATED_FRAME_AMPLITUDE_THRESHOLD = 70  # [cite: 182]
    PAUSE_BREAK_SEC_INT = 2  # [cite: 183]
    SILENCE_MIN_DURATION_SEC = 1.8  # [cite: 184]
    STEP_FROM_SILENCE_MIDDLE_SEC = 0.7  # [cite: 185]
    ORIG_SEGMENT_DELAY_OVERRIDE_SEC = 3  # [cite: 186]
    TRANSLATION_SEGMENT_DELAY_OVERRIDE_SEC = 1  # [cite: 186]
    DESCRIPTION_SEGMENT_DELAY_OVERRIDE_SEC = 0.85  # [cite: 187]
    ORIG_SEGMENT_SPEED = "90%"  # [cite: 187]
    # ORIG_SEGMENT_SPEED = "100%"  # [cite: 187]
    TRANSLATION_SEGMENT_SPEED = "100%"  # [cite: 188]
    SILENCE_AT_THE_END_SEC = 5  # [cite: 189]
    MAX_TEXT_LENGTH_BACK_SERVICE_VAL = 5000  # [cite: 189]

    # --- Mode & Paths ---
    temp_directory: Path
    output_directory: Path
    image_path: Path = Path("../img/img_german_flag_768_576.png")

    # --- Input/Output Naming ---
    track_identifier: str  # Original input path or blob name
    input_bucket: str | None = None
    input_blob: str | None = None
    audio_out_filename_prefix: str
    video_out_filename_prefix: str
    temp_out_filename_base: str  # Base name for temp files

    # --- Processing Parameters ---
    repeat_number: int = 3
    create_audio: bool = True
    create_video: bool = True
    create_aac: bool = True
    add_seconds_padding: bool = False
    skip_translation: bool = False
    standard_voice: bool = True  # [cite: 194]
    extra_delay_sec: float = 0.0  # Default changed from 3 [cite: 195]
    delay_multiplier_for_file_segment: float = 1.0  # [cite: 195]
    delay_after_orig_phrase_fix: bool = False  # [cite: 195]
    delay_after_orig_phrase_override_max: float = 5.0  # [cite: 196]
    german_audio_source_filename: str | None = None  # [cite: 111]
    get_types_callback = None  # Function assigned later

    # --- SubGroup Configs (Simplified - could be separate classes) ---
    orig_segment_config: dict
    transl_segment_config: dict
    description_segment_config: dict
    tts_configs: dict  # Keyed by Language enum

    has_translation: bool = True

    def __init__(self, track_identifier: str):
        self.track_identifier = track_identifier

        self._setup_paths()
        self._set_default_processing_params()
        self._set_default_subgroup_configs()
        self._set_default_tts_configs()
        self._derive_filenames()

        logger.info(f"Initialized config for track '{track_identifier}'")
        logger.debug(f"Temp directory: {self.temp_directory}")
        logger.debug(f"Output directory: {self.output_directory}")

    def _setup_paths(self):
        # Define base paths - adjust as needed
        # project_root = Path(__file__).resolve().parent.parent.parent
        # project_root = Path(r"./")
        project_root = get_app_dir()
        self.output_directory = project_root / "out"
        temp_dir = project_root / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.temp_directory = Path(tempfile.mkdtemp(prefix="langrep_", dir=temp_dir))
        # Ensure directories exist
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.temp_directory.mkdir(parents=True, exist_ok=True)  # mkdtemp creates it

        # Image path needs to be located correctly
        # self.image_path = project_root / "img" / "img_germ_flag_960_720.jpg"  # Example [cite: 1665]
        # if not self.image_path.exists():
        #     logger.warning(f"Image file not found at {self.image_path}")
        #     # raise ConfigError(f"Image file not found: {self.image_path}")

    def _derive_filenames(self):
        # Create safe filename prefixes from the track identifier
        base_name = Path(self.track_identifier).stem
        safe_base_name = "".join(c if c.isalnum() else "_" for c in base_name)
        self.audio_out_filename_prefix = f"audio_{safe_base_name}"
        self.video_out_filename_prefix = safe_base_name  # Use directly like Java [cite: 253]
        self.temp_out_filename_base = f"temp_{safe_base_name}"  # Base for various temp files

    def _set_default_processing_params(self):
        # Defaults set here, can be overridden later
        self.repeat_number = 3
        self.create_audio = True
        self.create_video = True
        # ... other params ...

    def _set_default_subgroup_configs(self):
        # Replicate Java defaults
        self.orig_segment_config = {'language': Language.DE, 'delay_override_sec': self.ORIG_SEGMENT_DELAY_OVERRIDE_SEC, 'type': SubGroupType.ORIGINAL_PHRASE}
        self.transl_segment_config = {'language': Language.EN, 'delay_override_sec': self.TRANSLATION_SEGMENT_DELAY_OVERRIDE_SEC, 'type': SubGroupType.TRANSLATION}
        self.description_segment_config = {'language': Language.EN, 'delay_override_sec': self.DESCRIPTION_SEGMENT_DELAY_OVERRIDE_SEC, 'type': SubGroupType.DESCRIPTION}

    def _set_default_tts_configs(self):
        self.tts_configs = {
            Language.DE: {'speed': self.ORIG_SEGMENT_SPEED},
            Language.EN: {'speed': self.TRANSLATION_SEGMENT_SPEED},
            Language.RU: {'speed': self.TRANSLATION_SEGMENT_SPEED},
        }

    def get_temp_filepath(self, suffix: str) -> Path:
        """Gets a unique temporary filepath within the job's temp dir."""
        # Consider using uuid for more uniqueness if needed
        return self.temp_directory / f"{self.temp_out_filename_base}_{suffix}"

    def get_output_filepath(self, suffix: str) -> Path:
        """Gets an output filepath."""
        return self.output_directory / f"{self.video_out_filename_prefix}{suffix}"  # Use video prefix for final output

    def cleanup_temp_dir(self):
        """Removes the temporary directory for this job."""
        try:
            if self.temp_directory and self.temp_directory.exists():
                import shutil
                shutil.rmtree(self.temp_directory)
                logger.info(f"Cleaned up temp directory: {self.temp_directory}")
        except Exception as e:
            logger.error(f"Failed to cleanup temp directory {self.temp_directory}: {e}", exc_info=True)
            exit(1)


# --- Factory Function ---
def create_config(track_identifier: str, create_video: bool, **kwargs) -> LanguageRepetitorConfig:
    """Creates and customizes configuration based on mode and track."""
    try:
        cfg = LanguageRepetitorConfig(track_identifier)

        # Apply common overrides based on Java main
        cfg.repeat_number = 3
        print(" ______ repeat_number: {repeat_number}")
        cfg.delay_multiplier_for_file_segment = 1.1
        cfg.create_aac = not create_video  # Default, adjust if needed
        cfg.standard_voice = True
        cfg.extra_delay_sec = 0
        cfg.delay_after_orig_phrase_fix = True
        if "_wav_rec" in track_identifier:
            cfg.delay_after_orig_phrase_override_max = 1
        else:
            cfg.delay_after_orig_phrase_override_max = 3

        # Set callback (example - needs proper definition matching Java)
        def get_types_callback_example(arg):
            # Replace with actual logic based on arg structure (language, subgroup type, interval)
            logger.debug(f"get_types_callback called with: {arg}")
            # Simplified logic based on Java
            if hasattr(arg, 'sub_group_type') and arg.sub_group_type == SubGroupType.ORIGINAL_PHRASE and \
                    hasattr(arg, 'subtitle_interval') and arg.subtitle_interval and arg.subtitle_interval.start_ts_sec >= 0:
                return {SegmentType.FILE_SEGMENT}
            else:
                lang = getattr(arg, 'language', None)
                stype = getattr(arg, 'sub_group_type', None)
                if lang == Language.DE:
                    return {SegmentType.GENERATED_CLOUD}
                elif lang == Language.RU:
                    return {SegmentType.GENERATED_CLOUD_BATCH}
                else:  # EN or default
                    return {SegmentType.GENERATED_CLOUD_BATCH}

        cfg.get_types_callback = get_types_callback_example

        # Apply kwargs for potential direct overrides (use with caution)
        for key, value in kwargs.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
            else:
                logger.warning(f"Attempted to set unknown config attribute: {key}")

        return cfg

    except Exception as e:
        logger.error(f"Failed to create configuration: {e}", exc_info=True)
        raise ConfigError("Configuration creation failed") from e
