import argparse
from src.lib_clean import lr_compiler_srt
from src.lib_clean.lib_common import get_app_dir, get_app_whisper_dir, get_app_wav_dir
from src.lib_clean.my_faster_whisper_json_args import run_faster_whisper
from src.lib_clean.lr_compiler_whisper_words_json_to_srt import do_lr_compiler_whisper_json
from src.langrepeater_app.main import langrepeater_main

import time

from src.lib_clean.whisper_vad_silero_vad import do_whiper_vad_silero

my_app_start_time = time.time()
print(f"app time start: {__name__} {my_app_start_time}")

def to_txt_file(out_dir, audio_file):
    import os
    base_name = os.path.splitext(os.path.basename(audio_file))[0]

    return str(out_dir / (base_name + '.txt'))

def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "infile",
        help="Path to the input audio wav file"
    )

    # optional flag with a default
    parser.add_argument(
        "--lrtxt_outdir",
        default="",
        help="Where to write the langrepeater txt file"
    )

    parser.add_argument(
        "--create_audio",
        action="store_true",
        help="If set, a video will be created"
    )

    return parser.parse_args()

output_speech_timestamps_enabled = True

def main():
    args = get_args()

    print(f"Reading agrs: {args.infile}")
    audio_file = args.infile

    from pathlib import Path
    if args.infile == "":
        out_dir = get_app_whisper_dir()
    else:
        out_dir = Path(args.lrtxt_outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_dir_wav = get_app_wav_dir()
    out_dir_wav.mkdir(parents=True, exist_ok=True)

    output_file = to_txt_file(out_dir, audio_file)

    step_2_copy = True
    step_3_vad_silero = True
    step_4_whisper = True
    step_5_json_whisper_srt_compiler = True
    step_6_lr_srt_compiler = True # translation
    step_7_run_langrepeater = True


    import os
    import shutil

    # Get filename from source path
    file_name = os.path.basename(audio_file)

    # Full destination file path
    destination_file = str(out_dir_wav / file_name)

    if step_2_copy:
        shutil.copy2(audio_file, destination_file)
        print(f"Copied: {audio_file} to {destination_file}")



    if step_3_vad_silero:
        speech_timestamps = do_whiper_vad_silero(audio_file)
        output_string = "".join(f"{item['start']},{item['end']}," for item in speech_timestamps)
        data = {
            "audio_filename": audio_file,
            "output_speech_timestamps": output_string,
            "output_speech_timestamps_enabled": output_speech_timestamps_enabled,
            "model": "large",
            "word_timestamps": True,
        }

    # call whisper
    if step_4_whisper:
        # fast whisper
        if data is None:
            raise ValueError("no data!")
        run_faster_whisper(data)

    if step_5_json_whisper_srt_compiler:
        generated_srt_file_from_whisper_json = do_lr_compiler_whisper_json(data, str(out_dir))

    if generated_srt_file_from_whisper_json is None:
        raise ValueError("No generated_srt_file_from_whisper_json!")

    if step_6_lr_srt_compiler:
        print(generated_srt_file_from_whisper_json)
        lr_compiler_srt.do_lr_compiler_srt_to_lr_txt_format_and_translate(generated_srt_file_from_whisper_json, output_file)

    if step_7_run_langrepeater:
        print("create_audio: " + str(args.create_audio))
        langrepeater_main(output_file, args.create_audio)

    my_app_end_time = time.time()
    print(f" app time end: {__name__} {my_app_end_time}")
    print(f" app runtime: {__name__} {my_app_end_time - my_app_start_time} {(my_app_end_time - my_app_start_time)/60}")

if __name__ == "__main__":
    main()