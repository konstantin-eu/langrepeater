import os
import json
from faster_whisper import WhisperModel

import time

def generate_output_paths(audio_path):
    # Extract subdirectory (e.g., "yt18") from the audio file path
    audio_dir = os.path.dirname(audio_path)
    sub_dir = os.path.basename(audio_dir)  # Extract last directory name

    # Ensure the target directory follows the required structure
    # target_base_dir = os.path.join(target_root_dir, sub_dir)

    # Extract filename without extension
    filename_no_ext = os.path.splitext(os.path.basename(audio_path))[0]

    # Define output paths
    json_output_path = os.path.join(audio_dir, f"{filename_no_ext}.json")
    srt_output_path = os.path.join(audio_dir, f"{filename_no_ext}.srt")

    return json_output_path, srt_output_path

def run_faster_whisper(json_data):
    dbg_start_time = time.time()  # Start time
    print("dbg_start_time", dbg_start_time)

    # Read JSON content
    # json_data = read_json(output_whisper_parameters)

    # Print results if successful
    if json_data:
        print("JSON Data Read Successfully:")
        print(json_data)


        # Access specific values
        audio_filename = json_data.get("audio_filename", "Not Found")
        output_speech_timestamps = json_data.get("output_speech_timestamps", "Not Found")
        output_speech_timestamps_enabled = json_data.get("output_speech_timestamps_enabled", False)
        in_model = json_data.get("model", "large")
        in_word_timestamps = json_data.get("word_timestamps", True)

        if in_model == "large":
            in_model = "large-v3"

        print("\nExtracted Values:")
        print(f"in_model: {in_model}")
        print(f"Audio Filename: {audio_filename}")
        print(f"Output Speech Timestamps: {output_speech_timestamps}")
        print(f"Output Speech Timestamps output_speech_timestamps_enabled: {output_speech_timestamps_enabled}")
        speech_timestamps_str = output_speech_timestamps.rstrip(',')
        print(f"Output Speech Timestamps: {speech_timestamps_str}")
    else:
        raise ValueError("1")

    model = WhisperModel(in_model, device="cuda", compute_type="float16")
    # Input audio file
    file = audio_filename

    # Input: Original audio file path
    audio_path = audio_filename

    # Generate file paths dynamically
    json_output_path, srt_output_path = generate_output_paths(audio_path)

    # Print generated paths
    print("Generated Files 2:")
    print(f"JSON Output Path: {json_output_path}")
    print(f"SRT Output Path: {srt_output_path}")
    print(f"output_speech_timestamps: {output_speech_timestamps}")

    if output_speech_timestamps_enabled:
        print("output_speech_timestamps:", output_speech_timestamps)

        float_list = [float(x) for x in output_speech_timestamps.strip(',').split(',')]

        print(float_list)

        segments, info = model.transcribe(file, language="de", beam_size=5, word_timestamps=in_word_timestamps, clip_timestamps=float_list)
    else:
        # 0,23
        # Transcribe with word-level timestamps
        # segments, info = model.transcribe(file, language="de", beam_size=5, word_timestamps=True, clip_timestamps=in_clip_timestamps)
        segments, info = model.transcribe(file, language="de", beam_size=5, word_timestamps=in_word_timestamps)

    print("Detected language '%s' with probability %f" % (info.language, info.language_probability))

    # Prepare output JSON and SRT content
    output_json = {
        "text": "",
        "segments": []
    }
    srt_content = ""

    def format_time(seconds):
        """ Convert seconds to SRT timestamp format (HH:MM:SS,mmm) """
        milliseconds = int((seconds % 1) * 1000)
        seconds = int(seconds)
        minutes = (seconds // 60) % 60
        hours = seconds // 3600
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    # Initialize a variable to collect the full transcript text.
    transcript_text = ""

    # Single loop over segments to build all outputs.
    for i, segment in enumerate(segments, start=1):
        transcript_text += segment.text

        # Build JSON segment data.
        segment_data = {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "words": []
        }
        for word in segment.words:
            word_data = {
                "start": word.start,
                "end": word.end,
                "word": word.word
            }
            segment_data["words"].append(word_data)
        output_json["segments"].append(segment_data)

        # Build SRT output.
        srt_content += f"{i}\n"
        srt_content += f"{format_time(segment.start)} --> {format_time(segment.end)}\n"
        srt_content += f"{segment.text}\n\n"

        print(f"{format_time(segment.start)} --> {format_time(segment.end)}")
        print(f"{segment.text}")

    # Update the full text in the JSON output.
    output_json["text"] = transcript_text

    # Save JSON file.
    json_output_file = "transcription.json"
    json_output_file = json_output_path
    with open(json_output_file, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=4)

    # Save SRT file.
    srt_output_file = "transcription.srt"
    srt_output_file = srt_output_path
    with open(srt_output_file, "w", encoding="utf-8") as f:
        f.write(srt_content)

    print(f"Transcription saved as JSON: {json_output_file}")
    print(f"Transcription saved as SRT: {srt_output_file}")


    dbg_end_time = time.time()  # End time
    print("dbg_end_time", dbg_end_time)
    execution_time = dbg_end_time - dbg_start_time
    print(f"Execution time: {execution_time:.4f} seconds")

    return output_json