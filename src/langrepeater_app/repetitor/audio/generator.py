import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set

# Project Imports
from src.langrepeater_app.repetitor.config import LanguageRepetitorConfig, SubGroupType, SegmentType
from src.langrepeater_app.repetitor.constants import Language, RUS_PREFIX, DE_PREFIX, EN_PREFIX
from src.langrepeater_app.repetitor.exceptions import RepetitorError, AudioProcessingError
from src.langrepeater_app.repetitor.phrasereader.models import Phrase, SubtitleInterval
from src.langrepeater_app.repetitor.audio.models import Group, SubGroup, Segment, SegmentVariant, Caption, RenderJob
from src.langrepeater_app.repetitor.audio.cache import MediaCache
from src.langrepeater_app.repetitor.audio.subtitles import SubtitleTrack, SubtitleGenerator
# Helper for fixing text before TTS/SRT
from src.langrepeater_app.repetitor.audio.text_fixer import SsmlSrtFixer

logger = logging.getLogger(__name__)

# Helper function similar to Java's PhrasesReader2.splitLine
def split_line_by_pipe(line: str) -> List[str]:
    """Splits a line by the '|' character, ignoring empty parts."""
    if not line:
        return []
    return [part.strip() for part in line.split('|') if part.strip()]

# Helper function similar to Java's RepetitorGoogleCloud.splitLineDe
# This might be better placed in a language-specific utility module
def split_line_de_by_sentence(line: str) -> List[str]:
    """Splits a German line by sentence terminators (., ?, !)."""
    if not line:
        return []
    # Basic split by common sentence endings, keeping the terminator
    # More robust splitting might use NLTK or spaCy
    sentences = re.split(r'([.?!])\s*', line)
    result = []
    if sentences:
        # Combine sentence parts with their terminators
        for i in range(0, len(sentences) - 1, 2):
            sentence = (sentences[i] + (sentences[i+1] or "")).strip()
            if sentence:
                result.append(sentence)
        # Add the last part if it exists and isn't just whitespace/empty
        last_part = sentences[-1].strip()
        if last_part:
            result.append(last_part)
    return result if result else [line] # Return original if split fails

