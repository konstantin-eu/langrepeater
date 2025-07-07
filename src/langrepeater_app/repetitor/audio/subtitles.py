# german_repetitor/repetitor/audio/subtitles.py

import logging
from pathlib import Path
from typing import List, Optional

# Project Imports
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig
from src.langrepeater_app.repetitor.exceptions import RepetitorError, AudioProcessingError
from src.langrepeater_app.repetitor.audio.models import Caption

logger = logging.getLogger(__name__)


class SubtitleTrack:
    """
    Holds a collection of subtitle captions for a media track.
    Equivalent to Java's SubtitleTrack.java
    """

    def __init__(self, config: LanguageRepetitorConfig):
        """
        Initializes the SubtitleTrack.

        Args:
            config: The main application configuration.
        """
        self.config = config
        self.captions: List[Caption] = []
        logger.debug("SubtitleTrack initialized.")

    def add_caption(self, caption: Caption) -> None:
        """Adds a caption object to the track."""
        if not isinstance(caption, Caption):
            logger.warning(f"Attempted to add non-Caption object to SubtitleTrack: {type(caption)}")
            return
        self.captions.append(caption)
        # Assign index if not already set (useful for SRT)
        if caption.index is None:
            caption.index = len(self.captions)

    def get_captions(self) -> List[Caption]:
        """Returns the list of captions."""
        return self.captions

    def scale_captions(self, scale_factor: float) -> None:
        """
        Applies a scaling factor to the timestamps of all captions.
        Note: It's often better to apply scaling during generation/writing.
        """
        if scale_factor == 1.0:
            return  # No scaling needed
        if scale_factor <= 0:
            logger.error(f"Invalid subtitle scaling factor: {scale_factor}. Must be positive.")
            raise ValueError("Scaling factor must be positive.")

        logger.info(f"Scaling {len(self.captions)} captions by factor: {scale_factor:.4f}")
        for caption in self.captions:
            caption.scale_caption(scale_factor)

    def __len__(self) -> int:
        return len(self.captions)

    def __str__(self) -> str:
        return f"SubtitleTrack with {len(self.captions)} captions."


class SubtitleGenerator:
    """
    Generates subtitle files (currently SRT) from a SubtitleTrack.
    Equivalent logic to Java's SubtitleGeneratorV1.java
    """

    def __init__(self, config: LanguageRepetitorConfig, track: SubtitleTrack):
        """
        Initializes the SubtitleGenerator.

        Args:
            config: The main application configuration.
            track: The SubtitleTrack containing the caption data.
        """
        self.config = config
        self.track = track
        logger.debug("SubtitleGenerator initialized.")

    def save_subtitles(self, output_filename: str, scale_factor: float = 1.0) -> Path:
        """
        Saves the captions to an SRT file, applying scaling if necessary.

        Args:
            output_filename: The desired base name for the output file (e.g., "video_output.srt").
            scale_factor: Factor to scale caption timestamps (default: 1.0).

        Returns:
            The Path object of the generated SRT file.

        Raises:
            AudioProcessingError: If writing the file fails or no captions exist.
        """
        if not self.track or not self.track.get_captions():
            logger.warning("No captions found in the SubtitleTrack. Cannot save subtitle file.")
            raise AudioProcessingError("Cannot generate subtitles: No caption data available.")

        # Determine output path (place it alongside video/audio output)
        output_path = self.config.get_output_filepath(f".{output_filename.split('.')[-1]}")  # Use suffix from filename
        output_path = output_path.with_name(output_filename)  # Ensure correct filename

        logger.info(f"Saving {len(self.track)} captions to SRT file: {output_path}")
        if abs(scale_factor - 1.0) > 1e-6:  # Apply scaling only if factor is not effectively 1.0
            logger.info(f"Applying scaling factor {scale_factor:.4f} to subtitle timestamps.")
            # Create a copy or scale in place? Let's scale a copy for safety.
            scaled_captions = [
                Caption(start_ts_ms=int(c.start_ts_ms * scale_factor),
                        end_ts_ms=int(c.end_ts_ms * scale_factor),
                        text=c.text,
                        index=c.index)
                for c in self.track.get_captions()
            ]
        else:
            logger.debug("No scaling factor applied to subtitles.")
            scaled_captions = self.track.get_captions()  # Use original captions

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, caption in enumerate(scaled_captions):
                    # Use caption index if available, otherwise generate 1-based index
                    srt_index = caption.index if caption.index is not None else i + 1
                    srt_segment = caption.to_srt_segment(srt_index)
                    f.write(srt_segment)
            logger.info(f"Successfully saved SRT file: {output_path}")
            return output_path
        except IOError as e:
            logger.error(f"Failed to write SRT file to {output_path}: {e}", exc_info=True)
            raise AudioProcessingError(f"Failed to write subtitle file: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error saving subtitles to {output_path}: {e}", exc_info=True)
            raise AudioProcessingError(f"Unexpected error saving subtitles: {e}") from e


