# german_repetitor/repetitor/google/tts.py

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

# Attempt to import Google Cloud Text-to-Speech library
try:
    from google.cloud import texttospeech_v1 as tts # Use v1
    from google.api_core import exceptions as google_exceptions
    GCTTS_AVAILABLE = True
except ImportError:
    tts = None # Define as None if library not installed
    google_exceptions = None
    GCTTS_AVAILABLE = False
    print("import error!")
    exit(1)

# Project Imports
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig, SegmentType  # To get config settings
from src.langrepeater_app.repetitor.constants import (
    Language,
    DEFAULT_VOICES, PREMIUM_VOICES,
    VOICE_DE_POLYGLOT_1, VOICE_DE_STUDIO_B, VOICE_DE_STANDARD_A,
    VOICE_EN_STANDARD_B, VOICE_RU_STANDARD_A
) # Import necessary constants
from src.langrepeater_app.repetitor.exceptions import GoogleCloudError, ConfigError
from src.langrepeater_app.repetitor.audio.models import WAVHeader # To get default audio params

logger = logging.getLogger(__name__)

# --- TTS Request DataClass ---
@dataclass
class TTSRequest:
    """Holds parameters for a Text-to-Speech request."""
    ssml: Optional[str] = None
    text: Optional[str] = None # Either text or ssml must be provided
    language_code: str = "en-US" # Default, should be overridden
    voice_name: Optional[str] = None # If None, API might choose default
    # Common audio encodings: MP3, LINEAR16 (PCM WAV), OGG_OPUS
    audio_encoding: str = "MP3" # Match Java default [cite: 330]
    sample_rate_hertz: int = WAVHeader.DEFAULT_SAMPLE_RATE # Match desired output [cite: 328]
    # Optional: speaking_rate, pitch, volume_gain_db, effects_profile_id

# --- Google TTS Client ---
# Singleton pattern for the client
_tts_client: Optional['tts.TextToSpeechClient'] = None

def _get_tts_client() -> 'tts.TextToSpeechClient':
    """Initializes and returns a singleton Google TTS API client instance."""
    global _tts_client
    if not GCTTS_AVAILABLE:
        raise GoogleCloudError("Google Cloud Text-to-Speech library ('google-cloud-texttospeech') is not installed.")

    if _tts_client is None:
        try:
            logger.info("Initializing Google Cloud Text-to-Speech client...")
            # Uses Application Default Credentials (ADC) by default.
            _tts_client = tts.TextToSpeechClient()
            logger.info("Google Cloud Text-to-Speech client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Text-to-Speech client: {e}", exc_info=True)
            raise GoogleCloudError(f"Google TTS client initialization failed: {e}") from e
    return _tts_client

