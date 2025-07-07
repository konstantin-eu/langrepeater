# german_repetitor/repetitor/video_generator.py

import subprocess
import logging
import shlex
from pathlib import Path
import platform

# Assumes config and exceptions are defined in these modules
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig
from src.langrepeater_app.repetitor.exceptions import RepetitorError

logger = logging.getLogger(__name__)

# Determine default FFmpeg executable based on OS
# This could also be part of the config
FFMPEG_EXEC = "ffmpeg"  # Assume ffmpeg is in PATH
if platform.system() == "Windows":
    # If ffmpeg isn't in PATH on Windows, provide a specific path:
    # FFMPEG_EXEC = "C:/path/to/ffmpeg/bin/ffmpeg.exe"
    pass  # Keep 'ffmpeg' if it's in PATH


class VideoGenerator:
    """
    Handles video generation using FFmpeg by combining audio and images,
    and potentially embedding subtitles.
    Equivalent to Java's VideoGenerator.java
    """

    def __init__(self, config: LanguageRepetitorConfig):
        """
        Initializes the VideoGenerator.

        Args:
            config: The LanguageRepetitorConfig object.
        """
        self.config = config
        logger.info("VideoGenerator initialized.")
        # Check if ffmpeg executable is accessible (optional)
        try:
            subprocess.run([FFMPEG_EXEC, "-version"], capture_output=True, check=True)
            logger.info(f"FFmpeg found at: {FFMPEG_EXEC}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error(f"FFmpeg executable ('{FFMPEG_EXEC}') not found or failed to execute. Video generation will fail.")
            # Depending on requirements, could raise an error here:
            # raise RepetitorError(f"FFmpeg not found or executable: {FFMPEG_EXEC}")
            exit(1)

    def _run_command(self, command: list[str], working_dir: Path) -> None:
        """
        Executes a system command using subprocess.

        Args:
            command: The command and arguments as a list of strings.
            working_dir: The directory to execute the command in.

        Raises:
            RepetitorError: If the command fails.
        """
        working_dir = "./"
        command_str = shlex.join(command)  # For logging safely
        logger.info(f"Executing command in '{working_dir}': {command_str}")
        try:
            process = subprocess.run(
                command,
                cwd=working_dir,
                check=True,  # Raises CalledProcessError if return code is non-zero
                capture_output=True,  # Capture stdout and stderr
                text=True,  # Decode output as text
                encoding='utf-8'  # Explicitly set encoding
            )
            if process.stdout:
                logger.info(f"FFmpeg STDOUT:\n{process.stdout}")
            if process.stderr:
                # FFmpeg often logs progress to stderr, so log as info
                logger.info(f"FFmpeg STDERR:\n{process.stderr}")
            logger.info(f"Command executed successfully: {command_str}")

        except FileNotFoundError:
            logger.error(f"FFmpeg command not found: '{command[0]}'. Ensure it's installed and in PATH.")
            raise RepetitorError(f"FFmpeg command not found: {command[0]}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}: {command_str}")
            logger.error(f"FFmpeg STDERR (Error):\n{e.stderr}")
            logger.error(f"FFmpeg STDOUT (Error):\n{e.stdout}")
            raise RepetitorError(f"FFmpeg command failed: {command_str}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred while running command {command_str}: {e}", exc_info=True)
            raise RepetitorError(f"Unexpected error running command: {command_str}") from e

    def exec_ffmpeg(self, audio_file_path: Path, subtitle_file_path: Path | None = None) -> Path:
        """
        Executes FFmpeg to create the video or convert audio.

        Args:
            audio_file_path: Path to the generated audio file (e.g., WAV or MP3).
            subtitle_file_path: Optional path to the generated subtitle file (e.g., SRT or ASS).

        Returns:
            The Path object of the generated output file (video or AAC).

        Raises:
            RepetitorError: If FFmpeg execution fails or config is invalid.
        """
        if not audio_file_path.exists():
            raise RepetitorError(f"Audio input file not found: {audio_file_path}")
        if subtitle_file_path and not subtitle_file_path.exists():
            logger.warning(f"Subtitle input file specified but not found: {subtitle_file_path}")
            subtitle_file_path = None  # Proceed without subtitles

        # --- Option 1: Convert to AAC (if configured) ---
        if self.config.create_aac:
            # exit(0)

            output_aac_path = self.config.get_output_filepath(".m4a")
            logger.info(f"Converting audio {audio_file_path} to AAC: {output_aac_path}")
            # ffmpeg -i input_audio.wav -c:a aac output.m4a
            command = [
                FFMPEG_EXEC,
                "-y",  # Overwrite output without asking
                "-i", str(audio_file_path),
                "-c:a", "aac",  # Specify AAC codec
                # Add bitrate options if needed: e.g., "-b:a", "192k"
                str(output_aac_path)
            ]
            self._run_command(command, working_dir=self.config.output_directory)  # Run in output dir
            logger.info(f"AAC file generated: {output_aac_path}")
            return output_aac_path

        # --- Option 2: Create Video ---
        else:
            if not self.config.image_path or not self.config.image_path.exists():
                raise RepetitorError(f"Image file path not configured or file not found: {self.config.image_path}")

            output_video_path = self.config.get_output_filepath(".mkv")  # Or .mp4
            logger.info(f"Creating video file: {output_video_path}")
            logger.info(f"Using image: {self.config.image_path}")
            logger.info(f"Using audio: {audio_file_path}")
            if subtitle_file_path:
                logger.info(f"Using subtitles: {subtitle_file_path}")

            # Base command: loop image, add audio, shortest duration
            # "-loop", "1": Loops the input image indefinitely.
            # "-i", image: Specifies the image file.
            # "-i", audio: Specifies the audio file.
            # "-c:v", "libx264": Choose a common video codec (like H.264). Alternatives: "libx265", "mpeg4".
            # "-tune", "stillimage": Optimizes encoding for static images.
            # "-c:a", "aac": Choose a common audio codec. If input audio is already desired format (e.g., AAC), use "copy".
            # "-b:a", "192k": Set audio bitrate (optional).
            # "-pix_fmt", "yuv420p": Common pixel format for compatibility.
            # "-shortest": Makes the output duration the same as the shortest input (the audio stream).
            command = [
                FFMPEG_EXEC,
                "-y",  # Overwrite output
                "-loop", "1",
                "-i", str(self.config.image_path.resolve()),  # Use resolved absolute path
                "-i", str(audio_file_path.resolve()),  # Use resolved absolute path
                "-c:v", "libx264",  # Video codec
                "-tune", "stillimage",  # Optimize for static image
                "-c:a", "aac",  # Audio codec (or "copy" if audio_file_path is already AAC)
                "-b:a", "192k",  # Audio bitrate
                "-pix_fmt", "yuv420p",  # Pixel format for compatibility
                "-shortest",  # Duration based on audio
            ]

            # Add subtitle filter if subtitles are provided
            if subtitle_file_path:
                # Use absolute path for subtitle file within the filter graph
                subtitle_path_str = str(subtitle_file_path.resolve()).replace('\\', '/')  # Use forward slashes for filter
                # Escape special characters in the path for the filter graph if necessary (e.g., ':')
                # For Windows paths with drive letters:
                if platform.system() == "Windows":
                    subtitle_path_str = subtitle_path_str.replace(':', '\\:')

                # Basic subtitle filter (SRT/ASS usually work directly)
                # More complex styling like in Java example [cite: 481] can be added here
                # vf_filter = f"subtitles='{subtitle_path_str}'"
                # Example with styling from Java [cite: 481] (adjust font size, etc. as needed)
                vf_filter = (
                    f"subtitles='{subtitle_path_str}':"
                    "force_style='Alignment=8,"
                    "Fontsize=24,"
                    "PrimaryColour=&H00FFFFFF,"  # white
                    "BorderStyle=1,Outline=1,Shadow=0,"
                    "MarginV=0'"
                )
                command.extend(["-vf", vf_filter])
                # If using ASS subtitles with specific styling, FFmpeg might handle it automatically,
                # or you might need '-c:s copy' if the container supports it (like MKV).
                # command.extend(["-c:s", "mov_text"]) # Example for MP4 compatibility

            command.append(str(output_video_path))  # Output file last

            self._run_command(command, working_dir=self.config.output_directory)  # Run in output dir
            logger.info(f"Video file generated: {output_video_path}")
            return output_video_path
