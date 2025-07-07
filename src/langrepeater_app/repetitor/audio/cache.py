import logging
import os
import io
import json # Added for silence cache
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set, BinaryIO, DefaultDict
from collections import defaultdict
import hashlib
import time

# Project Imports
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig, SegmentType
from src.langrepeater_app.repetitor.constants import Language, PAUSE_BREAK_SEC_INT, STEP_FROM_SILENCE_MIDDLE_SEC, MAX_TTS_TEXT_LENGTH
from src.langrepeater_app.repetitor.exceptions import RepetitorError, AudioProcessingError, ConfigError, GoogleCloudError
from src.langrepeater_app.repetitor.audio.models import Segment, SegmentVariant, WAVHeader, AudioContent, PcmPause, CloudTimepoint
# Assumed utility modules/classes
from src.langrepeater_app.repetitor.google.tts import GoogleTTSClient, TTSRequest
from src.langrepeater_app.repetitor.audio.tts_cache import TTSCache, TTSCacheKey
from src.langrepeater_app.repetitor.audio import processing as audio_processing
from src.langrepeater_app.repetitor.audio.text_fixer import SsmlSrtFixer
from src.lib_clean.lib_common import get_app_dir, get_app_wav_dir

logger = logging.getLogger(__name__)

# Define a structure for the processing plan
SegmentPlan = DefaultDict[Language, DefaultDict[SegmentType, List[Segment]]]