class GoogleTTSClient:
    """
    Provides methods to interact with the Google Cloud Text-to-Speech API (v1).
    Wraps functionality similar to Java's TextToSpeechGoogleCloudClient.
    """

    def __init__(self, config: LanguageRepetitorConfig):
        """
        Initializes the GoogleTTSClient.

        Args:
            config: The application configuration object.
        """
        self.client = _get_tts_client() # Get the singleton client
        self.config = config
        logger.info("GoogleTTSClient initialized.")

    def get_voice_name(self, language: Language, segment_type: SegmentType) -> str:
        """
        Determines the appropriate voice name based on config and segment type.
        Mirrors logic from Java config.getCloudVoice [cite: 216-233].

        Args:
            language: The target language enum.
            segment_type: The type of the segment being generated.

        Returns:
            The selected Google Cloud voice name string.
        """
        # Default voice based on language
        selected_voice = DEFAULT_VOICES.get(language)

        # Apply overrides based on config and type (similar to Java logic)
        if self.config.standard_voice:
             # Use premium voices for specific types if standard_voice is True (matching Java logic)
             if language == Language.DE:
                 # Java used Polyglot for GENERATED_CLOUD, Basic otherwise
                 if segment_type == SegmentType.GENERATED_CLOUD:
                      selected_voice = VOICE_DE_POLYGLOT_1 # Or VOICE_DE_STUDIO_B if preferred
                 else: # BATCH or FILE (though FILE won't use TTS)
                      selected_voice = VOICE_DE_STANDARD_A
             # Add similar logic for other languages if needed
             # elif language == Language.EN: ...
             # elif language == Language.RU: ...

        else:
            # If standard_voice is False in config, maybe use WaveNet or other defaults?
            # The Java code seems to *only* set specific names when standardVoice is true.
            # If standardVoice is false, it builds VoiceSelectionParams without a name.
            # The Python client requires a name if specified. Let's default to standard if config.standard_voice is False.
            logger.debug(f"config.standard_voice is False, using default voice for {language.name}")
            selected_voice = DEFAULT_VOICES.get(language)


        if not selected_voice:
            logger.error(f"Could not determine a voice name for language {language.name} and type {segment_type.name}. Falling back.")
            # Fallback to a known default if lookup fails
            selected_voice = VOICE_EN_STANDARD_B # Default fallback

        logger.debug(f"Selected voice for Lang={language.name}, Type={segment_type.name}, Standard={self.config.standard_voice}: {selected_voice}")
        return selected_voice

    def synthesize_ssml(self, request: TTSRequest) -> bytes:
        """
        Synthesizes speech from SSML input and returns the audio content as bytes.
        Similar to Java's TextToSpeechGoogleCloudClient.getAudioContents [cite: 340-389].

        Args:
            request: A TTSRequest object containing synthesis parameters.

        Returns:
            Bytes object containing the synthesized audio data.

        Raises:
            ValueError: If the request is invalid (e.g., missing SSML/text).
            GoogleCloudError: If the API call fails.
        """
        if not request.ssml and not request.text:
            raise ValueError("TTSRequest must contain either 'ssml' or 'text'.")
        if request.ssml and request.text:
             logger.warning("TTSRequest contains both 'ssml' and 'text'. Using 'ssml'.")
             request.text = None # Prioritize SSML

        input_data = tts.SynthesisInput(ssml=request.ssml) if request.ssml else tts.SynthesisInput(text=request.text)

        voice_params = tts.VoiceSelectionParams(
            language_code=request.language_code,
            name=request.voice_name # Use specific voice name determined earlier
            # ssml_gender can also be set if needed, but name is usually sufficient
        )

        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding[request.audio_encoding], # Get enum from string
            sample_rate_hertz=request.sample_rate_hertz,
            # Add other AudioConfig parameters like speaking_rate, pitch if needed
        )

        logger.debug(f"Sending TTS request: lang={request.language_code}, voice={request.voice_name}, encoding={request.audio_encoding}, rate={request.sample_rate_hertz}, input_len={len(str(request.ssml))} or {len(str(request.text))}")

        try:
            response = self.client.synthesize_speech(
                input=input_data,
                voice=voice_params,
                audio_config=audio_config
            )
            logger.info(f"Successfully synthesized speech ({len(response.audio_content)} bytes).")
            # Log usage details (optional, requires specific permissions/setup)
            # logger_superuser.info(...) # Replicate Java superuser logging if needed
            return response.audio_content

        except google_exceptions.InvalidArgument as e:
            logger.error(f"Invalid argument in TTS request: {e}. Input: '{str(input_data)[:100]}...'")
            raise GoogleCloudError(f"Invalid TTS request argument: {e}", service="TextToSpeech") from e
        except google_exceptions.GoogleAPICallError as e:
            logger.error(f"TTS API call failed: {e}", exc_info=True)
            raise GoogleCloudError(f"TTS API call failed: {e}", service="TextToSpeech") from e
        except Exception as e:
            logger.error(f"Unexpected error during speech synthesis: {e}", exc_info=True)
            raise GoogleCloudError(f"Unexpected TTS error: {e}", service="TextToSpeech") from e

    def synthesize_to_file(self, request: TTSRequest, output_path: Path) -> Path:
        """
        Synthesizes speech and saves the resulting audio directly to a file.

        Args:
            request: A TTSRequest object containing synthesis parameters.
            output_path: The Path object where the audio file should be saved.

        Returns:
            The Path object of the saved audio file.

        Raises:
            ValueError: If the request is invalid.
            GoogleCloudError: If the API call fails.
            IOError: If writing the file fails.
        """
        audio_bytes = self.synthesize_ssml(request)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
            with open(output_path, "wb") as out_file:
                out_file.write(audio_bytes)
            logger.info(f"Synthesized audio saved to file: {output_path}")
            return output_path
        except IOError as e:
            logger.error(f"Failed to write synthesized audio to file {output_path}: {e}", exc_info=True)
            raise IOError(f"Failed to write TTS output to {output_path}") from e
        except Exception as e:
            # Catch other potential errors during file writing
            logger.error(f"Unexpected error writing TTS output file {output_path}: {e}", exc_info=True)
            raise GoogleCloudError(f"Failed to save TTS output file: {e}") from e


# Example Usage (within your application logic, e.g., MediaCache):
# try:
#     config = LanguageRepetitorConfig(...) # Get config
#     tts_client = GoogleTTSClient(config)
#
#     request = TTSRequest(
#         ssml="<speak>Hallo Welt!</speak>",
#         language_code="de-DE",
#         voice_name=tts_client.get_voice_name(Language.DE, SegmentType.GENERATED_CLOUD), # Determine voice
#         audio_encoding="MP3",
#         sample_rate_hertz=22050
#     )
#
#     output_file = config.get_temp_filepath("hallo_welt.mp3")
#     tts_client.synthesize_to_file(request, output_file)
#
# except (ConfigError, GoogleCloudError, ValueError, IOError) as e:
#     logger.critical(f"TTS generation failed: {e}")
#     # Handle error appropriately
