# german_repetitor/repetitor/audio/tts_cache.py

import logging
import hashlib
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Project Imports
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig
from src.langrepeater_app.repetitor.exceptions import RepetitorError, ConfigError

logger = logging.getLogger(__name__)

@dataclass(frozen=True) # Make key immutable for use in dictionaries/sets
class TTSCacheKey:
    """Uniquely identifies a TTS request for caching purposes."""
    text: str
    language_code: str # e.g., "de-DE"
    voice_name: str    # e.g., "de-DE-Standard-A"
    speed_percent: str # e.g., "100%"

    def __post_init__(self):
        # Basic validation
        if not all([self.text, self.language_code, self.voice_name, self.speed_percent]):
            raise ValueError("All fields (text, language_code, voice_name, speed_percent) are required for TTSCacheKey")
        if not self.speed_percent.endswith('%'):
             # Ensure speed format consistency, although the value isn't directly used in hash
             logger.warning(f"TTSCacheKey speed '{self.speed_percent}' doesn't end with '%'. Ensure consistency.")


class TTSCache:
    """
    Manages a local file cache for generated Text-to-Speech audio (stored as WAV/PCM).
    Creates filenames based on a hash of the request parameters.
    """
    DEFAULT_CACHE_SUBDIR = "tts_cache"
    FILE_EXTENSION = ".wav" # Store cached files as WAV (containing PCM)

    def __init__(self, config: LanguageRepetitorConfig):
        """
        Initializes the TTSCache.

        Args:
            config: The application configuration object.

        Raises:
            ConfigError: If the cache directory cannot be determined or created.
        """
        self.config = config
        # Define cache directory relative to the main output/temp area
        # Example: <project_root>/mp3/tts_cache/
        self.cache_directory = config.output_directory.parent / self.DEFAULT_CACHE_SUBDIR
        self._ensure_cache_directory()
        logger.info(f"TTSCache initialized. Cache directory: {self.cache_directory}")

    def _ensure_cache_directory(self) -> None:
        """Creates the cache directory if it doesn't exist."""
        try:
            self.cache_directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create TTS cache directory '{self.cache_directory}': {e}", exc_info=True)
            raise ConfigError(f"Could not create TTS cache directory: {self.cache_directory}") from e

    def _generate_hash(self, key: TTSCacheKey) -> str:
        """Generates a SHA-256 hash based on the TTSCacheKey components."""
        hasher = hashlib.sha256()
        # Include all key components in the hash for uniqueness
        hasher.update(key.text.encode('utf-8'))
        hasher.update(key.language_code.encode('utf-8'))
        hasher.update(key.voice_name.encode('utf-8'))
        hasher.update(key.speed_percent.encode('utf-8'))
        return hasher.hexdigest()

    def _get_cache_path_structure(self, key: TTSCacheKey) -> Path:
        """Determines the subdirectory structure within the cache."""
        # Structure: cache_dir / language / voice / speed / hash.wav
        # Sanitize components for use as directory names
        lang_dir = key.language_code.replace('-', '_')
        voice_dir = key.voice_name.replace('-', '_').replace(':','_') # Basic sanitization
        speed_dir = key.speed_percent.replace('%', 'pct')
        return Path(lang_dir) / voice_dir / speed_dir

    def get_cache_key_string(self, key: TTSCacheKey) -> str:
        """
        Generates a unique string representation of the key, suitable for use
        as a dictionary key or identifier in MediaCache. Includes the hash.
        """
        hash_str = self._generate_hash(key)
        # Combine elements for a unique identifier string
        return f"{key.language_code}_{key.voice_name}_{key.speed_percent}_{hash_str}"


    def _get_full_cache_path(self, key: TTSCacheKey) -> Path:
        """Constructs the full, absolute path for a cached file based on the key."""
        hash_str = self._generate_hash(key)
        relative_path = self._get_cache_path_structure(key)
        filename = f"{hash_str}{self.FILE_EXTENSION}"
        return self.cache_directory / relative_path / filename

    def get_cached_file_path(self, key: TTSCacheKey) -> Optional[Path]:
        """
        Checks if a cached file exists for the given key and returns its path if it does.

        Args:
            key: The TTSCacheKey identifying the desired audio.

        Returns:
            The Path object to the cached file if it exists, otherwise None.
        """
        cache_path = self._get_full_cache_path(key)
        if cache_path.is_file():
            logger.debug(f"Cache hit for key {key}: Found at {cache_path}")
            return cache_path
        else:
            logger.debug(f"Cache miss for key {key}: File not found at {cache_path}")
            return None

    def save_to_cache(self, key_str: str, source_pcm_path: Path) -> Path:
        """
        Copies a generated PCM/WAV file into the appropriate cache location.
        Uses the key_str previously generated by get_cache_key_string to find the target path.
        This assumes the key_str was derived from a TTSCacheKey that matches the source_pcm_path content.

        Args:
            key_str: The unique string identifier previously generated via get_cache_key_string.
                     This string implicitly contains the hash and other key parts needed.
            source_pcm_path: Path to the temporary WAV/PCM file containing the generated audio.

        Returns:
            The Path object of the file saved in the cache.

        Raises:
            FileNotFoundError: If the source_pcm_path does not exist.
            RepetitorError: If copying fails or the key_str format is unexpected.
        """
        if not source_pcm_path.is_file():
            raise FileNotFoundError(f"Source PCM/WAV file not found: {source_pcm_path}")

        # Reconstruct the target cache path from the key_str
        # This requires parsing the key_str or regenerating the path components.
        # Let's regenerate the path based on the structure embedded in the key_str format.
        try:
            parts = key_str.split('_')
            if len(parts) < 4: # lang, voice(potentially multiple parts), speed, hash
                raise ValueError("key_str format is incorrect.")

            lang_code = parts[0]
            hash_str = parts[-1]
            speed_percent = parts[-2]
            voice_name = "_".join(parts[1:-2]) # Reassemble voice name

            # Reconstruct the relative path structure
            lang_dir = lang_code.replace('-', '_')
            voice_dir = voice_name.replace('-', '_').replace(':','_')
            speed_dir = speed_percent.replace('%', 'pct') # Already formatted like '100pct' potentially? Assume format from _get_cache_path_structure
            if not speed_dir.endswith('pct'): speed_dir += 'pct' # Ensure format

            relative_path = Path(lang_dir) / voice_dir / speed_dir
            filename = f"{hash_str}{self.FILE_EXTENSION}"
            cache_path = self.cache_directory / relative_path / filename

        except Exception as e:
             logger.error(f"Could not determine cache path from key_str '{key_str}': {e}")
             raise RepetitorError(f"Invalid key_str format for cache saving: {key_str}") from e


        logger.debug(f"Saving TTS result from '{source_pcm_path}' to cache: '{cache_path}'")

        try:
            # Ensure the target directory structure exists
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy the source file to the cache destination
            shutil.copy2(source_pcm_path, cache_path) # copy2 preserves metadata
            logger.info(f"Successfully saved to cache: {cache_path}")
            return cache_path
        except Exception as e:
            logger.error(f"Failed to copy file to cache '{cache_path}' from '{source_pcm_path}': {e}", exc_info=True)
            exit(1)
            # Clean up potentially partially copied file?
            cache_path.unlink(missing_ok=True)
            raise RepetitorError(f"Failed to save file to cache: {e}") from e

    def cleanup_temp_files(self):
        """Optional: Implement cleanup logic for temporary files if needed."""
        # This might involve scanning a specific temp directory used by MediaCache
        # and deleting files older than a certain age, or files matching a pattern.
        logger.warning("TTSCache cleanup_temp_files() is not implemented.")
        pass