class MediaCache:
    """
    Manages audio segment planning, generation/retrieval, caching,
    and concatenation into a final WAV file.
    Equivalent logic to Java's MediaCacheV2 + MediaCacheV2Populator.
    Includes caching for GENERATED_CLOUD_BATCH TTS and silence detection.
    """

    # How many TTS requests to batch together (adjust based on API limits/performance)
    TTS_BATCH_SIZE = 10  # Example value
    SILENCE_CACHE_SUBDIR = "silence_cache" # Subdirectory for silence results cache

    def __init__(self, config: LanguageRepetitorConfig):
        self.config = config
        self.tts_cache = TTSCache(config)  # Local file cache for TTS results
        self._google_tts_client: Optional[GoogleTTSClient] = None  # Lazy initialized
        self.text_fixer = SsmlSrtFixer()

        # Define silence cache directory
        self.silence_cache_directory = config.output_directory.parent / self.SILENCE_CACHE_SUBDIR
        self._ensure_silence_cache_directory()

        # --- State ---
        # Planning
        self._plan: SegmentPlan = defaultdict(lambda: defaultdict(list))
        # Caching
        self._audio_content_cache: Dict[str, AudioContent] = {}  # Key: audio_file_key -> AudioContent
        self._pause_pcm_cache: Dict[int, bytes] = {}  # Key: duration_ms -> pcm_bytes
        # Output Stream
        self._output_stream: Optional[BinaryIO] = None
        self._output_path_phase1: Path = config.get_temp_filepath("combined_raw.pcm")
        self._final_output_path: Path = config.get_output_filepath(".wav")  # Final WAV output
        # Header Info
        self._master_header: Optional[WAVHeader] = None
        self._final_duration_ms: int = -1
        self._bytes_written_phase1: int = 0

        logger.info(f"MediaCache initialized. Phase 1 output: {self._output_path_phase1}")
        logger.info(f"Silence cache directory: {self.silence_cache_directory}") # Log silence cache path

    # --- Silence Cache Management ---
    def _ensure_silence_cache_directory(self) -> None:
        """Creates the silence cache directory if it doesn't exist."""
        try:
            self.silence_cache_directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create silence cache directory '{self.silence_cache_directory}': {e}", exc_info=True)
            # Don't raise, maybe just warn, as silence caching is an optimization
            # raise ConfigError(f"Could not create silence cache directory: {self.silence_cache_directory}") from e
            exit(1)

    def _get_silence_cache_path(self, batch_key_hash: str) -> Path:
        """Constructs the path for a silence detection result file."""
        # Simple structure: silence_cache / batch_hash.json
        # More complex structure (like tts_cache) could be added if needed
        filename = f"{batch_key_hash}.json"
        return self.silence_cache_directory / filename

    def _get_cached_silence_pauses(self, batch_key_hash: str) -> Optional[List[PcmPause]]:
        """Loads cached silence detection results (list of PcmPause) for a batch."""
        cache_path = self._get_silence_cache_path(batch_key_hash)
        if cache_path.is_file():
            try:
                logger.debug(f"Silence cache hit for hash {batch_key_hash}: Found at {cache_path}")
                with open(cache_path, 'r', encoding='utf-8') as f:
                    pauses_data = json.load(f) # List of dicts [{'start_sec': float, 'end_sec': float}]
                # Convert list of dicts back to list of PcmPause objects
                pauses = [PcmPause(start_sec=p['start_sec'], end_sec=p['end_sec']) for p in pauses_data]
                return pauses
            except (json.JSONDecodeError, KeyError, Exception) as e:
                logger.error(f"Failed to load or parse silence cache file {cache_path}: {e}", exc_info=True)
                # Attempt to remove corrupted cache file
                exit(1)
                try:
                    cache_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return None
        else:
            logger.debug(f"Silence cache miss for hash {batch_key_hash}: File not found at {cache_path}")
            return None

    def _save_silence_pauses_to_cache(self, batch_key_hash: str, pauses: List[PcmPause]) -> None:
        """Saves detected silence pauses to the cache as a JSON file."""
        cache_path = self._get_silence_cache_path(batch_key_hash)
        pauses_data = [{'start_sec': p.start_sec, 'end_sec': p.end_sec} for p in pauses]
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(pauses_data, f, indent=2) # Save as formatted JSON
            logger.info(f"Successfully saved silence pauses to cache: {cache_path}")
        except (IOError, Exception) as e:
            logger.error(f"Failed to save silence pauses to cache file {cache_path}: {e}", exc_info=True)
            exit(1)
            # Don't raise, just log the error

    # --- Planning ---
    def add_segment_to_plan(self, segment: Segment) -> None:
        """Adds a non-silent segment to the processing plan."""
        if segment.is_silent:
            logger.debug(f"Skipping silent segment for planning: '{segment.text}'")
            return

        if not segment.variants:
            logger.warning(f"Segment '{segment.text[:30]}...' has no variants defined. Cannot add to plan.")
            return

        # Add segment under *all* its defined types in the plan
        for seg_type in segment.variants.keys():
            self._plan[segment.language][seg_type].append(segment)
            logger.debug(f"Added segment '{segment.text}.' to plan for Lang={segment.language.name}, Type={seg_type.name}")

    # --- Header Management ---
    def get_header(self) -> Optional[WAVHeader]:
        """Returns the master WAV header determined during cache population."""
        return self._master_header

    def set_header_if_missing(self, header: Optional[WAVHeader] = None) -> None:
        """Sets the master header if it's not already set."""
        if self._master_header is None:
            self._master_header = header or WAVHeader.get_default()
            logger.info(f"Master WAV header set to: {self._master_header}")

    def _check_and_set_header(self, header: WAVHeader, source_description: str) -> None:
        """Compares a new header with the master header and sets the master if needed."""
        if self._master_header is None:
            self._master_header = header
            logger.info(f"Master WAV header established from {source_description}: {header}")
        elif header != self._master_header:
            msg = (f"Inconsistent WAV header detected! "
                   f"Source: {source_description}, Header: {header}. "
                   f"Master Header: {self._master_header}. "
                   f"All audio must have the same sample rate, bit depth, and channels.")
            logger.error(msg)
            # Decide on behavior: raise error, try to resample (complex), or log warning and proceed (risky)
            raise AudioProcessingError(msg)
        # else: header matches master, no action needed

    # --- Cache Population ---
    def _get_google_tts_client(self) -> GoogleTTSClient:
        """Initializes and returns the Google TTS client."""
        if self._google_tts_client is None:
            try:
                self._google_tts_client = GoogleTTSClient(self.config)
                logger.info("GoogleTTSClient initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize GoogleTTSClient: {e}", exc_info=True)
                raise GoogleCloudError(f"Google TTS client initialization failed: {e}") from e
        return self._google_tts_client

    def populate_cache(self) -> None:
        """
        Processes the plan to fetch/generate audio for all segments.
        Downloads/Generates TTS, converts to PCM, stores AudioContent.
        """
        logger.info("Starting media cache population...")
        start_time = time.time()

        # Process segments language by language, type by type
        ii = 0
        for lang, type_map in self._plan.items():
            ii += 1
            logger.info(f" _______________ idx: {ii}/{len(self._plan.items())} Processing language: {lang.name}")
            # Prioritize FILE_SEGMENT as it might establish the header
            if SegmentType.FILE_SEGMENT in type_map:
                self._populate_file_segments(lang, type_map[SegmentType.FILE_SEGMENT])

            # Process individual cloud requests next
            if SegmentType.GENERATED_CLOUD in type_map:
                self._populate_cloud_segments(lang, type_map[SegmentType.GENERATED_CLOUD])

            # Process batch cloud requests last
            if SegmentType.GENERATED_CLOUD_BATCH in type_map:
                self._populate_cloud_batch_segments(lang, type_map[SegmentType.GENERATED_CLOUD_BATCH])

        # Ensure header is set after processing all types
        self.set_header_if_missing()  # Use default if no audio established it

        duration = time.time() - start_time
        logger.info(f"Media cache population finished in {duration:.2f} seconds.")

    def _populate_file_segments(self, lang: Language, segments: List[Segment]) -> None:
        """Loads audio content for FILE_SEGMENT types."""
        logger.info(f"Populating FILE_SEGMENT for {lang.name} ({len(segments)} segments)...")
        for segment in segments:
            variant = segment.variants.get(SegmentType.FILE_SEGMENT)
            if not variant or not variant.audio_file_key:
                logger.warning(f"Skipping FILE_SEGMENT for '{segment.text[:30]}...' - missing variant or audio_file_key.")
                continue

            # *** Assign start/end times from subtitle interval ***
            if variant.subtitle_interval and variant.subtitle_interval.is_valid():
                variant.start_time_sec = variant.subtitle_interval.start_ts_sec
                variant.end_time_sec = variant.subtitle_interval.end_ts_sec
                logger.debug(f"  Assigned FILE_SEGMENT times for '{segment.text[:20]}...': {variant.start_time_sec:.3f}s -> {variant.end_time_sec:.3f}s")
            else:
                logger.warning(f"Skipping FILE_SEGMENT for '{segment.text[:30]}...' - Invalid or missing subtitle_interval.")
                continue  # Cannot process without valid times from interval

            file_key = variant.audio_file_key  # Should be set if interval was valid
            if file_key in self._audio_content_cache:
                logger.debug(f"FILE_SEGMENT already in cache: {file_key}")
                continue  # Already loaded

            try:
                # Assume audio_file_key is a resolvable path for local files
                # For GCS, this would need adjustment to download first

                source_path = Path(get_app_wav_dir() / file_key)  # Needs adjustment if key isn't a direct path
                if not source_path.is_absolute():
                    potential_base = self.config.temp_directory.parent.parent
                    resolved_path = (potential_base / source_path).resolve()
                    if resolved_path.exists():
                        source_path = resolved_path
                    else:
                        source_path = source_path.resolve()
                    logger.warning(f"Attempted to resolve relative FILE_SEGMENT path: {file_key} -> {source_path}")

                if not source_path.exists():
                    raise FileNotFoundError(f"Source audio file not found: {source_path}")

                logger.debug(f"Loading FILE_SEGMENT from: {source_path}")
                header = audio_processing.read_wav_header(source_path)
                self._check_and_set_header(header, f"FILE_SEGMENT {source_path.name}")
                pcm_data = audio_processing.read_pcm_data(source_path)

                self._audio_content_cache[file_key] = AudioContent(header=header, pcm_bytes=pcm_data)
                logger.debug(f"Cached FILE_SEGMENT: {file_key} ({len(pcm_data)} bytes)")

            except Exception as e:
                logger.error(f"Failed to load FILE_SEGMENT {file_key} for '{segment.text[:30]}...': {e}", exc_info=True)
                exit(1) # Original behavior

    def _populate_cloud_segments(self, lang: Language, segments: List[Segment]) -> None:
        """Generates/retrieves individual TTS audio using GENERATED_CLOUD type."""
        logger.info(f"Populating GENERATED_CLOUD for {lang.name} ({len(segments)} segments)...")
        tts_client = self._get_google_tts_client()
        segments_to_generate = []

        # --- Check Cache First ---
        for segment in segments:
            variant = segment.variants.get(SegmentType.GENERATED_CLOUD)
            if not variant: continue

            tts_key = TTSCacheKey(
                text=segment.text,
                language_code=lang.value,
                voice_name=tts_client.get_voice_name(lang, SegmentType.GENERATED_CLOUD),
                speed_percent=variant.speed_percent
            )
            variant.audio_file_key = self.tts_cache.get_cache_key_string(tts_key)

            cached_content = self._audio_content_cache.get(variant.audio_file_key)
            if cached_content:
                logger.debug(f"GENERATED_CLOUD already in memory cache: {variant.audio_file_key}")
                continue

            cached_path = self.tts_cache.get_cached_file_path(tts_key)
            if cached_path and cached_path.exists():
                logger.debug(f"Found GENERATED_CLOUD in file cache: {cached_path}")
                try:
                    header = audio_processing.read_wav_header(cached_path)
                    self._check_and_set_header(header, f"GENERATED_CLOUD cache {cached_path.name}")
                    pcm_data = audio_processing.read_pcm_data(cached_path)
                    self._audio_content_cache[variant.audio_file_key] = AudioContent(header=header, pcm_bytes=pcm_data)
                except Exception as e:
                    logger.error(f"Failed to load GENERATED_CLOUD from file cache {cached_path}: {e}", exc_info=True)
                    exit(1) # Original behavior
                    try:
                        cached_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    segments_to_generate.append(segment)
            else:
                segments_to_generate.append(segment)

        # --- Generate Missing Segments ---
        if not segments_to_generate:
            logger.info("All GENERATED_CLOUD segments were cached.")
            return

        logger.info(f"Generating {len(segments_to_generate)} missing GENERATED_CLOUD segments for {lang.name}...")
        generated_count = 0
        for segment in segments_to_generate:
            variant = segment.variants[SegmentType.GENERATED_CLOUD]
            tts_key_str = variant.audio_file_key
            if not tts_key_str:
                logger.error(f"Missing audio_file_key for segment to generate: {segment.text[:30]}...")
                continue

            try:
                logger.debug(f"Requesting TTS for: '{segment.text[:30]}...' ({tts_key_str})")
                ssml_text = self.text_fixer.ssml_wrap_text(
                    text=segment.text,
                    lang_code=lang.value,
                    speed_percent=variant.speed_percent
                )

                request = TTSRequest(
                    ssml=ssml_text,
                    language_code=lang.value,
                    voice_name=tts_client.get_voice_name(lang, SegmentType.GENERATED_CLOUD),
                    audio_encoding='MP3',
                    sample_rate_hertz=WAVHeader.DEFAULT_SAMPLE_RATE
                )

                file_hash = tts_key_str.split('_')[-1]
                temp_mp3_path = self.config.get_temp_filepath(f"tts_{file_hash}.mp3")
                temp_pcm_path = self.config.get_temp_filepath(f"tts_{file_hash}.wav") # Save as WAV

                saved_mp3_path = tts_client.synthesize_to_file(request, temp_mp3_path)
                audio_processing.convert_mp3_to_pcm(saved_mp3_path, temp_pcm_path)

                header = audio_processing.read_wav_header(temp_pcm_path)
                self._check_and_set_header(header, f"GENERATED_CLOUD TTS {tts_key_str}")
                pcm_data = audio_processing.read_pcm_data(temp_pcm_path)

                self._audio_content_cache[tts_key_str] = AudioContent(header=header, pcm_bytes=pcm_data)
                self.tts_cache.save_to_cache(tts_key_str, temp_pcm_path) # Cache the WAV

                generated_count += 1
                logger.debug(f"Generated and cached TTS: {tts_key_str}")

                try:
                    saved_mp3_path.unlink(missing_ok=True)
                    # Don't delete temp_pcm_path (it was moved to cache)
                except OSError as e:
                    logger.warning(f"Could not delete temp TTS MP3 file for {tts_key_str}: {e}")
                    exit(1) # Original behavior

            except Exception as e:
                logger.error(f"Failed to generate GENERATED_CLOUD TTS for '{segment.text[:30]}...' ({tts_key_str}): {e}", exc_info=True)
                exit(1) # Original behavior

        logger.info(f"Generated {generated_count} GENERATED_CLOUD segments for {lang.name}.")

    def _populate_cloud_batch_segments(self, lang: Language, segments: List[Segment]) -> None:
        """Generates/retrieves TTS audio for a batch of segments and uses silence detection (with caching)."""
        if not segments: return

        logger.info(f"Populating GENERATED_CLOUD_BATCH for {lang.name} ({len(segments)} segments)...")
        tts_client = self._get_google_tts_client()

        # --- Prepare SSML Batch ---
        ssml_parts = []
        current_batch_segments = []
        current_ssml_len = 0
        combined_ssml_batches = []

        first_variant = segments[0].variants.get(SegmentType.GENERATED_CLOUD_BATCH)
        if not first_variant:
            raise ConfigError("First segment in CLOUD_BATCH has no variant.")
        batch_voice = tts_client.get_voice_name(lang, SegmentType.GENERATED_CLOUD_BATCH)
        batch_speed = first_variant.speed_percent

        # Construct SSML prefix and suffix including prosody tag if speed is not 100%
        ssml_prefix = "<speak>"
        ssml_suffix = "</speak>"
        prosody_needed = batch_speed != "100%"
        if prosody_needed:
            ssml_prefix += f'<prosody rate="{batch_speed}">'
            ssml_suffix = "</prosody>" + ssml_suffix
        current_ssml_len += len(ssml_prefix) + len(ssml_suffix)


        for segment in segments:
            variant = segment.variants.get(SegmentType.GENERATED_CLOUD_BATCH)
            if not variant: continue

            escaped_text = self.text_fixer._fix_text_for_ssml(segment.text)
            text_part = escaped_text + f"<break time='{PAUSE_BREAK_SEC_INT}s'/>"
            part_len = len(text_part)

            if current_ssml_len + part_len > MAX_TTS_TEXT_LENGTH:
                if ssml_parts:
                    full_ssml = ssml_prefix + "".join(ssml_parts) + ssml_suffix
                    combined_ssml_batches.append((full_ssml, current_batch_segments))
                    logger.info(f"Created SSML batch for {lang.name} with {len(current_batch_segments)} segments (length {len(full_ssml)}).")
                ssml_parts = [text_part]
                current_batch_segments = [segment]
                current_ssml_len = len(ssml_prefix) + len(ssml_suffix) + part_len
            else:
                ssml_parts.append(text_part)
                current_batch_segments.append(segment)
                current_ssml_len += part_len

        if ssml_parts:
            full_ssml = ssml_prefix + "".join(ssml_parts) + ssml_suffix
            combined_ssml_batches.append((full_ssml, current_batch_segments))
            logger.info(f"Created final SSML batch for {lang.name} with {len(current_batch_segments)} segments (length {len(full_ssml)}).")

        if not combined_ssml_batches:
            logger.warning(f"No SSML batches created for CLOUD_BATCH {lang.name}.")
            return

        # --- Generate/Retrieve Audio and Silence Info for each Batch ---
        batch_num = 0
        for full_ssml, batch_segments in combined_ssml_batches:
            batch_num += 1
            ssml_hash = hashlib.sha256(full_ssml.encode('utf-8')).hexdigest()[:16]

            # --- TTS Cache Check ---
            batch_tts_key = TTSCacheKey(
                text=ssml_hash, # Use hash instead of full SSML for key text
                language_code=lang.value,
                voice_name=batch_voice,
                speed_percent=batch_speed
            )
            batch_tts_key_str = self.tts_cache.get_cache_key_string(batch_tts_key)
            batch_audio_key: Optional[str] = None # Key for _audio_content_cache
            batch_pcm_path: Optional[Path] = None # Path to the batch PCM/WAV file

            cached_batch_path = self.tts_cache.get_cached_file_path(batch_tts_key)

            if cached_batch_path and cached_batch_path.exists():
                 logger.info(f"TTS Cache hit for batch {ssml_hash}. Using cached file: {cached_batch_path}")
                 batch_pcm_path = cached_batch_path
                 batch_audio_key = str(batch_pcm_path.resolve()) # Use absolute path as key
            else:
                logger.info(f"TTS Cache miss for batch {ssml_hash}. Generating audio...")
                try:
                    request = TTSRequest(
                        ssml=full_ssml,
                        language_code=lang.value,
                        voice_name=batch_voice,
                        audio_encoding='MP3',
                        sample_rate_hertz=WAVHeader.DEFAULT_SAMPLE_RATE
                    )
                    temp_mp3_path = self.config.get_temp_filepath(f"batch_{ssml_hash}.mp3")
                    temp_pcm_path = self.config.get_temp_filepath(f"batch_{ssml_hash}.wav") # Save as WAV

                    saved_mp3_path = tts_client.synthesize_to_file(request, temp_mp3_path)
                    audio_processing.convert_mp3_to_pcm(saved_mp3_path, temp_pcm_path)
                    batch_pcm_path = temp_pcm_path

                    # Save the generated WAV to TTS cache
                    self.tts_cache.save_to_cache(batch_tts_key_str, batch_pcm_path)
                    batch_audio_key = str(batch_pcm_path.resolve()) # Use absolute path as key

                    try:
                        saved_mp3_path.unlink(missing_ok=True)
                    except OSError as e:
                        logger.warning(f"Could not delete temp MP3 file for batch {ssml_hash}: {e}")
                        exit(1) # Original behavior

                except Exception as e:
                    logger.error(f"Failed to generate or cache CLOUD_BATCH {ssml_hash}: {e}", exc_info=True)
                    exit(1) # Original behavior

            # --- Load Batch Audio Content ---
            if not batch_pcm_path or not batch_audio_key:
                 logger.error(f"Batch PCM path or audio key is missing for batch {ssml_hash}. Skipping.")
                 continue # Skip this batch if audio path is invalid

            try:
                header = audio_processing.read_wav_header(batch_pcm_path)
                self._check_and_set_header(header, f"CLOUD_BATCH {ssml_hash}")
                pcm_data = audio_processing.read_pcm_data(batch_pcm_path)
                self._audio_content_cache[batch_audio_key] = AudioContent(header=header, pcm_bytes=pcm_data)
                logger.info(f"Cached batch audio content in memory: {batch_audio_key} ({len(pcm_data)} bytes)")
            except Exception as e:
                 logger.error(f"Failed to load batch audio content from {batch_pcm_path}: {e}", exc_info=True)
                 exit(1)
                 continue # Skip this batch if loading fails

            # --- Silence Detection (with Cache) ---
            pauses: Optional[List[PcmPause]] = self._get_cached_silence_pauses(ssml_hash)

            if pauses is None:
                 logger.info(f"Silence cache miss for batch {ssml_hash}. Detecting silence...")
                 try:
                    pauses = audio_processing.detect_silence(batch_pcm_path)
                    logger.info(f"Detected {len(pauses)} pauses in batch {ssml_hash}.")
                    # Save detected pauses to cache
                    self._save_silence_pauses_to_cache(ssml_hash, pauses)
                 except Exception as e:
                     logger.error(f"Silence detection failed for batch {batch_pcm_path}: {e}", exc_info=True)
                     pauses = [] # Proceed without pauses if detection fails? Or raise error?
                     exit(1)
                     # Let's proceed with empty pauses list but log error
            else:
                 logger.info(f"Silence cache hit for batch {ssml_hash}. Loaded {len(pauses)} pauses.")

            # --- Assign Timepoints to Segments ---
            if not pauses: # Handle case where detection failed or no pauses found
                 logger.warning(f"No pauses available for batch {ssml_hash}. Cannot assign timepoints accurately.")
                 # Mark segments as having invalid time? Or skip?
                 for segment in batch_segments:
                      variant = segment.variants.get(SegmentType.GENERATED_CLOUD_BATCH)
                      if variant:
                          variant.audio_file_key = batch_audio_key # Still assign audio key
                          variant.start_time_sec = -1 # Mark times as invalid
                          variant.end_time_sec = -1
                 continue # Skip time assignment for this batch


            # Expect number of pauses = number of segments (due to <break> tags)
            if len(pauses) != len(batch_segments):
                logger.warning(f"Mismatch! Expected {len(batch_segments)} segments based on SSML breaks, but detected/loaded {len(pauses)} pauses in batch {ssml_hash}. Timepoint assignment might be inaccurate.")

            current_start_sec = 0.0
            num_segments_to_assign = min(len(batch_segments), len(pauses))

            for i in range(num_segments_to_assign):
                segment = batch_segments[i]
                variant = segment.variants[SegmentType.GENERATED_CLOUD_BATCH]
                pause = pauses[i]

                variant.audio_file_key = batch_audio_key # Assign the batch PCM file path

                segment_end_sec = pause.get_middle()
                variant.start_time_sec = current_start_sec
                variant.end_time_sec = segment_end_sec

                if i > 0:
                    variant.start_time_sec += STEP_FROM_SILENCE_MIDDLE_SEC
                variant.end_time_sec -= STEP_FROM_SILENCE_MIDDLE_SEC

                if variant.start_time_sec >= variant.end_time_sec:
                    logger.warning(f"Corrected invalid time range for segment {i} in batch {ssml_hash}: start={variant.start_time_sec:.3f}s, end={variant.end_time_sec:.3f}s.")
                    variant.start_time_sec = pause.start_sec
                    variant.end_time_sec = pause.end_sec
                    if variant.start_time_sec >= variant.end_time_sec:
                        variant.end_time_sec = variant.start_time_sec + 0.01

                logger.debug(f"  Assigned time for segment {i} ('{segment.text[:20]}...'): {variant.start_time_sec:.3f}s -> {variant.end_time_sec:.3f}s")
                current_start_sec = segment_end_sec

            if len(batch_segments) > len(pauses):
                for i in range(len(pauses), len(batch_segments)):
                    segment = batch_segments[i]
                    logger.error(f"Could not assign timepoints for segment {i} ('{segment.text[:30]}...') in batch {ssml_hash} due to pause/segment count mismatch.")
                    variant = segment.variants.get(SegmentType.GENERATED_CLOUD_BATCH)
                    if variant:
                         variant.audio_file_key = batch_audio_key # Assign audio key
                         variant.start_time_sec = -1 # Mark times invalid
                         variant.end_time_sec = -1

            # Don't delete the batch_pcm_path here, it's either cached or needed by variants.
            # Cleanup of these batch files happens in post_save_cleanup.

        logger.info(f"Finished populating CLOUD_BATCH for {lang.name}.")


    # --- Concatenation ---
    def set_output_stream(self, stream: Optional[BinaryIO]) -> None:
        """Sets the binary output stream for writing concatenated PCM data."""
        self._output_stream = stream
        self._bytes_written_phase1 = 0
        if stream:
            logger.debug(f"Output stream set for Phase 1 audio writing.")
        else:
            logger.debug("Output stream unset.")

    def _write_to_stream(self, data: bytes) -> int:
        """Writes bytes to the output stream if it's set."""
        if self._output_stream is None:
            raise RepetitorError("Output stream is not set. Cannot write audio data.")
        if not data:
            return 0
        try:
            bytes_written = self._output_stream.write(data)
            self._bytes_written_phase1 += bytes_written
            return bytes_written
        except Exception as e:
            logger.error(f"Failed to write to audio output stream: {e}", exc_info=True)
            raise AudioProcessingError("Failed to write to audio stream") from e

    def save_segment_bytes(self, segment: Segment, seg_type: SegmentType) -> Tuple[int, int]:
        """Writes the PCM data for a specific segment variant to the output stream."""
        if self._master_header is None:
            raise RepetitorError("Master header is not set. Cannot process segments.")

        variant = segment.variants.get(seg_type)
        if not variant or not variant.audio_file_key:
            logger.warning(f"Cannot save segment '{segment.text[:30]}...' - Missing variant or audio_file_key for type {seg_type.name}")
            return 0, 0

        audio_content = self._audio_content_cache.get(variant.audio_file_key)
        if not audio_content:
            logger.error(f"Audio content for key {variant.audio_file_key} not found in cache during save for segment '{segment.text[:30]}...'. This should not happen.")
            raise AudioProcessingError(f"Audio content missing for key: {variant.audio_file_key}")

        if audio_content.header != self._master_header:
            logger.error(f"Header mismatch for segment! Key: {variant.audio_file_key}, Header: {audio_content.header}, Master: {self._master_header}")
            raise AudioProcessingError("Segment header mismatch during saving.")

        start_byte = 0
        end_byte = len(audio_content.pcm_bytes)

        # Check if segment has valid time range (especially for BATCH segments)
        if variant.start_time_sec >= 0 and variant.end_time_sec >= variant.start_time_sec:
            start_byte = audio_processing.bytes_for_duration(variant.start_time_sec, self._master_header)
            end_byte = audio_processing.bytes_for_duration(variant.end_time_sec, self._master_header)
            start_byte = max(0, start_byte)
            end_byte = min(len(audio_content.pcm_bytes), end_byte)
            # Align to frame boundary
            bytes_per_frame = self._master_header.channels * (self._master_header.bit_depth // 8)
            if bytes_per_frame > 0:
                 start_byte = (start_byte // bytes_per_frame) * bytes_per_frame
                 end_byte = (end_byte // bytes_per_frame) * bytes_per_frame
        elif variant.start_time_sec != -1.0 or variant.end_time_sec != -1.0:
             # Only warn if times were set but invalid, ignore default -1
             logger.warning(f"Segment '{segment.text[:30]}...' has invalid time range ({variant.start_time_sec=}, {variant.end_time_sec=}). Writing full content from key {variant.audio_file_key}.")
             # Reset to use full content
             exit(1)
             start_byte = 0
             end_byte = len(audio_content.pcm_bytes)


        if start_byte >= end_byte:
            logger.warning(f"Segment '{segment.text[:30]}...' has zero or negative length ({start_byte=}, {end_byte=}). Writing 0 bytes.")
            return 0, 0

        segment_data = audio_content.pcm_bytes[start_byte:end_byte]
        bytes_written = self._write_to_stream(segment_data)
        duration_ms = audio_processing.calculate_duration_ms(bytes_written, self._master_header)

        logger.debug(f"Wrote segment '{segment.text[:20]}...' ({seg_type.name}): {bytes_written} bytes, {duration_ms} ms")
        return duration_ms, bytes_written

    def _get_pause_pcm(self, duration_sec: float) -> bytes:
        """Gets or creates silent PCM data for the given duration."""
        if self._master_header is None:
            raise RepetitorError("Master header is not set. Cannot create pause.")
        if duration_sec <= 0:
            return b""

        duration_ms = int(duration_sec * 1000)
        if duration_ms <= 0:
            return b""

        if duration_ms not in self._pause_pcm_cache:
            try:
                self._pause_pcm_cache[duration_ms] = audio_processing.create_silence(duration_sec, self._master_header)
                logger.debug(f"Created pause cache for {duration_ms}ms ({len(self._pause_pcm_cache[duration_ms])} bytes)")
            except Exception as e:
                logger.error(f"Failed to create silence for {duration_sec}s: {e}", exc_info=True)
                exit(1) # Original behavior
                return b""

        return self._pause_pcm_cache[duration_ms]

    def save_pause_bytes(self, duration_sec: float, segment_type: Optional[SegmentType] = None) -> Tuple[int, int]:
        """Writes silent PCM data for the specified duration to the output stream."""
        adjusted_duration_sec = duration_sec
        if segment_type == SegmentType.GENERATED_CLOUD_BATCH:
            adjusted_duration_sec = max(0.0, duration_sec - PAUSE_BREAK_SEC_INT + (2 * STEP_FROM_SILENCE_MIDDLE_SEC))
            if abs(adjusted_duration_sec - duration_sec) > 1e-3:
                logger.debug(f"Adjusted pause for CLOUD_BATCH: {duration_sec:.3f}s -> {adjusted_duration_sec:.3f}s")
        elif duration_sec < 0:
            logger.warning(f"Requested negative pause duration ({duration_sec:.3f}s). Setting to 0.")
            adjusted_duration_sec = 0.0

        pause_data = self._get_pause_pcm(adjusted_duration_sec)
        bytes_written = self._write_to_stream(pause_data)
        actual_duration_ms = audio_processing.calculate_duration_ms(bytes_written, self._master_header) if self._master_header else 0

        return actual_duration_ms, bytes_written

    # --- Finalization and Duration ---
    def get_output_path_phase1(self) -> Path:
        """Returns the path where raw concatenated PCM is written."""
        return self._output_path_phase1

    def get_final_output_path(self) -> Path:
        """Returns the path for the final WAV output file."""
        return self._final_output_path

    def finalize_audio_file(self) -> Path:
        """Adds the WAV header to the raw PCM data written in phase 1."""
        if self._master_header is None:
            raise RepetitorError("Cannot finalize audio file: Master header is not set.")
        if not self._output_path_phase1.exists() or self._bytes_written_phase1 == 0:
            logger.warning(f"Finalizing audio file: Phase 1 output '{self._output_path_phase1}' is missing or empty ({self._bytes_written_phase1} bytes written). Creating empty WAV.")
            self._output_path_phase1.touch(exist_ok=True)

        logger.info(f"Finalizing audio file: Reading from {self._output_path_phase1} and writing to {self._final_output_path}")

        try:
            with open(self._output_path_phase1, 'rb') as f_pcm:
                raw_pcm_data = f_pcm.read()

            if len(raw_pcm_data) != self._bytes_written_phase1:
                logger.warning(f"Size mismatch when reading phase 1 PCM data. Expected {self._bytes_written_phase1}, got {len(raw_pcm_data)}.")

            audio_processing.write_wav_file(self._final_output_path, raw_pcm_data, self._master_header)
            self._final_duration_ms = audio_processing.calculate_duration_ms(len(raw_pcm_data), self._master_header)

            logger.info(f"Final WAV file created: {self._final_output_path} ({self._final_duration_ms} ms)")
            return self._final_output_path

        except Exception as e:
            logger.error(f"Failed to finalize WAV file: {e}", exc_info=True)
            raise AudioProcessingError("Failed to finalize WAV file") from e

    def get_final_duration_ms(self) -> int:
        """Returns the duration of the finalized audio file in milliseconds."""
        if self._final_duration_ms < 0:
            logger.warning("Final duration requested before audio finalization.")
            if self._master_header and self._bytes_written_phase1 > 0:
                return audio_processing.calculate_duration_ms(self._bytes_written_phase1, self._master_header)
            return 0
        return self._final_duration_ms

    # --- Cleanup ---
    def post_save_cleanup(self) -> None:
        """Cleans up temporary files created during the process."""
        logger.info("Performing post-save cleanup...")
        # Delete the raw PCM file from phase 1
        try:
            self._output_path_phase1.unlink(missing_ok=True)
            logger.debug(f"Deleted phase 1 PCM file: {self._output_path_phase1}")
        except OSError as e:
            logger.warning(f"Could not delete phase 1 PCM file {self._output_path_phase1}: {e}")
            exit(1) # Original behavior

        # Clean up batch PCM files that were generated (not retrieved from cache directly)
        # These are stored in the _audio_content_cache with absolute paths as keys.
        # We only want to delete those generated *in this run*. A simple way is to
        # check if the key corresponds to a file in the *temporary* directory.
        temp_dir_str = str(self.config.temp_directory.resolve())
        batch_keys_to_delete = {
            key for key in self._audio_content_cache
            if key.startswith(temp_dir_str) and key.endswith(".wav") and "batch_" in Path(key).name
        }
        for key in batch_keys_to_delete:
            try:
                key_path = Path(key)
                if key_path.is_file():
                    key_path.unlink(missing_ok=True)
                    logger.debug(f"Deleted temporary batch WAV file: {key}")
                else:
                    # This shouldn't happen if key is from cache, but log anyway
                    logger.warning(f"Attempted to delete non-existent temp batch file key/path: {key}")
            except OSError as e:
                logger.warning(f"Could not delete temporary batch WAV file {key}: {e}")
                exit(1) # Original behavior

        # Optional: Cleanup silence cache? Usually not needed unless it grows too large.
        # If needed, add logic to clean self.silence_cache_directory based on age/size.

        logger.info("Post-save cleanup finished.")