# german_repetitor/repetitor/audio/processing.py

import logging
import wave
import struct
import math # Added for log10
import numpy as np # Keep for potential future use, but not needed for pydub silence detection
from pathlib import Path
from typing import List, Optional, Tuple

# Project Imports
from src.langrepeater_app.repetitor.constants import WAV_HEADER_SIZE, VOICE_AMPLITUDE_THRESHOLD, SILENCE_MIN_DURATION_SEC
from src.langrepeater_app.repetitor.exceptions import AudioProcessingError
from src.langrepeater_app.repetitor.audio.models import WAVHeader, PcmPause

# Attempt to import pydub, but make it optional if only WAV processing is needed initially
try:
    from pydub import AudioSegment
    from pydub.silence import detect_silence as pydub_detect_silence # Import specific function
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    AudioSegment = None # Define as None if not available
    pydub_detect_silence = None # Define as None if not available
    print("PYDUB not available")
    exit(1)

logger = logging.getLogger(__name__)

# --- WAV File Handling ---

def read_wav_header(wav_path: Path) -> WAVHeader:
    """
    Reads the header information from a WAV file.
    Equivalent to Java's WAVHeaderReader.readWAVHeader.

    Args:
        wav_path: Path to the WAV file.

    Returns:
        A WAVHeader object.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        AudioProcessingError: If the file is not a valid WAV or header reading fails.
    """
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    try:
        with wave.open(str(wav_path), 'rb') as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth() # Bytes per sample
            frame_rate = wf.getframerate()
            # num_frames = wf.getnframes() # Not needed for header object

            bit_depth = sample_width * 8

            header = WAVHeader(
                sample_rate=frame_rate,
                bit_depth=bit_depth,
                channels=channels
            )
            # Optional: Add validation like in Java MediaCacheV2Populator.checkHeader
            if header.sample_rate != WAVHeader.DEFAULT_SAMPLE_RATE or \
               header.bit_depth != WAVHeader.DEFAULT_BIT_DEPTH or \
               header.channels != WAVHeader.DEFAULT_CHANNELS:
                logger.warning(f"WAV file header parameters differ from defaults: {header}. File: {wav_path}")
                # Consider raising an error if strict adherence is required:
                # raise AudioProcessingError(f"Unexpected WAV format: {header}. Expected defaults.")

            logger.debug(f"Read WAV header from {wav_path}: {header}")
            return header

    except wave.Error as e:
        logger.error(f"Error reading WAV header from {wav_path}: {e}")
        raise AudioProcessingError(f"Invalid WAV file or header: {wav_path}") from e
    except Exception as e:
        logger.error(f"Unexpected error reading WAV header {wav_path}: {e}", exc_info=True)
        raise AudioProcessingError(f"Failed to read WAV header: {wav_path}") from e

def read_pcm_data(wav_path: Path) -> bytes:
    """
    Reads the raw PCM audio data (excluding the header) from a WAV file.

    Args:
        wav_path: Path to the WAV file.

    Returns:
        Bytes object containing the raw PCM data.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        AudioProcessingError: If reading the WAV data fails.
    """
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    try:
        with wave.open(str(wav_path), 'rb') as wf:
            num_frames = wf.getnframes()
            pcm_data = wf.readframes(num_frames)
            logger.debug(f"Read {len(pcm_data)} bytes of PCM data from {wav_path}")
            return pcm_data
    except wave.Error as e:
        logger.error(f"Error reading WAV data from {wav_path}: {e}")
        raise AudioProcessingError(f"Error reading WAV data: {wav_path}") from e
    except Exception as e:
        logger.error(f"Unexpected error reading WAV data {wav_path}: {e}", exc_info=True)
        raise AudioProcessingError(f"Failed to read WAV data: {wav_path}") from e

