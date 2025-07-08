from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

import torchaudio
import soundfile as sf

def do_whiper_vad_silero(audio_file,
                         in_min_silence_duration_ms = 100,
                         in_min_speech_duration_ms = 250,
                         in_threshold = 0.3,
                         in_widen_extra_start = -0.25,
                         in_widen_extra_end = 2.0,
                         ):

    def format_srt_time(milliseconds):
      """Convert milliseconds to SRT timestamp format HH:MM:SS,MS"""
      total_seconds = milliseconds // 1000
      ms = milliseconds % 1000
      hours, remainder = divmod(total_seconds, 3600)
      minutes, seconds = divmod(remainder, 60)
      return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02},{int(ms):03}"

    def generate_srt(speech_timestamps, output_file="output.srt"):
        with open(output_file, "w", encoding="utf-8") as srt_file:
          for idx, ts in enumerate(speech_timestamps, start=1):
            # Convert seconds to milliseconds (do not divide by 16000 here)
            widen_val = 0.0 # TODO could be overlapping, check below min_silence_duration_ms value, ideally widen_val=min_silence_duration_ms/2
            # widen_val = 0.1
            ts["start"] = max(0, ts["start"] - widen_val)
            if idx <= len(speech_timestamps):
                # TODO check audio file length!
                ts["end"] = ts["end"] + widen_val
            start_time = format_srt_time(ts["start"] * 1000)
            end_time = format_srt_time(ts["end"] * 1000)
            srt_file.write(f"{idx}\n{start_time} --> {end_time}\n[SPEECH]\n\n")

        print(f"SRT file saved as {output_file}")

    if False:
        import json

        # Load JSON data from a file
        with open(r"data/1.json", "r") as file:
            speech_timestamps = json.load(file)

        # Print data
        print(speech_timestamps)

        # Access specific values
        for entry in speech_timestamps:
            print(f"Start: {entry['start']}, End: {entry['end']}")

        # Convert to SRT format and save
        generate_srt(speech_timestamps, "output.srt")

        exit(0)

    print("Torchaudio backends:", torchaudio.list_audio_backends())
    # print("Soundfile available:", sf.available_formats())
    # import soundfile as sf

    # torchaudio.set_audio_backend("ffmpeg")  # If you installed FFmpeg


    print("Torchaudio backends:", torchaudio.list_audio_backends())
    print("Soundfile is needed for silero_vad! Soundfile available:", sf.available_formats())

    # usage: tested only on wav audio files with large wisper model on german speach audio, but probably other audio format supported by soundfile will work!
    # silero_vad add extra step(slows down) before whisper inference and create a temp audio file
    def generate_file_paths(audio_file):
        import os

        # Get the directory and filename without extension
        base_dir = os.path.dirname(audio_file)
        filename = os.path.basename(audio_file)
        filename_no_ext = os.path.splitext(filename)[0]  # Remove .wav extension

        # Construct required paths
        subtitle_file = os.path.join(base_dir, f"{filename_no_ext}_speech_segments.srt")
        segments_dir = os.path.join(base_dir, "segments")

        return subtitle_file, segments_dir

    # Example Usage
    subtitle_file, segments_dir = generate_file_paths(audio_file)


    print("Subtitle File:", subtitle_file)
    print("Segments Directory:", segments_dir)

    model = load_silero_vad()
    wav = read_audio(audio_file)
    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        return_seconds=True,  # Return speech timestamps in seconds (default is samples)
        min_silence_duration_ms=in_min_silence_duration_ms,  # Require 700ms silence to split segments
        min_speech_duration_ms=in_min_speech_duration_ms,  # Ignore speech shorter than 250ms
        threshold=in_threshold  # Adjust sensitivity (higher = stricter)
    )

    # print("speech_timestamps 1: ", speech_timestamps)
    # Get the end timestamp of the last subtitle
    last_end_time = speech_timestamps[-1]['end'] if speech_timestamps else 0

    if True:
        # Widen subtitles by 0.25 sec, while respecting boundaries
        for timestamp in speech_timestamps:
            # Don't let start time go below 0
            timestamp['start'] = max(0, timestamp['start'] + in_widen_extra_start)
            # Don't let end time exceed the last subtitle's end time
            timestamp['end'] = min(last_end_time, timestamp['end'] + in_widen_extra_end)

    if True:
        # Join overlapping segments into a single segment
        i = 0
        while i < len(speech_timestamps) - 1:
            if speech_timestamps[i]['end'] > speech_timestamps[i + 1]['start']:
                print(f"Joining overlapping segments: {speech_timestamps[i]}, {speech_timestamps[i + 1]}")
                # Merge the two segments by taking the maximum end time
                speech_timestamps[i]['end'] = max(speech_timestamps[i]['end'], speech_timestamps[i + 1]['end'])
                # Remove the second segment since it's now merged with the first
                speech_timestamps.pop(i + 1)
                # Don't increment i since we need to check if the newly merged segment
                # overlaps with the next segment too
            else:
                i += 1

    if False:
        # Save to a text file
        with open(output_speech_timestamps, "w") as file:
            file.write(output_string)

        print(f"File {output_speech_timestamps} has been created successfully.")


    # Convert to SRT format and save
    generate_srt(speech_timestamps, subtitle_file)

    print("speech_timestamps 2: ", speech_timestamps)

    return speech_timestamps

