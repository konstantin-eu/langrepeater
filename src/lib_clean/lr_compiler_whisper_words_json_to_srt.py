import logging

logging.basicConfig(level=logging.ERROR)

def do_lr_compiler_whisper_json(json_data, target_root_dir):

    # Print results if successful
    if json_data:
        print("JSON Data Read Successfully:")
        print(json_data)

        # Access specific values
        audio_filename = json_data.get("audio_filename", "Not Found")
        output_speech_timestamps = json_data.get("output_speech_timestamps", "Not Found")
        output_speech_timestamps_enabled = json_data.get("output_speech_timestamps_enabled", False)

        print("\nExtracted Values:")
        print(f"Audio Filename: {audio_filename}")
        print(f"Output Speech Timestamps: {output_speech_timestamps}")
        print(f"Output Speech Timestamps output_speech_timestamps_enabled: {output_speech_timestamps_enabled}")
        speech_timestamps_str = output_speech_timestamps.rstrip(',')
        print(f"Output Speech Timestamps: {speech_timestamps_str}")


    import os
    import json

    def generate_output_paths(audio_path):
        # Extract subdirectory (e.g., "yt18") from the audio file path
        audio_dir = os.path.dirname(audio_path)

        if False:
            sub_dir = os.path.basename(audio_dir)  # Extract last directory name

            # Ensure the target directory follows the required structure
            target_base_dir = os.path.join(target_root_dir, sub_dir)
        target_base_dir = audio_dir

        # Extract filename without extension
        filename_no_ext = os.path.splitext(os.path.basename(audio_path))[0]

        # Define output paths
        json_output_path = os.path.join(target_base_dir, f"{filename_no_ext}.json")
        srt_output_path = os.path.join(target_base_dir, f"{filename_no_ext}.srt")

        return json_output_path, srt_output_path

    # Input: Original audio file path
    audio_path = audio_filename

    # Generate file paths dynamically
    json_output_path, srt_output_path = generate_output_paths(audio_path)

    # Print generated paths
    print("Generated Files 1:")
    print(f"JSON Output Path: {json_output_path}")
    print(f"SRT Output Path: {srt_output_path}")

    file_path = json_output_path

    import os

    def generate_word_merge_srt(srt_file_path):
        # Extract directory, filename, and extension
        base_dir = os.path.dirname(srt_file_path)
        filename, ext = os.path.splitext(os.path.basename(srt_file_path))  # Separate name and extension

        # Create new filename with "_word_merge"
        new_srt_file_path = os.path.join(base_dir, f"{filename}_word_merge{ext}")

        return new_srt_file_path

    srt_output_path = generate_word_merge_srt(srt_output_path)
    print("New SRT Path:", srt_output_path)


    # Write to SRT file
    # srt_file_path = 'output.srt'
    srt_file_path = srt_output_path

    concatenateQuestionMark = False
    append_dot_before_pause = False
    pause_len_sec = 1.0
    merge_max_gap_sec = 1.3
    short_sentence_len = 50
    segment_gap_sec = 1.0
    sentence_merge_threshold_len = 280

    do_second_merge = True
    shift_sentence_start_sec = -0.0
    shift_sentence_end_sec = +0.0
    shift_sentence_end_sec_extra = +1.5

    # Read the JSON file
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # Convert words to a list of dictionaries
    words_list = []
    for segment in data.get("segments", []):
        idx = 0
        s_words = segment.get("words", [])
        s_text = segment.get("text", [])
        s_start = segment.get("start")
        s_end = segment.get("end")

        if append_dot_before_pause:
            if words_list:  # Ensure words_list is not empty
                last_word_info = words_list[-1]
                time_diff = s_start - last_word_info["startTs"]
                if time_diff > pause_len_sec:
                    if not last_word_info["word"].endswith((".", "!", "?")):
                        last_word_info["word"] += "."

        if s_text.endswith(".") or s_text.endswith("!") or s_text.endswith("?"):
            word_entry = {
                "word": s_text,
                "startTs": s_start,
                "endTs": s_end,
                "is_sentence": True,
                "idx": -1,
                "s_len": -1
            }
            words_list.append(word_entry)
            continue

        for w_idx, word_info in enumerate(s_words):
            if False:
                startTs = word_info.get("start")
                endTs = word_info.get("end")
                if endTs <= startTs and len(word_info.get("word")) > 4:
                    raise ValueError("end <= start: ", endTs, startTs, word_info.get("word"), segment.get("text", []))

            word_entry = {
                "word": word_info.get("word"),
                "startTs": word_info.get("start"),
                "endTs": word_info.get("end"),
                "idx": idx,
                "s_len": len(s_words),
                "is_sentence": False,
                "is_last_in_segment": (w_idx == len(s_words) - 1)
            }
            words_list.append(word_entry)
            idx += 1

    # Print the resulting list
    # for entry in words_list:
    #     print(entry)

    # Initialize variables
    sentences = []
    current_sentence = []
    start_ts = None

    # Iterate over the words_list to construct sentences
    for w_idx, word_entry in enumerate(words_list):
        word = word_entry["word"]
        start = word_entry["startTs"]
        end = word_entry["endTs"]
        idx = word_entry["idx"]
        s_len = word_entry["s_len"]
        is_sentence = word_entry["is_sentence"]

        if False:
            if end <= start:
                raise ValueError("end <= start: ", end, start, word)

        # Start a new sentence
        if not current_sentence:
            start_ts = start

        # Add the word to the current sentence
        current_sentence.append(word)

        # Check if the word ends a sentence
        if (
                ((w_idx < len(words_list) - 2) and word_entry.get("is_last_in_segment", False) and (words_list[w_idx + 1]["startTs"] - end) > segment_gap_sec)
                or
                (is_sentence and not word.endswith("?"))
                or
                (is_sentence and not concatenateQuestionMark)
                or (not is_sentence and (
                    (word.endswith(".") and not (len(word) > 1 and word[-2].isdigit() and idx < (s_len - 1)))
                    or word.endswith("!")
                    or (word.endswith("?") and not concatenateQuestionMark))
                )
        ):
            # Construct the sentence entry
            sentence_entry = {
                # "text": "".join(current_sentence).strip(),
                "text": "".join(current_sentence),
                "startTs": start_ts + shift_sentence_start_sec,
                "endTs": end + shift_sentence_end_sec
            }


            if end <= start_ts:
                logging.error(
                    f"end <= start_ts: {sentence_entry}")
                # raise ValueError("end <= start_ts: ", sentence_entry)

            sentences.append(sentence_entry)

            # Reset for the next sentence
            current_sentence = []
            start_ts = None

    # After the main loop for processing words
    if len(current_sentence) > 0:
        # Instead of raising an error, add the remaining words as a final sentence

        last_sentence = "".join(current_sentence) + "."
        # print(" ____ last_sentence: ", last_sentence)

        sentence_entry = {
            "text": last_sentence,
            "startTs": start_ts + shift_sentence_start_sec,
            "endTs": words_list[-1]["endTs"] + shift_sentence_end_sec  # Use the end time of the last word
        }

        # Add a validation check similar to what's in the main loop
        if sentence_entry["endTs"] <= sentence_entry["startTs"]:
            logging.error(f"end <= start_ts in final sentence: {sentence_entry}")

        sentences.append(sentence_entry)

        # Reset for clarity (not strictly necessary as this is end of processing)
        current_sentence = []
        start_ts = None

    # Print the resulting sentences list
    # for sentence in sentences:
    #     print(sentence)


    def do_merged_sentences(sentences):
        # Iterate over the sentences list and merge short sentences
        # Merge short sentences with the previous or next sentence only if
        #   1) The sentence is short (< 50 chars),
        #   2) The previous/next sentence is not too long (< sentence_merge_threshold_len chars),
        #   3) The delay between current sentence and the candidate merge sentence is <= 3 seconds.

        merged_sentences = []
        i = 0

        while i < len(sentences):
            current = sentences[i]
            current_len = len(current["text"])

            if "Religionsunterricht teilnimmt." in current["text"]:
                print("b")

            # If the current sentence is short
            if current_len < short_sentence_len:
                # Calculate previous sentence length and time gap if it exists
                prev_question = False
                if merged_sentences:
                    prev_len = len(merged_sentences[-1]["text"])
                    prev_question = merged_sentences[-1]["text"].endswith("?")

                    # Time gap: how many seconds between the end of the previous and start of current
                    prev_delay = current["startTs"] - merged_sentences[-1]["endTs"]
                else:
                    prev_len = float('inf')
                    prev_delay = float('inf')

                # Calculate next sentence length and time gap if it exists
                if i + 1 < len(sentences):
                    next_len = len(sentences[i + 1]["text"])
                    # Time gap: how many seconds between the end of current and start of next
                    next_delay = sentences[i + 1]["startTs"] - current["endTs"]
                else:
                    next_len = float('inf')
                    next_delay = float('inf')

                # Decide whether to merge with the previous sentence
                can_merge_prev = False
                can_merge_next = False
                if (
                    merged_sentences                  # ensure there's a previous sentence
                    and prev_delay < merge_max_gap_sec              # 3-second gap check
                    # and ((prev_len <= next_len) or (concatenateQuestionMark and prev_question))
                    and ((concatenateQuestionMark and prev_question)
                        or (prev_len < sentence_merge_threshold_len))
                ):
                    can_merge_prev = True

                # Otherwise, decide whether to merge with the next sentence
                if (
                    i + 1 < len(sentences)           # ensure there's a next sentence
                    and next_delay < merge_max_gap_sec              # 3-second gap check
                    # and next_len < prev_len
                    and next_len < sentence_merge_threshold_len
                ):
                    can_merge_next = True

                if can_merge_prev and not can_merge_next:
                    merged_sentences[-1]["text"] += current["text"]
                    merged_sentences[-1]["endTs"] = current["endTs"]
                elif not can_merge_prev and can_merge_next:
                    sentences[i + 1]["text"] = current["text"] + sentences[i + 1]["text"]
                    sentences[i + 1]["startTs"] = current["startTs"]
                elif can_merge_prev and can_merge_next:
                    if prev_len <= next_len:
                        merged_sentences[-1]["text"] += current["text"]
                        merged_sentences[-1]["endTs"] = current["endTs"]
                    else:
                        sentences[i + 1]["text"] = current["text"] + sentences[i + 1]["text"]
                        sentences[i + 1]["startTs"] = current["startTs"]
                else:
                    # If neither merge condition is satisfied, keep the current sentence as-is
                    merged_sentences.append(current)

            else:
                # If the current sentence is not short, just add it to merged_sentences
                merged_sentences.append(current)

            i += 1

        # Print the resulting merged sentences (optional)
        # for sentence in merged_sentences:
        #     print(sentence)

        return merged_sentences


    merged_sentences = do_merged_sentences(sentences)
    if do_second_merge:
        merged_sentences = do_merged_sentences(merged_sentences)

    # Function to format timestamps for SRT
    def format_timestamp(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60  # Keep as a float to retain milliseconds
        milliseconds = int((seconds - int(seconds)) * 1000)
        seconds = int(seconds)  # Convert to integer for the final format
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    # Convert sentences to SRT format
    srt_content = []
    for idx, sentence in enumerate(merged_sentences, start=1):
        start = format_timestamp(sentence["startTs"])
        end = format_timestamp(sentence["endTs"] + shift_sentence_end_sec_extra)
        # sentence['text'] = sentence['text'].replace("  ", " ")
        sentence['text'] = sentence['text'].strip()
        srt_content.append(f"\n{idx}\n{start} --> {end}\n{sentence['text']}\n")

        if sentence["endTs"] <= sentence["startTs"]:
            logging.error(
                f"end <= start_ts: {start} --> {end}\n{sentence['text']}")


    with open(srt_file_path, 'w', encoding='utf-8') as srt_file:
        srt_file.writelines(srt_content)

    print(f"SRT file saved to {srt_file_path}")
    return srt_file_path