def write_wav_file(output_path: Path, pcm_data: bytes, header: WAVHeader) -> None:
    """
    Writes raw PCM data and header information to a new WAV file.
    Equivalent to Java's WAVCreator.createWAVFile.

    Args:
        output_path: Path where the WAV file will be saved.
        pcm_data: Bytes object containing the raw PCM data.
        header: WAVHeader object describing the data format.

    Raises:
        AudioProcessingError: If writing the WAV file fails.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(header.channels)
            wf.setsampwidth(header.bit_depth // 8)
            wf.setframerate(header.sample_rate)
            wf.writeframes(pcm_data)
        logger.info(f"Successfully wrote {len(pcm_data)} bytes of PCM data to WAV: {output_path}")
    except wave.Error as e:
        logger.error(f"Error writing WAV file to {output_path}: {e}")
        raise AudioProcessingError(f"Error writing WAV file: {output_path}") from e
    except Exception as e:
        logger.error(f"Unexpected error writing WAV file {output_path}: {e}", exc_info=True)
        raise AudioProcessingError(f"Failed to write WAV file: {output_path}") from e

# --- MP3 Conversion (Requires pydub and FFmpeg/libav) ---

def convert_mp3_to_pcm(mp3_path: Path, pcm_wav_output_path: Path) -> None:
    """
    Converts an MP3 file to a temporary WAV file (containing PCM data).
    Uses pydub, requiring FFmpeg or libav.
    Equivalent to Java's MP3ToPCMConverter.convertMP3ToPCM.

    Args:
        mp3_path: Path to the input MP3 file.
        pcm_wav_output_path: Path where the output WAV file will be saved.

    Raises:
        FileNotFoundError: If the MP3 file doesn't exist.
        AudioProcessingError: If pydub is not available or conversion fails.
        RuntimeError: If FFmpeg/libav is not found by pydub.
    """
    if not PYDUB_AVAILABLE:
        raise AudioProcessingError("pydub library is not installed. Cannot convert MP3.")
    if not mp3_path.exists():
        raise FileNotFoundError(f"MP3 input file not found: {mp3_path}")

    logger.info(f"Converting MP3 '{mp3_path}' to WAV '{pcm_wav_output_path}'...")
    try:
        # Ensure output directory exists
        pcm_wav_output_path.parent.mkdir(parents=True, exist_ok=True)
        # Delete existing output file to avoid potential issues
        pcm_wav_output_path.unlink(missing_ok=True)

        audio = AudioSegment.from_mp3(str(mp3_path))
        # Export as WAV (which inherently contains PCM)
        # Specify parameters to match expected format if necessary
        # For example, to force mono 16-bit:
        # audio = audio.set_channels(1).set_sample_width(2) # Example: Adjust if needed
        audio.export(str(pcm_wav_output_path), format="wav")
        logger.info(f"Successfully converted MP3 to WAV: {pcm_wav_output_path}")

    except FileNotFoundError as e: # Specifically for ffmpeg/avconv not found
        logger.error(f"FFmpeg or libav executable not found. pydub requires it for MP3 conversion. Error: {e}")
        raise RuntimeError("FFmpeg/libav not found, needed for MP3 conversion.") from e
    except Exception as e:
        logger.error(f"Error converting MP3 {mp3_path} to WAV {pcm_wav_output_path}: {e}", exc_info=True)
        raise AudioProcessingError(f"MP3 to WAV conversion failed: {e}") from e

# --- Silence Detection ---

def detect_silence(pcm_wav_path: Path, silence_threshold: float = VOICE_AMPLITUDE_THRESHOLD, min_silence_duration_sec: float = SILENCE_MIN_DURATION_SEC) -> List[PcmPause]:
    """
    Detects periods of silence in a WAV file using pydub.silence.detect_silence.

    Note: This function requires the 'pydub' library to be installed.

    Args:
        pcm_wav_path: Path to the input WAV file.
        silence_threshold: Amplitude threshold below which audio is considered silent.
                           This value is converted to dBFS for use with pydub.
                           It represents the raw amplitude (e.g., for 16-bit PCM,
                           max is 32767). A lower value means quieter threshold.
        min_silence_duration_sec: Minimum duration (in seconds) for a period to be
                                  considered a significant pause.

    Returns:
        A list of PcmPause objects representing detected silence intervals (in seconds).

    Raises:
        FileNotFoundError: If the WAV file doesn't exist.
        AudioProcessingError: If pydub is not available, reading the file fails,
                              or silence detection encounters an error.
        RuntimeError: If FFmpeg/libav is not found by pydub (might be needed
                      indirectly depending on pydub's WAV handling).
    """
    if not PYDUB_AVAILABLE or not AudioSegment or not pydub_detect_silence:
        raise AudioProcessingError("pydub library is not installed or not fully imported. Cannot detect silence.")
    if not pcm_wav_path.exists():
        raise FileNotFoundError(f"Input WAV file for silence detection not found: {pcm_wav_path}")

    logger.info(f"Detecting silence in '{pcm_wav_path}' using pydub (amplitude_threshold={silence_threshold}, min_duration={min_silence_duration_sec}s)")
    pauses: List[PcmPause] = []
    try:
        # Load the audio file using pydub
        audio = AudioSegment.from_wav(str(pcm_wav_path))

        # Convert minimum silence duration from seconds to milliseconds for pydub
        min_silence_len_ms = int(min_silence_duration_sec * 1000)
        if min_silence_len_ms == 0: min_silence_len_ms = 1 # Ensure it's at least 1ms

        # --- Convert amplitude threshold to dBFS for pydub ---
        # pydub's silence_thresh is in dBFS (relative to full scale)
        # Formula: dBFS = 20 * log10(amplitude / max_possible_amplitude)
        max_amplitude = audio.max_possible_amplitude
        if max_amplitude == 0:
            logger.warning(f"Could not determine max possible amplitude for {pcm_wav_path}. Silence detection might be inaccurate. Assuming 16-bit max.")
            max_amplitude = 32767 # Default fallback for 16-bit PCM

        if silence_threshold <= 0:
            # Logarithm of non-positive number is undefined. Use a very low dBFS value.
            logger.warning(f"Silence amplitude threshold ({silence_threshold}) is non-positive. Using a very low dBFS threshold (-96 dBFS).")
            silence_thresh_dbfs = -96.0 # Very quiet
        else:
            # Calculate dBFS from the provided amplitude threshold
            silence_thresh_dbfs = 20 * math.log10(silence_threshold / max_amplitude)

        logger.debug(f"Using pydub parameters: min_silence_len={min_silence_len_ms}ms, silence_thresh={silence_thresh_dbfs:.2f}dBFS")

        # Detect silence using pydub
        # seek_step=1 means check every millisecond (more accurate but slower)
        silent_ranges_ms = pydub_detect_silence(
            audio,
            min_silence_len=min_silence_len_ms,
            silence_thresh=silence_thresh_dbfs,
            seek_step=1
        )

        # Convert pydub's millisecond ranges to PcmPause objects (seconds)
        for start_ms, end_ms in silent_ranges_ms:
            start_sec = start_ms / 1000.0
            end_sec = end_ms / 1000.0
            # Skip zero-length pauses that might rarely occur
            if start_sec < end_sec:
                pauses.append(PcmPause(start_sec=start_sec, end_sec=end_sec))
                logger.debug(f"Detected pause (pydub): {start_sec:.3f}s - {end_sec:.3f}s (duration {(end_sec - start_sec):.3f}s)")

        logger.info(f"Silence detection complete using pydub. Found {len(pauses)} pauses.")
        return pauses

    except FileNotFoundError as e: # Catch potential ffmpeg/avconv not found from pydub loading
         logger.error(f"FFmpeg or libav executable might be missing, potentially needed by pydub even for WAV. Error: {e}")
         raise RuntimeError("FFmpeg/libav might be missing, needed for pydub audio loading.") from e
    except Exception as e:
        logger.error(f"Error during pydub silence detection for {pcm_wav_path}: {e}", exc_info=True)
        raise AudioProcessingError(f"Pydub silence detection failed: {pcm_wav_path}") from e


# --- Duration/Byte Calculation Helpers ---

def calculate_duration_ms(num_bytes: int, header: WAVHeader) -> int:
    """Calculates audio duration in milliseconds from byte count and header."""
    if not header or header.sample_rate <= 0 or header.bit_depth <= 0 or header.channels <= 0:
        logger.warning("Invalid header provided for duration calculation.")
        return 0
    bytes_per_frame = (header.bit_depth // 8) * header.channels
    if bytes_per_frame == 0: return 0
    # Ensure floating point division for accuracy before int conversion
    num_frames = num_bytes / bytes_per_frame
    duration_sec = num_frames / header.sample_rate
    return int(duration_sec * 1000)

def bytes_for_duration(duration_sec: float, header: WAVHeader) -> int:
    """Calculates the number of bytes for a given duration and header."""
    if not header or duration_sec < 0:
        return 0
    bytes_per_second = header.sample_rate * header.channels * (header.bit_depth // 8)
    # Use float calculation first for accuracy
    num_bytes_float = duration_sec * bytes_per_second
    num_bytes = int(round(num_bytes_float)) # Round to nearest byte

    # Ensure alignment to frame boundary (bytes per sample * channels)
    bytes_per_frame = header.channels * (header.bit_depth // 8)
    if bytes_per_frame > 0:
         # Align down to the nearest full frame
         num_bytes = (num_bytes // bytes_per_frame) * bytes_per_frame
    return num_bytes

def align_offset_to_bit_depth(byte_offset: int, bit_depth: int) -> int:
    """Aligns a byte offset to the sample boundary based on bit depth."""
    bytes_per_sample = bit_depth // 8
    if bytes_per_sample <= 0: return byte_offset # Avoid division by zero
    remainder = byte_offset % bytes_per_sample
    return byte_offset - remainder

# --- Silence Generation ---

def create_silence(duration_sec: float, header: WAVHeader) -> bytes:
    """Generates raw PCM data representing silence."""
    if duration_sec <= 0:
        return b""

    num_bytes = bytes_for_duration(duration_sec, header)
    if num_bytes <= 0:
        return b""

    # Silence is represented by zero for signed formats (like 16-bit)
    # or the midpoint (128) for unsigned formats (like 8-bit)
    bytes_per_sample = header.bit_depth // 8
    if bytes_per_sample == 1: # 8-bit unsigned
        silence_byte = 128
        return bytes([silence_byte] * num_bytes)
    elif bytes_per_sample == 2: # 16-bit signed
        silence_sample = 0
        num_samples = num_bytes // 2
        # Pack zero shorts (little-endian)
        fmt = f'<{num_samples}h' # 'h' is short (2 bytes)
        try:
            # Create a list/tuple of zeros of the correct length
            return struct.pack(fmt, *([silence_sample] * num_samples))
        except struct.error as e:
             logger.error(f"Struct packing error creating silence: {e} (Format: '{fmt}', Num Samples: {num_samples}, Bytes: {num_bytes})")
             # Fallback to creating zero bytes directly if packing fails
             exit(1)
             return bytes(num_bytes)
    else:
        logger.warning(f"Silence generation using zero bytes for unsupported bit depth: {header.bit_depth}")
        # Fallback to zeros, might be incorrect for some formats
        return bytes(num_bytes)