class AudioGeneratorV1:
    """
    Generates the main audio track by processing phrases, managing cache,
    concatenating segments, and creating subtitle data.
    Equivalent to Java's AudioGeneratorV1.java
    """

    def __init__(self, config: LanguageRepetitorConfig):
        self.config = config
        # Initialize the specific MediaCache implementation (e.g., V2)
        self.media_cache = MediaCache(self.config)
        self.text_fixer = SsmlSrtFixer() # Initialize text fixer utility
        logger.info("AudioGeneratorV1 initialized.")

    def _create_segment(
        self,
        subgroup: SubGroup,
        text: str,
        language: Language,
        segment_types: Set[SegmentType],
        subtitle_interval: SubtitleInterval,
        subgroup_config: dict
    ) -> Segment:
        """Creates a Segment object, handling text fixing and variant creation."""
        # Fix text for TTS processing before creating the segment
        fixed_text = self.text_fixer.fix_tss_text_segment(text)

        segment = Segment(text=fixed_text, language=language, subgroup_config=subgroup_config)

        # Create variants based on the determined segment types
        for seg_type in segment_types:
            # Speed comes from the language-specific TTS config
            speed = self.config.tts_configs.get(language, {}).get('speed', "100%")
            variant = SegmentVariant(
                subtitle_interval=subtitle_interval if seg_type == SegmentType.FILE_SEGMENT else None,
                audio_file_key=subtitle_interval.audio_file if seg_type == SegmentType.FILE_SEGMENT else None,
                speed_percent=speed
            )
            segment.variants[seg_type] = variant

        subgroup.segments.append(segment)
        return segment

    def _build_segments_from_text(
        self,
        group: Group,
        line: str,
        subgroup_config: dict,
        subtitle_interval: SubtitleInterval,
        delay_override: bool
    ) -> SubGroup:
        """
        Splits a line into text parts and creates Segments for them within a new SubGroup.
        Similar to logic in Java's RepetitorGoogleCloud.buildSegmentsFromText
        """
        subgroup_type = subgroup_config.get('type')
        if not subgroup_type:
            raise ValueError("Subgroup config dictionary must contain 'type'")

        subgroup = SubGroup(
            subgroup_type=subgroup_type,
            delay_override=delay_override,
            delay_override_sec=subgroup_config.get('delay_override_sec', 0)
        )
        group.subgroups[subgroup_type] = subgroup # Add subgroup to the main group

        # Split the input line into potential multiple segments based on '|'
        text_parts = split_line_by_pipe(line)
        if not text_parts:
             logger.warning(f"Line '{line}' produced no text parts after splitting by '|'.")
             # Create a single silent segment? Or raise error? For now, log and return empty subgroup.
             # Let's create one segment to avoid errors downstream, but mark as potentially problematic
             text_parts = [line.strip()] # Use original line if split yields nothing

        combined_caption_text = []
        for text in text_parts:
            if not text:
                logger.warning(f"Empty text part found in line '{line}' for subgroup {subgroup_type}.")
                continue

            # Determine language override based on prefixes (like Java)
            current_text = text
            current_lang = subgroup_config.get('language', Language.EN) # Default if not set

            # Check prefixes only for description/translation as per Java logic
            if subgroup_type in [SubGroupType.DESCRIPTION, SubGroupType.TRANSLATION]:
                if text.lower().startswith(DE_PREFIX):
                    current_text = text[len(DE_PREFIX):].strip()
                    current_lang = Language.DE
                elif text.lower().startswith(EN_PREFIX):
                    current_text = text[len(EN_PREFIX):].strip()
                    current_lang = Language.EN
                elif text.lower().startswith(RUS_PREFIX):
                    current_text = text[len(RUS_PREFIX):].strip()
                    current_lang = Language.RU
                # else: use the default language from subgroup_config

            # Determine required segment types (e.g., CLOUD, FILE_SEGMENT)
            callback_arg = type('CallbackArg', (object,), {
                'sub_group_type': subgroup_type,
                'language': current_lang,
                'subtitle_interval': subtitle_interval
            })() # Create a simple object matching expected callback arg structure

            segment_types: Set[SegmentType] = self.config.get_types_callback(callback_arg)

            # Further split German text if needed (e.g., for cloud generation)
            # This logic might vary based on exact requirements
            needs_sentence_split = (
                current_lang == Language.DE and
                SegmentType.GENERATED_CLOUD in segment_types and
                len(segment_types) == 1 # Only split if CLOUD is the *only* type
            )
            needs_sentence_split = False

            if needs_sentence_split:
                sentences = split_line_de_by_sentence(current_text)
                for sentence in sentences:
                    if sentence:
                        segment = self._create_segment(subgroup, sentence, current_lang, segment_types, subtitle_interval, subgroup_config)
                        combined_caption_text.append(segment.text) # Use fixed text for caption
            else:
                segment = self._create_segment(subgroup, current_text, current_lang, segment_types, subtitle_interval, subgroup_config)
                combined_caption_text.append(segment.text) # Use fixed text for caption

        if not subgroup.segments:
            logger.warning(f"No segments created for subgroup {subgroup_type} from line '{line}'.")
            # Handle this case - maybe add a silent segment?

        # Combine text from all segments in this subgroup for the subtitle
        subgroup.subtitle_track_caption_text = " ".join(combined_caption_text).strip()

        return subgroup

    def _phrase_to_card(self, phrase: Phrase) -> Group:
        """
        Converts a Phrase object into a Group (card) containing SubGroups and Segments.
        Similar to logic in Java's RepetitorGoogleCloud.phraseToCard
        """
        card = Group(config=self.config) # Pass config reference

        if phrase.is_description:
            # Create a single subgroup for the description
            self._build_segments_from_text(
                card,
                phrase.description,
                self.config.description_segment_config,
                SubtitleInterval.from_line(""), # Empty interval for descriptions
                delay_override=True # Descriptions often have fixed delay
            )
        else:
            # Create subgroups for original and translation
            original_interval = SubtitleInterval.from_line(phrase.original_ts_line)

            # Original Phrase SubGroup
            self._build_segments_from_text(
                card,
                phrase.original,
                self.config.orig_segment_config,
                original_interval,
                delay_override=False # Original usually has dynamic delay
            )

            # Translation Phrase SubGroup (if enabled)
            if self.config.has_translation:
                 if not phrase.translation:
                     logger.warning(f"Missing translation for original phrase: '{phrase.original[:50]}...'")
                     # Decide how to handle: skip, add silence, error?
                     # For now, create an empty subgroup to avoid breaking structure
                     trans_subgroup = SubGroup(
                         subgroup_type=SubGroupType.TRANSLATION,
                         delay_override=True, # Use fixed delay if translation missing
                         delay_override_sec=self.config.transl_segment_config.get('delay_override_sec', 0)
                     )
                     card.subgroups[SubGroupType.TRANSLATION] = trans_subgroup
                 else:
                    self._build_segments_from_text(
                        card,
                        phrase.translation,
                        self.config.transl_segment_config,
                        original_interval, # Use same interval context
                        delay_override=True # Translations often have fixed delay
                    )
            else:
                 logger.debug("Translation is disabled in config.")


        # Validation: Ensure subgroups were actually created if expected
        if not phrase.is_description:
            if SubGroupType.ORIGINAL_PHRASE not in card.subgroups:
                 logger.error(f"Failed to create ORIGINAL_PHRASE subgroup for phrase: {phrase}")
                 raise RepetitorError("Original phrase subgroup creation failed.")
            if self.config.has_translation and SubGroupType.TRANSLATION not in card.subgroups:
                 logger.error(f"Failed to create TRANSLATION subgroup for phrase: {phrase}")
                 raise RepetitorError("Translation phrase subgroup creation failed.")

        return card


    def _save_card_audio(
        self,
        current_ts_ms: int,
        card: Group,
        subtitle_track: SubtitleTrack,
        is_last_card: bool
    ) -> int:
        """
        Saves the audio for a single card (Group) to the media cache output stream
        and updates the subtitle track.

        Returns:
            The updated timestamp in milliseconds after processing this card.
        """
        logger.debug(f"Saving card: {'Description' if card.is_description() else 'Phrase'}")
        repeat_count = 1 if card.is_description() else self.config.repeat_number
        subgroups_to_process = card.get_subgroup_list()

        if not subgroups_to_process:
             logger.warning("Card has no subgroups to process.")
             return current_ts_ms

        for i in range(repeat_count):
            logger.debug(f"  Repeat {i+1}/{repeat_count}")
            for subgroup in subgroups_to_process:
                start_subgroup_ts_ms = current_ts_ms
                subgroup_duration_ms = 0
                primary_segment_type: Optional[SegmentType] = None # Track type for pause calc

                if not subgroup.segments:
                     logger.warning(f"Subgroup {subgroup.subgroup_type} has no segments.")
                     continue # Skip empty subgroups

                logger.debug(f"    Processing SubGroup: {subgroup.subgroup_type}")
                for segment in subgroup.segments:
                    # Select the audio type for this iteration (e.g., CLOUD, FILE)
                    # The selection logic might depend on 'i' if multiple types exist
                    segment_type = segment.select_type(subgroup.subgroup_type, i)
                    if primary_segment_type is None:
                        primary_segment_type = segment_type # Use type of first segment for pause calc

                    if segment_type is None:
                        logger.warning(f"Segment '{segment.text[:30]}...' has no suitable audio variant for iteration {i}. Skipping.")
                        continue

                    if segment.is_silent:
                        logger.debug(f"      Segment is silent: '{segment.text}'")
                        # Save a short pause for silent segments (e.g., punctuation only)
                        # Duration could be configurable
                        pause_duration_sec = 0.2 # Example short pause
                        try:
                            duration_ms, _ = self.media_cache.save_pause_bytes(pause_duration_sec)
                            current_ts_ms += duration_ms
                            subgroup_duration_ms += duration_ms
                        except Exception as e:
                            logger.error(f"Failed to save pause for silent segment: {e}", exc_info=True)
                            raise AudioProcessingError("Failed to save pause for silent segment") from e
                    else:
                        logger.debug(f"      Saving Segment ({segment_type.name}): '{segment.text[:30]}...'")
                        try:
                            # save_segment_bytes returns (duration_ms, bytes_written)
                            duration_ms, _ = self.media_cache.save_segment_bytes(segment, segment_type)
                            current_ts_ms += duration_ms
                            subgroup_duration_ms += duration_ms
                        except Exception as e:
                            logger.error(f"Failed to save segment bytes for '{segment.text[:30]}...': {e}", exc_info=True)
                            raise AudioProcessingError(f"Failed to save segment bytes: {e}") from e

                    # Optional: Add very short pause between segments within a subgroup?
                    # try:
                    #     pause_ms, _ = self.media_cache.save_pause_bytes(0.05) # 50ms pause
                    #     current_ts_ms += pause_ms
                    #     subgroup_duration_ms += pause_ms
                    # except Exception: pass # Ignore errors for minor pauses

                # --- Add Pause After SubGroup ---
                if subgroup_duration_ms > 0: # Only add pause if subgroup had content
                    pause_sec = 0.0
                    if subgroup.delay_override:
                        pause_sec = float(subgroup.delay_override_sec)
                        logger.debug(f"    Using fixed pause: {pause_sec}s")
                    else:
                        # Calculate dynamic pause based on subgroup duration and multiplier
                        multiplier = 1.0
                        # Apply multiplier for specific cases (e.g., file segments)
                        if primary_segment_type == SegmentType.FILE_SEGMENT:
                            multiplier = self.config.delay_multiplier_for_file_segment

                        base_pause_sec = (subgroup_duration_ms / 1000.0) * multiplier
                        pause_sec = base_pause_sec + self.config.extra_delay_sec

                        # Apply max limit if configured
                        if self.config.delay_after_orig_phrase_fix and subgroup.subgroup_type == SubGroupType.ORIGINAL_PHRASE:
                            pause_sec = min(pause_sec, self.config.delay_after_orig_phrase_override_max)

                        pause_sec = max(0.0, pause_sec) # Ensure pause is not negative
                        logger.debug(f"    Calculated dynamic pause: {pause_sec:.2f}s (base={base_pause_sec:.2f}s, extra={self.config.extra_delay_sec}s, mult={multiplier})")


                    try:
                        # Pass segment type for potential adjustments (like in Java V2)
                        pause_ms, _ = self.media_cache.save_pause_bytes(pause_sec, primary_segment_type)
                        current_ts_ms += pause_ms
                        logger.debug(f"    Added pause after subgroup: {pause_ms}ms")
                    except Exception as e:
                        logger.error(f"Failed to save pause after subgroup {subgroup.subgroup_type}: {e}", exc_info=True)
                        raise AudioProcessingError("Failed to save pause after subgroup") from e

                # --- Add Caption ---
                if subgroup_duration_ms > 0 and subgroup.subtitle_track_caption_text:
                     caption = Caption(
                         start_ts_ms=start_subgroup_ts_ms,
                         end_ts_ms=current_ts_ms, # End time includes the pause *after* the subgroup
                         text=subgroup.subtitle_track_caption_text
                     )
                     subtitle_track.add_caption(caption)
                     logger.debug(f"    Added caption: '{caption.text[:50]}...' ({caption.start_ts_ms}ms -> {caption.end_ts_ms}ms)")


        # --- Add Final Silence (only after the very last card) ---
        if is_last_card:
            logger.debug("Adding final silence at the end of the track.")
            try:
                pause_ms, _ = self.media_cache.save_pause_bytes(float(self.config.SILENCE_AT_THE_END_SEC))
                current_ts_ms += pause_ms
            except Exception as e:
                logger.error(f"Failed to save final silence: {e}", exc_info=True)
                # Don't necessarily raise, maybe just log warning
                exit(1)

        return current_ts_ms


    def create_audio(self, job: RenderJob) -> Tuple[Path, Optional[Path]]:
        """
        Generates the audio file and subtitle data for the given job.

        Args:
            job: The RenderJob containing config and phrases.

        Returns:
            A tuple containing:
                - Path to the generated audio file (e.g., WAV).
                - Optional Path to the generated subtitle file (e.g., SRT).

        Raises:
            AudioProcessingError: If any step in audio/subtitle generation fails.
        """
        logger.info("Starting audio and subtitle generation...")
        if not job.phrases:
            logger.warning("No phrases provided in the job. Skipping audio generation.")
            raise AudioProcessingError("No phrases to process.")

        # --- 1. Convert Phrases to Internal Card Representation ---
        logger.info("Converting phrases to internal card structure...")
        cards: List[Group] = []
        print(" ______ speed de: ", self.config.tts_configs.get(Language.DE, {}).get('speed', "100%"))
        print(" ______ speed en: ", self.config.tts_configs.get(Language.EN, {}).get('speed', "100%"))
        print(" ______ speed ru: ", self.config.tts_configs.get(Language.RU, {}).get('speed', "100%"))

        try:
            for phrase in job.phrases:
                card = self._phrase_to_card(phrase)
                cards.append(card)
        except Exception as e:
            logger.error(f"Failed to convert phrases to cards: {e}", exc_info=True)
            raise AudioProcessingError(f"Phrase conversion failed: {e}") from e
        logger.info(f"Converted {len(job.phrases)} phrases to {len(cards)} cards.")

        # --- 2. Populate Media Cache (Fetch/Generate individual segments) ---
        logger.info("Populating media cache...")
        try:
            # Add all segments from cards to the cache plan
            for card in cards:
                for subgroup in card.subgroups.values():
                    for segment in subgroup.segments:
                        if not segment.is_silent:
                            self.media_cache.add_segment_to_plan(segment)

            # Execute the plan (download/generate audio)
            self.media_cache.populate_cache()
            # Ensure header is set after population
            if self.media_cache.get_header() is None:
                 logger.warning("Audio header not set after cache population, using default.")
                 self.media_cache.set_header_if_missing() # Use default if needed

        except Exception as e:
            logger.error(f"Failed to populate media cache: {e}", exc_info=True)
            raise AudioProcessingError(f"Media cache population failed: {e}") from e
        logger.info("Media cache populated.")

        # --- 3. Save Combined Audio and Generate Subtitle Data ---
        logger.info("Saving combined audio track and generating subtitle data...")
        subtitle_track = SubtitleTrack(self.config)
        current_ts_ms = 0
        output_audio_phase1_path = self.media_cache.get_output_path_phase1()

        has_exception = False
        try:
            with open(output_audio_phase1_path, 'wb') as audio_stream:
                self.media_cache.set_output_stream(audio_stream) # Link stream to cache
                for i, card in enumerate(cards):
                    is_last = (i == len(cards) - 1)
                    print(f" _____ card: {i}/{len(cards)}")
                    current_ts_ms = self._save_card_audio(
                        current_ts_ms, card, subtitle_track, is_last
                    )
            logger.info(f"Phase 1 audio saved to: {output_audio_phase1_path}")
            logger.info(f"Total calculated duration (before finalization): {current_ts_ms}ms")

        except Exception as e:
            has_exception = True
            logger.error(f"Failed during audio stream writing or caption generation: {e}", exc_info=True)
            exit(1)
            # Attempt cleanup?
            if output_audio_phase1_path.exists():
                try: output_audio_phase1_path.unlink()
                except OSError: pass
            raise AudioProcessingError(f"Audio stream writing failed: {e}") from e
        finally:
            if has_exception:
                self.media_cache.set_output_stream(None) # Unlink stream

        # --- 4. Finalize Audio File (e.g., add WAV header) ---
        logger.info("Finalizing audio file...")
        try:
            final_audio_path = self.media_cache.finalize_audio_file()
            logger.info(f"Final audio file created: {final_audio_path}")
            # Get potentially more accurate duration after finalization
            final_duration_ms = self.media_cache.get_final_duration_ms()
            logger.info(f"Final audio duration: {final_duration_ms}ms")

        except Exception as e:
            logger.error(f"Failed to finalize audio file: {e}", exc_info=True)
            raise AudioProcessingError(f"Audio finalization failed: {e}") from e


        # --- 5. Scale and Save Subtitles ---
        logger.info("Saving subtitle file...")
        subtitle_output_path: Optional[Path] = None
        try:
            # Calculate scaling factor if needed (e.g., if calculated duration differs from final)
            scale_factor = 1.0
            if current_ts_ms > 0 and final_duration_ms > 0: # Avoid division by zero
                 scale_factor = final_duration_ms / current_ts_ms
                 if abs(scale_factor - 1.0) > 0.01: # Only log if significantly different
                     logger.info(f"Applying subtitle scaling factor: {scale_factor:.4f}")
                 else:
                     scale_factor = 1.0 # Reset if difference is negligible

            # Use a SubtitleGenerator implementation
            subtitle_generator = SubtitleGenerator(self.config, subtitle_track)
            # Define output filename (e.g., using video prefix + .srt)
            srt_filename = self.config.video_out_filename_prefix + ".srt"
            subtitle_output_path = subtitle_generator.save_subtitles(srt_filename, scale_factor)
            logger.info(f"Subtitle file saved: {subtitle_output_path}")

        except Exception as e:
            logger.error(f"Failed to save subtitle file: {e}", exc_info=True)
            # Don't necessarily raise an error for subtitle failure, maybe just warn
            logger.warning("Subtitle file generation failed, continuing without subtitles.")
            subtitle_output_path = None
            exit(1)


        # --- 6. Post-Save Steps (e.g., cleanup) ---
        try:
            self.media_cache.post_save_cleanup()
        except Exception as e:
            logger.warning(f"Error during post-save cleanup: {e}", exc_info=True)
            exit(1)

        logger.info("Audio and subtitle generation process finished.")
        return final_audio_path, subtitle_output_path