# --- ASS File Modification (Placeholder) ---

def change_ass_font_and_alignment(
        ass_subtitle_path: Path,
        new_font_size: str = "40",
        new_alignment: str = "5"  # ASS alignment code for middle-center
) -> None:
    """
    Modifies the font size and alignment in the [V4+ Styles] section of an ASS file.
    Based on Java's ASSFontAndAlignmentChangerJava9.java

    NOTE: This is a basic implementation relying on string splitting.
          Robust ASS parsing might require a dedicated library or more careful regex.

    Args:
        ass_subtitle_path: Path to the input/output ASS file.
        new_font_size: The desired font size as a string.
        new_alignment: The desired ASS alignment code as a string.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        RepetitorError: If processing fails.
    """
    if not ass_subtitle_path.exists():
        raise FileNotFoundError(f"ASS subtitle file not found: {ass_subtitle_path}")

    logger.info(f"Attempting to modify ASS file: {ass_subtitle_path} (Font Size: {new_font_size}, Alignment: {new_alignment})")

    try:
        content = ass_subtitle_path.read_text(encoding='utf-8')  # ASS often uses UTF-8
        lines = content.splitlines()
        new_lines = []
        modified = False

        in_styles_section = False
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.lower() == '[v4+ styles]':
                in_styles_section = True
                new_lines.append(line)
                continue
            elif stripped_line.startswith('['):  # Start of another section
                in_styles_section = False

            if in_styles_section and line.lower().startswith("style:"):
                parts = line.split(',', maxsplit=20)  # Split enough times for common fields
                # ASS Style Format (common):
                # Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,
                # Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,
                # BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
                # Indices (0-based): Fontsize=2, Alignment=18 (often)
                try:
                    # Modify Font Size (Index 2)
                    if len(parts) > 2:
                        if parts[2] != new_font_size:
                            logger.debug(f"  Changing font size from {parts[2]} to {new_font_size} in style line.")
                            parts[2] = new_font_size
                            modified = True

                    # Modify Alignment (Index 18) - Check length carefully
                    # ASS alignment uses Numpad notation: 5 = middle-center
                    if len(parts) > 18:
                        if parts[18] != new_alignment:
                            logger.debug(f"  Changing alignment from {parts[18]} to {new_alignment} in style line.")
                            parts[18] = new_alignment
                            modified = True

                    new_lines.append(",".join(parts))
                except IndexError:
                    logger.warning(f"Could not parse style line correctly, leaving unchanged: {line}")
                    new_lines.append(line)  # Append original if parsing fails
                    exit(1)
            else:
                new_lines.append(line)  # Keep non-style lines or lines outside section

        if modified:
            logger.info("ASS style section modified. Writing changes back to file.")
            new_content = "\n".join(new_lines)
            # Add trailing newline if original had one
            if content.endswith('\n') or content.endswith('\r\n'):
                new_content += '\n'
            ass_subtitle_path.write_text(new_content, encoding='utf-8')
        else:
            logger.info("No modifications needed in ASS style section.")

    except Exception as e:
        logger.error(f"Failed to process ASS file {ass_subtitle_path}: {e}", exc_info=True)
        raise RepetitorError(f"Failed to modify ASS file: {e}") from e
